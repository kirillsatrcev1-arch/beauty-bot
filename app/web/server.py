"""HTTP-сервер Mini App: статика (React-сборка), публичный JSON API, файлы и прокси фото из Telegram.
Админский API — в admin_api.py. Все запросы к /api/* проверяют подпись Telegram initData на сервере."""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiohttp import web

from .. import logic
from ..config import APP_DIR, Config
from ..db import DB, PORTFOLIO_SECTIONS
from ..media import UPLOAD_PREFIX, url_of
from ..scheduling import (
    SlotTaken, fmt_hm, free_slots_by_master, local_now, masters_for_service, month_map, nearest_free,
)
from ..subscription import channel_url, is_subscribed
from .auth import InitDataError, ics_sig, validate_init_data, verify_admin_token

log = logging.getLogger(__name__)
DIST = APP_DIR / "web" / "dist"
STATIC = APP_DIR / "web" / "static"
K_DB, K_BOT, K_CFG = web.AppKey("db", DB), web.AppKey("bot", Bot), web.AppKey("cfg", Config)
K_USER, K_ADMIN = web.RequestKey("user", dict), web.RequestKey("is_admin", bool)
K_TG = web.RequestKey("tg_user", dict)


def err(status: int, code: str, **extra) -> web.Response:
    return web.json_response({"ok": False, "error": code, **extra}, status=status)


def ok(**data) -> web.Response:
    return web.json_response({"ok": True, **data})


@web.middleware
async def json_errors_mw(request: web.Request, handler):
    """Ошибки API всегда в JSON — фронтенду не нужно разбирать HTML/текст."""
    try:
        return await handler(request)
    except web.HTTPException as e:
        if request.path.startswith("/api/") and e.status >= 400:
            return err(e.status, {400: "bad_request", 403: "forbidden", 404: "not_found"}.get(e.status, "error"))
        raise
    except (KeyError, ValueError, TypeError):
        if request.path.startswith("/api/"):
            return err(400, "bad_request")
        raise


