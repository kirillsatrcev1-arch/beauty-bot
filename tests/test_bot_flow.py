"""Сквозной сценарий через Dispatcher.feed_update с поддельным Telegram API."""
from datetime import datetime, timedelta

import pytest

from app import notifications
from app.scheduling import create_booking, local_now
from app.texts import SUB_NOT_YET, SUBSCRIBE
from tests.conftest import ADMIN, CLIENT

pytestmark = pytest.mark.asyncio


def first(buttons, prefix):
    return next(b for b in buttons if b.startswith(prefix))


async def test_full_booking_flow(env):
    s, db = env.session, env.db
    await db.set("channel_id", "@beauty_channel")

    # 1. Приветствие
    await env.text(CLIENT, "/start")
    scr = s.last_screen()
    assert type(scr).__name__ == "SendPhoto"
    assert "Добро пожаловать в мой beauty world! 🎀" in scr.caption
    assert "book" in env.buttons() and "pr" in env.buttons() and "a:home" not in env.buttons()

    # 2. Запись → требование подписки
    s.member_status = "left"
    await env.click(CLIENT, "book")
    assert s.text_of(s.last_screen()) == SUBSCRIBE
    await env.click(CLIENT, "sub:check")
    assert SUB_NOT_YET in env.alerts()

    # 3. Подписалась → категории
    s.member_status = "member"
    await env.click(CLIENT, "sub:check")
    assert "Выбери категорию" in s.text_of(s.last_screen())
    assert any(c.method == "getChatMember" if hasattr(c, "method") else type(c).__name__ == "GetChatMember" for c in s.calls)

    await env.click(CLIENT, "book:grp:mani")
    svc_cb = first(env.buttons(), "book:svc:")
    await env.click(CLIENT, svc_cb)
    assert "Выбери дату" in s.text_of(s.last_screen())
    day_cb = [x for x in env.buttons() if x.startswith("book:day:")][2]  # не сегодня: перенос возможен не позже чем за N часов
    await env.click(CLIENT, day_cb)
    time_cb = first(env.buttons(), "book:time:")
    await env.click(CLIENT, time_cb)
    assert "Как тебя зовут" in s.text_of(s.last_screen())

    # 4. Контакты
    await env.text(CLIENT, "Мария")
    assert "Номер телефона" in s.text_of(s.last_screen())
    await env.text(CLIENT, "abc")
    assert "Не получилось распознать" in s.text_of(s.last_screen())
    await env.text(CLIENT, "", contact="89001234567")
    assert "Комментарий" in s.text_of(s.last_screen())
    await env.text(CLIENT, "Хочу нюд с хромом")
    scr = s.text_of(s.last_screen())
    assert "Проверь запись" in scr and "+7 900 123-45-67" in scr and "нюд с хромом" in scr

    # 5. Подтверждение
    s.clear()
    await env.click(CLIENT, "book:confirm")
    scr = s.text_of(s.last_screen())
    for part in ("Твоя запись успешно создана! ♡", "🎀 <b>Услуга:</b>", "📅 <b>Дата:</b>", "⏰ <b>Время:</b>",
                 "💗 <b>Стоимость:</b>", "📍 <b>Адрес:</b>", "Буду с нетерпением ждать нашей встречи!"):
        assert part in scr, part
    b = await db.fetchone("SELECT * FROM bookings")
    assert b["status"] == "pending" and b["name"] == "Мария" and b["comment"] == "Хочу нюд с хромом"
    assert f"my:resch:{b['id']}" in env.buttons() and f"my:cancel:{b['id']}" in env.buttons()
    admin_msgs = [s.text_of(c) for c in s.sent_to(ADMIN)]
    assert any("Новая заявка" in t for t in admin_msgs)

    # повторное нажатие не создаёт дубль
    await env.click(CLIENT, "book:confirm")
    assert await db.scalar("SELECT COUNT(*) FROM bookings") == 1

    # 6. Мастер подтверждает
    s.clear()
    await env.click(ADMIN, f"a:bk:ok:{b['id']}", photo=False)
    assert (await db.booking(b["id"]))["status"] == "confirmed"
    assert any("Мастер подтвердил" in s.text_of(c) for c in s.sent_to(CLIENT))

    # 7. Клиентка переносит запись
    s.clear()
    await env.click(CLIENT, f"my:resch:{b['id']}")
    days = [x for x in env.buttons() if x.startswith("book:day:")]
    await env.click(CLIENT, days[-1])
    await env.click(CLIENT, first(env.buttons(), "book:time:"))
    assert "Перенос записи" in s.text_of(s.last_screen())
    await env.click(CLIENT, "book:confirm")
    nb = await db.booking(b["id"])
    assert nb["start"] != b["start"] and nb["status"] == "pending"
    assert any("перенесла запись" in s.text_of(c) for c in s.sent_to(ADMIN))
    assert await db.scalar("SELECT COUNT(*) FROM bookings") == 1

    # 8. Клиентка отменяет
    s.clear()
    await env.click(CLIENT, f"my:cancel:{b['id']}")
    assert "Отменить запись?" in s.text_of(s.last_screen())
    await env.click(CLIENT, f"my:cancelyes:{b['id']}")
    assert (await db.booking(b["id"]))["status"] == "cancelled"
    assert any("отменила запись" in s.text_of(c) for c in s.sent_to(ADMIN))

    # 9. Журнал действий заполнен
    actions = {r["action"] for r in await db.fetchall("SELECT action FROM events")}
    assert {"start", "booking_created", "booking_confirmed", "booking_rescheduled", "booking_cancelled"} <= actions


