"""Тестовая обвязка: поддельная сессия Telegram API, через которую бот «общается» без сети."""
from __future__ import annotations

import itertools
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import (
    CallbackQuery, Chat, ChatMemberLeft, ChatMemberMember, Contact, File, Message, MessageEntity, MessageId,
    PhotoSize, Update, User,
)

from app.config import Config
from app.covers import ensure_covers
from app.db import DB
from app.fsm_storage import SQLiteStorage
from app.handlers import setup_routers
from app.middlewares import UserMiddleware
from app.ui import set_covers_dir

TOKEN = "123456:TEST-token-for-tests"
ADMIN = 1000
CLIENT = 2000
COVERS = Path(__file__).resolve().parent.parent / "data" / "covers"


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.member_status = "member"
        self._ids = itertools.count(500)

    def _msg(self, chat_id: int, **kw) -> Message:
        if kw.get("reply_markup") is not None and not hasattr(kw["reply_markup"], "inline_keyboard"):
            kw["reply_markup"] = None
        return Message(message_id=next(self._ids), date=datetime.now(), chat=Chat(id=chat_id, type="private"), **kw)

    async def make_request(self, bot, method, timeout=None):
        res = await self._make(bot, method)
        return res.as_(bot) if hasattr(res, "as_") else res

    async def _make(self, bot, method):
        self.calls.append(method)
        name = type(method).__name__
        photo = [PhotoSize(file_id=f"photo-{next(self._ids)}", file_unique_id="u", width=1280, height=800)]
        if name == "SendMessage":
            return self._msg(method.chat_id, text=method.text, reply_markup=method.reply_markup)
        if name == "SendPhoto":
            return self._msg(method.chat_id, photo=photo, caption=method.caption, reply_markup=method.reply_markup)
        if name == "EditMessageMedia":
            return self._msg(method.chat_id or 0, photo=photo, caption=method.media.caption, reply_markup=method.reply_markup)
        if name == "EditMessageText":
            return self._msg(method.chat_id or 0, text=method.text, reply_markup=method.reply_markup)
        if name == "EditMessageReplyMarkup":
            return self._msg(method.chat_id or 0, text="x", reply_markup=method.reply_markup)
        if name == "CopyMessage":
            return MessageId(message_id=next(self._ids))
        if name == "GetChatMember":
            u = User(id=method.user_id, is_bot=False, first_name="U")
            return ChatMemberMember(user=u) if self.member_status == "member" else ChatMemberLeft(user=u)
        if name == "GetMe":
            return User(id=42, is_bot=True, first_name="Beauty", username="beauty_test_bot")
        if name == "GetFile":
            return File(file_id=method.file_id, file_unique_id="u", file_path="photos/x.jpg")
        return True

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b"\xff\xd8\xff\xe0fakejpeg"

    async def close(self):
        pass

    # ---- помощники для проверок ----
    def sent_to(self, chat_id: int) -> list:
        return [c for c in self.calls if getattr(c, "chat_id", None) == chat_id]

    def last_screen(self):
        for c in reversed(self.calls):
            if type(c).__name__ in ("SendMessage", "SendPhoto", "EditMessageMedia", "EditMessageText"):
                return c
        return None

    @staticmethod
    def text_of(call) -> str:
        n = type(call).__name__
        if n == "EditMessageMedia":
            return call.media.caption or ""
        return getattr(call, "text", None) or getattr(call, "caption", None) or ""

    def clear(self):
        self.calls.clear()


@pytest_asyncio.fixture
async def env(tmp_path):
    ensure_covers(COVERS)
    set_covers_dir(COVERS)
    cfg = Config(bot_token=TOKEN, admin_ids={ADMIN}, db_path=str(tmp_path / "t.db"), data_dir=tmp_path, tz_name="Europe/Moscow")
    db = DB(cfg.db_path)
    await db.connect()
    session = FakeSession()
    bot = Bot(TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=SQLiteStorage(db), db=db, cfg=cfg)
    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())
    dp.include_router(setup_routers())
    e = Env(db=db, cfg=cfg, bot=bot, dp=dp, session=session)
    yield e
    await db.close()


class Env:
    _uid = itertools.count(1)

    def __init__(self, db, cfg, bot, dp, session):
        self.db, self.cfg, self.bot, self.dp, self.session = db, cfg, bot, dp, session
        self.screen_photo: dict[int, bool] = {}

    def user(self, uid: int) -> User:
        return User(id=uid, is_bot=False, first_name="Маша" if uid == CLIENT else "Мастер", username=f"u{uid}")

    async def text(self, uid: int, text: str, contact: str | None = None):
        ents = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))] if text.startswith("/") else None
        msg = Message(message_id=next(self._uid), date=datetime.now(), chat=Chat(id=uid, type="private"), from_user=self.user(uid),
                      text=None if contact else text, entities=ents,
                      contact=Contact(phone_number=contact, first_name="Маша", user_id=uid) if contact else None)
        await self.dp.feed_update(self.bot, Update(update_id=next(self._uid), message=msg))

    async def click(self, uid: int, data: str, photo: bool = True):
        msg = Message(message_id=next(self._uid), date=datetime.now(), chat=Chat(id=uid, type="private"),
                      from_user=User(id=42, is_bot=True, first_name="Beauty"),
                      photo=[PhotoSize(file_id="p", file_unique_id="u", width=1, height=1)] if photo else None,
                      text=None if photo else "screen")
        cq = CallbackQuery(id=str(next(self._uid)), from_user=self.user(uid), chat_instance="ci", data=data, message=msg)
        await self.dp.feed_update(self.bot, Update(update_id=next(self._uid), callback_query=cq))

    def buttons(self, call=None) -> list[str]:
        call = call or self.session.last_screen()
        markup = getattr(call, "reply_markup", None)
        if not markup or not hasattr(markup, "inline_keyboard"):
            return []
        return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]

    def alerts(self) -> list[str]:
        return [c.text for c in self.session.calls if type(c).__name__ == "AnswerCallbackQuery" and c.text]


@pytest.fixture
def anyio_backend():
    return "asyncio"
