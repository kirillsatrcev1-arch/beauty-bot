"""API Mini App: подпись initData, запись, гонка, доступ к админке."""
import asyncio
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from app.web.auth import InitDataError, sign_init_data, validate_init_data
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
    return {"X-Init-Data": sign_init_data({"id": uid, "first_name": "Маша"}, TOKEN)}


async def test_api_requires_auth(client):
    r = await client.get("/api/bootstrap")
    assert r.status == 401
    r = await client.get("/api/bootstrap", headers={"X-Init-Data": "user=%7B%22id%22%3A1%7D&hash=bad"})
    assert r.status == 401


async def test_book_via_webapp(client, env):
    r = await client.get("/api/bootstrap", headers=hdr(CLIENT))
    data = await r.json()
    assert data["ok"] and data["services"] and not data["user"]["is_admin"]
    sid = data["services"][0]["id"]
    from app.scheduling import local_now
    now = local_now(env.cfg.tz)
    ym = f"{now.year}-{now.month:02d}"
    days = (await (await client.get(f"/api/month?service={sid}&ym={ym}", headers=hdr(CLIENT))).json())["days"]
    free = [d for d, st in days.items() if st == "free"]
    if not free:  # конец месяца — берём следующий
        y, m = (now.year + (now.month == 12), now.month % 12 + 1)
        ym = f"{y}-{m:02d}"
        days = (await (await client.get(f"/api/month?service={sid}&ym={ym}", headers=hdr(CLIENT))).json())["days"]
        free = [d for d, st in days.items() if st == "free"]
    date = f"{ym}-{int(free[0]):02d}"
    slots = (await (await client.get(f"/api/slots?service={sid}&date={date}", headers=hdr(CLIENT))).json())["slots"]
    body = {"service": sid, "date": date, "time": slots[0], "name": "Маша", "phone": "8 (900) 111-22-33"}

    # подписка обязательна
    await env.db.set("channel_id", "@chan")
    env.session.member_status = "left"
    r = await client.post("/api/book", json=body, headers=hdr(CLIENT))
    assert r.status == 403 and (await r.json())["error"] == "subscribe"
    env.session.member_status = "member"

    # две клиентки жмут одновременно — запись получает одна
    other = 3000
    rs = await asyncio.gather(client.post("/api/book", json=body, headers=hdr(CLIENT)),
                              client.post("/api/book", json={**body, "name": "Оля"}, headers=hdr(other)))
    assert sorted(r.status for r in rs) == [200, 409]
    ok = next(r for r in rs if r.status == 200)
    b = (await ok.json())["booking"]
    assert b["phone"] == "+7 900 111-22-33"

    # слот исчез из свободных
    slots2 = (await (await client.get(f"/api/slots?service={sid}&date={date}", headers=hdr(CLIENT))).json())["slots"]
    assert slots[0] not in slots2

    # чужая запись недоступна, своя отменяется
    owner = CLIENT if b["name"] == "Маша" else other
    stranger = other if owner == CLIENT else CLIENT
    r = await client.post("/api/cancel", json={"id": b["id"]}, headers=hdr(stranger))
    assert r.status == 404
    my = await (await client.get("/api/my", headers=hdr(owner))).json()
    assert my["active"][0]["id"] == b["id"]

    # админка: клиентке нельзя, мастеру можно
    assert (await client.get("/api/admin/day", headers=hdr(CLIENT))).status == 403
    r = await client.post("/api/admin/action", json={"id": b["id"], "action": "confirm"}, headers=hdr(ADMIN))
    assert (await r.json())["booking"]["status"] == "confirmed"
    r = await client.post("/api/cancel", json={"id": b["id"]}, headers=hdr(owner))
    assert (await r.json())["ok"]
    assert (await env.db.booking(b["id"]))["status"] == "cancelled"


async def test_media_whitelist(client, env):
    r = await client.get("/media/unknown-file-id")
    assert r.status == 404
    await env.db.execute("INSERT INTO portfolio(section, file_id, created_at) VALUES('nude','known-id','2026-01-01')")
    r = await client.get("/media/known-id")
    assert r.status == 200
    r = await client.get("/img/cover/welcome.jpg")
    assert r.status == 200 and r.headers["Content-Type"] == "image/jpeg"
    r = await client.get("/img/cover/..%2F..%2Fapp%2Fdb.jpg")
    assert r.status == 404