async def test_saved_contacts_and_repeat(env):
    s, db = env.session, env.db
    await env.text(CLIENT, "/start")
    await db.execute("UPDATE users SET name='Мария', phone='+7 900 000-00-00' WHERE id=?", (CLIENT,))
    sid = (await db.services())[0]["id"]
    await env.click(CLIENT, f"book:svcgo:{sid}")
    await env.click(CLIENT, first(env.buttons(), "book:day:"))
    await env.click(CLIENT, first(env.buttons(), "book:time:"))
    assert "book:saved" in env.buttons()
    await env.click(CLIENT, "book:saved")
    await env.click(CLIENT, "book:nocomment")
    await env.click(CLIENT, "book:confirm")
    assert await db.scalar("SELECT COUNT(*) FROM bookings") == 1
    await env.click(CLIENT, "book")
    assert "book:last" in env.buttons()


async def test_admin_panel_and_access(env):
    s, db = env.session, env.db
    # клиентка не может открыть админку
    await env.text(CLIENT, "/admin")
    await env.click(CLIENT, "a:home")
    assert not any("Админ-панель" in s.text_of(c) for c in s.calls)
    # мастер — может
    await env.text(ADMIN, "/admin")
    assert "Админ-панель" in s.text_of(s.last_screen())
    for cb in ("a:bks", "a:bl:today", "a:sch", "a:svc", "a:svcc:mani", "a:pf", "a:txt", "a:covers", "a:cls:0", "a:st", "a:rvs", "a:set"):
        s.clear()
        await env.click(ADMIN, cb, photo=False)
        assert s.last_screen() is not None, cb

    # смена цены
    sid = (await db.services(category="mani"))[0]["id"]
    await env.click(ADMIN, f"a:ed:svc:{sid}:price", photo=False)
    await env.text(ADMIN, "2500")
    assert (await db.service(sid))["price"] == 2500
    # новая услуга
    await env.click(ADMIN, "a:svnew:design", photo=False)
    for v in ("Стразы", "от 150", "15", "Сваровски на один ноготь"):
        await env.text(ADMIN, v)
    new = await db.fetchone("SELECT * FROM services WHERE title='Стразы'")
    assert new and new["price"] == 150 and new["price_from"] == 1 and new["duration"] == 15
    # рабочие часы и доп. окошко
    await env.click(ADMIN, "a:ed:hours", photo=False)
    await env.text(ADMIN, "11:00-19:00")
    assert db.get("work_start") == "11:00" and db.get("work_end") == "19:00"
    d = (local_now(env.cfg.tz) + timedelta(days=3)).date().isoformat()
    await env.click(ADMIN, f"a:dd:win:{d}", photo=False)
    await env.text(ADMIN, "20:00-22:00")
    assert await db.scalar("SELECT COUNT(*) FROM extra_windows WHERE date=?", (d,)) == 1
    await env.click(ADMIN, f"a:dd:close:{d}", photo=False)
    assert (await db.fetchone("SELECT closed FROM day_overrides WHERE date=?", (d,)))["closed"] == 1
    # тексты
    await env.click(ADMIN, "a:ed:set:address_text", photo=False)
    await env.text(ADMIN, "СПб, Невский 1")
    assert db.get("address_text") == "СПб, Невский 1"
    # рабочие дни
    await env.click(ADMIN, "a:wd:6", photo=False)
    assert "6" in db.get("work_days").split(",")


