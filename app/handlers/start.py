"""Приветствие, главное меню, «Обо мне», адрес, связь с мастером, проверка подписки."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, WebAppInfo

from .. import keyboards as K
from ..config import Config
from ..db import DB
from ..subscription import channel_url, is_subscribed
from ..texts import SUB_NOT_YET, SUB_OK, SUBSCRIBE, WELCOME, h
from ..ui import show
from .common import Support

router = Router(name="start")


def home_kb(db: DB, cfg: Config, user_id: int):
    return K.main_menu(cfg.is_admin(user_id), cfg.webapp_url)


async def show_home(event, db: DB, cfg: Config, state: FSMContext | None = None, new: bool = False):
    if state:
        await state.clear()
    await show(event, db, WELCOME, home_kb(db, cfg, event.from_user.id), photo="cover:welcome", new=new)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    await db.log(message.from_user.id, "start", arg=command.args)
    await state.clear()
    arg = (command.args or "").strip()
    if arg == "book" or arg.startswith("svc_"):
        from .booking import start_booking  # отложенный импорт, чтобы избежать циклов
        sid = int(arg[4:]) if arg.startswith("svc_") and arg[4:].isdigit() else None
        await start_booking(message, db, cfg, state, bot, svc_id=sid)
        return
    if cfg.webapp_url:
        # минималистичный вход: всё происходит в приложении
        await show(message, db, MINI_WELCOME, K.kb(
            [K.B(text="✨ Открыть студию", web_app=WebAppInfo(url=cfg.webapp_url))],
            [K.B(text="Меню в чате", callback_data="home")],
        ), photo="cover:welcome")
        return
    await show_home(message, db, cfg)


MINI_WELCOME = (
    "<b>Добро пожаловать в мой beauty world! 🎀</b>\n\n"
    "Запись, прайс, мои работы и свободные окошки — в приложении. Нажми кнопку ниже ♡"
)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db: DB, cfg: Config, state: FSMContext):
    await show_home(message, db, cfg, state)


@router.callback_query(F.data == "home")
async def cb_home(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await show_home(cb, db, cfg, state)


@router.callback_query(F.data.startswith("noop"))
async def cb_noop(cb: CallbackQuery):
    reason = cb.data.partition(":")[2]
    if reason == "busy":
        await cb.answer("В этот день все окошки заняты 🥺 Выбери другую дату", show_alert=False)
    elif reason == "off":
        await cb.answer("Выходной день мастера ♡", show_alert=False)
    else:
        await cb.answer()


# ---------- подписка ----------
async def show_subscribe(event, db: DB):
    await show(event, db, SUBSCRIBE, K.subscribe_kb(channel_url(db)), photo="cover:subscribe")


@router.callback_query(F.data == "sub:check")
async def cb_sub_check(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    if not await is_subscribed(bot, db, cb.from_user.id, cfg.admin_ids):
        await cb.answer(SUB_NOT_YET, show_alert=True)
        return
    await cb.answer(SUB_OK)
    await db.log(cb.from_user.id, "subscribed")
    data = await state.get_data()
    after = data.get("after_sub") or {}
    from .booking import start_booking
    await start_booking(cb, db, cfg, state, bot, svc_id=after.get("svc"))


# ---------- обо мне ----------
@router.callback_query(F.data == "about")
async def cb_about(cb: CallbackQuery, db: DB):
    await cb.answer()
    text = f"<b>🤍 Обо мне</b>\n\n{db.get('about_text')}"
    await show(cb, db, text, K.kb(
        [K.B(text="🎀 Записаться", callback_data="book"), K.B(text="🦢 Мои работы", callback_data="pf")],
        [K.B(text="⭐ Отзывы клиенток", callback_data="rv:0")],
        [K.HOME],
    ), photo="cover:about")


# ---------- адрес ----------
@router.callback_query(F.data == "addr")
async def cb_addr(cb: CallbackQuery, db: DB):
    await cb.answer()
    text = f"<b>📍 Адрес студии</b>\n\n{h(db.get('address_text'))}"
    if db.get("address_hint"):
        text += f"\n\n{h(db.get('address_hint'))}"
    text += "\n\nЖду тебя в гости ♡"
    rows = []
    if db.get("map_url"):
        rows.append([K.B(text="🗺 Открыть на карте", url=db.get("map_url"))])
    rows += [[K.B(text="🎀 Записаться", callback_data="book")], [K.HOME]]
    await show(cb, db, text, K.kb(*rows), photo="cover:address")


# ---------- связь с мастером ----------
def contact_text(db: DB) -> str:
    text = f"<b>💌 Связаться с мастером</b>\n\n{h(db.get('contact_text'))}"
    if db.get("contact_phone"):
        text += f"\n\n📱 {h(db.get('contact_phone'))}"
    if db.get("contact_username"):
        text += f"\n💬 @{h(db.get('contact_username').lstrip('@'))}"
    return text


@router.callback_query(F.data == "contact")
async def cb_contact(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.clear()
    rows = []
    if db.get("contact_username"):
        rows.append([K.B(text="💬 Написать в Telegram", url=f"https://t.me/{db.get('contact_username').lstrip('@')}")])
    rows.append([K.B(text="✍️ Написать прямо здесь", callback_data="contact:write")])
    rows.append([K.HOME])
    await show(cb, db, contact_text(db), K.kb(*rows), photo="cover:contact")


@router.callback_query(F.data == "contact:write")
async def cb_contact_write(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(Support.text)
    await show(cb, db, "<b>✍️ Сообщение мастеру</b>\n\nНапиши вопрос одним сообщением — можно прикрепить фото "
               "дизайна-референса. Я передам его мастеру, и она ответит тебе прямо здесь ♡",
               K.kb([K.B(text="✖️ Отмена", callback_data="contact")]), photo="cover:contact")


@router.message(Support.text)
async def on_support_text(message: Message, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    await state.clear()
    u = message.from_user
    head = (f"💌 <b>Сообщение от клиентки</b>\n{h(u.full_name)}"
            + (f" (@{h(u.username)})" if u.username else "") + f" · id <code>{u.id}</code>")
    reply_kb = K.kb([K.B(text="💬 Ответить", callback_data=f"a:msg:{u.id}"), K.B(text="👤 Клиентка", callback_data=f"a:cl:{u.id}")])
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(aid, head)
            await message.copy_to(aid, reply_markup=reply_kb)
        except Exception:  # noqa: BLE001 — уведомление не должно ронять хендлер
            pass
    await db.log(u.id, "support_message", text=(message.text or message.caption or "")[:500])
    await show(message, db, "Сообщение отправлено мастеру 💗 Ответ придёт сюда, в этот чат.",
               K.kb([K.HOME]), photo="cover:contact")
