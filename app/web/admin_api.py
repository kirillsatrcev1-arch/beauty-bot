"""API админ-панели. Каждый обработчик проверяет права на сервере (ADMIN_IDS), а не только во фронтенде.

Вход:
  * внутри Telegram — по подписанному initData администратора;
  * в обычном браузере — по одноразовой ссылке из бота (/panel), которая меняется на сессию на 7 дней.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from aiohttp import web

from .. import logic
from ..db import DB, PORTFOLIO_SECTIONS, now_str
from ..media import save_image, url_of
from ..scheduling import (
    SlotTaken, day_windows, fmt_hm, free_slots_by_master, hm, local_now, masters_for_service, parse_range,
)
from .auth import sign_admin_token, verify_admin_token
from .server import (
    K_ADMIN, K_BOT, K_CFG, K_DB, K_USER, booking_json, err, master_json, master_services_map, ok, parse_start,
    portfolio_item, svc_json,
)

SETTINGS_KEYS = {
    "studio_name", "master_name", "about_text", "address_text", "address_hint", "map_url", "contact_text",
    "contact_username", "contact_phone", "channel_id", "channel_url", "sub_required", "instagram_url", "vk_url",
    "cancel_rules", "cancel_min_hours", "auto_confirm", "remind_24", "remind_2", "notify_new_clients", "why_us",
    "work_start", "work_end", "work_days", "slot_step", "horizon_days", "min_lead_min", "logo", "photo_about", "photo_welcome",
}
STATUSES = {"pending", "confirmed", "done", "cancelled"}


def admin_only(handler):
    async def wrapped(request: web.Request):
        if not request.get(K_ADMIN):
            return err(403, "forbidden")
        return await handler(request)
    return wrapped


def _ctx(request: web.Request):
    return request.app[K_DB], request.app[K_CFG], request.app[K_BOT], request[K_USER]["id"]


async def _json(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='{"ok":false,"error":"bad_json"}', content_type="application/json")


# ---------- вход в браузере ----------
async def login(request: web.Request) -> web.Response:
    cfg = request.app[K_CFG]
    body = await _json(request)
    uid = verify_admin_token(str(body.get("token", "")), cfg.bot_token, kind="l")
    if not uid or not cfg.is_admin(uid):
        return err(401, "bad_token")
    return ok(session=sign_admin_token(uid, cfg.bot_token, ttl=7 * 86400))


@admin_only
async def me(request: web.Request) -> web.Response:
    db, cfg, _, uid = _ctx(request)
    u = await db.user(uid) or {}
    return ok(id=uid, name=u.get("name") or u.get("first_name") or "Администратор", studio=db.get("studio_name"))


# ---------- дашборд ----------
@admin_only
async def dashboard(request: web.Request) -> web.Response:
    db, cfg, _, _ = _ctx(request)
    now = local_now(cfg.tz)
    t = now.date()
    week_start = t - timedelta(days=t.weekday())
    month_start = t.replace(day=1)
    active = "status IN ('pending','confirmed','done')"
    today = await db.scalar(f"SELECT COUNT(*) FROM bookings WHERE date=? AND {active}", (t.isoformat(),))
    week = await db.scalar(f"SELECT COUNT(*) FROM bookings WHERE date BETWEEN ? AND ? AND {active}",
                           (week_start.isoformat(), (week_start + timedelta(days=6)).isoformat()))
    new_clients = await db.scalar("SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)>=?", ((t - timedelta(days=30)).isoformat(),))
    revenue_month = await db.scalar("SELECT COALESCE(SUM(price),0) FROM bookings WHERE status='done' AND date>=?", (month_start.isoformat(),))
    revenue_total = await db.scalar("SELECT COALESCE(SUM(price),0) FROM bookings WHERE status='done'")
    expected = await db.scalar("SELECT COALESCE(SUM(price),0) FROM bookings WHERE status IN ('pending','confirmed') AND date>=?", (t.isoformat(),))
    pending = await db.scalar("SELECT COUNT(*) FROM bookings WHERE status='pending'")
    upcoming = await db.fetchall("SELECT * FROM bookings WHERE status IN ('pending','confirmed') AND start>=? ORDER BY start LIMIT 8",
                                 (now.strftime("%Y-%m-%d %H:%M"),))
    months = []
    y, m = t.year, t.month
    for _ in range(6):
        ym = f"{y}-{m:02d}"
        r = await db.fetchone(
            "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN status='done' THEN price END),0) AS rev "
            f"FROM bookings WHERE substr(date,1,7)=? AND {active}", (ym,))
        months.append({"month": ym, "bookings": r["n"], "revenue": r["rev"]})
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    days = []
    for i in range(14):
        d = t - timedelta(days=13 - i)
        days.append({"date": d.isoformat(), "bookings": await db.scalar(f"SELECT COUNT(*) FROM bookings WHERE date=? AND {active}", (d.isoformat(),))})
    top = await db.fetchall(f"SELECT service_title AS title, COUNT(*) AS n FROM bookings WHERE {active} GROUP BY service_title ORDER BY n DESC LIMIT 5")
    return ok(today=today, week=week, new_clients=new_clients, revenue_month=revenue_month, revenue_total=revenue_total,
              expected=expected, pending=pending, upcoming=[booking_json(b) for b in upcoming],
              months=list(reversed(months)), days=days, top=top)


# ---------- записи ----------
@admin_only
async def bookings_list(request: web.Request) -> web.Response:
    db, cfg, _, _ = _ctx(request)
    q = request.query
    sql, params = "SELECT * FROM bookings WHERE 1=1", []
    if q.get("q"):
        like = f"%{q['q'].strip()}%"
        digits = "".join(ch for ch in q["q"] if ch.isdigit())
        sql += " AND (name LIKE ? OR service_title LIKE ?" + (" OR REPLACE(REPLACE(REPLACE(phone,' ',''),'-',''),'+','') LIKE ?" if digits else "") + ")"
        params += [like, like] + ([f"%{digits}%"] if digits else [])
    if q.get("from"):
        sql += " AND date>=?"
        params.append(q["from"])
    if q.get("to"):
        sql += " AND date<=?"
        params.append(q["to"])
    if q.get("master"):
        sql += " AND master_id=?"
        params.append(int(q["master"]))
    if q.get("status") in STATUSES:
        sql += " AND status=?"
        params.append(q["status"])
    sql += " ORDER BY start " + ("DESC" if q.get("order") == "desc" else "ASC") + " LIMIT 300"
    return ok(items=[booking_json(b) for b in await db.fetchall(sql, params)])


@admin_only
async def booking_create(request: web.Request) -> web.Response:
    """Ручная запись мастером (например, клиентка позвонила)."""
    db, cfg, bot, uid = _ctx(request)
    body = await _json(request)
    s = await db.service(int(body.get("service", 0)))
    if not s:
        return err(404, "service")
    name = " ".join(str(body.get("name", "")).split())[:40]
    if len(name) < 2:
        return err(400, "name")
    master = body.get("master")
    try:
        b = await logic.book(bot, db, cfg, user_id=int(body.get("user_id") or 0), service=s, start=parse_start(body),
                             name=name, phone=str(body.get("phone") or "")[:30], comment=(body.get("comment") or None),
                             source="admin", master_id=int(master) if master else None, status="confirmed", force=True)
    except SlotTaken:
        return err(409, "slot_taken")
    except (KeyError, ValueError):
        return err(400, "bad_request")
    await db.log(uid, "admin_booking_create", id=b["id"])
    return ok(booking=booking_json(b))


@admin_only
async def booking_update(request: web.Request) -> web.Response:
    db, cfg, bot, uid = _ctx(request)
    bid = int(request.match_info["id"])
    b = await db.booking(bid)
    if not b:
        return err(404, "not_found")
    body = await _json(request)
    action = body.get("action")
    if action == "confirm":
        await logic.confirm(bot, db, cfg, bid, uid)
    elif action == "cancel":
        await logic.cancel(bot, db, cfg, bid, by="admin", actor_id=uid, reason=(body.get("reason") or None))
    elif action == "done":
        await logic.mark_done(db, bid, uid)
    elif action == "status" and body.get("status") in STATUSES:
        st = body["status"]
        if st == "confirmed" and b["status"] == "pending":
            await logic.confirm(bot, db, cfg, bid, uid)
        elif st == "cancelled":
            await logic.cancel(bot, db, cfg, bid, by="admin", actor_id=uid, reason=(body.get("reason") or None))
        else:
            await db.set_status(bid, st)
            await db.log(uid, "admin_status", id=bid, status=st)
    elif action == "move":
        try:
            await logic.reschedule(bot, db, cfg, bid, parse_start(body), by="admin", actor_id=uid,
                                   master_id=int(body["master"]) if body.get("master") else None)
        except SlotTaken:
            return err(409, "slot_taken")
    elif action == "comment":
        await db.execute("UPDATE bookings SET comment=?, updated_at=? WHERE id=?", ((body.get("comment") or "")[:500], now_str(), bid))
    else:
        return err(400, "action")
    return ok(booking=booking_json(await db.booking(bid)))


@admin_only
async def admin_slots(request: web.Request) -> web.Response:
    """Свободное время для переноса / ручной записи (без ограничения «минимум до записи»)."""
    db, cfg, _, _ = _ctx(request)
    q = request.query
    d = date.fromisoformat(q["date"])
    exclude = int(q["exclude"]) if q.get("exclude") else None
    if exclude:
        b = await db.booking(exclude)
        duration, sid = b["duration"], b["service_id"]
    else:
        s = await db.service(int(q["service"]))
        duration, sid = s["duration"], s["id"]
    masters = [int(q["master"])] if q.get("master") else await masters_for_service(db, sid)
    res = await free_slots_by_master(db, d, duration, local_now(cfg.tz), masters, exclude, ignore_lead=True)
    return ok(slots=[{"time": fmt_hm(t), "masters": ms} for t, ms in res.items()])


# ---------- календарь ----------
@admin_only
async def calendar(request: web.Request) -> web.Response:
    db, cfg, _, _ = _ctx(request)
    q = request.query
    start = date.fromisoformat(q["from"])
    end = date.fromisoformat(q["to"])
    if (end - start).days > 45:
        return err(400, "range")
    masters = await db.fetchall("SELECT * FROM masters WHERE active=1 ORDER BY sort, id")
    if q.get("master"):
        masters = [m for m in masters if m["id"] == int(q["master"])]
    days = []
    d = start
    while d <= end:
        ds = d.isoformat()
        windows = {m["id"]: [[s, e] for s, e in await day_windows(db, d, m["id"])] for m in masters}
        bks = await db.fetchall("SELECT * FROM bookings WHERE date=? AND status!='cancelled' ORDER BY start", (ds,))
        if q.get("master"):
            bks = [b for b in bks if b["master_id"] == int(q["master"])]
        blocks = await db.fetchall("SELECT * FROM time_blocks WHERE date=?", (ds,))
        days.append({"date": ds, "windows": windows, "bookings": [booking_json(b) for b in bks], "blocks": blocks})
        d += timedelta(days=1)
    return ok(days=days, masters=[{"id": m["id"], "name": m["name"]} for m in masters])


# ---------- услуги ----------
@admin_only
async def services_list(request: web.Request) -> web.Response:
    db, _, _, _ = _ctx(request)
    masters = await db.fetchall("SELECT * FROM masters ORDER BY sort, id")
    ms = await master_services_map(db)
    cats = await db.categories()
    return ok(services=[svc_json(s, masters, ms) for s in await db.services(include_hidden=True)],
              categories=[{"id": c["id"], "title": c["title"], "emoji": c["emoji"]} for c in cats])


@admin_only
async def service_save(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    body = await _json(request)
    title = str(body.get("title", "")).strip()[:80]
    if len(title) < 2:
        return err(400, "title")
    try:
        price, duration = int(body.get("price", 0)), int(body.get("duration", 0))
    except (TypeError, ValueError):
        return err(400, "number")
    if price < 0 or not 5 <= duration <= 600:
        return err(400, "number")
    if not await db.category(str(body.get("category", ""))):
        return err(400, "category")
    fields = (str(body["category"]), title, str(body.get("description", ""))[:600], price, int(bool(body.get("price_from"))),
              duration, int(body.get("active", True)))
    sid = body.get("id")
    if sid:
        await db.execute("UPDATE services SET category=?, title=?, description=?, price=?, price_from=?, duration=?, active=? WHERE id=?",
                         (*fields, int(sid)))
    else:
        sort = (await db.scalar("SELECT COALESCE(MAX(sort),0)+1 FROM services")) or 1
        sid = await db.execute("INSERT INTO services(category, title, description, price, price_from, duration, active, sort, created_at)"
                               " VALUES(?,?,?,?,?,?,?,?,?)", (*fields, sort, now_str()))
    if "photo" in body:
        await db.execute("UPDATE services SET photo=? WHERE id=?", (body["photo"] or None, int(sid)))
    await db.log(uid, "admin_service_save", id=sid)
    return ok(id=int(sid))


@admin_only
async def service_delete(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    sid = int(request.match_info["id"])
    await db.execute("DELETE FROM favorites WHERE service_id=?", (sid,))
    await db.execute("DELETE FROM master_services WHERE service_id=?", (sid,))
    await db.execute("DELETE FROM services WHERE id=?", (sid,))
    await db.log(uid, "admin_service_delete", id=sid)
    return ok()


# ---------- мастера ----------
@admin_only
async def masters_list(request: web.Request) -> web.Response:
    db, _, _, _ = _ctx(request)
    ms = await master_services_map(db)
    return ok(masters=[master_json(m, ms) for m in await db.fetchall("SELECT * FROM masters ORDER BY sort, id")])


def _time_or_none(v) -> str | None:
    if not v:
        return None
    r = parse_range(f"{v}-23:59")
    return r[0] if r else None


@admin_only
async def master_save(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    body = await _json(request)
    name = str(body.get("name", "")).strip()[:60]
    if len(name) < 2:
        return err(400, "name")
    days = ",".join(str(int(x)) for x in body.get("work_days", []) if str(x).isdigit() and 0 <= int(x) <= 6) \
        if isinstance(body.get("work_days"), list) else None
    ws, we = _time_or_none(body.get("work_start")), _time_or_none(body.get("work_end"))
    bs, be = _time_or_none(body.get("break_start")), _time_or_none(body.get("break_end"))
    if ws and we and hm(ws) >= hm(we):
        return err(400, "hours")
    if (bs and not be) or (be and not bs) or (bs and be and hm(bs) >= hm(be)):
        return err(400, "break")
    fields = (name, str(body.get("role", ""))[:60], str(body.get("bio", ""))[:600], int(bool(body.get("active", True))),
              days, ws, we, bs, be)
    mid = body.get("id")
    if mid:
        await db.execute("UPDATE masters SET name=?, role=?, bio=?, active=?, work_days=?, work_start=?, work_end=?, break_start=?, break_end=?"
                         " WHERE id=?", (*fields, int(mid)))
    else:
        mid = await db.execute("INSERT INTO masters(name, role, bio, active, work_days, work_start, work_end, break_start, break_end, sort, created_at)"
                               " VALUES(?,?,?,?,?,?,?,?,?,?,?)", (*fields, 99, now_str()))
    if "photo" in body:
        await db.execute("UPDATE masters SET photo=? WHERE id=?", (body["photo"] or None, int(mid)))
    if isinstance(body.get("service_ids"), list):
        await db.execute("DELETE FROM master_services WHERE master_id=?", (int(mid),))
        for sid in body["service_ids"]:
            await db.execute("INSERT OR IGNORE INTO master_services(master_id, service_id) VALUES(?,?)", (int(mid), int(sid)))
    await db.log(uid, "admin_master_save", id=mid)
    return ok(id=int(mid))


@admin_only
async def master_delete(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    mid = int(request.match_info["id"])
    if await db.scalar("SELECT COUNT(*) FROM masters WHERE active=1 AND id!=?", (mid,)) == 0:
        return err(400, "last_master")
    future = await db.scalar("SELECT COUNT(*) FROM bookings WHERE master_id=? AND status IN ('pending','confirmed')", (mid,))
    if future:
        return err(400, "has_bookings", count=future)
    await db.execute("UPDATE masters SET active=0 WHERE id=?", (mid,))
    await db.log(uid, "admin_master_disable", id=mid)
    return ok()


# ---------- расписание ----------
@admin_only
async def schedule_get(request: web.Request) -> web.Response:
    db, cfg, _, _ = _ctx(request)
    t = local_now(cfg.tz).date().isoformat()
    return ok(
        defaults={k: db.get(k) for k in ("work_days", "work_start", "work_end", "slot_step", "horizon_days", "min_lead_min")},
        vacations=await db.fetchall("SELECT * FROM vacations WHERE date_to>=? ORDER BY date_from", (t,)),
        blocks=await db.fetchall("SELECT * FROM time_blocks WHERE date>=? ORDER BY date, start", (t,)),
        windows=await db.fetchall("SELECT * FROM extra_windows WHERE date>=? ORDER BY date, start", (t,)),
        studio_days=await db.fetchall("SELECT * FROM day_overrides WHERE date>=? ORDER BY date", (t,)),
        master_days=await db.fetchall("SELECT * FROM master_overrides WHERE date>=? ORDER BY date", (t,)),
    )


def _date(v) -> str:
    return date.fromisoformat(str(v)).isoformat()


@admin_only
async def schedule_add(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    kind = request.match_info["kind"]
    body = await _json(request)
    mid = int(body["master_id"]) if body.get("master_id") else None
    try:
        if kind == "vacation":
            a, b = _date(body["date_from"]), _date(body["date_to"])
            if b < a or not mid:
                return err(400, "range")
            new_id = await db.execute("INSERT INTO vacations(master_id, date_from, date_to, note) VALUES(?,?,?,?)", (mid, a, b, body.get("note")))
        elif kind in ("block", "window"):
            r = parse_range(f"{body['start']}-{body['end']}")
            if not r:
                return err(400, "time")
            table = "time_blocks" if kind == "block" else "extra_windows"
            if kind == "block":
                new_id = await db.execute("INSERT INTO time_blocks(master_id, date, start, end, reason) VALUES(?,?,?,?,?)",
                                          (mid, _date(body["date"]), r[0], r[1], body.get("reason")))
            else:
                new_id = await db.execute(f"INSERT INTO {table}(master_id, date, start, end) VALUES(?,?,?,?)", (mid, _date(body["date"]), r[0], r[1]))
        elif kind == "day":
            ds = _date(body["date"])
            closed = int(bool(body.get("closed")))
            r = None if closed else parse_range(f"{body.get('start')}-{body.get('end')}")
            if not closed and not r:
                return err(400, "time")
            vals = (closed, r[0] if r else None, r[1] if r else None)
            if mid:
                await db.execute("INSERT INTO master_overrides(master_id, date, closed, start, end) VALUES(?,?,?,?,?) "
                                 "ON CONFLICT(master_id, date) DO UPDATE SET closed=excluded.closed, start=excluded.start, end=excluded.end",
                                 (mid, ds, *vals))
            else:
                await db.execute("INSERT INTO day_overrides(date, closed, start, end) VALUES(?,?,?,?) "
                                 "ON CONFLICT(date) DO UPDATE SET closed=excluded.closed, start=excluded.start, end=excluded.end", (ds, *vals))
            new_id = 0
        else:
            return err(404, "kind")
    except (KeyError, ValueError):
        return err(400, "bad_request")
    await db.log(uid, "admin_schedule_add", kind=kind)
    return ok(id=new_id)


@admin_only
async def schedule_delete(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    kind, key = request.match_info["kind"], request.match_info["id"]
    if kind == "vacation":
        await db.execute("DELETE FROM vacations WHERE id=?", (int(key),))
    elif kind == "block":
        await db.execute("DELETE FROM time_blocks WHERE id=?", (int(key),))
    elif kind == "window":
        await db.execute("DELETE FROM extra_windows WHERE id=?", (int(key),))
    elif kind == "day":  # key = YYYY-MM-DD или <master>_<date>
        if "_" in key:
            m, d = key.split("_", 1)
            await db.execute("DELETE FROM master_overrides WHERE master_id=? AND date=?", (int(m), d))
        else:
            await db.execute("DELETE FROM day_overrides WHERE date=?", (key,))
    else:
        return err(404, "kind")
    await db.log(uid, "admin_schedule_delete", kind=kind, id=key)
    return ok()


# ---------- клиенты ----------
@admin_only
async def clients(request: web.Request) -> web.Response:
    db, _, _, _ = _ctx(request)
    q = request.query.get("q", "").strip()
    sql = ("SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.user_id=u.id AND b.status='done') AS visits, "
           "(SELECT COALESCE(SUM(price),0) FROM bookings b WHERE b.user_id=u.id AND b.status='done') AS spent, "
           "(SELECT MAX(date) FROM bookings b WHERE b.user_id=u.id AND b.status='done') AS last_visit FROM users u")
    params: list = []
    if q:
        like = f"%{q.lstrip('@')}%"
        sql += " WHERE u.name LIKE ? OR u.first_name LIKE ? OR u.username LIKE ? OR u.phone LIKE ? OR CAST(u.id AS TEXT) LIKE ?"
        params = [like] * 5
    sql += " ORDER BY u.last_seen DESC LIMIT 300"
    return ok(items=await db.fetchall(sql, params))


@admin_only
async def client_detail(request: web.Request) -> web.Response:
    db, _, _, _ = _ctx(request)
    uid = int(request.match_info["id"])
    u = await db.user(uid)
    if not u:
        return err(404, "not_found")
    bks = await db.fetchall("SELECT * FROM bookings WHERE user_id=? ORDER BY start DESC", (uid,))
    return ok(user=u, bookings=[booking_json(b) for b in bks],
              favorites=[s["title"] for s in await db.favorites(uid)])


# ---------- галерея ----------
@admin_only
async def gallery_list(request: web.Request) -> web.Response:
    db, _, _, _ = _ctx(request)
    rows = await db.fetchall("SELECT * FROM portfolio ORDER BY id DESC LIMIT 500")
    return ok(items=[portfolio_item(i) for i in rows], sections=[{"id": k, "title": t} for k, t, _ in PORTFOLIO_SECTIONS])


@admin_only
async def gallery_add(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    body = await _json(request)
    sec = body.get("section")
    if sec not in {k for k, _, _ in PORTFOLIO_SECTIONS} or not str(body.get("photo", "")).startswith("upload:"):
        return err(400, "bad_request")
    pid = await db.execute("INSERT INTO portfolio(section, file_id, kind, caption, created_at) VALUES(?,?, 'upload', ?, ?)",
                           (sec, body["photo"], (body.get("caption") or "")[:300] or None, now_str()))
    await db.log(uid, "admin_portfolio_add", id=pid)
    return ok(id=pid)


@admin_only
async def gallery_update(request: web.Request) -> web.Response:
    db, _, _, _ = _ctx(request)
    body = await _json(request)
    pid = int(request.match_info["id"])
    if body.get("section") in {k for k, _, _ in PORTFOLIO_SECTIONS}:
        await db.execute("UPDATE portfolio SET section=? WHERE id=?", (body["section"], pid))
    if "caption" in body:
        await db.execute("UPDATE portfolio SET caption=? WHERE id=?", ((body["caption"] or "")[:300] or None, pid))
    return ok()


@admin_only
async def gallery_delete(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    await db.execute("DELETE FROM portfolio WHERE id=?", (int(request.match_info["id"]),))
    await db.log(uid, "admin_portfolio_delete", id=request.match_info["id"])
    return ok()


@admin_only
async def upload(request: web.Request) -> web.Response:
    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "file":
        return err(400, "file")
    data = await field.read(decode=False)
    if len(data) > 15 * 1024 ** 2:
        return err(413, "too_large")
    try:
        value = save_image(bytes(data))
    except Exception:  # noqa: BLE001 — не картинка
        return err(400, "not_image")
    return ok(value=value, url=url_of(value))


# ---------- настройки ----------
@admin_only
async def settings_get(request: web.Request) -> web.Response:
    db, cfg, _, _ = _ctx(request)
    data = {k: db.get(k) for k in sorted(SETTINGS_KEYS)}
    data["logo_url"] = url_of(db.get("logo")) if db.get("logo") else None
    data["photo_about_url"] = url_of(db.get("photo_about")) if db.get("photo_about") else None
    data["photo_welcome_url"] = url_of(db.get("photo_welcome")) if db.get("photo_welcome") else None
    return ok(settings=data, webapp_url=cfg.webapp_url)


@admin_only
async def settings_save(request: web.Request) -> web.Response:
    db, _, _, uid = _ctx(request)
    body = await _json(request)
    for k, v in body.items():
        if k in SETTINGS_KEYS:
            await db.set(k, str(v if v is not None else "")[:4000])
    await db.log(uid, "admin_settings", keys=sorted(k for k in body if k in SETTINGS_KEYS))
    return ok()


def setup_admin_routes(app: web.Application) -> None:
    r = app.router
    r.add_post("/api/admin/login", login)
    r.add_get("/api/admin/me", me)
    r.add_get("/api/admin/dashboard", dashboard)
    r.add_get("/api/admin/bookings", bookings_list)
    r.add_post("/api/admin/bookings", booking_create)
    r.add_post("/api/admin/bookings/{id:\\d+}", booking_update)
    r.add_get("/api/admin/slots", admin_slots)
    r.add_get("/api/admin/calendar", calendar)
    r.add_get("/api/admin/services", services_list)
    r.add_post("/api/admin/services", service_save)
    r.add_delete("/api/admin/services/{id:\\d+}", service_delete)
    r.add_get("/api/admin/masters", masters_list)
    r.add_post("/api/admin/masters", master_save)
    r.add_delete("/api/admin/masters/{id:\\d+}", master_delete)
    r.add_get("/api/admin/schedule", schedule_get)
    r.add_post("/api/admin/schedule/{kind}", schedule_add)
    r.add_delete("/api/admin/schedule/{kind}/{id}", schedule_delete)
    r.add_get("/api/admin/clients", clients)
    r.add_get("/api/admin/clients/{id:\\d+}", client_detail)
    r.add_get("/api/admin/gallery", gallery_list)
    r.add_post("/api/admin/gallery", gallery_add)
    r.add_post("/api/admin/gallery/{id:\\d+}", gallery_update)
    r.add_delete("/api/admin/gallery/{id:\\d+}", gallery_delete)
    r.add_post("/api/admin/upload", upload)
    r.add_get("/api/admin/settings", settings_get)
    r.add_post("/api/admin/settings", settings_save)