async def test_reminders_and_reviews(env):
    s, db, cfg = env.session, env.db, env.cfg
    await env.text(CLIENT, "/start")
    svc = await db.fetchone("SELECT * FROM services WHERE duration=60")
    now = local_now(cfg.tz)
    await db.set("work_days", "0,1,2,3,4,5,6")
    await db.set("work_start", "00:00")
    await db.set("work_end", "23:59")
    await db.set("min_lead_min", "0")
    start = (now + timedelta(hours=20)).replace(minute=0)
    b = await create_booking(db, user_id=CLIENT, service=svc, start=start, name="М", phone="+7", comment=None,
                             now=now - timedelta(days=2), status="confirmed")
    s.clear()
    st = await notifications.tick(env.bot, db, cfg)
    assert st["r24"] == 1
    assert any("Напоминаю о записи" in s.text_of(c) for c in s.sent_to(CLIENT))
    st = await notifications.tick(env.bot, db, cfg)
    assert st["r24"] == 0  # не дублируется

    # подтверждение визита клиенткой → мастеру
    s.clear()
    await env.click(CLIENT, f"my:come:{b['id']}", photo=False)
    assert any("подтвердила визит" in s.text_of(c) for c in s.sent_to(ADMIN))

    # прошедший визит → done → просьба об отзыве
    await db.execute("UPDATE bookings SET start=?, end=?, remind2=1 WHERE id=?",
                     ((now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M"), (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M"), b["id"]))
    s.clear()
    st = await notifications.tick(env.bot, db, cfg)
    assert st["done"] == 1 and st["review"] == 1
    await env.click(CLIENT, f"rv:rate:{b['id']}:5")
    await env.text(CLIENT, "Лучший мастер!")
    r = await db.fetchone("SELECT * FROM reviews")
    assert r["rating"] == 5 and r["status"] == "new"
    await env.click(ADMIN, f"a:rv:pub:{r['id']}", photo=False)
    assert (await db.fetchone("SELECT status FROM reviews"))["status"] == "published"
    s.clear()
    await env.click(CLIENT, "rv:0")
    assert "Лучший мастер!" in s.text_of(s.last_screen())


async def test_portfolio_and_prices(env):
    s, db = env.session, env.db
    await env.click(ADMIN, "a:pfu:nude", photo=False)
    from aiogram.types import Chat, Message, PhotoSize, Update
    for i in range(3):
        msg = Message(message_id=900 + i, date=datetime.now(), chat=Chat(id=ADMIN, type="private"), from_user=env.user(ADMIN),
                      photo=[PhotoSize(file_id=f"nude-{i}", file_unique_id=f"n{i}", width=10, height=10)], caption=f"Работа {i}")
        await env.dp.feed_update(env.bot, Update(update_id=9000 + i, message=msg))
    assert len(await db.portfolio("nude")) == 3
    s.clear()
    await env.click(CLIENT, "pf:nude:0")
    assert "1/3" in s.text_of(s.last_screen())
    assert "pf:nude:1" in env.buttons()
    await env.click(CLIENT, "pr")
    await env.click(CLIENT, "pr:cat:mani")
    sid = int(first(env.buttons(), "pr:svc:").split(":")[2])
    await env.click(CLIENT, f"pr:svc:{sid}")
    assert f"book:svcgo:{sid}" in env.buttons()
    await env.click(CLIENT, f"pr:fav:{sid}")
    assert await db.is_favorite(CLIENT, sid)
    await env.click(CLIENT, "fav")
    assert f"book:svcgo:{sid}" in env.buttons()
