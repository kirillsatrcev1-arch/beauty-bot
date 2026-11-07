"""Запись на процедуру (FSM): категория → услуга → дата → время → контакты → подтверждение.
Тот же поток используется для переноса записи клиенткой."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from .. import keyboards as K
from .. import logic
from ..config import Config
from ..db import DB
from ..scheduling import SlotTaken, fmt_hm, free_slots, local_now, masters_for_service, month_map, nearest_free
from ..subscription import is_subscribed
from ..texts import (
    ASK_COMMENT, ASK_NAME, ASK_PHONE, BAD_PHONE, BOOK_CATEGORY, CAL_LEGEND, SLOT_TAKEN,
    booking_created, booking_details, dur, h, human_date, rub,
)
from ..ui import safe_delete, show
from .common import Booking

router = Router(name="booking")
_confirming: set[int] = set()  # защита от двойного нажатия «Подтвердить»


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if not 11 <= len(digits) <= 15:
        return None
    if len(digits) == 11 and digits[0] == "7":
        return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:]}"
    return "+" + digits


# ---------- вход в запись ----------
async def start_booking(event, db: DB, cfg: Config, state: FSMContext, bot: Bot, svc_id: int | None = None):
    user_id = event.from_user.id
    if not await is_subscribed(bot, db, user_id, cfg.admin_ids):
        await state.clear()
        await state.update_data(after_sub={"svc": svc_id})
        from .start import show_subscribe
        await show_subscribe(event, db)
        await db.log(user_id, "subscription_gate")
        return
    await state.clear()
    if svc_id:
        s = await db.service(svc_id)
        if s and s["active"]:
            await _select_service(event, db, cfg, state, s)
            return
    last = await db.fetchone(
        "SELECT b.service_id FROM bookings b JOIN services s ON s.id=b.service_id AND s.active=1 "
        "WHERE b.user_id=? ORDER BY b.id DESC LIMIT 1", (user_id,))
    has_fav = bool(await db.favorites(user_id))
    await show(event, db, BOOK_CATEGORY, K.book_categories(bool(last), has_fav), photo="cover:booking")


@router.callback_query(F.data == "book")
async def cb_book(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    await cb.answer()
    await start_booking(cb, db, cfg, state, bot)


@router.callback_query(F.data.startswith("book:svcgo:"))
async def cb_book_service_direct(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    """«Записаться» из прайса / избранного / истории."""
    await cb.answer()
    await start_booking(cb, db, cfg, state, bot, svc_id=int(cb.data.split(":")[2]))


@router.callback_query(F.data == "book:last")
async def cb_book_last(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    await cb.answer()
    last = await db.fetchone(
        "SELECT b.service_id FROM bookings b JOIN services s ON s.id=b.service_id AND s.active=1 "
        "WHERE b.user_id=? ORDER BY b.id DESC LIMIT 1", (cb.from_user.id,))
    await start_booking(cb, db, cfg, state, bot, svc_id=last["service_id"] if last else None)


@router.callback_query(F.data.startswith("book:grp:"))
async def cb_group(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    group = cb.data.split(":")[2]
    services = await db.services(group=group)
    title = dict(K.BOOK_GROUPS).get(group, "Услуги")
    lines = [f"<b>{title}</b>\nШаг 2 из 6 · Выбери процедуру ♡\n"]
    for s in services:
        lines.append(f"• <b>{h(s['title'])}</b> — {rub(s['price'], s['price_from'])}, {dur(s['duration'])}")
    if not services:
        lines.append("<i>Скоро здесь появятся услуги ♡</i>")
    await state.update_data(group=group)
    cover = {"mani": "cat_mani", "pedi": "cat_pedi", "combo": "cat_combo", "extra": "cat_extra"}.get(group, "booking")
    await show(cb, db, "\n".join(lines), K.book_services(services), photo=f"cover:{cover}")


async def _select_service(event, db: DB, cfg: Config, state: FSMContext, s: dict, resched: dict | None = None):
    cat = await db.category(s["category"]) if s else None
    await state.update_data(
        svc=s["id"] if s else None, dur=s["duration"], title=s["title"], price=s["price"], pfrom=s["price_from"],
        resched=resched["id"] if resched else None,
        group=(cat or {}).get("book_group", "mani"),
        masters=await masters_for_service(db, s.get("id")),
    )
    await show_calendar(event, db, cfg, state)


@router.callback_query(F.data.startswith("book:svc:"))
async def cb_service(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    s = await db.service(int(cb.data.split(":")[2]))
    if not s or not s["active"]:
        await cb.answer("Эта услуга сейчас недоступна", show_alert=True)
        return
    await cb.answer()
    await db.log(cb.from_user.id, "booking_service", service=s["id"])
    await _select_service(cb, db, cfg, state, s)


# ---------- календарь ----------
async def show_calendar(event, db: DB, cfg: Config, state: FSMContext, ym: str | None = None):
    data = await state.get_data()
    if not data.get("dur"):
        await show(event, db, "Сессия записи устарела — начнём заново ♡", K.kb([K.B(text="🎀 Записаться", callback_data="book")]))
        return
    now = local_now(cfg.tz)
    horizon_end = now.date() + timedelta(days=db.get_int("horizon_days", 45))
    exclude = data.get("resched")
    if ym:
        y, m = map(int, ym.split("-"))
    else:
        y, m = now.year, now.month
    days = await month_map(db, y, m, data["dur"], now, exclude_id=exclude, masters=data.get("masters"))
    if not ym and "free" not in days.values() and (horizon_end.year, horizon_end.month) > (y, m):
        y, m = (y + (m == 12), m % 12 + 1)
        days = await month_map(db, y, m, data["dur"], now, exclude_id=exclude, masters=data.get("masters"))
    await state.update_data(ym=f"{y}-{m:02d}")
    head = "🔁 <b>Перенос записи</b>\n" if exclude else ""
    text = (f"{head}<b>Шаг 3 из 6 · Выбери дату</b> 📅\n\n"
            f"🎀 {h(data['title'])} · {rub(data['price'], data.get('pfrom'))} · {dur(data['dur'])}\n\n{CAL_LEGEND}")
    near = await nearest_free(db, data["dur"], now, 3, masters=data.get("masters")) if not exclude else []
    if near:
        text += "\n\n✨ <b>Ближайшие окошки:</b> " + ", ".join(f"{human_date(d, False)} в {fmt_hm(t)}" for d, t in near)
    elif "free" not in days.values():
        text += "\n\n<i>В этом месяце свободных окошек нет — загляни в следующий ♡</i>"
    back_cb = "my" if exclude else f"book:grp:{data.get('group', 'mani')}"
    markup = K.calendar_kb(y, m, days, "book", back_cb,
                           can_prev=(y, m) > (now.year, now.month),
                           can_next=(y, m) < (horizon_end.year, horizon_end.month))
    await show(event, db, text, markup, photo="cover:calendar")


@router.callback_query(F.data.startswith("book:cal:"))
async def cb_cal(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await show_calendar(cb, db, cfg, state, cb.data.split(":")[2])


@router.callback_query(F.data == "book:back:cal")
async def cb_back_cal(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await show_calendar(cb, db, cfg, state, (await state.get_data()).get("ym"))


# ---------- время ----------
async def show_times(event, db: DB, cfg: Config, state: FSMContext, day: date):
    data = await state.get_data()
    slots = await free_slots(db, day, data["dur"], local_now(cfg.tz), exclude_id=data.get("resched"), masters=data.get("masters"))
    await state.update_data(day=day.isoformat())
    if not slots:
        await show(event, db, "В этот день свободных окошек уже не осталось 🥺 Выбери другую дату ♡",
                   K.kb([K.back("book:back:cal", "⬅️ К календарю")]), photo="cover:time")
        return
    text = (f"<b>Шаг 4 из 6 · Выбери время</b> ⏰\n\n📅 {human_date(day)}\n"
            f"🎀 {h(data['title'])} · {dur(data['dur'])}\n\nПоказаны только свободные окошки ♡")
    await show(event, db, text, K.times_kb(day, slots, "book", "book:back:cal"), photo="cover:time")


@router.callback_query(F.data.startswith("book:day:"))
async def cb_day(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await show_times(cb, db, cfg, state, date.fromisoformat(cb.data.split(":")[2]))


@router.callback_query(F.data == "book:back:time")
async def cb_back_time(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    data = await state.get_data()
    if not data.get("day"):
        await show_calendar(cb, db, cfg, state)
        return
    await show_times(cb, db, cfg, state, date.fromisoformat(data["day"]))


@router.callback_query(F.data.startswith("book:time:"))
async def cb_time(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    _, _, day_s, hhmm = cb.data.split(":")
    data = await state.get_data()
    if not data.get("dur"):
        await cb.answer("Сессия записи устарела — начни заново ♡", show_alert=True)
        return
    day = date.fromisoformat(day_s)
    t = int(hhmm[:2]) * 60 + int(hhmm[2:])
    if t not in await free_slots(db, day, data["dur"], local_now(cfg.tz), exclude_id=data.get("resched"), masters=data.get("masters")):
        await cb.answer(SLOT_TAKEN, show_alert=True)
        await show_times(cb, db, cfg, state, day)
        return
    await cb.answer()
    await state.update_data(day=day_s, time=hhmm)
    if data.get("resched"):
        await show_confirm(cb, db, state)
        return
    user = await db.user(cb.from_user.id)
    if user and user.get("name") and user.get("phone"):
        await show(cb, db, "<b>Шаг 5 из 6 · Контакты</b> 💌\n\nЗаписать на эти данные?",
                   K.contacts_choice(user["name"], user["phone"]), photo="cover:contacts")
        return
    await ask_name(cb, db, state)


# ---------- контакты ----------
async def ask_name(event, db: DB, state: FSMContext):
    await state.set_state(Booking.name)
    m = await show(event, db, ASK_NAME, K.kb([K.back("book:back:time"), K.HOME]), photo="cover:contacts")
    await state.update_data(screen=m.message_id)


async def _drop_screen(message: Message, state: FSMContext):
    sid = (await state.get_data()).get("screen")
    if sid:
        try:
            await message.bot.delete_message(message.chat.id, sid)
        except Exception:  # noqa: BLE001
            pass


@router.callback_query(F.data == "book:saved")
async def cb_saved(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    user = await db.user(cb.from_user.id)
    await state.update_data(name=user["name"], phone=user["phone"])
    await ask_comment(cb, db, state)


@router.callback_query(F.data == "book:newcontacts")
async def cb_newcontacts(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await ask_name(cb, db, state)


@router.message(Booking.name, F.text)
async def on_name(message: Message, db: DB, state: FSMContext):
    name = " ".join(message.text.split())[:40]
    if len(name) < 2 or name.startswith("/"):
        await message.answer("Напиши, пожалуйста, своё имя ♡")
        return
    await _drop_screen(message, state)
    await state.update_data(name=name)
    await state.set_state(Booking.phone)
    m = await message.answer(f"Очень приятно, {h(name)}! 🌸\n\n{ASK_PHONE}", reply_markup=K.phone_reply())
    await state.update_data(screen=m.message_id)


@router.message(Booking.phone)
async def on_phone(message: Message, db: DB, state: FSMContext):
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = normalize_phone(raw)
    if not phone:
        await message.answer(BAD_PHONE)
        return
    await _drop_screen(message, state)
    await state.update_data(phone=phone)
    tmp = await message.answer("Спасибо! ♡", reply_markup=ReplyKeyboardRemove())
    await safe_delete(tmp)
    await ask_comment(message, db, state)


async def ask_comment(event, db: DB, state: FSMContext):
    await state.set_state(Booking.comment)
    m = await show(event, db, ASK_COMMENT, K.skip_comment(), photo="cover:contacts")
    await state.update_data(screen=m.message_id)


@router.message(Booking.comment)
async def on_comment(message: Message, db: DB, state: FSMContext):
    text = (message.text or message.caption or "").strip()[:500]
    await _drop_screen(message, state)
    await state.update_data(comment=text or None)
    await state.set_state(None)
    await show_confirm(message, db, state)


@router.callback_query(F.data == "book:nocomment")
async def cb_nocomment(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.update_data(comment=None)
    await state.set_state(None)
    await show_confirm(cb, db, state)


# ---------- подтверждение ----------
async def show_confirm(event, db: DB, state: FSMContext):
    d = await state.get_data()
    resched = d.get("resched")
    fake = {"service_title": d["title"], "date": d["day"], "start": f"{d['day']} {d['time'][:2]}:{d['time'][2:]}",
            "price": d["price"], "price_from": d.get("pfrom")}
    text = ("<b>🔁 Перенос записи</b>\n\nНовое время:\n\n" if resched else "<b>Шаг 6 из 6 · Проверь запись</b> ✨\n\n")
    text += booking_details(fake, db.get("address_text"))
    if not resched:
        text += f"\n\n👤 {h(d.get('name'))}\n📱 {h(d.get('phone'))}"
        if d.get("comment"):
            text += f"\n💬 {h(d['comment'])}"
    await show(event, db, text, K.confirm_kb(bool(resched)), photo="cover:confirm")


@router.callback_query(F.data == "book:abort")
async def cb_abort(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer("Запись не создана")
    from .start import show_home
    await show_home(cb, db, cfg, state)


@router.callback_query(F.data == "book:confirm")
async def cb_confirm(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    uid = cb.from_user.id
    if uid in _confirming:
        await cb.answer("Секундочку… ♡")
        return
    d = await state.get_data()
    if not d.get("time") or not d.get("dur"):
        await cb.answer("Эта запись уже оформлена ♡", show_alert=True)
        return
    _confirming.add(uid)
    try:
        start = datetime.strptime(f"{d['day']} {d['time']}", "%Y-%m-%d %H%M")
        try:
            if d.get("resched"):
                old = await db.booking(d["resched"])
                if not old or old["user_id"] != uid:
                    await cb.answer("Запись не найдена", show_alert=True)
                    return
                b = await logic.reschedule(bot, db, cfg, d["resched"], start, by="client", actor_id=uid)
                text = "<b>Запись перенесена! ♡</b>\n\n" + booking_details(b, db.get("address_text"))
                if b["status"] == "pending":
                    text += "\n\n<i>Мастер подтвердит новое время — я пришлю уведомление 🤍</i>"
            else:
                service = await db.service(d["svc"])
                if not service or not service["active"]:
                    await cb.answer("Эта услуга сейчас недоступна", show_alert=True)
                    return
                b = await logic.book(bot, db, cfg, user_id=uid, service=service, start=start,
                                     name=d["name"], phone=d["phone"], comment=d.get("comment"))
                text = booking_created(b, db.get("address_text"))
        except SlotTaken:
            await cb.answer(SLOT_TAKEN, show_alert=True)
            await state.update_data(time=None)
            await show_times(cb, db, cfg, state, date.fromisoformat(d["day"]))
            return
        await state.clear()
        await cb.answer("Готово! 💗")
        await show(cb, db, text, K.booking_client_kb(b["id"]), photo="cover:success")
    finally:
        _confirming.discard(uid)
