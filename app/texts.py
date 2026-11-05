"""Тексты бота и форматирование."""
from __future__ import annotations

from datetime import date, datetime
from html import escape

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

STATUS = {
    "pending": "🤍 ждёт подтверждения мастера",
    "confirmed": "💗 подтверждена",
    "done": "✨ визит состоялся",
    "cancelled": "✖️ отменена",
    "expired": "⌛ не подтверждена",
}

WELCOME = (
    "<b>Добро пожаловать в мой beauty world! 🎀</b>\n\n"
    "Здесь начинается твоя маленькая история красоты и заботы о себе.\n\n"
    "Выбирай услугу, вдохновляйся моими работами и бронируй удобное время. "
    "Я с любовью позабочусь о твоих ноготках! ♡"
)

SUBSCRIBE = (
    "<b>Маленькая просьба перед записью! ♡</b>\n\n"
    "Подпишись на мой Telegram-канал, чтобы не пропускать свободные окошки, красивые работы, "
    "новости и специальные предложения.\n\n"
    "После подписки ты сможешь перейти к записи 💗"
)
SUB_NOT_YET = "Кажется, подписки пока нет 🥺 Подпишись на канал и нажми «Я подписалась» ещё раз ♡"
SUB_OK = "Спасибо за подписку! 💗 Теперь можно записываться"

BOOK_CATEGORY = "<b>🎀 Запись на процедуру</b>\n\nШаг 1 из 5 · Выбери категорию услуг ♡"
CAL_LEGEND = "<i>12</i> — есть окошки   ✕ — всё занято   · — выходной"

ASK_NAME = "<b>Шаг 4 из 5 · Как тебя зовут?</b> ♡\n\nНапиши своё имя одним сообщением."
ASK_PHONE = (
    "<b>Номер телефона</b> 📱\n\nНажми кнопку «Отправить номер» внизу или напиши номер в формате "
    "<code>+7 900 123-45-67</code>."
)
ASK_COMMENT = (
    "<b>Комментарий для мастера</b> 💌\n\nЕсть пожелания по дизайну, длине или форме? "
    "Напиши их сюда или нажми «Пропустить»."
)
BAD_PHONE = "Не получилось распознать номер 🥺 Напиши его, пожалуйста, в формате +7 900 123-45-67"
SLOT_TAKEN = "Ой! Это время только что заняли 🥺 Выбери, пожалуйста, другое окошко ♡"


def rub(n: int, price_from: int | bool = 0) -> str:
    s = f"{n:,}".replace(",", " ") + " ₽"
    return ("от " + s) if price_from else s


def dur(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h} ч {m} мин"
    return f"{h} ч" if h else f"{m} мин"


def human_date(d: date | str, weekday: bool = True) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    s = f"{d.day} {MONTHS[d.month - 1]}"
    return f"{s}, {WEEKDAYS[d.weekday()]}" if weekday else s


def b_time(b: dict) -> str:
    return b["start"][11:16]


def b_dt(b: dict) -> datetime:
    return datetime.strptime(b["start"], "%Y-%m-%d %H:%M")


def h(s: str | None) -> str:
    return escape(s or "")


def service_card(s: dict, fav: bool = False) -> str:
    out = f"<b>{h(s['title'])}</b>{'  ♡' if fav else ''}\n\n"
    if s.get("description"):
        out += f"{h(s['description'])}\n\n"
    out += f"💗 <b>{rub(s['price'], s['price_from'])}</b>\n⏳ {dur(s['duration'])}"
    return out


def booking_details(b: dict, address: str) -> str:
    return (
        f"🎀 <b>Услуга:</b> {h(b['service_title'])}\n"
        f"📅 <b>Дата:</b> {human_date(b['date'])}\n"
        f"⏰ <b>Время:</b> {b_time(b)}\n"
        f"💗 <b>Стоимость:</b> {rub(b['price'], b.get('price_from'))}\n"
        f"📍 <b>Адрес:</b> {h(address)}"
    )


def booking_created(b: dict, address: str) -> str:
    status = "" if b["status"] == "confirmed" else "\n\n<i>Статус: ждёт подтверждения мастера 🤍 Я пришлю уведомление, как только мастер подтвердит.</i>"
    return (
        "<b>Твоя запись успешно создана! ♡</b>\n\n"
        f"{booking_details(b, address)}\n\n"
        f"Буду с нетерпением ждать нашей встречи!{status}"
    )


def booking_short(b: dict) -> str:
    return f"{human_date(b['date'], weekday=False)} · {b_time(b)} — {h(b['service_title'])}"


def booking_admin(b: dict, user: dict | None = None) -> str:
    uname = f" (@{h(user['username'])})" if user and user.get("username") else ""
    lines = [
        f"<b>Запись №{b['id']}</b> · {STATUS.get(b['status'], b['status'])}",
        "",
        f"🎀 {h(b['service_title'])} · {rub(b['price'], b.get('price_from'))} · {dur(b['duration'])}",
        f"📅 {human_date(b['date'])}, {b_time(b)}–{b['end'][11:16]}",
        f"👤 {h(b['name'])}{uname}",
        f"📱 {h(b['phone'])}",
    ]
    if b.get("comment"):
        lines.append(f"💬 {h(b['comment'])}")
    if b.get("client_confirmed"):
        lines.append("✅ Клиентка подтвердила, что придёт")
    if b.get("cancel_reason"):
        lines.append(f"<i>Причина отмены: {h(b['cancel_reason'])}</i>")
    return "\n".join(lines)
