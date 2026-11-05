"""Конфигурация из переменных окружения (или файла .env рядом с проектом)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Минимальный парсер .env, чтобы не тянуть лишнюю зависимость."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@dataclass
class Config:
    bot_token: str
    admin_ids: set[int] = field(default_factory=set)
    webapp_url: str = ""
    db_path: str = str(BASE_DIR / "data" / "beauty.db")
    data_dir: Path = BASE_DIR / "data"
    tz_name: str = "Europe/Moscow"
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    run_web: bool = True

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)

    def is_admin(self, user_id: int | None) -> bool:
        return bool(user_id) and user_id in self.admin_ids


def load_config() -> Config:
    _load_dotenv(BASE_DIR / ".env")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather.")
    admins = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()}
    data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        bot_token=token,
        admin_ids=admins,
        webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
        db_path=os.getenv("DB_PATH", str(data_dir / "beauty.db")),
        data_dir=data_dir,
        tz_name=os.getenv("TZ_NAME", os.getenv("TIMEZONE", "Europe/Moscow")),
        web_host=os.getenv("WEB_HOST", "0.0.0.0"),
        web_port=int(os.getenv("PORT", os.getenv("WEB_PORT", "8080"))),
        run_web=os.getenv("RUN_WEB", "1") != "0",
    )
