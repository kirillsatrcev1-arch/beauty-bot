"""«Экраны»: одно сообщение-карточка, которое редактируется на месте (без спама в чате)."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InputMediaPhoto, Message

from .db import DB
from .media import is_upload, upload_path

log = logging.getLogger(__name__)
COVERS_DIR = Path("data/covers")
CAPTION_LIMIT = 1024


def set_covers_dir(path: Path) -> None:
    global COVERS_DIR
    COVERS_DIR = path


async def resolve_photo(db: DB, photo: str) -> tuple[object, str | None]:
    """'cover:key' -> фото мастера из настроек / закэшированный file_id / файл обложки.
    Иначе photo — это file_id из Telegram."""
    if is_upload(photo):
        path = upload_path(photo)
        if path and path.exists():
            return FSInputFile(path), None
        photo = "cover:welcome"
    if not photo.startswith("cover:"):
        return photo, None
    key = photo[6:]
    custom = db.get(f"photo_{key}")
    if custom:
        return custom, None
    cached = await db.cached_file(f"cover:{key}")
    if cached:
        return cached, None
    path = COVERS_DIR / f"{key}.jpg"
    if not path.exists():
        path = COVERS_DIR / "welcome.jpg"
    return FSInputFile(path), key


async def safe_delete(msg: Message | None) -> None:
    if not msg:
        return
    try:
        await msg.delete()
    except TelegramBadRequest:
        pass


async def _send_photo(bot: Bot, db: DB, chat_id: int, photo: str, text: str, markup) -> Message:
    media, cache_key = await resolve_photo(db, photo)
    try:
        sent = await bot.send_photo(chat_id, media, caption=text, reply_markup=markup)
    except TelegramBadRequest:
        # битый file_id (например, после смены бота) — отправляем исходную обложку
        if photo.startswith("cover:"):
            key = photo[6:]
            await db.execute("DELETE FROM media_cache WHERE key=?", (f"cover:{key}",))
            path = COVERS_DIR / f"{key}.jpg"
            sent = await bot.send_photo(chat_id, FSInputFile(path if path.exists() else COVERS_DIR / "welcome.jpg"),
                                        caption=text, reply_markup=markup)
            cache_key = key
        else:
            return await bot.send_message(chat_id, text, reply_markup=markup)
    if cache_key and sent.photo:
        await db.cache_file(f"cover:{cache_key}", sent.photo[-1].file_id)
    return sent


async def show(
    event: Message | CallbackQuery,
    db: DB,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    photo: str | None = None,
    new: bool = False,
) -> Message:
    """Показать экран. Для колбэка — редактируем текущее сообщение, для сообщения — отправляем новое."""
    bot: Bot = event.bot
    msg = event.message if isinstance(event, CallbackQuery) else None
    chat_id = msg.chat.id if msg else event.chat.id
    if photo and len(text) > CAPTION_LIMIT:
        photo = None
    if new:
        msg = None

    if photo:
        if msg and msg.photo:
            media, cache_key = await resolve_photo(db, photo)
            try:
                res = await msg.edit_media(InputMediaPhoto(media=media, caption=text), reply_markup=markup)
                if cache_key and isinstance(res, Message) and res.photo:
                    await db.cache_file(f"cover:{cache_key}", res.photo[-1].file_id)
                return res if isinstance(res, Message) else msg
            except TelegramBadRequest as e:
                if "not modified" in str(e):
                    return msg
                log.debug("edit_media failed: %s", e)
        sent = await _send_photo(bot, db, chat_id, photo, text, markup)
        await safe_delete(msg)
        return sent

    if msg and msg.text:
        try:
            res = await msg.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
            return res if isinstance(res, Message) else msg
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return msg
    sent = await bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
    await safe_delete(msg)
    return sent


async def send_safe(bot: Bot, db: DB, chat_id: int, text: str, markup=None, photo: str | None = None) -> Message | None:
    """Уведомление пользователю: не падаем, если он заблокировал бота."""
    if not chat_id:  # запись создана мастером вручную, без Telegram-аккаунта клиентки
        return None
    try:
        if photo:
            return await _send_photo(bot, db, chat_id, photo, text, markup)
        return await bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramForbiddenError:
        await db.execute("UPDATE users SET blocked=1 WHERE id=?", (chat_id,))
    except TelegramBadRequest as e:
        log.warning("send to %s failed: %s", chat_id, e)
    return None
