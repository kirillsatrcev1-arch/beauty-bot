"""HTTP-сервер Mini App: статика, JSON API и прокси фотографий из Telegram."""
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
from ..scheduling import SlotTaken, fmt_hm, free_slots, local_now, month_map
from ..subscription import channel_url, is_subscribed
from .auth import InitDataError, validate_init_data

log = logging.getLogger(__name__)
STATIC = APP_DIR / "web" / "static"
K_DB, K_BOT, K_CFG = web.AppKey("db", DB), web.AppKey("bot", Bot), web.AppKey("cfg", Config)
K_USER, K_ADMIN = web.RequestKey("user", dict), web.RequestKey("is_admin", bool)


def err(status: int, code: str, **extra) -> web.Response:
    return web.json_response({"ok": False, "error": code, **extra}, status=status)


def _img(fid: str | None, fallback: str) -> str:
    return f"/media/{fid}" if fid else f"/img/{fallback}.jpg"


@web.middleware
async def auth_mw(request: web.Request, handler):
    if request.path.startswith("/api/"):
        cfg: Config = request.app[K_CFG]
        raw = request.headers.get("X-Init-Data", "")
        try:
            tg_user = validate_init_data(raw, cfg.bot_token)
        except InitDataError as e:
            return err(401, "unauthorized", detail=str(e))
        db: DB = request.app[K_DB]
        request[K_USER] = await db.touch_user(int(tg_user["id"]), tg_user.get("username"), tg_user.get("first_name"))
        request[K_ADMIN] = cfg.is_admin(int(tg_user["id"]))
    return await handler(request)


def _svc(s: dict, cats: dict) -> dict:
    c = cats.get(s["category"], {})
    return {"id": s["id"], "category": s["category"], "title": s["title"], "description": s["description"],
            "price": s["price"], "price_from": bool(s["price_from"]), "duration": s["duration"],
            "photo": f"/media/{s['photo']}" if s["photo"] else None,
            "image": _img(s["photo"] or c.get("photo"), f"cover/cat_{s['category']}")}


def _booking(b: dict) -> dict:
    return {k: b[k] for k in ("id", "service_id", "service_title", "price", "price_from", "duration", "date", "start", "end",
                              "status", "name", "phone", "comment", "client_confirmed")}


