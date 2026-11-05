"""Расписание: рабочие окна, свободные слоты и атомарная запись без двойных бронирований."""
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


async def day_windows(db: DB, d: date) -> list[tuple[int, int]]:
    """Рабочие интервалы дня в минутах от полуночи (с учётом выходных, особых часов и доп. окошек)."""
    ds = d.isoformat()
    windows: list[tuple[int, int]] = []
    ov = await db.fetchone("SELECT * FROM day_overrides WHERE date=?", (ds,))
    if ov and ov["closed"]:
        pass
    elif ov and ov["start"] and ov["end"]:
        windows.append((hm(ov["start"]), hm(ov["end"])))
    else:
        days = {int(x) for x in db.get("work_days").split(",") if x.strip().isdigit()}
        if d.weekday() in days:
            windows.append((hm(db.get("work_start")), hm(db.get("work_end"))))
    for w in await db.fetchall("SELECT start, end FROM extra_windows WHERE date=? ORDER BY start", (ds,)):
        windows.append((hm(w["start"]), hm(w["end"])))
    # склеиваем пересекающиеся окна
    windows.sort()
    merged: list[tuple[int, int]] = []
    for s, e in windows:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


async def busy_intervals(db: DB, d: date, exclude_id: int | None = None) -> list[tuple[int, int]]:
    rows = await db.fetchall(
        "SELECT id, start, end FROM bookings WHERE date=? AND status IN ('pending','confirmed')", (d.isoformat(),)
    )
    out = []
    for r in rows:
        if exclude_id and r["id"] == exclude_id:
            continue
        s = datetime.strptime(r["start"], FMT)
        e = datetime.strptime(r["end"], FMT)
        end_min = (e - datetime.combine(d, datetime.min.time())).total_seconds() // 60
        out.append((s.hour * 60 + s.minute, int(end_min)))
    return out


def in_horizon(db: DB, d: date, now: datetime) -> bool:
    return now.date() <= d <= now.date() + timedelta(days=db.get_int("horizon_days", 45))


async def free_slots(
    db: DB, d: date, duration: int, now: datetime, exclude_id: int | None = None, ignore_lead: bool = False
) -> list[int]:
    """Время начала (в минутах), когда услуга длительностью duration целиком помещается в окно
    и не пересекается ни с одной активной записью."""
    if not ignore_lead and not in_horizon(db, d, now):
        return []
    step = max(5, db.get_int("slot_step", 30))
    lead = 0 if ignore_lead else db.get_int("min_lead_min", 120)
    earliest = now + timedelta(minutes=lead)
    busy = await busy_intervals(db, d, exclude_id)
    result: list[int] = []
    for ws, we in await day_windows(db, d):
        t = ws
        while t + duration <= we:
            start_dt = datetime.combine(d, datetime.min.time()) + timedelta(minutes=t)
            if start_dt >= earliest and all(t + duration <= bs or t >= be for bs, be in busy):
                result.append(t)
            t += step
    return result


async def month_map(
    db: DB, year: int, month: int, duration: int, now: datetime, exclude_id: int | None = None, ignore_lead: bool = False
) -> dict[int, str]:
    """day -> 'free' | 'busy' (рабочий, но всё занято) | 'off' (выходной) | 'past' (прошло/вне горизонта)."""
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    out: dict[int, str] = {}
    d = first
    while d < nxt:
        if d < now.date() or (not ignore_lead and not in_horizon(db, d, now)):
            out[d.day] = "past"
        elif not await day_windows(db, d):
            out[d.day] = "off"
        elif await free_slots(db, d, duration, now, exclude_id, ignore_lead):
            out[d.day] = "free"
        else:
            out[d.day] = "busy"
        d += timedelta(days=1)
    return out


async def nearest_free(db: DB, duration: int, now: datetime, limit: int = 3) -> list[tuple[date, int]]:
    out = []
    d = now.date()
    for _ in range(db.get_int("horizon_days", 45) + 1):
        for t in await free_slots(db, d, duration, now):
            out.append((d, t))
            if len(out) >= limit:
                return out
        d += timedelta(days=1)
    return out


def _flags(start: datetime, now: datetime) -> tuple[int, int]:
    """Если до визита уже меньше 24 ч / 2 ч, соответствующее напоминание не нужно."""
    left = start - now
    return int(left <= timedelta(hours=24)), int(left <= timedelta(hours=2))


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
) -> dict:
    """Атомарно создаёт запись. Если слот уже занят — SlotTaken."""
    d, t = start.date(), start.hour * 60 + start.minute
    end = start + timedelta(minutes=service["duration"])
    r24, r2 = _flags(start, now)
    try:
        async with db.tx():
            if t not in await free_slots(db, d, service["duration"], now, ignore_lead=ignore_lead):
                raise SlotTaken
            ts = now_str()
            bid = await db.execute(
                "INSERT INTO bookings(user_id, service_id, service_title, price, price_from, duration, date, start, end, status,"
                " name, phone, comment, source, remind24, remind2, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    user_id, service["id"], service["title"], service["price"], service.get("price_from", 0),
                    service["duration"], d.isoformat(), start.strftime(FMT), end.strftime(FMT), status,
                    name, phone, comment, source, r24, r2, ts, ts,
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
    db: DB, bid: int, start: datetime, now: datetime, status: str | None = None, ignore_lead: bool = False
) -> dict:
    """Атомарный перенос существующей записи на новое время."""
    try:
        async with db.tx():
            b = await db.booking(bid)
            if not b or b["status"] not in ("pending", "confirmed"):
                raise SlotTaken
            d, t = start.date(), start.hour * 60 + start.minute
            if t not in await free_slots(db, d, b["duration"], now, exclude_id=bid, ignore_lead=ignore_lead):
                raise SlotTaken
            end = start + timedelta(minutes=b["duration"])
            r24, r2 = _flags(start, now)
            await db.execute(
                "UPDATE bookings SET date=?, start=?, end=?, status=?, remind24=?, remind2=?, client_confirmed=0, updated_at=?"
                " WHERE id=?",
                (d.isoformat(), start.strftime(FMT), end.strftime(FMT), status or b["status"], r24, r2, now_str(), bid),
            )
    except SlotTaken:
        raise
    except Exception as e:
        if "UNIQUE" in str(e).upper():
            raise SlotTaken from e
        raise
    return await db.booking(bid)
