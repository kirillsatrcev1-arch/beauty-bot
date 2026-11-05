import asyncio
from datetime import date, datetime, timedelta

import pytest

from app.db import DB
from app.scheduling import SlotTaken, create_booking, day_windows, free_slots, hm, month_map, move_booking, parse_range

pytestmark = pytest.mark.asyncio


def next_weekday(wd: int) -> date:
    d = date.today() + timedelta(days=2)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


@pytest.fixture
async def db(tmp_path):
    d = DB(str(tmp_path / "s.db"))
    await d.connect()
    yield d
    await d.close()


NOW = datetime.now().replace(second=0, microsecond=0)


async def svc(db, minutes=120):
    s = await db.fetchone("SELECT * FROM services WHERE duration=? LIMIT 1", (minutes,))
    assert s, minutes
    return s


async def test_parse_range():
    assert parse_range("10:00-20:00") == ("10:00", "20:00")
    assert parse_range("9 - 18") == ("09:00", "18:00")
    assert parse_range("19.30–21") == ("19:30", "21:00")
    assert parse_range("20:00-10:00") is None
    assert parse_range("абв") is None


async def test_slots_fit_into_working_hours(db):
    d = next_weekday(1)  # вторник — рабочий
    s = await svc(db, 120)
    slots = await free_slots(db, d, s["duration"], NOW)
    assert slots[0] == hm("10:00")
    assert slots[-1] == hm("18:00")  # 18:00 + 2 ч = 20:00, конец дня
    assert all(t % 30 == 0 for t in slots)


async def test_day_off_and_overrides(db):
    sunday = next_weekday(6)
    assert await day_windows(db, sunday) == []
    await db.execute("INSERT INTO extra_windows(date, start, end) VALUES(?,?,?)", (sunday.isoformat(), "12:00", "15:00"))
    s = await svc(db, 60)
    assert await free_slots(db, sunday, 60, NOW) == [hm("12:00"), hm("12:30"), hm("13:00"), hm("13:30"), hm("14:00")]
    tue = next_weekday(1)
    await db.execute("INSERT INTO day_overrides(date, closed) VALUES(?,1)", (tue.isoformat(),))
    assert await free_slots(db, tue, s["duration"], NOW) == []
    wed = next_weekday(2)
    await db.execute("INSERT INTO day_overrides(date, closed, start, end) VALUES(?,0,'14:00','16:00')", (wed.isoformat(),))
    assert await free_slots(db, wed, 60, NOW) == [hm("14:00"), hm("14:30"), hm("15:00")]


async def test_booking_blocks_overlapping_slots(db):
    d = next_weekday(3)
    s120, s60 = await svc(db, 120), await svc(db, 60)
    await create_booking(db, user_id=1, service=s120, start=datetime.combine(d, datetime.min.time()) + timedelta(hours=11),
                         name="A", phone="+7", comment=None, now=NOW)
    slots = await free_slots(db, d, 60, NOW)
    for busy in ("10:30", "11:00", "11:30", "12:00", "12:30"):
        assert hm(busy) not in slots, busy
    assert hm("10:00") in slots and hm("13:00") in slots
    # двухчасовую услугу нельзя поставить на 09:30-… или 10:00 (пересечение с 11:00)
    assert hm("10:00") not in await free_slots(db, d, 120, NOW)
    assert s60


async def test_concurrent_bookings_same_slot_only_one_wins(db):
    d = next_weekday(4)
    s = await svc(db, 120)
    start = datetime.combine(d, datetime.min.time()) + timedelta(hours=12)

    async def attempt(i):
        try:
            await create_booking(db, user_id=100 + i, service=s, start=start, name=f"U{i}", phone="+7", comment=None, now=NOW)
            return True
        except SlotTaken:
            return False

    results = await asyncio.gather(*(attempt(i) for i in range(30)))
    assert sum(results) == 1
    assert await db.scalar("SELECT COUNT(*) FROM bookings WHERE status IN ('pending','confirmed')") == 1


async def test_concurrent_overlapping_from_two_connections(tmp_path):
    """Два независимых соединения (как два процесса) — пересекающиеся записи не проходят обе."""
    path = str(tmp_path / "two.db")
    a, b = DB(path), DB(path)
    await a.connect()
    await b.connect()
    d = next_weekday(1)
    s = await svc(a, 120)
    base = datetime.combine(d, datetime.min.time())

    async def attempt(db, uid, h):
        try:
            await create_booking(db, user_id=uid, service=s, start=base + timedelta(hours=h), name="x", phone="+7", comment=None, now=NOW)
            return True
        except SlotTaken:
            return False

    res = await asyncio.gather(*[attempt(a if i % 2 else b, i, 12 if i % 3 else 13) for i in range(20)])
    assert sum(res) == 1
    await a.close()
    await b.close()


async def test_move_booking_excludes_itself(db):
    d = next_weekday(2)
    s = await svc(db, 120)
    base = datetime.combine(d, datetime.min.time())
    bk = await create_booking(db, user_id=1, service=s, start=base + timedelta(hours=12), name="A", phone="+7", comment=None, now=NOW)
    other = await create_booking(db, user_id=2, service=s, start=base + timedelta(hours=16), name="B", phone="+7", comment=None, now=NOW)
    moved = await move_booking(db, bk["id"], base + timedelta(hours=13), NOW)  # пересекается только с собой — можно
    assert moved["start"].endswith("13:00")
    with pytest.raises(SlotTaken):
        await move_booking(db, bk["id"], base + timedelta(hours=15), NOW)  # пересекается с B
    assert other


async def test_min_lead_and_month_map(db):
    s = await svc(db, 60)
    late = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=19)
    # в 19:00 минимальный запас 2 ч — сегодня уже ничего
    assert await free_slots(db, late.date(), 60, late) == []
    m = await month_map(db, NOW.year, NOW.month, s["duration"], NOW)
    assert set(m.values()) <= {"free", "busy", "off", "past"}
