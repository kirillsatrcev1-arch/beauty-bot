"""Мидлвари: регистрация/обновление пользователя на каждое действие."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from .db import DB
from .logic import notify_new_client


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        db: DB = data["db"]
        if user and not user.is_bot:
            row = await db.touch_user(user.id, user.username, user.first_name)
            data["user_row"] = row
            if row.get("_new"):
                await notify_new_client(data["bot"], db, data["cfg"], row)
        return await handler(event, data)
