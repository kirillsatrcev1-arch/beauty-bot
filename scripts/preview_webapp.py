"""Локальный предпросмотр Mini App без Telegram: фейковый бот, демо-данные, подписанный initData.

    python scripts/preview_webapp.py          # http://127.0.0.1:8099
Выводит initData для пользователя-админа; Playwright-скрипт подставляет его в window.Telegram.WebApp.
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402
from aiohttp import web  # noqa: E402

from app.config import Config  # noqa: E402
from app.covers import ensure_covers  # noqa: E402
from app.db import DB, now_str  # noqa: E402
from app.scheduling import create_booking, local_now  # noqa: E402
from app.ui import set_covers_dir  # noqa: E402
from app.web.auth import sign_init_data  # noqa: E402
from app.web.server import create_app  # noqa: E402
from tests.conftest import FakeSession  # noqa: E402

TOKEN = "123456:PREVIEW"
COVERS = ROOT / "data" / "covers"


class PreviewSession(FakeSession):
    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        name = url.rsplit("/", 1)[-1].split("__")[-1]
        yield (COVERS / f"{name}.jpg").read_bytes()

    async def _make(self, bot, method):
        if type(method).__name__ == "GetFile":
            from aiogram.types import File
            return File(file_id=method.file_id, file_unique_id="u", file_path=f"photos/{method.file_id}")
        return await super()._make(bot, method)


async def main(port=8099):
    tmp = ROOT / "data" / "preview"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*"):
        if f.is_file():
            f.unlink()
    ensure_covers(COVERS)
    set_covers_dir(COVERS)
    cfg = Config(bot_token=TOKEN, admin_ids={1000}, db_path=str(tmp / "p.db"), data_dir=tmp)
    db = DB(cfg.db_path)
    await db.connect()
    await db.set("address_text", "Москва, Патриаршие пруды, Малая Бронная 24")
    await db.set("contact_username", "beauty_master")
    for i, key in enumerate(["pf_nude", "pf_red", "pf_french", "cat_ext", "pf_design", "welcome", "cat_mani", "pf_pedi"]):
        await db.execute("INSERT INTO portfolio(section, file_id, caption, created_at) VALUES(?,?,?,?)",
                         ("nude", f"demo{i}__{key}", "Нюд с жемчужной втиркой" if i == 0 else None, now_str()))
    await db.execute("INSERT INTO reviews(user_id, name, rating, text, status, created_at) VALUES(1,'Алёна',5,'Самый уютный маникюр в моей жизни, носится уже четвёртую неделю ♡','published',?)", (now_str(),))
    await db.execute("INSERT INTO reviews(user_id, name, rating, text, status, created_at) VALUES(2,'Катя',5,'Идеальный миндаль и нюд, мастер — золото!','published',?)", (now_str(),))
    svc = (await db.services())[0]
    now = local_now(cfg.tz)
    await db.touch_user(1000, "master", "Алина")
    d = now + timedelta(days=2)
    while d.weekday() == 6:
        d += timedelta(days=1)
    await create_booking(db, user_id=1000, service=svc, start=d.replace(hour=12, minute=0), name="Мария", phone="+7 900 123-45-67",
                         comment="Хочу нюд", now=now)
    bot = Bot(TOKEN, session=PreviewSession())
    runner = web.AppRunner(create_app(db, bot, cfg))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    print("INITDATA=" + sign_init_data({"id": 1000, "first_name": "Алина", "username": "master"}, TOKEN), flush=True)
    print(f"READY http://127.0.0.1:{port}", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8099))
