"""Бизнес-логика записей и уведомления (общая для чата и Mini App)."""
from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot

from . import keyboards as K
from .config import Config
from .db import DB
from .scheduling import SlotTaken, create_booking, local_now, move_booking
from .texts import b_time, booking_admin, booking_created, booking_details, h, human_date
from .ui import send_safe

log = logging.getLogger(__name__)

__all__ = ["SlotTaken", "book", "confirm", "cancel", "reschedule", "mark_done", "client_will_come", "notify_admins"]


async def notify_admins(bot: Bot, db: DB, cfg: Config, text: str, markup=None) -> None:
    for aid in cfg.admin_ids:
        await send_safe(bot, db, aid, text, markup)


async def _user(db: DB, uid: int) -> dict | None:
    return await db.user(uid)


async def book(
    bot: Bot, db: DB, cfg: Config, *, user_id: int, service: dict, start: datetime,
    name: str, phone: str, comment: str | None, source: str = "chat", notify_client: bool = False,
    master_id: int | None = None, status: str | None = None, force: bool = False,
) -> dict:
    status = status or ("confirmed" if db.flag("auto_confirm") else "pending")
    b = await create_booking(
        db, user_id=user_id, service=service, start=start, name=name, phone=phone,
        comment=comment, now=local_now(cfg.tz), source=source, status=status, master_id=master_id,
        ignore_lead=force, force=force,
    )
    if user_id:
        await db.save_contacts(user_id, name, phone)
    await db.log(user_id, "booking_created", id=b["id"], start=b["start"], service=b["service_title"], source=source)
    title = "🆕 <b>Новая запись</b>" if status == "confirmed" else "🆕 <b>Новая заявка на запись</b>"
    await notify_admins(bot, db, cfg, f"{title}\n\n{booking_admin(b, await _user(db, user_id))}", K.admin_booking_kb(b))
    if notify_client:
        await send_safe(bot, db, user_id, booking_created(b, db.get("address_text")), K.booking_client_kb(b["id"]), photo="cover:success")
    return b


async def confirm(bot: Bot, db: DB, cfg: Config, bid: int, admin_id: int | None = None) -> dict | None:
    b = await db.booking(bid)
    if not b or b["status"] != "pending":
        return b
    await db.set_status(bid, "confirmed")
    b = await db.booking(bid)
    await db.log(admin_id, "booking_confirmed", id=bid)
    await send_safe(
        bot, db, b["user_id"],
        "<b>Мастер подтвердил твою запись! 💗</b>\n\n" + booking_details(b, db.get("address_text")) + "\n\nДо встречи ♡",
        K.booking_client_kb(bid),
    )
    for aid in cfg.admin_ids:
        if aid != admin_id:
            await send_safe(bot, db, aid, f"✅ Запись №{bid} подтверждена.\n\n{booking_admin(b)}")
    return b


async def cancel(bot: Bot, db: DB, cfg: Config, bid: int, by: str, actor_id: int | None = None, reason: str | None = None) -> dict | None:
    b = await db.booking(bid)
    if not b or b["status"] not in ("pending", "confirmed"):
        return b
    await db.set_status(bid, "cancelled", reason or ("клиентка отменила" if by == "client" else "мастер отменил"))
    b = await db.booking(bid)
    await db.log(actor_id, "booking_cancelled", id=bid, by=by)
    if by == "client":
        await notify_admins(bot, db, cfg, f"❌ <b>Клиентка отменила запись</b>\n\n{booking_admin(b, await _user(db, b['user_id']))}\n\n"
                                          "Окошко снова свободно для записи 🤍")
    else:
        await send_safe(
            bot, db, b["user_id"],
            "<b>Твоя запись отменена</b> 🥺\n\n"
            f"🎀 {h(b['service_title'])}\n📅 {human_date(b['date'])}, {b_time(b)}"
            + (f"\n\n<i>{h(reason)}</i>" if reason else "")
            + "\n\nВыбери, пожалуйста, другое удобное время ♡",
            K.kb([K.B(text="🎀 Записаться снова", callback_data="book")], [K.HOME]),
        )
    return b


async def reschedule(bot: Bot, db: DB, cfg: Config, bid: int, start: datetime, by: str, actor_id: int | None = None,
                     master_id: int | None = None) -> dict:
    old = await db.booking(bid)
    if by == "admin":
        status = "confirmed"
    else:
        status = "confirmed" if db.flag("auto_confirm") else "pending"
    b = await move_booking(db, bid, start, local_now(cfg.tz), status=status, ignore_lead=(by == "admin"), master_id=master_id)
    await db.log(actor_id, "booking_rescheduled", id=bid, old=old["start"], new=b["start"], by=by)
    was = f"<s>{human_date(old['date'], False)}, {b_time(old)}</s>"
    if by == "client":
        await notify_admins(
            bot, db, cfg,
            f"🔁 <b>Клиентка перенесла запись</b>\nБыло: {was}\n\n{booking_admin(b, await _user(db, b['user_id']))}",
            K.admin_booking_kb(b),
        )
    else:
        await send_safe(
            bot, db, b["user_id"],
            "<b>Время записи изменено</b> ⏰\n\n" f"Было: {was}\n\n" + booking_details(b, db.get("address_text")) + "\n\nДо встречи ♡",
            K.booking_client_kb(bid),
        )
    return b


async def mark_done(db: DB, bid: int, admin_id: int | None = None) -> None:
    await db.set_status(bid, "done")
    await db.log(admin_id, "booking_done", id=bid)


async def client_will_come(bot: Bot, db: DB, cfg: Config, bid: int, user_id: int) -> dict | None:
    b = await db.booking(bid)
    if not b or b["user_id"] != user_id or b["status"] not in ("pending", "confirmed"):
        return None
    await db.execute("UPDATE bookings SET client_confirmed=1 WHERE id=?", (bid,))
    await db.log(user_id, "client_confirmed", id=bid)
    await notify_admins(bot, db, cfg, f"💗 <b>Клиентка подтвердила визит</b>\n\n{booking_admin(await db.booking(bid))}")
    return b


async def notify_new_client(bot: Bot, db: DB, cfg: Config, user: dict) -> None:
    """Мастеру — о новой клиентке (первое появление в боте или приложении)."""
    if not db.flag("notify_new_clients") or cfg.is_admin(user["id"]):
        return
    uname = f" (@{h(user['username'])})" if user.get("username") else ""
    await notify_admins(bot, db, cfg, f"✨ <b>Новая клиентка</b>\n{h(user.get('first_name'))}{uname}")
