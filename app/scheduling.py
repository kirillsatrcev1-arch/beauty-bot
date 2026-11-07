"""Расписание: рабочие окна мастеров, свободные слоты и атомарная запись без двойных бронирований.

Мастер работает по своему графику (дни, часы, перерыв). Если у мастера часы не заданы,
берутся общие настройки студии. Дополнительно учитываются:
  * day_overrides      — студия закрыта / особые часы на дату (для всех мастеров);
  * master_overrides   — выходной / особые часы конкретного мастера на дату;
  * vacations          — отпуск мастера (диапазон дат);
  * extra_windows      — дополнительные окна (для всех или для мастера);
  * time_blocks        — заблокированные интервалы (для всех или для мастера).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .db import DB, now_str

FMT = "%Y-%m-%d %H:%M"


class SlotTaken(Exception):
    """Время уже занято (или перестало быть доступным)."""


def local_now(tz: ZoneInfo) -> datetime:
    return datetime.now(tz).replace(tzinfo=None, second=0, microsecond=0)


def hm(s: str) -> int:
    h, m = s.strip().split(":")
    return int(h) * 60 + int(m)


def fmt_hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_range(text: str) -> tuple[str, str] | None:
    """'10:00-18:30' -> ('10:00', '18:30')."""
    t = text.replace("—", "-").replace("–", "-").replace(" ", "").replace(".", ":")
    if "-" not in t:
        return None
    a, b = t.split("-", 1)
    try:
        if len(a) <= 2:
            a += ":00"
        if len(b) <= 2:
            b += ":00"
        sa, sb = hm(a), hm(b)
    except ValueError:
        return None
    if not (0 <= sa < sb <= 24 * 60):
        return None
    return fmt_hm(sa), fmt_hm(sb)


def _merge(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    windows = sorted(w for w in windows if w[1] > w[0])
    out: list[tuple[int, int]] = []
    for s, e in windows:
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _subtract(windows: list[tuple[int, int]], cut: tuple[int, int]) -> list[tuple[int, int]]:
    cs, ce = cut
    out = []
    for s, e in windows:
        if ce <= s or cs >= e:
            out.append((s, e))
            continue
        if s < cs:
            out.append((s, cs))
        if ce < e:
            out.append((ce, e))
    return out


# ---------- мастера ----------
async def active_masters(db: DB) -> list[dict]:
    return await db.fetchall("SELECT * FROM masters WHERE active=1 ORDER BY sort, id")


async def masters_for_service(db: DB, service_id: int | None) -> list[int]:
    """Активные мастера, которые делают услугу. Мастер без списка услуг делает все."""
    masters = await active_masters(db)
    if not service_id:
        return [m["id"] for m in masters]
    out = []
    for m in masters:
        rows = await db.fetchall("SELECT service_id FROM master_services WHERE master_id=?", (m["id"],))
        if not rows or any(r["service_id"] == service_id for r in rows):
            out.append(m["id"])
    return out


async def day_windows(db: DB, d: date, master_id: int | None = None) -> list[tuple[int, int]]:
    """Рабочие интервалы дня в минутах. master_id=None — объединение по всем активным мастерам."""
    if master_id is None:
        res: list[tuple[int, int]] = []
        for m in await active_masters(db):
            res += await day_windows(db, d, m["id"])
        return _merge(res)
    ds = d.isoformat()
    m = await db.fetchone("SELECT * FROM masters WHERE id=?", (master_id,))
    if not m:
        return []
    windows: list[tuple[int, int]] = []
    studio = await db.fetchone("SELECT * FROM day_overrides WHERE date=?", (ds,))
    personal = await db.fetchone("SELECT * FROM master_overrides WHERE master_id=? AND date=?", (master_id, ds))
    vacation = await db.fetchone(
        "SELECT 1 AS x FROM vacations WHERE master_id=? AND date_from<=? AND date_to>=?", (master_id, ds, ds))
    closed = vacation or (studio and studio["closed"]) or (personal and personal["closed"])
    if not closed:
        if personal and personal["start"] and personal["end"]:
            windows.append((hm(personal["start"]), hm(personal["end"])))
        elif studio and studio["start"] and studio["end"]:
            windows.append((hm(studio["start"]), hm(studio["end"])))
        else:
            days = m["work_days"] if m["work_days"] is not None else db.get("work_days")
            if d.weekday() in {int(x) for x in str(days).split(",") if x.strip().isdigit()}:
                windows.append((hm(m["work_start"] or db.get("work_start")), hm(m["work_end"] or db.get("work_end"))))
        if windows and m["break_start"] and m["break_end"]:
            windows = _subtract(windows, (hm(m["break_start"]), hm(m["break_end"])))
    if not vacation:
        for w in await db.fetchall(
                "SELECT start, end FROM extra_windows WHERE date=? AND (master_id IS NULL OR master_id=?)", (ds, master_id)):
            windows.append((hm(w["start"]), hm(w["end"])))
    windows = _merge(windows)
    for blk in await db.fetchall(
            "SELECT start, end FROM time_blocks WHERE date=? AND (master_id IS NULL OR master_id=?)", (ds, master_id)):
        windows = _subtract(windows, (hm(blk["start"]), hm(blk["end"])))
    return windows


async def busy_intervals(db: DB, d: date, master_id: int, exclude_id: int | None = None) -> list[tuple[int, int]]:
    rows = await db.fetchall(
        "SELECT id, start, end FROM bookings WHERE date=? AND master_id=? AND status IN ('pending','confirmed')",
        (d.isoformat(), master_id))
    out = []
    base = datetime.combine(d, datetime.min.time())
    for r in rows:
        if exclude_id and r["id"] == exclude_id:
            continue
        s = datetime.strptime(r["start"], FMT)
        e = datetime.strptime(r["end"], FMT)
        out.append((int((s - base).total_seconds() // 60), int((e - base).total_seconds() // 60)))
    return out


def in_horizon(db: DB, d: date, now: datetime) -> bool:
    return now.date() <= d <= now.date() + timedelta(days=db.get_int("horizon_days", 45))


async def master_free_slots(db: DB, d: date, duration: int, now: datetime, master_id: int,
                            exclude_id: int | None = None, ignore_lead: bool = False) -> list[int]:
    if not ignore_lead and not in_horizon(db, d, now):
        return []
    step = max(5, db.get_int("slot_step", 30))
    lead = 0 if ignore_lead else db.get_int("min_lead_min", 120)
    earliest = now + timedelta(minutes=lead)
    busy = await busy_intervals(db, d, master_id, exclude_id)
    base = datetime.combine(d, datetime.min.time())
    result: list[int] = []
    for ws, we in await day_windows(db, d, master_id):
        t = ws
        while t + duration <= we:
            if base + timedelta(minutes=t) >= earliest and all(t + duration <= bs or t >= be for bs, be in busy):
                result.append(t)
            t += step
    return result


async def free_slots_by_master(db: DB, d: date, duration: int, now: datetime, masters: list[int] | None = None,
                               exclude_id: int | None = None, ignore_lead: bool = False) -> dict[int, list[int]]:
    """{минуты: [id мастеров, свободных в это время]}"""
    if masters is None:
        masters = [m["id"] for m in await active_masters(db)]
    out: dict[int, list[int]] = {}
    for mid in masters:
        for t in await master_free_slots(db, d, duration, now, mid, exclude_id, ignore_lead):
            out.setdefault(t, []).append(mid)
    return dict(sorted(out.items()))


async def free_slots(db: DB, d: date, duration: int, now: datetime, exclude_id: int | None = None,
                     ignore_lead: bool = False, masters: list[int] | None = None) -> list[int]:
    """Время начала (в минутах), когда хотя бы один из мастеров свободен на всю длительность услуги."""
    return list((await free_slots_by_master(db, d, duration, now, masters, exclude_id, ignore_lead)).keys())


async def month_map(db: DB, year: int, month: int, duration: int, now: datetime, exclude_id: int | None = None,
                    ignore_lead: bool = False, masters: list[int] | None = None) -> dict[int, str]:
    """day -> 'free' | 'busy' (рабочий, но всё занято) | 'off' (выходной) | 'past'."""
    if masters is None:
        masters = [m["id"] for m in await active_masters(db)]
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    out: dict[int, str] = {}
    d = first
    while d < nxt:
        if d < now.date() or (not ignore_lead and not in_horizon(db, d, now)):
            out[d.day] = "past"
        else:
            working = False
            for mid in masters:
                if await day_windows(db, d, mid):
                    working = True
                    break
            if not working:
                out[d.day] = "off"
            elif await free_slots(db, d, duration, now, exclude_id, ignore_lead, masters):
                out[d.day] = "free"
            else:
                out[d.day] = "busy"
        d += timedelta(days=1)
    return out


async def nearest_free(db: DB, duration: int, now: datetime, limit: int = 3,
                       masters: list[int] | None = None) -> list[tuple[date, int]]:
    out = []
    d = now.date()
    for _ in range(db.get_int("horizon_days", 45) + 1):
        for t in await free_slots(db, d, duration, now, masters=masters):
            out.append((d, t))
            if len(out) >= limit:
                return out
        d += timedelta(days=1)
    return out


def _flags(start: datetime, now: datetime) -> tuple[int, int]:
    """Если до визита уже меньше 24 ч / 2 ч, соответствующее напоминание не нужно."""
    left = start - now
    return int(left <= timedelta(hours=24)), int(left <= timedelta(hours=2))


async def _master_name(db: DB, mid: int) -> str:
    return (await db.scalar("SELECT name FROM masters WHERE id=?", (mid,))) or ""


async def create_booking(
    db: DB,
    *,
    user_id: int,
    service: dict,
    start: datetime,
    name: str,
    phone: str,
    comment: str | None,
    now: datetime,
    source: str = "chat",
    status: str = "pending",
    ignore_lead: bool = False,
    master_id: int | None = None,
    force: bool = False,
) -> dict:
    """Атомарно создаёт запись. master_id=None — любой свободный мастер. Если слот занят — SlotTaken.
    force=True (ручная запись администратором) разрешает время вне графика, но не поверх других записей."""
    d, t = start.date(), start.hour * 60 + start.minute
    end = start + timedelta(minutes=service["duration"])
    r24, r2 = _flags(start, now)
    candidates = [master_id] if master_id else await masters_for_service(db, service.get("id"))
    if not candidates:
        raise SlotTaken
    try:
        async with db.tx():
            chosen = None
            for mid in candidates:
                if force:
                    busy = await busy_intervals(db, d, mid)
                    ok = all(t + service["duration"] <= bs or t >= be for bs, be in busy)
                else:
                    ok = t in await master_free_slots(db, d, service["duration"], now, mid, ignore_lead=ignore_lead)
                if ok:
                    chosen = mid
                    break
            if chosen is None:
                raise SlotTaken
            ts = now_str()
            bid = await db.execute(
                "INSERT INTO bookings(user_id, service_id, service_title, price, price_from, duration, date, start, end, status,"
                " name, phone, comment, source, remind24, remind2, master_id, master_name, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    user_id, service.get("id"), service["title"], service["price"], service.get("price_from", 0),
                    service["duration"], d.isoformat(), start.strftime(FMT), end.strftime(FMT), status,
                    name, phone, comment, source, r24, r2, chosen, await _master_name(db, chosen), ts, ts,
                ),
            )
    except SlotTaken:
        raise
    except Exception as e:  # уникальный индекс сработал в другом процессе
        if "UNIQUE" in str(e).upper():
            raise SlotTaken from e
        raise
    return await db.booking(bid)


async def move_booking(
    db: DB, bid: int, start: datetime, now: datetime, status: str | None = None, ignore_lead: bool = False,
    master_id: int | None = None,
) -> dict:
    """Атомарный перенос записи. Сначала пробуем того же мастера, затем других (если мастер не указан явно)."""
    try:
        async with db.tx():
            b = await db.booking(bid)
            if not b or b["status"] not in ("pending", "confirmed"):
                raise SlotTaken
            d, t = start.date(), start.hour * 60 + start.minute
            if master_id:
                candidates = [master_id]
            else:
                others = [m for m in await masters_for_service(db, b["service_id"]) if m != b["master_id"]]
                candidates = [b["master_id"], *others]
            chosen = None
            for mid in candidates:
                if t in await master_free_slots(db, d, b["duration"], now, mid, exclude_id=bid, ignore_lead=ignore_lead):
                    chosen = mid
                    break
            if chosen is None:
                raise SlotTaken
            end = start + timedelta(minutes=b["duration"])
            r24, r2 = _flags(start, now)
            await db.execute(
                "UPDATE bookings SET date=?, start=?, end=?, status=?, remind24=?, remind2=?, client_confirmed=0,"
                " master_id=?, master_name=?, updated_at=? WHERE id=?",
                (d.isoformat(), start.strftime(FMT), end.strftime(FMT), status or b["status"], r24, r2,
                 chosen, await _master_name(db, chosen), now_str(), bid),
            )
    except SlotTaken:
        raise
    except Exception as e:
        if "UNIQUE" in str(e).upper():
            raise SlotTaken from e
        raise
    return await db.booking(bid)