# ---------------- публичные данные ----------------
async def bootstrap(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    user = request[K_USER]
    cats = await db.categories()
    cmap = {c["id"]: c for c in cats}
    services = await db.services()
    counts = await db.portfolio_counts()
    favs = [s["id"] for s in await db.favorites(user["id"])]
    reviews = await db.fetchall("SELECT name, rating, text, created_at FROM reviews WHERE status='published' ORDER BY id DESC LIMIT 30")
    return web.json_response({
        "ok": True,
        "studio": {
            "name": db.get("studio_name"), "master": db.get("master_name"), "about": db.get("about_text"),
            "address": db.get("address_text"), "address_hint": db.get("address_hint"), "map_url": db.get("map_url"),
            "contact_text": db.get("contact_text"), "contact_username": db.get("contact_username").lstrip("@"),
            "contact_phone": db.get("contact_phone"), "channel_url": channel_url(db),
            "images": {k: _img(db.get(f"photo_{k}") or None, f"cover/{k}") for k in ("welcome", "about", "address", "portfolio", "prices", "booking")},
            "cancel_min_hours": db.get_int("cancel_min_hours", 3),
        },
        "categories": [{"id": c["id"], "title": c["title"], "emoji": c["emoji"], "group": c["book_group"],
                        "image": _img(c["photo"], f"cover/cat_{c['id']}")} for c in cats],
        "services": [_svc(s, cmap) for s in services],
        "portfolio": [{"id": k, "title": t, "emoji": e, "count": counts.get(k, 0), "image": f"/img/cover/pf_{k}.jpg"}
                      for k, t, e in PORTFOLIO_SECTIONS],
        "reviews": reviews,
        "favorites": favs,
        "user": {"id": user["id"], "name": user["name"] or user["first_name"] or "", "phone": user["phone"] or "",
                 "is_admin": request[K_ADMIN]},
    })


async def portfolio(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    items = await db.portfolio(request.query.get("s", "nude"))
    return web.json_response({"ok": True, "items": [
        {"id": i["id"], "src": f"/media/{i['file_id']}", "orig": f"/media/{i['orig_id']}" if i["orig_id"] else f"/media/{i['file_id']}",
         "caption": i["caption"] or ""} for i in items]})


async def _service_or_booking(request: web.Request, db: DB) -> tuple[int, int | None]:
    """Длительность и exclude_id для календаря (новая запись или перенос)."""
    rid = request.query.get("resched")
    if rid:
        b = await db.booking(int(rid))
        if not b or b["user_id"] != request[K_USER]["id"]:
            raise web.HTTPNotFound()
        return b["duration"], b["id"]
    s = await db.service(int(request.query.get("service", "0")))
    if not s or not s["active"]:
        raise web.HTTPNotFound()
    return s["duration"], None


async def month(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    duration, exclude = await _service_or_booking(request, db)
    y, m = map(int, request.query["ym"].split("-"))
    now = local_now(cfg.tz)
    days = await month_map(db, y, m, duration, now, exclude_id=exclude)
    horizon = now.date() + timedelta(days=db.get_int("horizon_days", 45))
    return web.json_response({"ok": True, "days": days, "min": f"{now.year}-{now.month:02d}",
                              "max": f"{horizon.year}-{horizon.month:02d}"})


async def slots(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    duration, exclude = await _service_or_booking(request, db)
    d = date.fromisoformat(request.query["date"])
    res = await free_slots(db, d, duration, local_now(cfg.tz), exclude_id=exclude)
    return web.json_response({"ok": True, "slots": [fmt_hm(t) for t in res]})


async def sub_check(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    ok = await is_subscribed(request.app[K_BOT], db, request[K_USER]["id"], request.app[K_CFG].admin_ids)
    return web.json_response({"ok": True, "subscribed": ok, "channel_url": channel_url(db)})


def _parse_start(body: dict) -> datetime:
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
    try:
        b = await logic.book(bot, db, cfg, user_id=user["id"], service=s, start=_parse_start(body), name=name, phone=phone,
                             comment=(str(body.get("comment") or "").strip()[:500] or None), source="webapp", notify_client=True)
    except SlotTaken:
        return err(409, "slot_taken")
    except (KeyError, ValueError):
        return err(400, "bad_request")
    return web.json_response({"ok": True, "booking": _booking(b), "address": db.get("address_text")})


async def _own_active(request: web.Request, db: DB, bid: int) -> dict:
    b = await db.booking(bid)
    if not b or b["user_id"] != request[K_USER]["id"]:
        raise web.HTTPNotFound()
    return b


def _too_late(db: DB, cfg: Config, b: dict) -> bool:
    start = datetime.strptime(b["start"], "%Y-%m-%d %H:%M")
    return start - local_now(cfg.tz) < timedelta(hours=db.get_int("cancel_min_hours", 3))


async def reschedule(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    body = await request.json()
    b = await _own_active(request, db, int(body["id"]))
    if b["status"] not in ("pending", "confirmed"):
        return err(400, "inactive")
    if _too_late(db, cfg, b):
        return err(400, "too_late")
    try:
        nb = await logic.reschedule(request.app[K_BOT], db, cfg, b["id"], _parse_start(body), by="client", actor_id=b["user_id"])
    except SlotTaken:
        return err(409, "slot_taken")
    return web.json_response({"ok": True, "booking": _booking(nb)})


async def cancel(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    body = await request.json()
    b = await _own_active(request, db, int(body["id"]))
    if b["status"] not in ("pending", "confirmed"):
        return err(400, "inactive")
    if _too_late(db, cfg, b):
        return err(400, "too_late")
    await logic.cancel(request.app[K_BOT], db, cfg, b["id"], by="client", actor_id=b["user_id"])
    return web.json_response({"ok": True})


async def my(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    uid = request[K_USER]["id"]
    return web.json_response({"ok": True,
                              "active": [_booking(b) for b in await db.user_bookings(uid, True)],
                              "history": [_booking(b) for b in await db.user_bookings(uid, False)]})


async def favorite(request: web.Request) -> web.Response:
    db: DB = request.app[K_DB]
    body = await request.json()
    on = await db.toggle_favorite(request[K_USER]["id"], int(body["service"]))
    return web.json_response({"ok": True, "favorite": on})


# ---------------- админ ----------------
def _admin(request: web.Request):
    if not request[K_ADMIN]:
        raise web.HTTPForbidden()


async def admin_day(request: web.Request) -> web.Response:
    _admin(request)
    db: DB = request.app[K_DB]
    d = request.query.get("date") or local_now(request.app[K_CFG].tz).date().isoformat()
    rows = await db.fetchall("SELECT * FROM bookings WHERE date=? AND status!='cancelled' ORDER BY start", (d,))
    pending = await db.fetchall("SELECT * FROM bookings WHERE status='pending' ORDER BY start LIMIT 50")
    return web.json_response({"ok": True, "date": d, "items": [_booking(b) for b in rows],
                              "pending": [_booking(b) for b in pending]})


async def admin_action(request: web.Request) -> web.Response:
    _admin(request)
    db: DB = request.app[K_DB]
    cfg: Config = request.app[K_CFG]
    bot: Bot = request.app[K_BOT]
    body = await request.json()
    bid, action = int(body["id"]), body["action"]
    uid = request[K_USER]["id"]
    if action == "confirm":
        await logic.confirm(bot, db, cfg, bid, uid)
    elif action == "cancel":
        await logic.cancel(bot, db, cfg, bid, by="admin", actor_id=uid, reason=body.get("reason"))
    elif action == "done":
        await logic.mark_done(db, bid, uid)
    else:
        return err(400, "action")
    return web.json_response({"ok": True, "booking": _booking(await db.booking(bid))})


# ---------------- картинки ----------------
async def cover(request: web.Request) -> web.StreamResponse:
    db: DB = request.app[K_DB]
    key = request.match_info["key"]
    custom = db.get(f"photo_{key}")
    if custom:
        raise web.HTTPFound(f"/media/{custom}")
    if key.startswith("cat_"):
        c = await db.category(key[4:])
        if c and c["photo"]:
            raise web.HTTPFound(f"/media/{c['photo']}")
    from .. import ui
    path = (ui.COVERS_DIR / f"{key}.jpg").resolve()
    if not path.is_file() or ui.COVERS_DIR.resolve() not in path.parents:
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})


async def _known_file(db: DB, fid: str) -> bool:
    q = ("SELECT 1 AS x FROM portfolio WHERE file_id=? OR orig_id=? UNION SELECT 1 FROM services WHERE photo=? "
         "UNION SELECT 1 FROM categories WHERE photo=? UNION SELECT 1 FROM settings WHERE key LIKE 'photo_%' AND value=?")
    return bool(await db.fetchone(q, (fid, fid, fid, fid, fid)))


async def media(request: web.Request) -> web.StreamResponse:
    """Отдаёт фото из Telegram по file_id (только известные боту файлы), с дисковым кэшем."""
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
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


def create_app(db: DB, bot: Bot, cfg: Config) -> web.Application:
    app = web.Application(middlewares=[auth_mw], client_max_size=1024 ** 2)
    app[K_DB], app[K_BOT], app[K_CFG] = db, bot, cfg
    r = app.router
    r.add_get("/", index)
    r.add_get("/health", health)
    r.add_static("/static", STATIC, append_version=True)
    r.add_get("/img/cover/{key}.jpg", cover)
    r.add_get("/media/{fid}", media)
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
    r.add_get("/api/admin/day", admin_day)
    r.add_post("/api/admin/action", admin_action)
    return app
