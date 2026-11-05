"""Админ-панель мастера (доступна только ADMIN_IDS)."""
from __future__ import annotations

import asyncio
import calendar
import io
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import keyboards as K
from .. import logic
from ..config import Config
from ..db import DB, PORTFOLIO_SECTIONS, now_str
from ..scheduling import SlotTaken, day_windows, fmt_hm, free_slots, local_now, month_map, parse_range
from ..subscription import channel_url
from ..texts import (
    MONTHS_NOM, STATUS, WD_SHORT, b_time, booking_admin, dur, h, human_date, rub,
)
from ..ui import show
from .common import AdminInput, IsAdmin

log = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

B = K.B
ADMIN_HOME = B(text="⬅️ Админка", callback_data="a:home")

COVER_NAMES = {
    "welcome": "Приветствие", "booking": "Запись", "subscribe": "Подписка", "prices": "Прайс-лист",
    "portfolio": "Портфолио", "about": "Обо мне", "address": "Адрес", "contact": "Связь",
    "calendar": "Календарь", "time": "Выбор времени", "contacts": "Контакты", "confirm": "Подтверждение",
    "success": "Запись создана", "my": "Мои записи", "reviews": "Отзывы", "favorites": "Избранное",
}
TEXT_FIELDS = {
    "master_name": "Имя мастера", "about_text": "Текст «Обо мне»", "address_text": "Адрес",
    "address_hint": "Как пройти", "map_url": "Ссылка на карту (Яндекс/Google)", "contact_text": "Текст «Связаться»",
    "contact_username": "Telegram мастера (@username)", "contact_phone": "Телефон мастера",
    "channel_id": "ID канала (@username или -100…)", "channel_url": "Ссылка-приглашение на канал",
    "studio_name": "Название студии",
}
INT_FIELDS = {
    "slot_step": ("Шаг сетки, мин", 5, 240), "horizon_days": ("На сколько дней вперёд можно записаться", 1, 365),
    "min_lead_min": ("Минимум минут до записи", 0, 7 * 24 * 60), "cancel_min_hours": ("Отмена/перенос не позже, ч", 0, 168),
    "review_delay_hours": ("Через сколько часов после визита просить отзыв", 1, 72),
}
SECTIONS = {k: (t, e) for k, t, e in PORTFOLIO_SECTIONS}


def now(cfg: Config) -> datetime:
    return local_now(cfg.tz)


# ======================= Главная админки =======================
async def admin_home(event, db: DB, cfg: Config, state: FSMContext | None = None):
    if state:
        await state.clear()
    n = now(cfg)
    today = n.date().isoformat()
    pending = await db.scalar("SELECT COUNT(*) FROM bookings WHERE status='pending'")
    today_cnt = await db.scalar("SELECT COUNT(*) FROM bookings WHERE date=? AND status IN ('pending','confirmed','done')", (today,))
    nxt = await db.fetchone("SELECT * FROM bookings WHERE status IN ('pending','confirmed') AND start>=? ORDER BY start LIMIT 1",
                            (n.strftime("%Y-%m-%d %H:%M"),))
    new_rv = await db.scalar("SELECT COUNT(*) FROM reviews WHERE status='new'")
    text = (f"<b>👑 Админ-панель</b>\n\n📅 Сегодня записей: <b>{today_cnt}</b>\n🤍 Ждут подтверждения: <b>{pending}</b>")
    if nxt:
        text += f"\n⏰ Следующая: {human_date(nxt['date'], False)} в {b_time(nxt)} — {h(nxt['name'])}, {h(nxt['service_title'])}"
    markup = K.kb(
        [B(text=f"📋 Записи{f' · {pending} новых' if pending else ''}", callback_data="a:bks")],
        [B(text="🗓 График и окошки", callback_data="a:sch"), B(text="💅 Услуги и цены", callback_data="a:svc")],
        [B(text="🦢 Портфолио", callback_data="a:pf"), B(text="🖼 Тексты и фото", callback_data="a:txt")],
        [B(text="👥 Клиентки", callback_data="a:cls:0"), B(text="📣 Рассылка", callback_data="a:bc")],
        [B(text="📊 Статистика", callback_data="a:st"), B(text=f"⭐ Отзывы{f' · {new_rv}' if new_rv else ''}", callback_data="a:rvs")],
        [B(text="⚙️ Настройки и канал", callback_data="a:set")],
        [K.HOME],
    )
    await show(event, db, text, markup)


@router.message(Command("admin"))
async def cmd_admin(message: Message, db: DB, cfg: Config, state: FSMContext):
    await admin_home(message, db, cfg, state)


