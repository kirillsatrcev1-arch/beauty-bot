"""Локальный предпросмотр Mini App на настоящем сервере и демо-данных (без Telegram).

    python scripts/preview_webapp.py [порт] [папка-с-фото]

Поднимает API + собранный фронтенд, заполняет базу примерами (2 мастера, записи, галерея из папки с фото)
и печатает подписанный initData администратора — Playwright подставляет его в window.Telegram.WebApp.
"""
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402
from aiohttp import web  # noqa: E402

from app.config import Config  # noqa: E402
from app.covers import ensure_covers  # noqa: E402
from app.db import DB, now_str  # noqa: E402
from app.media import save_image, set_upload_dir  # noqa: E402
from app.scheduling import create_booking, local_now  # noqa: E402
from app.ui import set_covers_dir  # noqa: E402
from app.web.auth import sign_init_data  # noqa: E402
from app.web.server import create_app  # noqa: E402
from tests.conftest import FakeSession  # noqa: E402

TOKEN = "123456:PREVIEW"


async def main(port: int, photos_dir: Path | None):
    tmp = ROOT / "data" / "preview"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("p.db*"):
        f.unlink()
    ensure_covers(ROOT / "data" / "covers")
    set_covers_dir(ROOT / "data" / "covers")
    set_upload_dir(tmp / "uploads")
    cfg = Config(bot_token=TOKEN, admin_ids={1000}, db_path=str(tmp / "p.db"), data_dir=tmp)
    db = DB(cfg.db_path)
    await db.connect()
    await db.set("studio_name", "Lumière Nails")
    await db.set("address_text", "Москва, Малая Бронная, 24")
    await db.set("contact_username", "lumiere_nails")
    await db.set("contact_phone", "+7 900 123-45-67")
    await db.set("work_days", "0,1,2,3,4,5,6")
    await db.execute("UPDATE masters SET name='Алина', bio='6 лет в nail-индустрии. Аппаратный маникюр, архитектура и тонкий дизайн.' WHERE id=1")
    await db.execute("INSERT INTO masters(name, role, bio, sort, created_at) VALUES('Вероника', 'Мастер-дизайнер', 'Френч, втирки и сложные дизайны. Работаю с длиной.', 1, ?)", (now_str(),))
    photos = sorted(photos_dir.glob("*.jpg")) if photos_dir else []
    vals = [save_image(p.read_bytes()) for p in photos]
    if vals:
        sections = ["nude", "red", "nude", "ext", "french", "design", "ext", "nude"]
        caps = ["Нюдовая кошачья втирка", "Вишнёвый глянец", "Розовая втирка", "Длинный квадрат", "Розовый френч с серебром",
                "Молочный с синей росписью", "Серебряная втирка", "Френч в полоску"]
        for i, v in enumerate(vals):
            await db.execute("INSERT INTO portfolio(section, file_id, kind, caption, created_at) VALUES(?,?, 'upload', ?, ?)",
                             (sections[i % len(sections)], v, caps[i % len(caps)], now_str()))
        for s in await db.services():
            await db.execute("UPDATE services SET photo=? WHERE id=?", (vals[s["id"] % len(vals)], s["id"]))
        await db.set("photo_welcome", vals[0])
        await db.execute("UPDATE masters SET photo=? WHERE id=1", (vals[2 % len(vals)],))
        await db.execute("UPDATE masters SET photo=? WHERE id=2", (vals[4 % len(vals)],))
    for name, r, text in (("Алёна", 5, "Самый уютный маникюр в моей жизни, носится уже четвёртую неделю"),
                          ("Катя", 5, "Идеальный миндаль и нюд. Мастер — золото!")):
        await db.execute("INSERT INTO reviews(user_id, name, rating, text, status, created_at) VALUES(1,?,?,?,'published',?)", (name, r, text, now_str()))
    now = local_now(cfg.tz)
    await db.touch_user(1000, "master", "Алина")
    services = await db.services()
    names = ["Мария", "Софья", "Дарья", "Ева", "Полина", "Ксения"]
    for i in range(10):
        d = (now + timedelta(days=i // 3 + 1)).replace(hour=10 + (i % 3) * 3, minute=0)
        try:
            await create_booking(db, user_id=2000 + i, service=services[i % len(services)], start=d, name=names[i % len(names)],
                                 phone="+7 900 000-00-0" + str(i), comment=None, now=now, status="confirmed" if i % 2 else "pending")
        except Exception:  # noqa: BLE001
            pass
    for i in range(6):  # прошлые визиты для статистики
        d = (now - timedelta(days=5 + i * 9)).replace(hour=12, minute=0)
        await db.execute("INSERT INTO bookings(user_id, service_id, service_title, price, duration, date, start, end, status, name, phone, master_id, master_name, created_at, updated_at)"
                         " VALUES(?,?,?,?,?,?,?,?,'done',?,?,1,'Алина',?,?)",
                         (2100 + i, services[i]["id"], services[i]["title"], services[i]["price"], services[i]["duration"], d.date().isoformat(),
                          d.strftime("%Y-%m-%d %H:%M"), (d + timedelta(minutes=services[i]["duration"])).strftime("%Y-%m-%d %H:%M"),
                          names[i], "+7 900 111-11-1" + str(i), now_str(), now_str()))
    bot = Bot(TOKEN, session=FakeSession())
    runner = web.AppRunner(create_app(db, bot, cfg))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    print("INITDATA=" + sign_init_data({"id": 1000, "first_name": "Алина", "username": "master"}, TOKEN), flush=True)
    print("CLIENT=" + sign_init_data({"id": 3000, "first_name": "Мария"}, TOKEN), flush=True)
    print(f"READY http://127.0.0.1:{port}", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8099, Path(sys.argv[2]) if len(sys.argv) > 2 else None))
