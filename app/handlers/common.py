"""Общие фильтры, состояния FSM и хелперы для хендлеров."""
from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..config import Config


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, cfg: Config) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user) and cfg.is_admin(user.id)


class Booking(StatesGroup):
    name = State()
    phone = State()
    comment = State()


class Support(StatesGroup):
    text = State()


class ReviewText(StatesGroup):
    text = State()


class AdminInput(StatesGroup):
    value = State()      # универсальный ввод значения (data: field, ...)
    photos = State()     # загрузка фото в портфолио
    broadcast = State()  # сообщение для рассылки
    message = State()    # личное сообщение клиентке
    search = State()     # поиск клиентки


def uid(event: Message | CallbackQuery) -> int:
    return event.from_user.id
