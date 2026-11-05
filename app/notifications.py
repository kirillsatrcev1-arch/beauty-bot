"""Фоновый планировщик: напоминания за 24 ч и 2 ч, автозавершение визитов, просьба об отзыве."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot

from . import keyboards as K
from .config import Config
from .db import DB
from .scheduling import FMT, local_now
from .texts import booking_details, h
from .ui import send_safe

log = logging.getLogger(__name__)


async def tick(bot: Bot, db: DB, cfg: Config) -> dict[str, int]:
    now = local_now(cfg.tz)
    ns = now.strftime(FMT)
    stats = {"r24": 0, "r2": 0, "done": 0, "expired": 0, "review": 0}

    # напоминание за 24 часа (с кнопкой «Буду!»)
    rows = await db.fetchall(
        "SELECT * FROM bookings WHERE status IN ('pending','confirmed') AND remind24=0 AND start>? AND start<=?",
        (ns, (now + timedelta(hours=24)).strftime(FMT)))
    for b in rows:
        await db.execute("UPDATE bookings SET remind24=1 WHERE id=?", (b["id"],))
        if not db.flag("remind_24"):
            continue
        await send_safe(bot, db, b["user_id"],
                        "<b>Напоминаю о записи завтра ♡</b>\n\n" + booking_details(b, db.get("address_text"))
                        + "\n\nПодтверди, пожалуйста, что придёшь 💗", K.reminder_kb(b["id"]))
        stats["r24"] += 1

    # напоминание за 2 часа
    rows = await db.fetchall(
        "SELECT * FROM bookings WHERE status IN ('pending','confirmed') AND remind2=0 AND start>? AND start<=?",
        (ns, (now + timedelta(hours=2)).strftime(FMT)))
    for b in rows:
        await db.execute("UPDATE bookings SET remind2=1 WHERE id=?", (b["id"],))
        if not db.flag("remind_2"):
            continue
        hint = db.get("address_hint")
        await send_safe(bot, db, b["user_id"],
                        f"<b>Совсем скоро встречаемся! ✨</b>\n\nЖду тебя в {b['start'][11:16]}\n🎀 {h(b['service_title'])}\n"
                        f"📍 {h(db.get('address_text'))}" + (f"\n{h(hint)}" if hint else ""),
                        K.kb([K.B(text="📍 Как добраться", callback_data="addr")]))
        stats["r2"] += 1

    # визит прошёл: подтверждённые -> done, неподтверждённые -> expired
    stats["done"] = await db.execute_rc(
        "UPDATE bookings SET status='done', updated_at=? WHERE status='confirmed' AND end<=?", (ns, ns))
    stats["expired"] = await db.execute_rc(
        "UPDATE bookings SET status='expired', updated_at=? WHERE status='pending' AND end<=?", (ns, ns))

    # просьба оставить отзыв
    delay = (now - timedelta(hours=db.get_int("review_delay_hours", 3))).strftime(FMT)
    rows = await db.fetchall("SELECT * FROM bookings WHERE status='done' AND review_asked=0 AND end<=?", (delay,))
    for b in rows:
        await db.execute("UPDATE bookings SET review_asked=1 WHERE id=?", (b["id"],))
        if b["end"] < (now - timedelta(days=2)).strftime(FMT):
            continue  # слишком давно — не беспокоим
        await send_safe(bot, db, b["user_id"],
                        f"<b>Спасибо, что была у меня сегодня! 💗</b>\n\nКак тебе {h(b['service_title']).lower()}? "
                        "Поставь оценку — мне очень важно твоё мнение ♡", K.stars_kb(b["id"]))
        stats["review"] += 1
    return stats


async def scheduler_loop(bot: Bot, db: DB, cfg: Config, interval: int = 60) -> None:
    while True:
        try:
            st = await tick(bot, db, cfg)
            if any(st.values()):
                log.info("scheduler: %s", st)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval)
