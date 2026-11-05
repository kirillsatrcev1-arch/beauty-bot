"""Прайс-лист (карточки услуг), портфолио-галерея и избранное."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, WebAppInfo

from .. import keyboards as K
from ..config import Config
from ..db import DB, PORTFOLIO_SECTIONS
from ..texts import dur, h, rub, service_card
from ..ui import show

router = Router(name="catalog")


# ---------- прайс ----------
@router.callback_query(F.data == "pr")
async def cb_prices(cb: CallbackQuery, db: DB):
    await cb.answer()
    cats = await db.categories()
    services = await db.services()
    count = {c["id"]: sum(1 for s in services if s["category"] == c["id"]) for c in cats}
    lines = ["<b>💅 Прайс-лист</b>\n", "Выбери категорию, чтобы посмотреть карточки услуг ♡\n"]
    rows = []
    for c in cats:
        if not count[c["id"]]:
            continue
        mn = min(s["price"] for s in services if s["category"] == c["id"])
        lines.append(f"{c['emoji']} {h(c['title'])} — от {rub(mn)}")
        rows.append([K.B(text=f"{c['emoji']} {c['title']}", callback_data=f"pr:cat:{c['id']}")])
    rows.append([K.HOME])
    await show(cb, db, "\n".join(lines), K.kb(*rows), photo="cover:prices")


def _cat_photo(c: dict) -> str:
    return c.get("photo") or f"cover:cat_{c['id']}"


@router.callback_query(F.data.startswith("pr:cat:"))
async def cb_price_cat(cb: CallbackQuery, db: DB):
    await cb.answer()
    c = await db.category(cb.data.split(":")[2])
    if not c:
        return
    services = await db.services(category=c["id"])
    lines = [f"<b>{c['emoji']} {h(c['title'])}</b>\n"]
    for s in services:
        lines.append(f"<b>{h(s['title'])}</b>\n💗 {rub(s['price'], s['price_from'])} · ⏳ {dur(s['duration'])}\n")
    lines.append("<i>Нажми на услугу, чтобы открыть карточку ♡</i>")
    rows = [[K.B(text=f"{s['title']} · {rub(s['price'], s['price_from'])}", callback_data=f"pr:svc:{s['id']}")] for s in services]
    rows.append([K.back("pr", "⬅️ Все категории"), K.HOME])
    await show(cb, db, "\n".join(lines), K.kb(*rows), photo=_cat_photo(c))


async def show_service(cb: CallbackQuery, db: DB, sid: int):
    s = await db.service(sid)
    if not s or not s["active"]:
        await cb.answer("Услуга недоступна", show_alert=True)
        return
    c = await db.category(s["category"])
    siblings = await db.services(category=s["category"])
    ids = [x["id"] for x in siblings]
    i = ids.index(sid) if sid in ids else 0
    fav = await db.is_favorite(cb.from_user.id, sid)
    nav = []
    if len(ids) > 1:
        nav = [K.B(text="‹", callback_data=f"pr:svc:{ids[i - 1]}"),
               K.B(text=f"{i + 1} / {len(ids)}", callback_data="noop"),
               K.B(text="›", callback_data=f"pr:svc:{ids[(i + 1) % len(ids)]}")]
    markup = K.kb(
        [K.B(text="🎀 Записаться", callback_data=f"book:svcgo:{sid}")],
        [K.B(text="💔 Убрать из избранного" if fav else "♡ В избранное", callback_data=f"pr:fav:{sid}")],
        nav,
        [K.back(f"pr:cat:{s['category']}", "⬅️ К категории"), K.HOME],
    )
    await show(cb, db, service_card(s, fav), markup, photo=s.get("photo") or _cat_photo(c))


@router.callback_query(F.data.startswith("pr:svc:"))
async def cb_service(cb: CallbackQuery, db: DB):
    await cb.answer()
    await show_service(cb, db, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("pr:fav:"))
async def cb_fav(cb: CallbackQuery, db: DB):
    sid = int(cb.data.split(":")[2])
    added = await db.toggle_favorite(cb.from_user.id, sid)
    await db.log(cb.from_user.id, "favorite_add" if added else "favorite_remove", service=sid)
    await cb.answer("Добавлено в избранное ♡" if added else "Убрано из избранного")
    await show_service(cb, db, sid)


@router.callback_query(F.data == "fav")
async def cb_favorites(cb: CallbackQuery, db: DB):
    await cb.answer()
    favs = await db.favorites(cb.from_user.id)
    if not favs:
        text = "<b>♡ Избранное</b>\n\nЗдесь будут твои любимые услуги. Открой карточку в прайсе и нажми «♡ В избранное»."
        rows = [[K.B(text="💅 Открыть прайс", callback_data="pr")], [K.HOME]]
    else:
        text = "<b>♡ Избранное</b>\n\n" + "\n".join(f"• {h(s['title'])} — {rub(s['price'], s['price_from'])}" for s in favs)
        rows = [[K.B(text=f"🎀 {s['title']}", callback_data=f"book:svcgo:{s['id']}"),
                 K.B(text="ⓘ", callback_data=f"pr:svc:{s['id']}")] for s in favs]
        rows.append([K.HOME])
    await show(cb, db, text, K.kb(*rows), photo="cover:favorites")


# ---------- портфолио ----------
SECTIONS = {k: (t, e) for k, t, e in PORTFOLIO_SECTIONS}


@router.callback_query(F.data == "pf")
async def cb_portfolio(cb: CallbackQuery, db: DB, cfg: Config):
    await cb.answer()
    counts = await db.portfolio_counts()
    rows = [[K.B(text=f"{e} {t}" + (f" · {counts[k]}" if counts.get(k) else ""), callback_data=f"pf:{k}:0")]
            for k, t, e in PORTFOLIO_SECTIONS]
    if cfg.webapp_url:
        rows.append([K.B(text="✨ Галерея с зумом", web_app=WebAppInfo(url=f"{cfg.webapp_url}/?tab=portfolio"))])
    rows.append([K.HOME])
    text = ("<b>🦢 Моё портфолио</b>\n\nВдохновляйся моими работами ♡ Выбери стиль — листай фото стрелками. "
            "Нажми на фото, чтобы открыть его на весь экран и приблизить.")
    await show(cb, db, text, K.kb(*rows), photo="cover:portfolio")


@router.callback_query(F.data.startswith("pf:full:"))
async def cb_pf_full(cb: CallbackQuery, db: DB):
    item = await db.fetchone("SELECT * FROM portfolio WHERE id=?", (int(cb.data.split(":")[2]),))
    if not item:
        await cb.answer()
        return
    await cb.answer("Отправляю оригинал ♡")
    if item.get("orig_id"):
        await cb.message.answer_document(item["orig_id"], caption=h(item.get("caption")))
    else:
        await cb.message.answer_photo(item["file_id"], caption=h(item.get("caption")))


@router.callback_query(F.data.startswith("pf:"))
async def cb_pf_section(cb: CallbackQuery, db: DB, cfg: Config):
    await cb.answer()
    _, sec, idx = cb.data.split(":")
    title, emoji = SECTIONS.get(sec, ("Работы", "✨"))
    items = await db.portfolio(sec)
    if not items:
        await show(cb, db, f"<b>{emoji} {title}</b>\n\nСовсем скоро здесь появятся мои работы ♡",
                   K.kb([K.B(text="🎀 Записаться", callback_data="book")], [K.back("pf", "⬅️ Разделы"), K.HOME]),
                   photo=f"cover:pf_{sec}")
        return
    i = int(idx) % len(items)
    it = items[i]
    text = f"<b>{emoji} {title}</b> · {i + 1}/{len(items)}"
    if it.get("caption"):
        text += f"\n\n{h(it['caption'])}"
    nav = [K.B(text="◀", callback_data=f"pf:{sec}:{(i - 1) % len(items)}"),
           K.B(text=f"{i + 1} / {len(items)}", callback_data="noop"),
           K.B(text="▶", callback_data=f"pf:{sec}:{(i + 1) % len(items)}")] if len(items) > 1 else []
    rows = [nav, [K.B(text="🔍 Оригинал", callback_data=f"pf:full:{it['id']}"),
                  K.B(text="🎀 Хочу так же", callback_data="book")]]
    if cfg.webapp_url:
        rows.append([K.B(text="✨ Открыть галерею", web_app=WebAppInfo(url=f"{cfg.webapp_url}/?tab=portfolio&s={sec}"))])
    rows.append([K.back("pf", "⬅️ Разделы"), K.HOME])
    await show(cb, db, text, K.kb(*rows), photo=it["file_id"])
