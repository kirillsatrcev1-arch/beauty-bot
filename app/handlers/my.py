"""Мои записи: просмотр, отмена, перенос, подтверждение визита, история и повтор."""
from __future__ import annotations

from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .. import keyboards as K
from .. import logic
from ..config import Config
from ..db import DB
from ..scheduling import local_now
from ..texts import STATUS, b_dt, b_time, booking_details, h, human_date, rub
from ..ui import show
from .booking import _select_service

router = Router(name="my")


async def _own(cb: CallbackQuery, db: DB) -> dict | None:
    b = await db.booking(int(cb.data.split(":")[2]))
    if not b or b["user_id"] != cb.from_user.id:
        await cb.answer("Запись не найдена", show_alert=True)
        return None
    return b


@router.callback_query(F.data == "my")
async def cb_my(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.clear()
    items = await db.user_bookings(cb.from_user.id, active=True)
    if items:
        text = "<b>📒 Мои записи</b>\n\n" + "\n\n".join(
            f"🎀 <b>{h(b['service_title'])}</b>\n📅 {human_date(b['date'])}, {b_time(b)}\n{STATUS[b['status']]}" for b in items
        ) + "\n\n<i>Нажми на запись, чтобы перенести или отменить её.</i>"
    else:
        text = "<b>📒 Мои записи</b>\n\nПредстоящих записей пока нет. Самое время побаловать себя ♡"
    await show(cb, db, text, K.my_list(items), photo="cover:my")


@router.callback_query(F.data.startswith("my:b:"))
async def cb_my_booking(cb: CallbackQuery, db: DB):
    b = await _own(cb, db)
    if not b:
        return
    await cb.answer()
    text = f"<b>Запись</b> · {STATUS.get(b['status'], '')}\n\n" + booking_details(b, db.get("address_text"))
    rows = []
    if b["status"] in ("pending", "confirmed"):
        rows.append([K.B(text="🔁 Перенести", callback_data=f"my:resch:{b['id']}"),
                     K.B(text="❌ Отменить", callback_data=f"my:cancel:{b['id']}")])
    rows.append([K.back("my"), K.HOME])
    await show(cb, db, text, K.kb(*rows), photo="cover:my")


def _too_late(db: DB, cfg: Config, b: dict) -> bool:
    return b_dt(b) - local_now(cfg.tz) < timedelta(hours=db.get_int("cancel_min_hours", 3))


async def _late_screen(cb: CallbackQuery, db: DB, what: str):
    hours = db.get_int("cancel_min_hours", 3)
    await show(cb, db, f"До визита осталось меньше {hours} ч, поэтому {what} можно только через мастера 🤍\n\n"
               "Напиши ей, пожалуйста — она обязательно поможет!",
               K.kb([K.B(text="💌 Написать мастеру", callback_data="contact:write")], [K.back("my"), K.HOME]),
               photo="cover:contact")


@router.callback_query(F.data.startswith("my:cancel:"))
async def cb_cancel(cb: CallbackQuery, db: DB, cfg: Config):
    b = await _own(cb, db)
    if not b:
        return
    await cb.answer()
    if b["status"] not in ("pending", "confirmed"):
        await show(cb, db, "Эта запись уже неактивна ♡", K.kb([K.back("my"), K.HOME]), photo="cover:my")
        return
    if _too_late(db, cfg, b):
        await _late_screen(cb, db, "отменить запись")
        return
    await show(cb, db, f"<b>Отменить запись?</b> 🥺\n\n🎀 {h(b['service_title'])}\n📅 {human_date(b['date'])}, {b_time(b)}",
               K.kb([K.B(text="Да, отменить", callback_data=f"my:cancelyes:{b['id']}")],
                    [K.B(text="🔁 Лучше перенести", callback_data=f"my:resch:{b['id']}")],
                    [K.B(text="Нет, я приду ♡", callback_data="my")]),
               photo="cover:my")


@router.callback_query(F.data.startswith("my:cancelyes:"))
async def cb_cancel_yes(cb: CallbackQuery, db: DB, cfg: Config, bot: Bot):
    b = await _own(cb, db)
    if not b:
        return
    if b["status"] not in ("pending", "confirmed"):
        await cb.answer("Запись уже отменена")
        return
    await logic.cancel(bot, db, cfg, b["id"], by="client", actor_id=cb.from_user.id)
    await cb.answer("Запись отменена")
    await show(cb, db, "Запись отменена. Буду ждать тебя в другой раз ♡",
               K.kb([K.B(text="🎀 Записаться на другое время", callback_data="book")], [K.HOME]), photo="cover:my")


@router.callback_query(F.data.startswith("my:resch:"))
async def cb_resched(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    b = await _own(cb, db)
    if not b:
        return
    await cb.answer()
    if b["status"] not in ("pending", "confirmed"):
        await show(cb, db, "Эта запись уже неактивна ♡", K.kb([K.back("my"), K.HOME]), photo="cover:my")
        return
    if _too_late(db, cfg, b):
        await _late_screen(cb, db, "перенести запись")
        return
    await state.clear()
    svc = await db.service(b["service_id"]) if b["service_id"] else None
    pseudo = {"id": b["service_id"], "duration": b["duration"], "title": b["service_title"], "price": b["price"],
              "price_from": b["price_from"], "category": (svc or {}).get("category")}
    await _select_service(cb, db, cfg, state, pseudo, resched=b)


@router.callback_query(F.data.startswith("my:come:"))
async def cb_come(cb: CallbackQuery, db: DB, cfg: Config, bot: Bot):
    b = await _own(cb, db)
    if not b:
        return
    if await logic.client_will_come(bot, db, cfg, b["id"], cb.from_user.id):
        await cb.answer("Спасибо! Жду тебя 💗", show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=K.booking_client_kb(b["id"], show_menu=True))
        except Exception:  # noqa: BLE001
            pass
    else:
        await cb.answer("Эта запись уже неактивна")


@router.callback_query(F.data == "my:hist")
async def cb_history(cb: CallbackQuery, db: DB):
    await cb.answer()
    items = await db.user_bookings(cb.from_user.id, active=False)
    done = [b for b in items if b["status"] == "done"]
    if not items:
        text = "<b>🗂 История визитов</b>\n\nЗдесь появятся твои прошедшие визиты ♡"
    else:
        total = sum(b["price"] for b in done)
        text = f"<b>🗂 История визитов</b>\n\nВизитов: <b>{len(done)}</b> · на сумму {rub(total)}\n\n" + "\n".join(
            f"{'✨' if b['status'] == 'done' else '✖️'} {human_date(b['date'], False)} — {h(b['service_title'])}" for b in items[:15]
        )
    seen, rows = set(), []
    for b in done:
        if b["service_id"] and b["service_id"] not in seen:
            seen.add(b["service_id"])
            rows.append([K.B(text=f"🔁 Повторить: {b['service_title']}"[:60], callback_data=f"book:svcgo:{b['service_id']}")])
        if len(rows) >= 4:
            break
    if done:
        rows.append([K.B(text="⭐ Оставить отзыв", callback_data="rv:new")])
    rows.append([K.back("my"), K.HOME])
    await show(cb, db, text, K.kb(*rows), photo="cover:my")
