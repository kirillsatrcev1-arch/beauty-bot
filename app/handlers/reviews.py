"""Отзывы: просмотр опубликованных и отзыв после визита."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards as K
from ..config import Config
from ..db import DB, now_str
from ..texts import h, human_date
from ..ui import show
from .common import ReviewText

router = Router(name="reviews")
PAGE = 4


@router.callback_query(F.data.regexp(r"^rv:\d+$"))
async def cb_reviews(cb: CallbackQuery, db: DB):
    await cb.answer()
    page = int(cb.data.split(":")[1])
    total = await db.scalar("SELECT COUNT(*) FROM reviews WHERE status='published'")
    avg = await db.scalar("SELECT AVG(rating) FROM reviews WHERE status='published'")
    items = await db.fetchall("SELECT * FROM reviews WHERE status='published' ORDER BY id DESC LIMIT ? OFFSET ?",
                              (PAGE, page * PAGE))
    if not total:
        text = "<b>⭐ Отзывы</b>\n\nЗдесь будут слова моих клиенток ♡ Стань первой, кто поделится впечатлениями!"
    else:
        text = f"<b>⭐ Отзывы</b> · {avg:.1f} из 5 · {total} шт.\n\n" + "\n\n".join(
            f"{'★' * r['rating']}{'☆' * (5 - r['rating'])}  <b>{h(r['name'] or 'Клиентка')}</b>\n"
            f"<i>{h(r['text']) or '—'}</i>" for r in items)
    nav = []
    if page > 0:
        nav.append(K.B(text="‹ Новее", callback_data=f"rv:{page - 1}"))
    if (page + 1) * PAGE < (total or 0):
        nav.append(K.B(text="Ещё ›", callback_data=f"rv:{page + 1}"))
    await show(cb, db, text[:1000], K.kb(nav, [K.B(text="✍️ Оставить отзыв", callback_data="rv:new")], [K.HOME]),
               photo="cover:reviews")


@router.callback_query(F.data == "rv:new")
async def cb_new(cb: CallbackQuery, db: DB):
    b = await db.fetchone(
        "SELECT * FROM bookings WHERE user_id=? AND status='done' AND id NOT IN (SELECT booking_id FROM reviews WHERE booking_id IS NOT NULL)"
        " ORDER BY start DESC LIMIT 1", (cb.from_user.id,))
    if not b:
        await cb.answer("Отзыв можно оставить после визита ♡ (или ты уже оставила его — спасибо!)", show_alert=True)
        return
    await cb.answer()
    await show(cb, db, f"<b>Как тебе визит?</b> ✨\n\n🎀 {h(b['service_title'])}, {human_date(b['date'], False)}\n\nПоставь оценку ♡",
               K.stars_kb(b["id"]), photo="cover:reviews")


@router.callback_query(F.data.startswith("rv:rate:"))
async def cb_rate(cb: CallbackQuery, db: DB, state: FSMContext):
    _, _, bid, n = cb.data.split(":")
    b = await db.booking(int(bid))
    if not b or b["user_id"] != cb.from_user.id:
        await cb.answer()
        return
    if await db.fetchone("SELECT id FROM reviews WHERE booking_id=?", (b["id"],)):
        await cb.answer("Ты уже оставила отзыв на этот визит — спасибо! ♡", show_alert=True)
        return
    await cb.answer("♡")
    await state.set_state(ReviewText.text)
    await state.update_data(rv_bid=b["id"], rv_rating=int(n))
    await show(cb, db, f"{'★' * int(n)}{'☆' * (5 - int(n))}\n\nНапиши пару слов о визите — мне очень важно твоё мнение 💗",
               K.kb([K.B(text="Без текста ➝", callback_data="rv:skip")]), photo="cover:reviews")


async def _save(event, db: DB, cfg: Config, state: FSMContext, bot: Bot, text: str | None):
    d = await state.get_data()
    await state.clear()
    if not d.get("rv_bid"):
        return
    b = await db.booking(d["rv_bid"])
    rid = await db.execute(
        "INSERT INTO reviews(user_id, booking_id, name, rating, text, status, created_at) VALUES(?,?,?,?,?, 'new', ?)",
        (event.from_user.id, d["rv_bid"], (b or {}).get("name") or event.from_user.first_name, d["rv_rating"], text, now_str()),
    )
    await db.log(event.from_user.id, "review", id=rid, rating=d["rv_rating"])
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(
                aid, f"⭐ <b>Новый отзыв</b> {'★' * d['rv_rating']}\nот {h((b or {}).get('name'))}\n\n<i>{h(text) or 'без текста'}</i>",
                reply_markup=K.kb([K.B(text="✅ Опубликовать", callback_data=f"a:rv:pub:{rid}"),
                                   K.B(text="🙈 Скрыть", callback_data=f"a:rv:hide:{rid}")]))
        except Exception:  # noqa: BLE001
            pass
    await show(event, db, "Спасибо за отзыв! 💗 Мне безумно приятно ♡", K.kb([K.HOME]), photo="cover:reviews")


@router.message(ReviewText.text, F.text)
async def on_review_text(message: Message, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    await _save(message, db, cfg, state, bot, message.text.strip()[:700])


@router.callback_query(F.data == "rv:skip")
async def cb_skip(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    await cb.answer()
    await _save(cb, db, cfg, state, bot, None)
