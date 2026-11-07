"""API Mini App и админ-панели: подпись initData, запись, гонки, мастера, права доступа."""
import asyncio
import io
import time
from datetime import timedelta

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from app.scheduling import local_now
from app.web.auth import InitDataError, sign_admin_token, sign_init_data, validate_init_data
from app.web.server import create_app
from tests.conftest import ADMIN, CLIENT, TOKEN

pytestmark = pytest.mark.asyncio


async def test_init_data_signature():
    raw = sign_init_data({"id": 5, "first_name": "Маша"}, TOKEN)
    assert validate_init_data(raw, TOKEN)["id"] == 5
    with pytest.raises(InitDataError):
        validate_init_data(raw.replace("5", "6", 1), TOKEN)
    with pytest.raises(InitDataError):
        validate_init_data(raw, "999:other")
    old = sign_init_data({"id": 5}, TOKEN, auth_date=int(time.time()) - 3 * 86400)
    with pytest.raises(InitDataError):
        validate_init_data(old, TOKEN)


@pytest.fixture
async def client(env):
    c = TestClient(TestServer(create_app(env.db, env.bot, env.cfg)))
    await c.start_server()
    yield c
    await c.close()


def hdr(uid):
    return {"X-Init-Data": sign_init_data({"id": uid, "first_name": "Маша", "photo_url": "https://t.me/i/u.jpg"}, TOKEN)}


async def get(client, url, uid=CLIENT):
    r = await client.get(url, headers=hdr(uid))
    return r.status, await r.json()


async def post(client, url, body, uid=CLIENT):
    r = await client.post(url, json=body, headers=hdr(uid))
    return r.status, await r.json()


async def free_date(client, sid, uid=CLIENT, master="any", skip=2):
    now = local_now(__import__("zoneinfo").ZoneInfo("Europe/Moscow"))
    for k in range(3):
        y, m = now.year + (now.month + k - 1) // 12, (now.month + k - 1) % 12 + 1
        ym = f"{y}-{m:02d}"
        _, data = await get(client, f"/api/month?service={sid}&ym={ym}&master={master}", uid)
        free = [d for d, st in data["days"].items() if st == "free"]
        if len(free) > skip:
            return f"{ym}-{int(free[skip]):02d}"
    raise AssertionError("нет свободных дней")


async def test_api_requires_auth(client):
    r = await client.get("/api/bootstrap")
    assert r.status == 401
    r = await client.get("/api/bootstrap", headers={"X-Init-Data": "user=%7B%22id%22%3A1%7D&hash=bad"})
    assert r.status == 401


async def test_bootstrap_shape(client):
    st, data = await get(client, "/api/bootstrap")
    assert st == 200 and data["services"] and data["masters"] and data["categories"]
    assert data["user"]["photo_url"] == "https://t.me/i/u.jpg" and not data["user"]["is_admin"]
    assert data["nearest"] and data["nearest"]["time"]
    assert {"why_us", "cancel_rules", "address"} <= set(data["studio"])


async def test_book_via_webapp(client, env):
    _, boot = await get(client, "/api/bootstrap")
    sid = boot["services"][0]["id"]
    date = await free_date(client, sid)
    _, s = await get(client, f"/api/slots?service={sid}&date={date}")
    t = s["slots"][0]["time"]
    body = {"service": sid, "master": "any", "date": date, "time": t, "name": "Маша", "phone": "8 (900) 111-22-33"}

    await env.db.set("channel_id", "@chan")
    env.session.member_status = "left"
    st, data = await post(client, "/api/book", body)
    assert st == 403 and data["error"] == "subscribe"
    env.session.member_status = "member"

    rs = await asyncio.gather(post(client, "/api/book", body, CLIENT), post(client, "/api/book", {**body, "name": "Оля"}, 3000))
    assert sorted(r[0] for r in rs) == [200, 409]
    st, data = next(r for r in rs if r[0] == 200)
    b = data["booking"]
    assert b["phone"] == "+7 900 111-22-33" and b["master_name"] and b["ics"].startswith("/ics/")

    # календарь-файл открывается по подписанной ссылке и не открывается без подписи
    r = await client.get(b["ics"])
    assert r.status == 200 and "BEGIN:VCALENDAR" in await r.text()
    assert (await client.get(f"/ics/{b['id']}.ics?sig=bad")).status == 404

    _, s2 = await get(client, f"/api/slots?service={sid}&date={date}")
    assert t not in [x["time"] for x in s2["slots"]]

    owner = CLIENT if b["name"] == "Маша" else 3000
    stranger = 3000 if owner == CLIENT else CLIENT
    st, _ = await post(client, "/api/cancel", {"id": b["id"]}, stranger)
    assert st == 404
    _, my = await get(client, "/api/my", owner)
    assert my["active"][0]["id"] == b["id"]
    st, data = await post(client, "/api/cancel", {"id": b["id"]}, owner)
    assert data["ok"] and (await env.db.booking(b["id"]))["status"] == "cancelled"


async def test_two_masters_share_the_load(client, env):
    """Два мастера: одно и то же время можно продать дважды, третий раз — уже нет."""
    st, m = await post(client, "/api/admin/masters", {"name": "Вика", "role": "Мастер"}, ADMIN)
    assert st == 200
    _, boot = await get(client, "/api/bootstrap")
    assert len(boot["masters"]) == 2
    sid = boot["services"][0]["id"]
    date = await free_date(client, sid)
    _, s = await get(client, f"/api/slots?service={sid}&date={date}")
    slot = s["slots"][0]
    assert len(slot["masters"]) == 2
    body = {"service": sid, "date": date, "time": slot["time"], "name": "Аня", "phone": "+79001112233"}
    res = [await post(client, "/api/book", {**body, "name": n}, uid) for n, uid in (("Аня", 5001), ("Боня", 5002), ("Вера", 5003))]
    assert [r[0] for r in res] == [200, 200, 409]
    assert {res[0][1]["booking"]["master_id"], res[1][1]["booking"]["master_id"]} == {1, m["id"]}
    # выбор конкретного мастера
    _, s = await get(client, f"/api/slots?service={sid}&date={date}&master={m['id']}")
    assert slot["time"] not in [x["time"] for x in s["slots"]]


