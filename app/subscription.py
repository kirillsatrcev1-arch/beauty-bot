"""Проверка подписки на канал через getChatMember (на сервере, не на доверии)."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from .db import DB

log = logging.getLogger(__name__)
OK_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER}


def channel_url(db: DB) -> str:
    url = db.get("channel_url").strip()
    if url:
        return url
    ch = db.get("channel_id").strip()
    if ch.startswith("@"):
        return f"https://t.me/{ch[1:]}"
    return ""


def gate_enabled(db: DB) -> bool:
    return db.flag("sub_required") and bool(db.get("channel_id").strip())


async def is_subscribed(bot: Bot, db: DB, user_id: int, admin_ids: set[int] | None = None) -> bool:
    if admin_ids and user_id in admin_ids:
        return True
    if not gate_enabled(db):
        return True
    chat = db.get("channel_id").strip()
    try:
        member = await bot.get_chat_member(chat, user_id)
    except TelegramAPIError as e:
        # Бот не админ канала или канал указан неверно: не блокируем клиенток, но пишем в лог.
        log.error("Не удалось проверить подписку на %s: %s. Добавьте бота администратором канала.", chat, e)
        return True
    ok = member.status in OK_STATUSES or (
        member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False)
    )
    await db.execute("UPDATE users SET is_subscribed=? WHERE id=?", (int(ok), user_id))
    return ok