@router.callback_query(F.data == "a:home")
async def cb_admin(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await admin_home(cb, db, cfg, state)


# ======================= Записи =======================
@router.callback_query(F.data == "a:bks")
async def cb_bookings(cb: CallbackQuery, db: DB, cfg: Config):
    await cb.answer()
    n = now(cfg)
    pending = await db.scalar("SELECT COUNT(*) FROM bookings WHERE status='pending'")
    await show(cb, db, "<b>📋 Записи</b>\n\nВыбери, что показать:", K.kb(
        [B(text=f"🤍 Ждут подтверждения · {pending}", callback_data="a:bl:pending")],
        [B(text="Сегодня", callback_data="a:bl:today"), B(text="Завтра", callback_data="a:bl:tomorrow")],
        [B(text="Ближайшие 7 дней", callback_data="a:bl:week"), B(text="Все будущие", callback_data="a:bl:future")],
        [B(text="📅 Выбрать дату", callback_data=f"a:dc:view:{n.year}-{n.month:02d}")],
        [B(text="🗂 Прошедшие (30 дн.)", callback_data="a:bl:past")],
        [ADMIN_HOME],
    ))


async def _list(cb: CallbackQuery, db: DB, title: str, rows: list[dict], back: str = "a:bks"):
    if not rows:
        text = f"<b>{title}</b>\n\nЗаписей нет ♡"
    else:
        lines = [f"<b>{title}</b> · {len(rows)}\n"]
        cur = None
        for b in rows[:40]:
            if b["date"] != cur:
                cur = b["date"]
                lines.append(f"\n<b>{human_date(b['date'])}</b>")
            mark = {"pending": "🤍", "confirmed": "💗", "done": "✨", "cancelled": "✖️", "expired": "⌛"}.get(b["status"], "")
            lines.append(f"{mark} {b_time(b)}–{b['end'][11:16]} · {h(b['name'])} · {h(b['service_title'])}")
        text = "\n".join(lines)
    buttons = [[B(text=f"{b['date'][8:]}.{b['date'][5:7]} {b_time(b)} · {b['name']} · {b['service_title']}"[:60],
                  callback_data=f"a:b:{b['id']}")] for b in rows[:25]]
    buttons.append([K.back(back), ADMIN_HOME])
    await show(cb, db, text[:4000], K.kb(*buttons))


@router.callback_query(F.data.startswith("a:bl:"))
async def cb_blist(cb: CallbackQuery, db: DB, cfg: Config):
    await cb.answer()
    kind = cb.data.split(":")[2]
    n = now(cfg)
    t = n.date()
    act = "status IN ('pending','confirmed')"
    q = {
        "pending": ("🤍 Ждут подтверждения", f"SELECT * FROM bookings WHERE status='pending' ORDER BY start", ()),
        "today": ("Сегодня", f"SELECT * FROM bookings WHERE date=? AND status!='cancelled' ORDER BY start", (t.isoformat(),)),
        "tomorrow": ("Завтра", f"SELECT * FROM bookings WHERE date=? AND {act} ORDER BY start", ((t + timedelta(days=1)).isoformat(),)),
        "week": ("Ближайшие 7 дней", f"SELECT * FROM bookings WHERE date BETWEEN ? AND ? AND {act} ORDER BY start",
                 (t.isoformat(), (t + timedelta(days=7)).isoformat())),
        "future": ("Все будущие", f"SELECT * FROM bookings WHERE date>=? AND {act} ORDER BY start", (t.isoformat(),)),
        "past": ("Прошедшие 30 дней", "SELECT * FROM bookings WHERE date BETWEEN ? AND ? AND status!='pending' ORDER BY start DESC",
                 ((t - timedelta(days=30)).isoformat(), (t - timedelta(days=1)).isoformat())),
    }[kind]
    await _list(cb, db, q[0], await db.fetchall(q[1], q[2]))


async def booking_card(event, db: DB, bid: int, note: str = ""):
    b = await db.booking(bid)
    if not b:
        await show(event, db, "Запись не найдена", K.kb([ADMIN_HOME]))
        return
    user = await db.user(b["user_id"])
    text = (note + "\n\n" if note else "") + booking_admin(b, user)
    markup = K.admin_booking_kb(b)
    markup.inline_keyboard.append([K.back("a:bks", "⬅️ К записям"), ADMIN_HOME])
    await show(event, db, text, markup)


@router.callback_query(F.data.startswith("a:b:"))
async def cb_booking(cb: CallbackQuery, db: DB):
    await cb.answer()
    await booking_card(cb, db, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("a:bk:"))
async def cb_booking_action(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    _, _, action, bid_s = cb.data.split(":")
    bid = int(bid_s)
    b = await db.booking(bid)
    if not b:
        await cb.answer("Запись не найдена", show_alert=True)
        return
    if action == "ok":
        if b["status"] != "pending":
            await cb.answer("Запись уже обработана")
        else:
            await logic.confirm(bot, db, cfg, bid, cb.from_user.id)
            await cb.answer("Подтверждено ✅ Клиентка получила уведомление")
        await booking_card(cb, db, bid)
    elif action == "no":
        await cb.answer()
        await show(cb, db, f"<b>Отменить запись №{bid}?</b>\n\n{booking_admin(b)}\n\nКлиентка получит уведомление.",
                   K.kb([B(text="❌ Да, отменить", callback_data=f"a:bk:noyes:{bid}")],
                        [B(text="✍️ Отменить с причиной", callback_data=f"a:bk:noreason:{bid}")],
                        [K.back(f"a:b:{bid}")]))
    elif action == "noyes":
        await logic.cancel(bot, db, cfg, bid, by="admin", actor_id=cb.from_user.id)
        await cb.answer("Запись отменена")
        await booking_card(cb, db, bid)
    elif action == "noreason":
        await cb.answer()
        await state.set_state(AdminInput.value)
        await state.update_data(field=f"cancel:{bid}")
        await show(cb, db, "Напиши причину отмены — она придёт клиентке:", K.kb([K.back(f"a:b:{bid}", "✖️ Отмена")]))
    elif action == "done":
        await logic.mark_done(db, bid, cb.from_user.id)
        await cb.answer("Отмечено: визит состоялся ✨")
        await booking_card(cb, db, bid)
    elif action == "mv":
        await cb.answer()
        await state.update_data(a_mv=bid)
        n = now(cfg)
        await admin_move_calendar(cb, db, cfg, state, f"{n.year}-{n.month:02d}")


# ---------- перенос записи мастером ----------
async def admin_move_calendar(event, db: DB, cfg: Config, state: FSMContext, ym: str):
    bid = (await state.get_data()).get("a_mv")
    b = await db.booking(bid) if bid else None
    if not b:
        await show(event, db, "Запись не найдена", K.kb([ADMIN_HOME]))
        return
    y, m = map(int, ym.split("-"))
    n = now(cfg)
    days = await month_map(db, y, m, b["duration"], n, exclude_id=bid, ignore_lead=True)
    text = (f"<b>🔁 Перенос записи №{bid}</b>\n{h(b['name'])} · {h(b['service_title'])} · {dur(b['duration'])}\n"
            f"Сейчас: {human_date(b['date'])}, {b_time(b)}\n\nВыбери новую дату:")
    await show(event, db, text, K.calendar_kb(y, m, days, "a:mv", f"a:b:{bid}", (y, m) > (n.year, n.month), True))


@router.callback_query(F.data.startswith("a:mv:cal:"))
async def cb_mv_cal(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await admin_move_calendar(cb, db, cfg, state, cb.data.split(":")[3])


@router.callback_query(F.data.startswith("a:mv:day:"))
async def cb_mv_day(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    bid = (await state.get_data()).get("a_mv")
    b = await db.booking(bid)
    d = date.fromisoformat(cb.data.split(":")[3])
    slots = await free_slots(db, d, b["duration"], now(cfg), exclude_id=bid, ignore_lead=True)
    await show(cb, db, f"<b>🔁 Перенос №{bid}</b> · {human_date(d)}\n\nВыбери время:",
               K.times_kb(d, slots, "a:mv", f"a:mv:cal:{d.year}-{d.month:02d}"))


@router.callback_query(F.data.startswith("a:mv:time:"))
async def cb_mv_time(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    parts = cb.data.split(":")
    d, hhmm = parts[3], parts[4]
    bid = (await state.get_data()).get("a_mv")
    start = datetime.strptime(f"{d} {hhmm}", "%Y-%m-%d %H%M")
    try:
        await logic.reschedule(bot, db, cfg, bid, start, by="admin", actor_id=cb.from_user.id)
    except SlotTaken:
        await cb.answer("Это время уже занято", show_alert=True)
        return
    await cb.answer("Перенесено ✅ Клиентка получила уведомление")
    await state.update_data(a_mv=None)
    await booking_card(cb, db, bid, note="✅ Запись перенесена")


# ======================= График =======================
def _wd_names(s: str) -> str:
    days = sorted(int(x) for x in s.split(",") if x.strip().isdigit())
    return ", ".join(WD_SHORT[d] for d in days) or "нет"


@router.callback_query(F.data == "a:sch")
async def cb_schedule(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    t = now(cfg).date().isoformat()
    ovs = await db.fetchall("SELECT * FROM day_overrides WHERE date>=? ORDER BY date LIMIT 15", (t,))
    wins = await db.fetchall("SELECT * FROM extra_windows WHERE date>=? ORDER BY date, start LIMIT 15", (t,))
    text = (
        "<b>🗓 График работы</b>\n\n"
        f"⏰ Часы: <b>{db.get('work_start')}–{db.get('work_end')}</b>\n"
        f"📆 Рабочие дни: <b>{_wd_names(db.get('work_days'))}</b>\n"
        f"⏱ Шаг сетки: <b>{db.get('slot_step')} мин</b>\n"
        f"📏 Запись открыта на <b>{db.get('horizon_days')} дн.</b> вперёд\n"
        f"⏳ Минимум до записи: <b>{db.get('min_lead_min')} мин</b>\n"
        f"❌ Отмена/перенос клиенткой не позже чем за <b>{db.get('cancel_min_hours')} ч</b>"
    )
    if ovs:
        text += "\n\n<b>Особые дни:</b>\n" + "\n".join(
            f"• {human_date(o['date'], False)} — {'выходной 🚫' if o['closed'] else o['start'] + '–' + o['end']}" for o in ovs)
    if wins:
        text += "\n\n<b>Доп. окошки:</b>\n" + "\n".join(f"• {human_date(w['date'], False)} {w['start']}–{w['end']}" for w in wins)
    n = now(cfg)
    ym = f"{n.year}-{n.month:02d}"
    await show(cb, db, text, K.kb(
        [B(text="⏰ Рабочие часы", callback_data="a:ed:hours"), B(text="📆 Рабочие дни", callback_data="a:wd")],
        [B(text="🚫 Закрыть/открыть дату", callback_data=f"a:dc:close:{ym}")],
        [B(text="🕐 Особые часы на дату", callback_data=f"a:dc:hours:{ym}")],
        [B(text="➕ Добавить окошко", callback_data=f"a:dc:win:{ym}"), B(text="🗑 Удалить окошко", callback_data="a:wins")],
        [B(text="⏱ Шаг сетки", callback_data="a:ed:int:slot_step"), B(text="📏 Горизонт", callback_data="a:ed:int:horizon_days")],
        [B(text="⏳ Мин. до записи", callback_data="a:ed:int:min_lead_min"), B(text="❌ Срок отмены", callback_data="a:ed:int:cancel_min_hours")],
        [ADMIN_HOME],
    ))


@router.callback_query(F.data.regexp(r"^a:wd(:\d)?$"))
async def cb_workdays(cb: CallbackQuery, db: DB):
    days = {int(x) for x in db.get("work_days").split(",") if x.strip().isdigit()}
    if cb.data.startswith("a:wd:"):
        d = int(cb.data.split(":")[2])
        days ^= {d}
        await db.set("work_days", ",".join(str(x) for x in sorted(days)))
        await db.log(cb.from_user.id, "admin_work_days", days=sorted(days))
    await cb.answer()
    row = [B(text=("✅ " if i in days else "▫️ ") + WD_SHORT[i], callback_data=f"a:wd:{i}") for i in range(7)]
    await show(cb, db, "<b>📆 Рабочие дни</b>\n\nНажми на день, чтобы включить или выключить его:",
               K.kb(row[:4], row[4:], [K.back("a:sch", "⬅️ График")]))


async def admin_day_calendar(event, db: DB, cfg: Config, mode: str, ym: str):
    y, m = map(int, ym.split("-"))
    n = now(cfg)
    titles = {"close": "🚫 Закрыть или открыть дату", "hours": "🕐 Особые часы на дату",
              "win": "➕ Добавить окошко", "view": "📅 Записи на дату"}
    first, last = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    ovs = {o["date"]: o for o in await db.fetchall("SELECT * FROM day_overrides WHERE date BETWEEN ? AND ?",
                                                    (first.isoformat(), last.isoformat()))}
    cnt = {r["date"]: r["n"] for r in await db.fetchall(
        "SELECT date, COUNT(*) AS n FROM bookings WHERE date BETWEEN ? AND ? AND status IN ('pending','confirmed','done') GROUP BY date",
        (first.isoformat(), last.isoformat()))}
    ym_prev = f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"
    ym_next = f"{y + (m == 12)}-{m % 12 + 1:02d}"
    rows = [[B(text="‹", callback_data=f"a:dc:{mode}:{ym_prev}"), B(text=f"{MONTHS_NOM[m - 1]} {y}", callback_data="noop"),
             B(text="›", callback_data=f"a:dc:{mode}:{ym_next}")],
            [B(text=w, callback_data="noop") for w in WD_SHORT]]
    for week in calendar.Calendar().monthdayscalendar(y, m):
        row = []
        for d in week:
            if not d:
                row.append(B(text=" ", callback_data="noop"))
                continue
            ds = f"{y}-{m:02d}-{d:02d}"
            if mode != "view" and date.fromisoformat(ds) < n.date():
                row.append(B(text=" ", callback_data="noop"))
                continue
            label = str(d)
            o = ovs.get(ds)
            if o and o["closed"]:
                label = f"✕{d}"
            elif o:
                label = f"{d}*"
            elif not await day_windows(db, date.fromisoformat(ds)):
                label = f"·{d}"
            if mode == "view" and cnt.get(ds):
                label = f"{d}•{cnt[ds]}"
            row.append(B(text=label, callback_data=f"a:dd:{mode}:{ds}"))
        rows.append(row)
    back = "a:bks" if mode == "view" else "a:sch"
    rows.append([K.back(back), ADMIN_HOME])
    legend = "✕ — закрыт · ·N — выходной по графику · N* — особые часы" + (" · N•k — записей" if mode == "view" else "")
    await show(event, db, f"<b>{titles[mode]}</b>\n\n{legend}", K.kb(*rows))


@router.callback_query(F.data.startswith("a:dc:"))
async def cb_day_cal(cb: CallbackQuery, db: DB, cfg: Config):
    await cb.answer()
    _, _, mode, ym = cb.data.split(":")
    await admin_day_calendar(cb, db, cfg, mode, ym)


@router.callback_query(F.data.startswith("a:dd:"))
async def cb_day_pick(cb: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    _, _, mode, ds = cb.data.split(":")
    d = date.fromisoformat(ds)
    ym = f"{d.year}-{d.month:02d}"
    if mode == "view":
        await cb.answer()
        rows = await db.fetchall("SELECT * FROM bookings WHERE date=? AND status!='cancelled' ORDER BY start", (ds,))
        await _list(cb, db, human_date(d), rows, back=f"a:dc:view:{ym}")
        return
    if mode == "close":
        o = await db.fetchone("SELECT * FROM day_overrides WHERE date=?", (ds,))
        if o and o["closed"]:
            await db.execute("DELETE FROM day_overrides WHERE date=?", (ds,))
            await cb.answer(f"{human_date(d, False)} снова рабочий ✅", show_alert=True)
        else:
            active = await db.scalar("SELECT COUNT(*) FROM bookings WHERE date=? AND status IN ('pending','confirmed')", (ds,))
            await db.execute("INSERT INTO day_overrides(date, closed) VALUES(?,1) ON CONFLICT(date) DO UPDATE SET closed=1, start=NULL, end=NULL", (ds,))
            await cb.answer(f"{human_date(d, False)} закрыт для записи 🚫"
                            + (f"\n\nВнимание: на этот день уже есть записи ({active}) — они не отменены автоматически." if active else ""),
                            show_alert=True)
        await db.log(cb.from_user.id, "admin_toggle_day", date=ds)
        await admin_day_calendar(cb, db, cfg, "close", ym)
        return
    await cb.answer()
    await state.set_state(AdminInput.value)
    await state.update_data(field=f"{'dayhours' if mode == 'hours' else 'win'}:{ds}")
    wins = await day_windows(db, d)
    cur = ", ".join(f"{fmt_hm(s)}–{fmt_hm(e)}" for s, e in wins) or "выходной"
    hint = ("Напиши часы работы на этот день, например <code>12:00-18:00</code>.\nЧтобы вернуть обычный график — отправь <code>-</code>"
            if mode == "hours" else "Напиши время окошка, например <code>19:00-21:30</code>. Оно добавится к рабочим часам.")
    await show(cb, db, f"<b>{human_date(d)}</b>\nСейчас: {cur}\n\n{hint}", K.kb([K.back(f"a:dc:{mode}:{ym}", "✖️ Отмена")]))


@router.callback_query(F.data == "a:wins")
async def cb_windows(cb: CallbackQuery, db: DB, cfg: Config):
    await cb.answer()
    wins = await db.fetchall("SELECT * FROM extra_windows WHERE date>=? ORDER BY date, start", (now(cfg).date().isoformat(),))
    rows = [[B(text=f"🗑 {human_date(w['date'], False)} {w['start']}–{w['end']}", callback_data=f"a:wdel:{w['id']}")] for w in wins[:30]]
    rows.append([K.back("a:sch", "⬅️ График")])
    await show(cb, db, "<b>🗑 Доп. окошки</b>\n\n" + ("Нажми, чтобы удалить:" if wins else "Доп. окошек нет."), K.kb(*rows))


@router.callback_query(F.data.startswith("a:wdel:"))
async def cb_window_del(cb: CallbackQuery, db: DB, cfg: Config):
    await db.execute("DELETE FROM extra_windows WHERE id=?", (int(cb.data.split(":")[2]),))
    await db.log(cb.from_user.id, "admin_window_delete", id=cb.data.split(":")[2])
    await cb_windows(cb, db, cfg)


# ======================= Универсальное редактирование =======================
@router.callback_query(F.data.startswith("a:ed:"))
async def cb_edit(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    parts = cb.data.split(":")
    kind = parts[2]
    back = "a:txt"
    if kind == "hours":
        field, prompt, back = "hours", f"Сейчас: {db.get('work_start')}–{db.get('work_end')}\n\nНапиши новые часы, например <code>10:00-20:00</code>", "a:sch"
    elif kind == "int":
        key = parts[3]
        title, lo, hi = INT_FIELDS[key]
        field, prompt = f"int:{key}", f"<b>{title}</b>\nСейчас: {db.get(key)}\n\nНапиши число от {lo} до {hi}:"
        back = "a:sch" if key in ("slot_step", "horizon_days", "min_lead_min", "cancel_min_hours") else "a:set"
    elif kind == "set":
        key = parts[3]
        cur = db.get(key)
        field = f"set:{key}"
        prompt = (f"<b>{TEXT_FIELDS.get(key, key)}</b>\n\nСейчас:\n{cur if key == 'about_text' else h(cur) or '—'}\n\n"
                  "Отправь новое значение одним сообщением (можно с форматированием). Чтобы очистить — отправь <code>-</code>")
        back = "a:ch" if key.startswith("channel") else "a:txt"
    elif kind == "photo":
        key = parts[3]
        field, prompt, back = f"photo:{key}", f"Отправь фото для раздела «{COVER_NAMES.get(key, key)}».\nЧтобы вернуть стандартную обложку — отправь <code>-</code>", "a:covers"
    elif kind == "catphoto":
        field, prompt, back = f"catphoto:{parts[3]}", "Отправь фото-обложку категории. Чтобы вернуть стандартную — <code>-</code>", f"a:svcc:{parts[3]}"
    elif kind == "svc":
        sid, f = int(parts[3]), parts[4]
        labels = {"title": "новое название", "description": "новое описание", "price": "новую цену в рублях (число)",
                  "duration": "длительность в минутах (число)", "photo": "фото для карточки услуги (или <code>-</code>, чтобы убрать)"}
        field, prompt, back = f"svc:{sid}:{f}", f"Отправь {labels[f]}:", f"a:sv:{sid}"
    else:
        return
    await state.set_state(AdminInput.value)
    await state.update_data(field=field)
    await show(cb, db, prompt, K.kb([K.back(back, "✖️ Отмена")]))


async def _photo_id(message: Message, bot: Bot) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        buf = io.BytesIO()
        await bot.download(message.document.file_id, destination=buf)
        tmp = await bot.send_photo(message.chat.id, BufferedInputFile(buf.getvalue(), "photo.jpg"), disable_notification=True)
        fid = tmp.photo[-1].file_id
        await tmp.delete()
        return fid
    return None


@router.message(AdminInput.value)
async def on_admin_value(message: Message, db: DB, cfg: Config, state: FSMContext, bot: Bot):
    field = (await state.get_data()).get("field", "")
    raw = (message.text or message.caption or "").strip()
    uid = message.from_user.id
    reset = raw == "-"

    async def done(text: str, back_cb: str, back_text: str = "⬅️ Назад"):
        await state.set_state(None)
        await db.log(uid, "admin_edit", field=field)
        await show(message, db, text, K.kb([K.back(back_cb, back_text), ADMIN_HOME]))

    if field == "hours":
        r = parse_range(raw)
        if not r:
            await message.answer("Не поняла формат 🙈 Пример: 10:00-20:00")
            return
        await db.set("work_start", r[0])
        await db.set("work_end", r[1])
        await done(f"✅ Рабочие часы: {r[0]}–{r[1]}", "a:sch", "⬅️ График")
    elif field.startswith("int:"):
        key = field[4:]
        title, lo, hi = INT_FIELDS[key]
        if not raw.isdigit() or not lo <= int(raw) <= hi:
            await message.answer(f"Нужно число от {lo} до {hi}")
            return
        await db.set(key, raw)
        await done(f"✅ {title}: {raw}", "a:sch" if key in ("slot_step", "horizon_days", "min_lead_min", "cancel_min_hours") else "a:set")
    elif field.startswith("set:"):
        key = field[4:]
        if key == "about_text":
            value = "" if reset else (message.html_text if message.text else raw)
        else:
            value = "" if reset else raw
        if key == "contact_username":
            value = value.lstrip("@").replace("https://t.me/", "")
        if key == "channel_id" and value:
            value = value.replace("https://t.me/", "@") if value.startswith("https://t.me/") and "+" not in value else value
        await db.set(key, value)
        extra = ""
        if key == "channel_id" and value:
            extra = "\n\n" + await channel_status(bot, db)
        await done(f"✅ Сохранено: {TEXT_FIELDS.get(key, key)}{extra}", "a:ch" if key.startswith("channel") else "a:txt")
    elif field.startswith("photo:") or field.startswith("catphoto:"):
        key = field.split(":", 1)[1]
        fid = None if reset else await _photo_id(message, bot)
        if not reset and not fid:
            await message.answer("Пришли, пожалуйста, фото 📷 (или «-» для стандартной обложки)")
            return
        if field.startswith("photo:"):
            await db.set(f"photo_{key}", fid or "")
            await done("✅ Фото обновлено", "a:covers", "⬅️ Обложки")
        else:
            await db.execute("UPDATE categories SET photo=? WHERE id=?", (fid, key))
            await done("✅ Обложка категории обновлена", f"a:svcc:{key}", "⬅️ Категория")
    elif field.startswith("svc:"):
        _, sid_s, f = field.split(":")
        sid = int(sid_s)
        if f in ("price", "duration"):
            num = raw.replace(" ", "").replace("₽", "")
            if not num.isdigit() or int(num) <= 0 or (f == "duration" and int(num) > 600):
                await message.answer("Нужно положительное число")
                return
            await db.execute(f"UPDATE services SET {f}=? WHERE id=?", (int(num), sid))
        elif f == "photo":
            fid = None if reset else await _photo_id(message, bot)
            if not reset and not fid:
                await message.answer("Пришли фото 📷")
                return
            await db.execute("UPDATE services SET photo=? WHERE id=?", (fid, sid))
        elif f in ("title", "description"):
            if not raw or (f == "title" and reset):
                await message.answer("Отправь текст")
                return
            await db.execute(f"UPDATE services SET {f}=? WHERE id=?", ("" if reset else raw[:600], sid))
        await state.set_state(None)
        await db.log(uid, "admin_service_edit", id=sid, field=f)
        await service_card_admin(message, db, sid, note="✅ Сохранено")
    elif field.startswith("svcnew:"):
        await new_service_step(message, db, state, raw)
    elif field.startswith("dayhours:"):
        ds = field.split(":", 1)[1]
        if reset:
            await db.execute("DELETE FROM day_overrides WHERE date=?", (ds,))
            await done(f"✅ {human_date(ds)} — обычный график", "a:sch", "⬅️ График")
            return
        r = parse_range(raw)
        if not r:
            await message.answer("Пример: 12:00-18:00")
            return
        await db.execute("INSERT INTO day_overrides(date, closed, start, end) VALUES(?,0,?,?) "
                         "ON CONFLICT(date) DO UPDATE SET closed=0, start=excluded.start, end=excluded.end", (ds, r[0], r[1]))
        await done(f"✅ {human_date(ds)}: {r[0]}–{r[1]}", "a:sch", "⬅️ График")
    elif field.startswith("win:"):
        ds = field.split(":", 1)[1]
        r = parse_range(raw)
        if not r:
            await message.answer("Пример: 19:00-21:00")
            return
        await db.execute("INSERT INTO extra_windows(date, start, end) VALUES(?,?,?)", (ds, r[0], r[1]))
        await done(f"✅ Окошко добавлено: {human_date(ds)}, {r[0]}–{r[1]}", "a:sch", "⬅️ График")
    elif field.startswith("cancel:"):
        bid = int(field.split(":")[1])
        await state.set_state(None)
        await logic.cancel(bot, db, cfg, bid, by="admin", actor_id=uid, reason=raw[:300] or None)
        await booking_card(message, db, bid, note="❌ Запись отменена, клиентка уведомлена")
    else:
        await state.clear()


# ======================= Услуги =======================
@router.callback_query(F.data == "a:svc")
async def cb_services(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    cats = await db.categories()
    services = await db.services(include_hidden=True)
    rows = [[B(text=f"{c['emoji']} {c['title']} · {sum(1 for s in services if s['category'] == c['id'])}",
               callback_data=f"a:svcc:{c['id']}")] for c in cats]
    rows.append([ADMIN_HOME])
    await show(cb, db, "<b>💅 Услуги и цены</b>\n\nВыбери категорию:", K.kb(*rows))


@router.callback_query(F.data.startswith("a:svcc:"))
async def cb_service_cat(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    cid = cb.data.split(":")[2]
    c = await db.category(cid)
    services = await db.services(category=cid, include_hidden=True)
    text = f"<b>{c['emoji']} {h(c['title'])}</b>\n\n" + ("\n".join(
        f"{'🙈 ' if not s['active'] else ''}{h(s['title'])} — {rub(s['price'], s['price_from'])}, {dur(s['duration'])}" for s in services)
        or "Услуг пока нет")
    rows = [[B(text=("🙈 " if not s["active"] else "") + s["title"], callback_data=f"a:sv:{s['id']}")] for s in services]
    rows.append([B(text="➕ Добавить услугу", callback_data=f"a:svnew:{cid}")])
    rows.append([B(text="🖼 Обложка категории", callback_data=f"a:ed:catphoto:{cid}")])
    rows.append([K.back("a:svc"), ADMIN_HOME])
    await show(cb, db, text, K.kb(*rows))


async def service_card_admin(event, db: DB, sid: int, note: str = ""):
    s = await db.service(sid)
    if not s:
        await show(event, db, "Услуга удалена", K.kb([K.back("a:svc"), ADMIN_HOME]))
        return
    text = ((note + "\n\n") if note else "") + (
        f"<b>{h(s['title'])}</b>{' · 🙈 скрыта' if not s['active'] else ''}\n\n{h(s['description']) or '<i>без описания</i>'}\n\n"
        f"💗 {rub(s['price'], s['price_from'])}\n⏳ {dur(s['duration'])}\n🖼 Фото: {'есть' if s['photo'] else 'стандартная обложка'}")
    await show(event, db, text, K.kb(
        [B(text="✏️ Название", callback_data=f"a:ed:svc:{sid}:title"), B(text="📝 Описание", callback_data=f"a:ed:svc:{sid}:description")],
        [B(text="💗 Цена", callback_data=f"a:ed:svc:{sid}:price"), B(text="⏳ Длительность", callback_data=f"a:ed:svc:{sid}:duration")],
        [B(text="🖼 Фото", callback_data=f"a:ed:svc:{sid}:photo"),
         B(text=("☑️ «от» в цене" if s["price_from"] else "▫️ «от» в цене"), callback_data=f"a:svf:{sid}")],
        [B(text="👁 Показать" if not s["active"] else "🙈 Скрыть", callback_data=f"a:svh:{sid}"),
         B(text="🗑 Удалить", callback_data=f"a:svd:{sid}")],
        [K.back(f"a:svcc:{s['category']}"), ADMIN_HOME],
    ))


@router.callback_query(F.data.startswith("a:sv:"))
async def cb_service_admin(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    await service_card_admin(cb, db, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("a:svf:") | F.data.startswith("a:svh:"))
async def cb_service_toggle(cb: CallbackQuery, db: DB):
    sid = int(cb.data.split(":")[2])
    col = "price_from" if cb.data.startswith("a:svf:") else "active"
    await db.execute(f"UPDATE services SET {col}=1-{col} WHERE id=?", (sid,))
    await db.log(cb.from_user.id, "admin_service_toggle", id=sid, col=col)
    await cb.answer("Готово")
    await service_card_admin(cb, db, sid)


@router.callback_query(F.data.startswith("a:svd:"))
async def cb_service_delete(cb: CallbackQuery, db: DB):
    sid = int(cb.data.split(":")[2])
    await cb.answer()
    await show(cb, db, "Удалить услугу? Прошлые записи сохранятся в истории.\n\n<i>Если услуга нужна позже — лучше «Скрыть».</i>",
               K.kb([B(text="🗑 Да, удалить", callback_data=f"a:svdy:{sid}")], [K.back(f"a:sv:{sid}")]))


@router.callback_query(F.data.startswith("a:svdy:"))
async def cb_service_delete_yes(cb: CallbackQuery, db: DB, state: FSMContext):
    sid = int(cb.data.split(":")[2])
    s = await db.service(sid)
    await db.execute("DELETE FROM favorites WHERE service_id=?", (sid,))
    await db.execute("DELETE FROM services WHERE id=?", (sid,))
    await db.log(cb.from_user.id, "admin_service_delete", id=sid)
    await cb.answer("Удалено")
    cb_data = f"a:svcc:{s['category']}" if s else "a:svc"
    await show(cb, db, "🗑 Услуга удалена", K.kb([K.back(cb_data), ADMIN_HOME]))


@router.callback_query(F.data.startswith("a:svnew:"))
async def cb_service_new(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminInput.value)
    await state.update_data(field="svcnew:title", new_cat=cb.data.split(":")[2])
    await show(cb, db, "<b>➕ Новая услуга</b>\n\nШаг 1/4 · Напиши название:", K.kb([K.back("a:svc", "✖️ Отмена")]))


async def new_service_step(message: Message, db: DB, state: FSMContext, raw: str):
    d = await state.get_data()
    step = d["field"].split(":")[1]
    cancel = K.kb([K.back("a:svc", "✖️ Отмена")])
    if step == "title":
        if len(raw) < 2:
            await message.answer("Напиши название")
            return
        await state.update_data(new_title=raw[:80], field="svcnew:price")
        await show(message, db, "Шаг 2/4 · Цена в рублях (число). Если цена «от», напиши например <code>от 300</code>:", cancel)
    elif step == "price":
        pfrom = raw.lower().startswith("от")
        num = "".join(ch for ch in raw if ch.isdigit())
        if not num:
            await message.answer("Нужно число, например 2000")
            return
        await state.update_data(new_price=int(num), new_pfrom=int(pfrom), field="svcnew:dur")
        await show(message, db, "Шаг 3/4 · Длительность в минутах (например 90):", cancel)
    elif step == "dur":
        if not raw.isdigit() or not 5 <= int(raw) <= 600:
            await message.answer("Нужно число минут от 5 до 600")
            return
        await state.update_data(new_dur=int(raw), field="svcnew:desc")
        await show(message, db, "Шаг 4/4 · Короткое описание (или <code>-</code>, чтобы пропустить):", cancel)
    elif step == "desc":
        d = await state.get_data()
        sort = (await db.scalar("SELECT COALESCE(MAX(sort),0)+1 FROM services")) or 1
        sid = await db.execute(
            "INSERT INTO services(category, title, description, price, price_from, duration, sort, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (d["new_cat"], d["new_title"], "" if raw == "-" else raw[:600], d["new_price"], d["new_pfrom"], d["new_dur"], sort, now_str()))
        await state.set_state(None)
        await db.log(message.from_user.id, "admin_service_create", id=sid)
        await service_card_admin(message, db, sid, note="✅ Услуга добавлена! Можно добавить фото:")


# ======================= Портфолио =======================
@router.callback_query(F.data == "a:pf")
async def cb_pf(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    counts = await db.portfolio_counts()
    rows = [[B(text=f"{e} {t} · {counts.get(k, 0)}", callback_data=f"a:pfs:{k}")] for k, t, e in PORTFOLIO_SECTIONS]
    rows.append([ADMIN_HOME])
    await show(cb, db, "<b>🦢 Портфолио</b>\n\nВыбери раздел, чтобы загрузить или удалить фото:", K.kb(*rows))


@router.callback_query(F.data.startswith("a:pfs:"))
async def cb_pf_section(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    sec = cb.data.split(":")[2]
    t, e = SECTIONS[sec]
    n = len(await db.portfolio(sec))
    await show(cb, db, f"<b>{e} {t}</b>\n\nФото в разделе: {n}", K.kb(
        [B(text="📤 Загрузить фото", callback_data=f"a:pfu:{sec}")],
        [B(text="🗂 Просмотр и удаление", callback_data=f"a:pfm:{sec}:0")] if n else [],
        [K.back("a:pf"), ADMIN_HOME],
    ))


@router.callback_query(F.data.startswith("a:pfu:"))
async def cb_pf_upload(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    sec = cb.data.split(":")[2]
    await state.set_state(AdminInput.photos)
    await state.update_data(pf_sec=sec, pf_added=0)
    await show(cb, db, f"<b>📤 Загрузка в «{SECTIONS[sec][0]}»</b>\n\nОтправляй фото — можно сразу альбомом. "
               "Подпись к фото станет описанием работы.\n\n💎 Для максимального качества отправляй фото <b>файлом</b> — "
               "клиентки смогут открыть оригинал.\n\nКогда закончишь — нажми «Готово».",
               K.kb([B(text="✅ Готово", callback_data=f"a:pfs:{sec}")]))


_album_seen: dict[str, int] = {}


@router.message(AdminInput.photos, F.photo | F.document)
async def on_pf_photo(message: Message, db: DB, state: FSMContext, bot: Bot):
    d = await state.get_data()
    sec = d.get("pf_sec")
    orig = None
    if message.document:
        if not (message.document.mime_type or "").startswith("image/"):
            await message.answer("Это не изображение 🙈")
            return
        orig = message.document.file_id
    try:
        fid = await _photo_id(message, bot)
    except TelegramAPIError as e:
        await message.answer(f"Не удалось обработать файл: {h(str(e))}")
        return
    await db.execute("INSERT INTO portfolio(section, file_id, kind, orig_id, caption, created_at) VALUES(?,?,?,?,?,?)",
                     (sec, fid, "document" if orig else "photo", orig, (message.caption or "")[:300] or None, now_str()))
    await db.log(message.from_user.id, "admin_portfolio_add", section=sec)
    total = len(await db.portfolio(sec))
    gid = message.media_group_id
    if gid:
        if gid in _album_seen:
            return
        _album_seen[gid] = 1
        if len(_album_seen) > 200:
            _album_seen.clear()
    await message.answer(f"✓ Добавлено. В разделе «{SECTIONS[sec][0]}» сейчас {total} фото (альбом сохраняется целиком).",
                         reply_markup=K.kb([B(text="✅ Готово", callback_data=f"a:pfs:{sec}")]))


@router.callback_query(F.data.startswith("a:pfm:"))
async def cb_pf_manage(cb: CallbackQuery, db: DB):
    await cb.answer()
    _, _, sec, idx = cb.data.split(":")
    await pf_manage(cb, db, sec, int(idx))


async def pf_manage(cb: CallbackQuery, db: DB, sec: str, idx: int):
    items = await db.portfolio(sec)
    if not items:
        await show(cb, db, "Фото в разделе нет", K.kb([K.back(f"a:pfs:{sec}")]))
        return
    i = int(idx) % len(items)
    it = items[i]
    await show(cb, db, f"{SECTIONS[sec][1]} {SECTIONS[sec][0]} · {i + 1}/{len(items)}\n{h(it.get('caption'))}", K.kb(
        [B(text="◀", callback_data=f"a:pfm:{sec}:{i - 1}"), B(text=f"{i + 1}/{len(items)}", callback_data="noop"),
         B(text="▶", callback_data=f"a:pfm:{sec}:{i + 1}")],
        [B(text="🗑 Удалить это фото", callback_data=f"a:pfdel:{it['id']}:{i}")],
        [K.back(f"a:pfs:{sec}")],
    ), photo=it["file_id"])


@router.callback_query(F.data.startswith("a:pfdel:"))
async def cb_pf_delete(cb: CallbackQuery, db: DB):
    _, _, pid, i = cb.data.split(":")
    it = await db.fetchone("SELECT * FROM portfolio WHERE id=?", (int(pid),))
    if it:
        await db.execute("DELETE FROM portfolio WHERE id=?", (int(pid),))
        await db.log(cb.from_user.id, "admin_portfolio_delete", id=pid)
    await cb.answer("Удалено")
    if it:
        await pf_manage(cb, db, it["section"], max(0, int(i) - 1))


# ======================= Тексты, фото, канал, настройки =======================
@router.callback_query(F.data == "a:txt")
async def cb_texts(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    await show(cb, db, "<b>🖼 Тексты и фото</b>\n\nЧто изменить?", K.kb(
        [B(text="🤍 Текст «Обо мне»", callback_data="a:ed:set:about_text"), B(text="👩 Имя мастера", callback_data="a:ed:set:master_name")],
        [B(text="📍 Адрес", callback_data="a:ed:set:address_text"), B(text="🧭 Как пройти", callback_data="a:ed:set:address_hint")],
        [B(text="🗺 Ссылка на карту", callback_data="a:ed:set:map_url")],
        [B(text="💌 Текст «Связаться»", callback_data="a:ed:set:contact_text")],
        [B(text="@ Telegram мастера", callback_data="a:ed:set:contact_username"), B(text="📱 Телефон", callback_data="a:ed:set:contact_phone")],
        [B(text="🖼 Фото разделов (обложки)", callback_data="a:covers")],
        [ADMIN_HOME],
    ))


@router.callback_query(F.data == "a:covers")
async def cb_covers(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    btns = [B(text=("📷 " if db.get(f"photo_{k}") else "") + v, callback_data=f"a:ed:photo:{k}") for k, v in COVER_NAMES.items()]
    rows = K.chunk(btns, 2) + [[K.back("a:txt"), ADMIN_HOME]]
    await show(cb, db, "<b>🖼 Фото разделов</b>\n\nВыбери раздел и пришли своё фото (например, твоё фото для «Обо мне» или фото студии для «Адреса»). 📷 — уже заменено.",
               K.kb(*rows))


async def channel_status(bot: Bot, db: DB) -> str:
    ch = db.get("channel_id")
    if not ch:
        return "⚠️ Канал не указан — проверка подписки отключена."
    try:
        chat = await bot.get_chat(ch)
        me = await bot.me()
        member = await bot.get_chat_member(ch, me.id)
        if member.status not in ("administrator", "creator"):
            return f"⚠️ Канал «{h(chat.title)}» найден, но бот не администратор — добавь бота в админы канала, иначе проверка не работает."
        return f"✅ Канал «{h(chat.title)}» подключён, бот — администратор. Проверка подписки работает."
    except TelegramAPIError as e:
        return f"⚠️ Не удалось открыть канал: {h(str(e))}\nУбедись, что ID верный и бот добавлен в канал администратором."


@router.callback_query(F.data == "a:ch")
async def cb_channel(cb: CallbackQuery, db: DB, state: FSMContext, bot: Bot):
    await cb.answer()
    await state.set_state(None)
    req = db.flag("sub_required")
    text = (f"<b>📣 Канал и подписка</b>\n\nID канала: <code>{h(db.get('channel_id')) or '—'}</code>\n"
            f"Ссылка: {h(channel_url(db)) or '—'}\nОбязательная подписка: <b>{'включена' if req else 'выключена'}</b>\n\n"
            + await channel_status(bot, db))
    await show(cb, db, text, K.kb(
        [B(text="✏️ ID канала", callback_data="a:ed:set:channel_id"), B(text="🔗 Ссылка", callback_data="a:ed:set:channel_url")],
        [B(text=("🔒 Подписка обязательна" if req else "🔓 Подписка не обязательна"), callback_data="a:tg:sub_required:a:ch")],
        [K.back("a:set"), ADMIN_HOME],
    ))


@router.callback_query(F.data == "a:set")
async def cb_settings(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    on = lambda k: "✅" if db.flag(k) else "▫️"  # noqa: E731
    await show(cb, db, "<b>⚙️ Настройки</b>\n\n"
               "• <b>Автоподтверждение</b> — записи сразу подтверждены, без твоего ✅\n"
               "• <b>Напоминания</b> клиенткам за 24 ч и за 2 ч до визита", K.kb(
                   [B(text=f"{on('auto_confirm')} Автоподтверждение записей", callback_data="a:tg:auto_confirm:a:set")],
                   [B(text=f"{on('remind_24')} Напоминание за 24 ч", callback_data="a:tg:remind_24:a:set"),
                    B(text=f"{on('remind_2')} За 2 ч", callback_data="a:tg:remind_2:a:set")],
                   [B(text="⭐ Когда просить отзыв", callback_data="a:ed:int:review_delay_hours")],
                   [B(text="📣 Канал и обязательная подписка", callback_data="a:ch")],
                   [ADMIN_HOME],
               ))


@router.callback_query(F.data.startswith("a:tg:"))
async def cb_toggle(cb: CallbackQuery, db: DB, state: FSMContext, bot: Bot):
    parts = cb.data.split(":")
    key, back = parts[2], ":".join(parts[3:])
    await db.set(key, "0" if db.flag(key) else "1")
    await db.log(cb.from_user.id, "admin_toggle", key=key, value=db.get(key))
    if back == "a:ch":
        await cb_channel(cb, db, state, bot)
    else:
        await cb_settings(cb, db, state)


# ======================= Клиентки =======================
CL_PAGE = 10


@router.callback_query(F.data.startswith("a:cls:"))
async def cb_clients(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(None)
    page = int(cb.data.split(":")[2])
    total = await db.scalar("SELECT COUNT(*) FROM users")
    rows = await db.fetchall(
        "SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.user_id=u.id AND b.status='done') AS visits "
        "FROM users u ORDER BY u.last_seen DESC LIMIT ? OFFSET ?", (CL_PAGE, page * CL_PAGE))
    with_visits = await db.scalar("SELECT COUNT(DISTINCT user_id) FROM bookings WHERE status='done'")
    text = f"<b>👥 Клиентская база</b>\n\nВсего пользователей: {total} · были на визите: {with_visits}"
    btns = [[B(text=f"{u['name'] or u['first_name'] or u['id']} · {u['phone'] or '—'} · ✨{u['visits']}"[:60],
               callback_data=f"a:cl:{u['id']}")] for u in rows]
    nav = []
    if page:
        nav.append(B(text="‹", callback_data=f"a:cls:{page - 1}"))
    if (page + 1) * CL_PAGE < total:
        nav.append(B(text="›", callback_data=f"a:cls:{page + 1}"))
    btns += [nav, [B(text="🔍 Поиск по имени/телефону", callback_data="a:clsearch")], [ADMIN_HOME]]
    await show(cb, db, text, K.kb(*btns))


@router.callback_query(F.data == "a:clsearch")
async def cb_client_search(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminInput.search)
    await show(cb, db, "Напиши имя, часть телефона или @username:", K.kb([K.back("a:cls:0", "✖️ Отмена")]))


@router.message(AdminInput.search, F.text)
async def on_client_search(message: Message, db: DB, state: FSMContext):
    await state.set_state(None)
    q = message.text.strip().lstrip("@")
    digits = "".join(ch for ch in q if ch.isdigit())
    like = f"%{q}%"
    rows = await db.fetchall(
        "SELECT * FROM users WHERE name LIKE ? OR first_name LIKE ? OR username LIKE ? "
        + ("OR REPLACE(REPLACE(REPLACE(REPLACE(phone,' ',''),'-',''),'+',''),'(','') LIKE ? " if digits else "")
        + "ORDER BY last_seen DESC LIMIT 20",
        (like, like, like, f"%{digits}%") if digits else (like, like, like))
    btns = [[B(text=f"{u['name'] or u['first_name']} · {u['phone'] or '—'}"[:60], callback_data=f"a:cl:{u['id']}")] for u in rows]
    btns.append([K.back("a:cls:0"), ADMIN_HOME])
    await show(message, db, f"🔍 Найдено: {len(rows)}", K.kb(*btns))


@router.callback_query(F.data.startswith("a:cl:"))
async def cb_client(cb: CallbackQuery, db: DB):
    await cb.answer()
    uid = int(cb.data.split(":")[2])
    u = await db.user(uid)
    if not u:
        await show(cb, db, "Клиентка не найдена", K.kb([ADMIN_HOME]))
        return
    bs = await db.fetchall("SELECT * FROM bookings WHERE user_id=? ORDER BY start DESC", (uid,))
    done = [b for b in bs if b["status"] == "done"]
    upcoming = [b for b in bs if b["status"] in ("pending", "confirmed")]
    favs = await db.favorites(uid)
    text = (f"<b>👤 {h(u['name'] or u['first_name'])}</b>"
            + (f" (@{h(u['username'])})" if u["username"] else "")
            + f"\n📱 {h(u['phone']) or '—'}\n🆔 <code>{uid}</code>\n"
            f"С нами с {u['created_at'][:10]} · был(а) {u['last_seen'][:16]}\n"
            f"{'🚫 заблокировала бота' if u['blocked'] else ''}\n"
            f"✨ Визитов: <b>{len(done)}</b> на {rub(sum(b['price'] for b in done))}\n"
            f"✖️ Отмен: {sum(1 for b in bs if b['status'] == 'cancelled')}")
    if done:
        text += f"\nПоследний визит: {human_date(done[0]['date'], False)} — {h(done[0]['service_title'])}"
    if favs:
        text += "\n♡ Избранное: " + ", ".join(h(s["title"]) for s in favs[:5])
    btns = [[B(text=f"{'🤍' if b['status'] == 'pending' else '💗'} {human_date(b['date'], False)} {b_time(b)} · {b['service_title']}"[:60],
               callback_data=f"a:b:{b['id']}")] for b in upcoming[:5]]
    btns += [[B(text="💬 Написать", callback_data=f"a:msg:{uid}")], [K.back("a:cls:0", "⬅️ Клиентки"), ADMIN_HOME]]
    await show(cb, db, text, K.kb(*btns))


@router.callback_query(F.data.startswith("a:msg:"))
async def cb_message_client(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    uid = int(cb.data.split(":")[2])
    await state.set_state(AdminInput.message)
    await state.update_data(msg_to=uid)
    u = await db.user(uid)
    await show(cb, db, f"Напиши сообщение для {h((u or {}).get('name') or (u or {}).get('first_name') or uid)} — "
               "можно текст, фото или голосовое. Оно придёт от имени бота:", K.kb([K.back(f"a:cl:{uid}", "✖️ Отмена")]), new=True)


@router.message(AdminInput.message)
async def on_message_client(message: Message, db: DB, state: FSMContext, bot: Bot):
    uid = (await state.get_data()).get("msg_to")
    await state.set_state(None)
    try:
        await bot.send_message(uid, "💌 <b>Сообщение от мастера:</b>")
        await message.copy_to(uid, reply_markup=K.kb([B(text="💬 Ответить", callback_data="contact:write")]))
        await db.log(message.from_user.id, "admin_message", to=uid)
        await message.answer("✅ Отправлено", reply_markup=K.kb([K.back(f"a:cl:{uid}", "👤 Карточка клиентки"), ADMIN_HOME]))
    except TelegramForbiddenError:
        await db.execute("UPDATE users SET blocked=1 WHERE id=?", (uid,))
        await message.answer("❌ Клиентка заблокировала бота — сообщение не доставлено.")
    except TelegramAPIError as e:
        await message.answer(f"❌ Не отправлено: {h(str(e))}")


# ======================= Рассылка =======================
@router.callback_query(F.data == "a:bc")
async def cb_broadcast(cb: CallbackQuery, db: DB, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminInput.broadcast)
    n_all = await db.scalar("SELECT COUNT(*) FROM users WHERE blocked=0")
    await show(cb, db, f"<b>📣 Рассылка</b>\n\nПолучателей сейчас: {n_all}\n\nОтправь сообщение для рассылки — текст, фото с подписью, "
               "видео… Я покажу превью и спрошу подтверждение.", K.kb([K.back("a:home", "✖️ Отмена")]))


@router.message(AdminInput.broadcast)
async def on_broadcast(message: Message, db: DB, state: FSMContext):
    await state.set_state(None)
    await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id)
    n_all = await db.scalar("SELECT COUNT(*) FROM users WHERE blocked=0")
    n_cl = await db.scalar("SELECT COUNT(DISTINCT b.user_id) FROM bookings b JOIN users u ON u.id=b.user_id WHERE u.blocked=0 AND b.status='done'")
    await message.answer("👆 Так будет выглядеть сообщение. Кому отправить?", reply_markup=K.kb(
        [B(text=f"Всем · {n_all}", callback_data="a:bcgo:all")],
        [B(text=f"Только клиенткам с визитами · {n_cl}", callback_data="a:bcgo:clients")],
        [B(text="✖️ Отмена", callback_data="a:home")]))


async def run_broadcast(bot: Bot, db: DB, admin_id: int, chat_id: int, msg_id: int, audience: str):
    if audience == "clients":
        ids = [r["id"] for r in await db.fetchall(
            "SELECT DISTINCT u.id FROM users u JOIN bookings b ON b.user_id=u.id WHERE u.blocked=0 AND b.status='done'")]
    else:
        ids = [r["id"] for r in await db.fetchall("SELECT id FROM users WHERE blocked=0")]
    bid = await db.execute("INSERT INTO broadcasts(admin_id, audience, total, created_at) VALUES(?,?,?,?)",
                           (admin_id, audience, len(ids), now_str()))
    sent = failed = 0
    for uid in ids:
        for attempt in range(2):
            try:
                await bot.copy_message(uid, chat_id, msg_id)
                sent += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                await db.execute("UPDATE users SET blocked=1 WHERE id=?", (uid,))
                failed += 1
                break
            except TelegramAPIError:
                failed += 1
                break
        await asyncio.sleep(0.05)  # ~20 сообщений в секунду — в рамках лимитов Telegram
    await db.execute("UPDATE broadcasts SET sent=?, failed=? WHERE id=?", (sent, failed, bid))
    await db.log(admin_id, "broadcast", id=bid, sent=sent, failed=failed)
    try:
        await bot.send_message(admin_id, f"📣 Рассылка завершена\n\n✅ Доставлено: {sent}\n❌ Не доставлено: {failed}")
    except TelegramAPIError:
        pass


@router.callback_query(F.data.startswith("a:bcgo:"))
async def cb_broadcast_go(cb: CallbackQuery, db: DB, state: FSMContext, bot: Bot):
    d = await state.get_data()
    if not d.get("bc_msg"):
        await cb.answer("Сообщение не найдено — начни заново", show_alert=True)
        return
    await state.update_data(bc_msg=None)
    await cb.answer("Рассылка запущена 🚀")
    await cb.message.edit_text("📣 Рассылка запущена… Я пришлю отчёт, когда закончу.")
    asyncio.create_task(run_broadcast(bot, db, cb.from_user.id, d["bc_chat"], d["bc_msg"], cb.data.split(":")[2]))


# ======================= Статистика =======================
async def stats_text(db: DB, cfg: Config) -> str:
    t = now(cfg).date()
    periods = [("Сегодня", t, t), ("7 дней", t - timedelta(days=6), t), ("30 дней", t - timedelta(days=29), t)]
    out = ["<b>📊 Статистика</b>"]
    for title, a, b in periods:
        r = await db.fetchone(
            "SELECT COUNT(*) AS n, SUM(status='done') AS done, SUM(status='cancelled') AS canc, "
            "SUM(CASE WHEN status='done' THEN price ELSE 0 END) AS rev FROM bookings WHERE date BETWEEN ? AND ?",
            (a.isoformat(), b.isoformat()))
        created = await db.scalar("SELECT COUNT(*) FROM bookings WHERE substr(created_at,1,10) BETWEEN ? AND ?", (a.isoformat(), b.isoformat()))
        new_users = await db.scalar("SELECT COUNT(*) FROM users WHERE substr(created_at,1,10) BETWEEN ? AND ?", (a.isoformat(), b.isoformat()))
        avg = (r["rev"] or 0) / r["done"] if r["done"] else 0
        out.append(f"\n<b>{title}</b>\nВизитов: {r['done'] or 0} · выручка {rub(r['rev'] or 0)} · средний чек {rub(int(avg))}\n"
                   f"Новых заявок: {created} · отмен: {r['canc'] or 0} · новых пользователей: {new_users}")
    future = await db.fetchone("SELECT COUNT(*) AS n, SUM(price) AS s FROM bookings WHERE status IN ('pending','confirmed') AND date>=?",
                               (t.isoformat(),))
    out.append(f"\n<b>Впереди</b>\nЗаписей: {future['n']} на {rub(future['s'] or 0)}")
    top = await db.fetchall("SELECT service_title, COUNT(*) AS n FROM bookings WHERE status IN ('done','confirmed','pending') "
                            "GROUP BY service_title ORDER BY n DESC LIMIT 5")
    if top:
        out.append("\n<b>Топ услуг</b>\n" + "\n".join(f"{i + 1}. {h(x['service_title'])} — {x['n']}" for i, x in enumerate(top)))
    users = await db.fetchone("SELECT COUNT(*) AS n, SUM(is_subscribed) AS subs, SUM(blocked) AS bl FROM users")
    repeat = await db.scalar("SELECT COUNT(*) FROM (SELECT user_id FROM bookings WHERE status='done' GROUP BY user_id HAVING COUNT(*)>1)")
    out.append(f"\n<b>Аудитория</b>\nПользователей: {users['n']} · подписаны на канал: {users['subs'] or 0} · "
               f"заблокировали бота: {users['bl'] or 0}\nПостоянных клиенток (2+ визита): {repeat}")
    return "\n".join(out)


@router.callback_query(F.data == "a:st")
async def cb_stats(cb: CallbackQuery, db: DB, cfg: Config):
    await cb.answer()
    await show(cb, db, await stats_text(db, cfg), K.kb([B(text="🔄 Обновить", callback_data="a:st")], [ADMIN_HOME]))


# ======================= Отзывы =======================
@router.callback_query(F.data == "a:rvs")
async def cb_reviews_admin(cb: CallbackQuery, db: DB):
    await cb.answer()
    items = await db.fetchall("SELECT * FROM reviews WHERE status='new' ORDER BY id LIMIT 10")
    pub = await db.scalar("SELECT COUNT(*) FROM reviews WHERE status='published'")
    if not items:
        text = f"<b>⭐ Отзывы</b>\n\nНовых отзывов нет. Опубликовано: {pub}"
    else:
        text = "<b>⭐ Новые отзывы</b>\n\n" + "\n\n".join(
            f"№{r['id']} {'★' * r['rating']} — {h(r['name'])}\n<i>{h(r['text']) or 'без текста'}</i>" for r in items)
    btns = [[B(text=f"✅ №{r['id']}", callback_data=f"a:rv:pub:{r['id']}"), B(text=f"🙈 №{r['id']}", callback_data=f"a:rv:hide:{r['id']}")]
            for r in items]
    btns.append([ADMIN_HOME])
    await show(cb, db, text, K.kb(*btns))


@router.callback_query(F.data.startswith("a:rv:"))
async def cb_review_mod(cb: CallbackQuery, db: DB):
    _, _, action, rid = cb.data.split(":")
    await db.execute("UPDATE reviews SET status=? WHERE id=?", ("published" if action == "pub" else "hidden", int(rid)))
    await db.log(cb.from_user.id, "admin_review", id=rid, decision=action)
    await cb.answer("Опубликовано ✅" if action == "pub" else "Скрыто")
    if cb.message and cb.message.text and cb.message.text.startswith("⭐ Новый отзыв"):
        await cb.message.edit_reply_markup(reply_markup=None)
    else:
        await cb_reviews_admin(cb, db)
