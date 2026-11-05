"""Мидлвари: регистрация/обновление пользователя на каждое действие."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from .db import DB


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        db: DB = data["db"]
        if user and not user.is_bot:
            data["user_row"] = await db.touch_user(user.id, user.username, user.first_name)
        return await handler(event, data)