async def test_admin_api_permissions_and_flow(client, env):
    # клиентке нельзя
    for url in ("/api/admin/dashboard", "/api/admin/bookings", "/api/admin/clients", "/api/admin/settings"):
        st, data = await get(client, url)
        assert st == 403, url
    st, _ = await post(client, "/api/admin/services", {"title": "Взлом", "price": 1, "duration": 30, "category": "mani"})
    assert st == 403
    # браузерная сессия: поддельная — 401, настоящая — 200
    r = await client.get("/api/admin/dashboard", headers={"X-Admin-Session": "s.1000.9999999999.bad"})
    assert r.status == 401
    r = await client.post("/api/admin/login", json={"token": sign_admin_token(ADMIN, TOKEN, 600, kind="l")})
    session = (await r.json())["session"]
    r = await client.get("/api/admin/dashboard", headers={"X-Admin-Session": session})
    assert r.status == 200 and "months" in await r.json()
    r = await client.post("/api/admin/login", json={"token": sign_admin_token(CLIENT, TOKEN, 600, kind="l")})
    assert r.status == 401

    # услуга: создать, изменить, отключить
    st, s = await post(client, "/api/admin/services", {"title": "Японский маникюр", "price": 1800, "duration": 90, "category": "mani",
                                                         "description": "Уход"}, ADMIN)
    assert st == 200
    st, _ = await post(client, "/api/admin/services", {"id": s["id"], "title": "Японский маникюр", "price": 2100, "duration": 90,
                                                       "category": "mani", "active": False}, ADMIN)
    svc = await env.db.service(s["id"])
    assert svc["price"] == 2100 and svc["active"] == 0

    # загрузка фото и галерея
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (240, 200, 210)).save(buf, "JPEG")
    form = FormData()
    form.add_field("file", buf.getvalue(), filename="n.jpg", content_type="image/jpeg")
    r = await client.post("/api/admin/upload", data=form, headers=hdr(ADMIN))
    up = await r.json()
    assert r.status == 200 and up["value"].startswith("upload:")
    assert (await client.get(up["url"])).status == 200
    form = FormData()
    form.add_field("file", b"not an image", filename="x.jpg")
    assert (await client.post("/api/admin/upload", data=form, headers=hdr(ADMIN))).status == 400
    st, _ = await post(client, "/api/admin/gallery", {"section": "nude", "photo": up["value"], "caption": "Нюд"}, ADMIN)
    _, pf = await get(client, "/api/portfolio?s=nude")
    assert pf["items"][0]["src"] == up["url"]

    # расписание: отпуск закрывает дни мастера
    now = local_now(env.cfg.tz).date()
    d1 = (now + timedelta(days=3)).isoformat()
    st, _ = await post(client, "/api/admin/schedule/vacation", {"master_id": 1, "date_from": d1, "date_to": d1}, ADMIN)
    _, s = await get(client, f"/api/slots?service=1&date={d1}")
    assert s["slots"] == []
    # блокировка окна
    d2 = (now + timedelta(days=4)).isoformat()
    await env.db.set("work_days", "0,1,2,3,4,5,6")
    _, before = await get(client, f"/api/slots?service=2&date={d2}")
    await post(client, "/api/admin/schedule/block", {"master_id": 1, "date": d2, "start": "10:00", "end": "14:00"}, ADMIN)
    _, after = await get(client, f"/api/slots?service=2&date={d2}")
    assert "10:00" in [x["time"] for x in before["slots"]] and "10:00" not in [x["time"] for x in after["slots"]]

    # ручная запись мастером и смена статуса
    st, b = await post(client, "/api/admin/bookings", {"service": 2, "master": 1, "date": d2, "time": "18:00",
                                                       "name": "Ольга", "phone": "+7 900 000-00-00"}, ADMIN)
    assert st == 200 and b["booking"]["status"] == "confirmed"
    bid = b["booking"]["id"]
    st, _ = await post(client, f"/api/admin/bookings/{bid}", {"action": "status", "status": "done"}, ADMIN)
    _, lst = await get(client, "/api/admin/bookings?q=Ольга", ADMIN)
    assert lst["items"][0]["status"] == "done"
    _, cal = await get(client, f"/api/admin/calendar?from={d2}&to={d2}", ADMIN)
    assert cal["days"][0]["bookings"] and cal["days"][0]["blocks"]

    # настройки
    await post(client, "/api/admin/settings", {"studio_name": "Lumière", "evil_key": "x"}, ADMIN)
    assert env.db.get("studio_name") == "Lumière" and env.db.get("evil_key", "") == ""
    _, cl = await get(client, "/api/admin/clients?q=Маша", ADMIN)
    assert cl["items"]


async def test_media_whitelist(client, env):
    r = await client.get("/media/unknown-file-id")
    assert r.status == 404
    await env.db.execute("INSERT INTO portfolio(section, file_id, created_at) VALUES('nude','known-id','2026-01-01')")
    r = await client.get("/media/known-id")
    assert r.status == 200
    assert (await client.get("/uploads/..%2F..%2Fapp%2Fdb.py")).status == 404