@web.middleware
async def auth_mw(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    cfg: Config = request.app[K_CFG]
    db: DB = request.app[K_DB]
    # веб-админка в браузере: подписанная сессия, выданная по одноразовой ссылке из бота
    session = request.headers.get("X-Admin-Session", "")
    if session and request.path.startswith("/api/admin/"):
        uid = verify_admin_token(session, cfg.bot_token)
        if uid and cfg.is_admin(uid):
            request[K_USER] = await db.user(uid) or {"id": uid, "name": "", "first_name": "", "phone": ""}
            request[K_ADMIN] = True
            request[K_TG] = {}
            return await handler(request)
        return err(401, "unauthorized", detail="session")
    if request.path == "/api/admin/login":
        return await handler(request)
    try:
        tg_user = validate_init_data(request.headers.get("X-Init-Data", ""), cfg.bot_token)
    except InitDataError as e:
        return err(401, "unauthorized", detail=str(e))
    user = await db.touch_user(int(tg_user["id"]), tg_user.get("username"), tg_user.get("first_name"))
    if user.get("_new"):
        await logic.notify_new_client(request.app[K_BOT], db, cfg, user)
    request[K_USER] = user
    request[K_TG] = tg_user
    request[K_ADMIN] = cfg.is_admin(int(tg_user["id"]))
    return await handler(request)


# ---------- сериализация ----------
async def master_services_map(db: DB) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for r in await db.fetchall("SELECT master_id, service_id FROM master_services"):
        out.setdefault(r["master_id"], []).append(r["service_id"])
    return out


def svc_json(s: dict, masters: list[dict], ms: dict[int, list[int]]) -> dict:
    return {"id": s["id"], "category": s["category"], "title": s["title"], "description": s["description"],
            "price": s["price"], "price_from": bool(s["price_from"]), "duration": s["duration"],
            "photo": url_of(s["photo"]), "active": bool(s["active"]),
            "master_ids": [m["id"] for m in masters if not ms.get(m["id"]) or s["id"] in ms[m["id"]]]}


def master_json(m: dict, ms: dict[int, list[int]]) -> dict:
    return {"id": m["id"], "name": m["name"], "role": m["role"], "bio": m["bio"], "photo": url_of(m["photo"]),
            "active": bool(m["active"]), "service_ids": ms.get(m["id"], []),
            "work_days": m["work_days"], "work_start": m["work_start"], "work_end": m["work_end"],
            "break_start": m["break_start"], "break_end": m["break_end"]}


def booking_json(b: dict, cfg: Config | None = None) -> dict:
    out = {k: b.get(k) for k in ("id", "user_id", "service_id", "service_title", "price", "price_from", "duration", "date",
                                 "start", "end", "status", "name", "phone", "comment", "client_confirmed", "master_id",
                                 "master_name", "source", "created_at", "cancel_reason")}
    out["price_from"] = bool(out["price_from"])
    if cfg:
        out["ics"] = f"/ics/{b['id']}.ics?sig={ics_sig(b['id'], cfg.bot_token)}"
    return out


def portfolio_item(i: dict) -> dict:
    return {"id": i["id"], "section": i["section"], "src": url_of(i["file_id"]),
            "orig": url_of(i["orig_id"]) if i.get("orig_id") else url_of(i["file_id"]), "caption": i["caption"] or ""}


# ---------- публичные данные ----------
async def bootstrap(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    user, tg = request[K_USER], request[K_TG]
    cats = await db.categories()
    services = await db.services()
    masters = await db.fetchall("SELECT * FROM masters WHERE active=1 ORDER BY sort, id")
    ms = await master_services_map(db)
    counts = await db.portfolio_counts()
    sections = []
    for k, t, e in PORTFOLIO_SECTIONS:
        cover = await db.fetchone("SELECT file_id FROM portfolio WHERE section=? ORDER BY id DESC LIMIT 1", (k,))
        sections.append({"id": k, "title": t, "emoji": e, "count": counts.get(k, 0), "cover": url_of(cover["file_id"]) if cover else None})
    reviews = await db.fetchall("SELECT name, rating, text, created_at FROM reviews WHERE status='published' ORDER BY id DESC LIMIT 30")
    # ближайшее свободное окно для самой популярной услуги
    nearest = None
    pop = await db.fetchone("SELECT service_id, COUNT(*) n FROM bookings WHERE service_id IS NOT NULL GROUP BY service_id ORDER BY n DESC LIMIT 1")
    svc = next((s for s in services if pop and s["id"] == pop["service_id"]), None) or next(
        (s for s in services if s["category"] == "cover"), services[0] if services else None)
    if svc:
        found = await nearest_free(db, svc["duration"], local_now(cfg.tz), 1, masters=await masters_for_service(db, svc["id"]))
        if found:
            d, t = found[0]
            nearest = {"service_id": svc["id"], "date": d.isoformat(), "time": fmt_hm(t)}
    g = db.get
    return ok(
        studio={
            "name": g("studio_name"), "logo": url_of(g("logo")) if g("logo") else None, "master": g("master_name"),
            "about": g("about_text"), "address": g("address_text"), "address_hint": g("address_hint"), "map_url": g("map_url"),
            "contact_text": g("contact_text"), "contact_username": g("contact_username").lstrip("@"), "contact_phone": g("contact_phone"),
            "channel_url": channel_url(db), "instagram_url": g("instagram_url"), "vk_url": g("vk_url"),
            "cancel_rules": g("cancel_rules"), "cancel_min_hours": db.get_int("cancel_min_hours", 3),
            "why_us": [x.strip() for x in g("why_us").split("|") if x.strip()],
            "about_photo": url_of(g("photo_about")) if g("photo_about") else None,
            "hero_photo": url_of(g("photo_welcome")) if g("photo_welcome") else None,
        },
        categories=[{"id": c["id"], "title": c["title"], "emoji": c["emoji"], "photo": url_of(c["photo"]),
                     "count": sum(1 for s in services if s["category"] == c["id"])} for c in cats],
        services=[svc_json(s, masters, ms) for s in services],
        masters=[master_json(m, ms) for m in masters],
        portfolio=sections,
        reviews=reviews,
        favorites=[s["id"] for s in await db.favorites(user["id"])],
        nearest=nearest,
        user={"id": user["id"], "name": user.get("name") or user.get("first_name") or "", "first_name": user.get("first_name") or "",
              "phone": user.get("phone") or "", "photo_url": tg.get("photo_url"), "is_admin": request[K_ADMIN]},
    )


async def portfolio(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    s = request.query.get("s")
    rows = await db.portfolio(s) if s else await db.fetchall("SELECT * FROM portfolio ORDER BY id DESC LIMIT 200")
    return ok(items=[portfolio_item(i) for i in rows])


async def _target(request: web.Request, db: DB) -> tuple[int, int | None, list[int]]:
    """Длительность, exclude_id и список мастеров для календаря (новая запись или перенос)."""
    rid = request.query.get("resched")
    if rid:
        b = await db.booking(int(rid))
        if not b or b["user_id"] != request[K_USER]["id"]:
            raise web.HTTPNotFound()
        return b["duration"], b["id"], await masters_for_service(db, b["service_id"]) or [b["master_id"]]
    s = await db.service(int(request.query.get("service", "0")))
    if not s or not s["active"]:
        raise web.HTTPNotFound()
    masters = await masters_for_service(db, s["id"])
    m = request.query.get("master")
    if m and m != "any":
        masters = [x for x in masters if x == int(m)]
    return s["duration"], None, masters


async def month(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    duration, exclude, masters = await _target(request, db)
    y, m = map(int, request.query["ym"].split("-"))
    now = local_now(cfg.tz)
    days = await month_map(db, y, m, duration, now, exclude_id=exclude, masters=masters)
    horizon = now.date() + timedelta(days=db.get_int("horizon_days", 45))
    return ok(days=days, min=f"{now.year}-{now.month:02d}", max=f"{horizon.year}-{horizon.month:02d}")


async def slots(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    duration, exclude, masters = await _target(request, db)
    d = date.fromisoformat(request.query["date"])
    res = await free_slots_by_master(db, d, duration, local_now(cfg.tz), masters, exclude)
    return ok(slots=[{"time": fmt_hm(t), "masters": ms} for t, ms in res.items()])


async def sub_check(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    ok_ = await is_subscribed(request.app[K_BOT], db, request[K_USER]["id"], request.app[K_CFG].admin_ids)
    return ok(subscribed=ok_, channel_url=channel_url(db))


def parse_start(body: dict) -> datetime:
    return datetime.strptime(f"{body['date']} {body['time']}", "%Y-%m-%d %H:%M")


async def book(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    bot: Bot = request.app[K_BOT]
    user = request[K_USER]
    body = await request.json()
    if not await is_subscribed(bot, db, user["id"], cfg.admin_ids):
        return err(403, "subscribe", channel_url=channel_url(db))
    from ..handlers.booking import normalize_phone
    name = " ".join(str(body.get("name", "")).split())[:40]
    phone = normalize_phone(str(body.get("phone", "")))
    if len(name) < 2:
        return err(400, "name")
    if not phone:
        return err(400, "phone")
    s = await db.service(int(body.get("service", 0)))
    if not s or not s["active"]:
        return err(404, "service")
    master = body.get("master")
    master_id = int(master) if master not in (None, "", "any") else None
    if master_id and master_id not in await masters_for_service(db, s["id"]):
        return err(400, "master")
    try:
        b = await logic.book(bot, db, cfg, user_id=user["id"], service=s, start=parse_start(body), name=name, phone=phone,
                             comment=(str(body.get("comment") or "").strip()[:500] or None), source="webapp",
                             notify_client=True, master_id=master_id)
    except SlotTaken:
        return err(409, "slot_taken")
    except (KeyError, ValueError):
        return err(400, "bad_request")
    return ok(booking=booking_json(b, cfg), address=db.get("address_text"))


async def _own(request: web.Request, db: DB, bid: int) -> dict:
    b = await db.booking(bid)
    if not b or b["user_id"] != request[K_USER]["id"]:
        raise web.HTTPNotFound()
    return b


def too_late(db: DB, cfg: Config, b: dict) -> bool:
    start = datetime.strptime(b["start"], "%Y-%m-%d %H:%M")
    return start - local_now(cfg.tz) < timedelta(hours=db.get_int("cancel_min_hours", 3))


async def reschedule(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    body = await request.json()
    b = await _own(request, db, int(body["id"]))
    if b["status"] not in ("pending", "confirmed"):
        return err(400, "inactive")
    if too_late(db, cfg, b):
        return err(400, "too_late")
    try:
        nb = await logic.reschedule(request.app[K_BOT], db, cfg, b["id"], parse_start(body), by="client", actor_id=b["user_id"])
    except SlotTaken:
        return err(409, "slot_taken")
    return ok(booking=booking_json(nb, cfg))


async def cancel(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    body = await request.json()
    b = await _own(request, db, int(body["id"]))
    if b["status"] not in ("pending", "confirmed"):
        return err(400, "inactive")
    if too_late(db, cfg, b):
        return err(400, "too_late")
    await logic.cancel(request.app[K_BOT], db, cfg, b["id"], by="client", actor_id=b["user_id"])
    return ok()


async def my(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    uid = request[K_USER]["id"]
    return ok(active=[booking_json(b, cfg) for b in await db.user_bookings(uid, True)],
              history=[booking_json(b, cfg) for b in await db.user_bookings(uid, False)])


async def favorite(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    body = await request.json()
    return ok(favorite=await db.toggle_favorite(request[K_USER]["id"], int(body["service"])))


# ---------- файлы ----------
async def ics(request: web.Request) -> web.Response:
    """Файл календаря для кнопки «Добавить в календарь» (ссылка подписана, чужую запись не открыть)."""
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    bid = int(request.match_info["id"])
    if request.query.get("sig") != ics_sig(bid, cfg.bot_token):
        raise web.HTTPNotFound()
    b = await db.booking(bid)
    if not b:
        raise web.HTTPNotFound()
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(cfg.tz_name)
    fmt = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")  # noqa: E731
    esc = lambda s: (s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")  # noqa: E731
    studio = db.get("studio_name")
    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Beauty Studio//RU", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
        f"UID:booking-{bid}@beauty-studio", f"DTSTAMP:{datetime.now(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{fmt(b['start'])}", f"DTEND:{fmt(b['end'])}",
        f"SUMMARY:{esc(b['service_title'])} — {esc(studio)}",
        f"LOCATION:{esc(db.get('address_text'))}",
        f"DESCRIPTION:{esc('Мастер: ' + (b.get('master_name') or ''))}",
        "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", "DESCRIPTION:Скоро запись на маникюр", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR", ""])
    return web.Response(body=body.encode(), content_type="text/calendar", charset="utf-8",
                        headers={"Content-Disposition": f'attachment; filename="booking-{bid}.ics"'})


async def uploads(request: web.Request) -> web.StreamResponse:
    from ..media import upload_path
    p = upload_path(UPLOAD_PREFIX + request.match_info["name"])
    if not p or not p.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "public, max-age=2592000, immutable"})


async def cover(request: web.Request) -> web.StreamResponse:
    from .. import ui
    key = request.match_info["key"]
    path = (ui.COVERS_DIR / f"{key}.jpg").resolve()
    if not path.is_file() or ui.COVERS_DIR.resolve() not in path.parents:
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})


async def _known_file(db: DB, fid: str) -> bool:
    q = ("SELECT 1 AS x FROM portfolio WHERE file_id=? OR orig_id=? UNION SELECT 1 FROM services WHERE photo=? "
         "UNION SELECT 1 FROM categories WHERE photo=? UNION SELECT 1 FROM masters WHERE photo=? "
         "UNION SELECT 1 FROM settings WHERE (key LIKE 'photo_%' OR key='logo') AND value=?")
    return bool(await db.fetchone(q, (fid, fid, fid, fid, fid, fid)))


async def media(request: web.Request) -> web.StreamResponse:
    """Фото из Telegram по file_id (только известные боту файлы), с дисковым кэшем."""
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    fid = request.match_info["fid"]
    cache_dir: Path = cfg.data_dir / "media"
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir / (hashlib.sha1(fid.encode()).hexdigest() + ".bin")
    if not path.exists():
        if not await _known_file(db, fid):
            raise web.HTTPNotFound()
        bot: Bot = request.app[K_BOT]
        try:
            f = await bot.get_file(fid)
            await bot.download_file(f.file_path, destination=path)
        except Exception as e:  # noqa: BLE001
            log.warning("media %s: %s", fid, e)
            raise web.HTTPNotFound()
    ctype = "image/png" if path.read_bytes()[:4] == b"\x89PNG" else "image/jpeg"
    return web.FileResponse(path, headers={"Cache-Control": "public, max-age=604800", "Content-Type": ctype})


async def index(request: web.Request) -> web.FileResponse:
    page = DIST / "index.html"
    if not page.exists():
        page = STATIC / "index.html"  # запасной вариант, если фронтенд не собран
    return web.FileResponse(page, headers={"Cache-Control": "no-cache"})


async def health(request: web.Request) -> web.Response:
    return ok()


def create_app(db: DB, bot: Bot, cfg: Config) -> web.Application:
    from .admin_api import setup_admin_routes
    app = web.Application(middlewares=[json_errors_mw, auth_mw], client_max_size=16 * 1024 ** 2)
    app[K_DB], app[K_BOT], app[K_CFG] = db, bot, cfg
    r = app.router
    r.add_get("/", index)
    r.add_get("/admin", index)
    r.add_get("/health", health)
    if (DIST / "assets").exists():
        r.add_static("/assets", DIST / "assets")
    if (DIST / "fonts").exists():
        r.add_static("/fonts", DIST / "fonts")
    if (DIST / "demo").exists():
        r.add_static("/demo", DIST / "demo")
    r.add_static("/static", STATIC, append_version=True)
    r.add_get("/img/cover/{key}.jpg", cover)
    r.add_get("/media/{fid}", media)
    r.add_get("/uploads/{name}", uploads)
    r.add_get("/ics/{id:\\d+}.ics", ics)
    r.add_get("/api/bootstrap", bootstrap)
    r.add_get("/api/portfolio", portfolio)
    r.add_get("/api/month", month)
    r.add_get("/api/slots", slots)
    r.add_post("/api/sub", sub_check)
    r.add_post("/api/book", book)
    r.add_post("/api/reschedule", reschedule)
    r.add_post("/api/cancel", cancel)
    r.add_get("/api/my", my)
    r.add_post("/api/favorite", favorite)
    setup_admin_routes(app)
    return app
