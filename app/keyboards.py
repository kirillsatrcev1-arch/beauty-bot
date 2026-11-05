"""Клавиатуры."""
from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import (
    InlineKeyboardButton as B,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .texts import MONTHS_NOM, WD_SHORT, b_time, human_date, rub, dur


def kb(*rows: list[B]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def chunk(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


HOME = B(text="🏠 Главное меню", callback_data="home")


def back(cb: str, text: str = "⬅️ Назад") -> B:
    return B(text=text, callback_data=cb)


def main_menu(is_admin: bool = False, webapp_url: str = "") -> InlineKeyboardMarkup:
    rows = [
        [B(text="🎀 Записаться на процедуру", callback_data="book")],
        [B(text="💅 Прайс-лист", callback_data="pr"), B(text="🦢 Моё портфолио", callback_data="pf")],
        [B(text="🤍 Обо мне", callback_data="about"), B(text="📍 Адрес студии", callback_data="addr")],
        [B(text="💌 Связаться с мастером", callback_data="contact")],
        [B(text="📒 Мои записи", callback_data="my"), B(text="⭐ Отзывы", callback_data="rv:0")],
        [B(text="♡ Избранное", callback_data="fav")],
    ]
    if webapp_url:
        rows.append([B(text="✨ Открыть beauty-приложение", web_app=WebAppInfo(url=webapp_url))])
    if is_admin:
        rows.append([B(text="👑 Админ-панель", callback_data="a:home")])
    return kb(*rows)


def subscribe_kb(url: str) -> InlineKeyboardMarkup:
    rows = []
    if url:
        rows.append([B(text="🤍 Подписаться на канал", url=url)])
    rows.append([B(text="✨ Я подписалась", callback_data="sub:check")])
    rows.append([HOME])
    return kb(*rows)


BOOK_GROUPS = [("mani", "💅 Маникюр"), ("pedi", "🦶 Педикюр"), ("combo", "🎀 Комплекс"), ("extra", "✨ Доп. услуги")]


def book_categories(has_last: bool = False, has_fav: bool = False) -> InlineKeyboardMarkup:
    rows = [[B(text=t, callback_data=f"book:grp:{g}")] for g, t in BOOK_GROUPS]
    extra = []
    if has_last:
        extra.append(B(text="🔁 Как в прошлый раз", callback_data="book:last"))
    if has_fav:
        extra.append(B(text="♡ Из избранного", callback_data="fav"))
    if extra:
        rows.append(extra)
    rows.append([HOME])
    return kb(*rows)


def book_services(services: list[dict]) -> InlineKeyboardMarkup:
    rows = [[B(text=f"{s['title']} · {rub(s['price'], s['price_from'])}", callback_data=f"book:svc:{s['id']}")] for s in services]
    rows.append([back("book"), HOME])
    return kb(*rows)


def calendar_kb(year: int, month: int, days: dict[int, str], prefix: str, back_cb: str,
                can_prev: bool, can_next: bool) -> InlineKeyboardMarkup:
    """prefix: 'book' или 'a:cal' — колбэки prefix:cal:YYYY-MM и prefix:day:YYYY-MM-DD."""
    ym_prev = f"{year - (month == 1)}-{(month - 2) % 12 + 1:02d}"
    ym_next = f"{year + (month == 12)}-{month % 12 + 1:02d}"
    rows = [[
        B(text="‹" if can_prev else " ", callback_data=f"{prefix}:cal:{ym_prev}" if can_prev else "noop"),
        B(text=f"{MONTHS_NOM[month - 1]} {year}", callback_data="noop"),
        B(text="›" if can_next else " ", callback_data=f"{prefix}:cal:{ym_next}" if can_next else "noop"),
    ], [B(text=w, callback_data="noop") for w in WD_SHORT]]
    for week in calendar.Calendar().monthdayscalendar(year, month):
        row = []
        for d in week:
            if d == 0:
                row.append(B(text=" ", callback_data="noop"))
                continue
            st = days.get(d, "past")
            if st == "free":
                row.append(B(text=str(d), callback_data=f"{prefix}:day:{year}-{month:02d}-{d:02d}"))
            elif st == "busy":
                row.append(B(text="✕", callback_data="noop:busy"))
            elif st == "off":
                row.append(B(text="·", callback_data="noop:off"))
            else:
                row.append(B(text=" ", callback_data="noop"))
        rows.append(row)
    rows.append([back(back_cb), HOME])
    return kb(*rows)


def times_kb(day: date, slots: list[int], prefix: str, back_cb: str) -> InlineKeyboardMarkup:
    btns = [B(text=f"{t // 60:02d}:{t % 60:02d}", callback_data=f"{prefix}:time:{day.isoformat()}:{t // 60:02d}{t % 60:02d}") for t in slots]
    rows = chunk(btns, 4)
    rows.append([back(back_cb, "⬅️ Другая дата"), HOME])
    return kb(*rows)


def contacts_choice(name: str, phone: str) -> InlineKeyboardMarkup:
    return kb(
        [B(text=f"✅ {name}, {phone}", callback_data="book:saved")],
        [B(text="✏️ Указать другие данные", callback_data="book:newcontacts")],
        [back("book:back:time"), HOME],
    )


def phone_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True, input_field_placeholder="+7 900 123-45-67",
    )


def skip_comment() -> InlineKeyboardMarkup:
    return kb([B(text="Пропустить ➝", callback_data="book:nocomment")], [HOME])


def confirm_kb(resched: bool = False) -> InlineKeyboardMarkup:
    return kb(
        [B(text="💗 Перенести запись" if resched else "💗 Подтвердить запись", callback_data="book:confirm")],
        [B(text="⏰ Изменить время", callback_data="book:back:time"), B(text="✖️ Отмена", callback_data="book:abort")],
    )


def booking_client_kb(bid: int, show_menu: bool = True) -> InlineKeyboardMarkup:
    rows = [[B(text="🔁 Перенести", callback_data=f"my:resch:{bid}"), B(text="❌ Отменить запись", callback_data=f"my:cancel:{bid}")]]
    if show_menu:
        rows.append([HOME])
    return kb(*rows)


def reminder_kb(bid: int) -> InlineKeyboardMarkup:
    return kb(
        [B(text="✅ Буду обязательно!", callback_data=f"my:come:{bid}")],
        [B(text="🔁 Перенести", callback_data=f"my:resch:{bid}"), B(text="❌ Отменить", callback_data=f"my:cancel:{bid}")],
    )


def admin_booking_kb(b: dict) -> InlineKeyboardMarkup:
    bid = b["id"]
    rows = []
    if b["status"] == "pending":
        rows.append([B(text="✅ Подтвердить", callback_data=f"a:bk:ok:{bid}"), B(text="❌ Отменить", callback_data=f"a:bk:no:{bid}")])
    elif b["status"] == "confirmed":
        rows.append([B(text="✔️ Визит состоялся", callback_data=f"a:bk:done:{bid}"), B(text="❌ Отменить", callback_data=f"a:bk:no:{bid}")])
    if b["status"] in ("pending", "confirmed"):
        rows.append([B(text="🔁 Перенести", callback_data=f"a:bk:mv:{bid}")])
    rows.append([B(text="💬 Написать клиентке", callback_data=f"a:msg:{b['user_id']}"),
                 B(text="👤 Клиентка", callback_data=f"a:cl:{b['user_id']}")])
    return kb(*rows)


def stars_kb(bid: int) -> InlineKeyboardMarkup:
    return kb([B(text="★" * n, callback_data=f"rv:rate:{bid}:{n}") for n in (1, 2, 3)],
              [B(text="★" * n, callback_data=f"rv:rate:{bid}:{n}") for n in (4, 5)])


def my_list(bookings: list[dict]) -> InlineKeyboardMarkup:
    rows = [[B(text=f"{human_date(b['date'], False)} · {b_time(b)} · {b['service_title']}"[:60], callback_data=f"my:b:{b['id']}")] for b in bookings]
    rows.append([B(text="🗂 История визитов", callback_data="my:hist")])
    rows.append([B(text="🎀 Новая запись", callback_data="book"), HOME])
    return kb(*rows)


def service_line(s: dict) -> str:
    return f"{s['title']} · {rub(s['price'], s['price_from'])} · {dur(s['duration'])}"
