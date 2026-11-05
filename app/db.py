"""SQLite-хранилище: схема, начальные данные и репозиторий.

Одно соединение aiosqlite в режиме autocommit. Все обращения идут через asyncio.Lock,
а транзакции (BEGIN IMMEDIATE) удерживают его целиком — так параллельные корутины
не «вклиниваются» в чужую транзакцию. BEGIN IMMEDIATE + уникальный индекс по времени
защищают и от гонок между разными процессами.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

import aiosqlite

ACTIVE = ("pending", "confirmed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories(
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '',
    book_group TEXT NOT NULL,
    sort INTEGER NOT NULL DEFAULT 0,
    photo TEXT
);
CREATE TABLE IF NOT EXISTS services(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL REFERENCES categories(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL,
    price_from INTEGER NOT NULL DEFAULT 0,
    duration INTEGER NOT NULL,
    photo TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    name TEXT,
    phone TEXT,
    is_subscribed INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    service_id INTEGER,
    service_title TEXT NOT NULL,
    price INTEGER NOT NULL,
    price_from INTEGER NOT NULL DEFAULT 0,
    duration INTEGER NOT NULL,
    date TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    status TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    comment TEXT,
    source TEXT NOT NULL DEFAULT 'chat',
    client_confirmed INTEGER NOT NULL DEFAULT 0,
    remind24 INTEGER NOT NULL DEFAULT 0,
    remind2 INTEGER NOT NULL DEFAULT 0,
    review_asked INTEGER NOT NULL DEFAULT 0,
    cancel_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bookings_date ON bookings(date, status);
CREATE INDEX IF NOT EXISTS ix_bookings_user ON bookings(user_id, status);
-- Последний рубеж защиты от двойной записи: два активных визита не могут начинаться в одну минуту.
CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_active_start ON bookings(start) WHERE status IN ('pending','confirmed');

CREATE TABLE IF NOT EXISTS day_overrides(
    date TEXT PRIMARY KEY,
    closed INTEGER NOT NULL DEFAULT 0,
    start TEXT,
    end TEXT
);
CREATE TABLE IF NOT EXISTS extra_windows(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portfolio(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    file_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'photo',
    orig_id TEXT,
    caption TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    booking_id INTEGER,
    name TEXT,
    rating INTEGER NOT NULL,
    text TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites(
    user_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(user_id, service_id)
);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    data TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_cache(
    key TEXT PRIMARY KEY,
    file_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS broadcasts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    audience TEXT,
    total INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

DEFAULT_ABOUT = (
    "Привет! Меня зовут <b>Алина</b>, и я влюблена в ноготки ♡\n\n"
    "🤍 <b>Опыт:</b> 6 лет в nail-индустрии, более 3 000 довольных клиенток\n"
    "🎓 <b>Обучение:</b> базовый курс маникюра и педикюра, повышение квалификации "
    "по аппаратному маникюру, курсы по архитектуре и дизайну ногтей\n"
    "🧴 <b>Материалы:</b> премиальные гели и базы Luxio, Kodi, The Nail Theory, "
    "одноразовые пилки и бафы\n"
    "✨ <b>Стерильность:</b> 3 этапа обработки инструмента, сухожар, крафт-пакеты при вас\n"
    "💗 <b>Мой подход:</b> никакого конвейера — подберу форму и оттенок под вашу руку, "
    "образ и стиль жизни. Уютная атмосфера, кофе или чай и любимая музыка."
)

DEFAULT_SETTINGS: dict[str, str] = {
    "studio_name": "BEAUTY STUDIO",
    "master_name": "Алина",
    "about_text": DEFAULT_ABOUT,
    "address_text": "г. Москва, ул. Пример, 1, студия 12",
    "address_hint": "Вход со двора, домофон 12. Рядом бесплатная парковка 🤍",
    "map_url": "",
    "contact_username": "",
    "contact_phone": "",
    "contact_text": "Пиши мне по любым вопросам: подбор дизайна, свободные окошки, уход за ноготками ♡",
    "channel_id": "",
    "channel_url": "",
    "sub_required": "1",
    "work_start": "10:00",
    "work_end": "20:00",
    "slot_step": "30",
    "work_days": "0,1,2,3,4,5",
    "horizon_days": "45",
    "min_lead_min": "120",
    "cancel_min_hours": "3",
    "auto_confirm": "0",
    "remind_24": "1",
    "remind_2": "1",
    "review_delay_hours": "3",
}

CATEGORIES = [
    # id, title, emoji, группа для записи, сортировка
    ("mani", "Маникюр", "💅", "mani", 1),
    ("pedi", "Педикюр", "🦶", "pedi", 2),
    ("ext", "Наращивание", "💎", "mani", 3),
    ("combo", "Комплекс", "🎀", "combo", 4),
    ("design", "Дизайн", "🎨", "extra", 5),
    ("extra", "Доп. услуги", "✨", "extra", 6),
]

SERVICES = [
    ("mani", "Маникюр с покрытием", "Аппаратно-комбинированный маникюр, выравнивание и стойкое покрытие гель-лаком. Держится 3–4 недели.", 2000, 0, 120),
    ("mani", "Маникюр без покрытия", "Бережная обработка кутикулы, форма, уход и масло. Для натуральной ухоженности.", 1000, 0, 60),
    ("mani", "Снятие + маникюр", "Снятие старого покрытия и аккуратный маникюр без покрытия.", 1300, 0, 75),
    ("mani", "Укрепление ногтей", "Маникюр, укрепление базой или гелем и покрытие. Для тонких и ломких ногтей.", 2400, 0, 140),
    ("ext", "Наращивание ногтей", "Наращивание на верхние формы любой длины и формы: миндаль, овал, квадрат.", 3200, 0, 180),
    ("ext", "Коррекция наращивания", "Коррекция отросших ногтей, восстановление архитектуры и новое покрытие.", 2600, 0, 150),
    ("pedi", "Педикюр с покрытием", "Аппаратный педикюр пальчиков и стоп, покрытие гель-лаком.", 2500, 0, 120),
    ("pedi", "Педикюр без покрытия", "Обработка пальчиков, кутикулы и формы, уход.", 1700, 0, 75),
    ("pedi", "Обработка стоп", "Аппаратная обработка стоп, удаление натоптышей, мягкий уход.", 1200, 0, 45),
    ("combo", "Маникюр + педикюр с покрытием", "Комплекс в 4 руки времени: идеально перед отпуском или праздником.", 4200, 0, 210),
    ("design", "Дизайн ногтей", "Втирка, стемпинг, наклейки, слайдеры, рисунок — цена зависит от сложности.", 300, 1, 20),
    ("design", "Френч", "Классический или цветной френч на все ногти.", 500, 0, 30),
    ("extra", "Снятие покрытия", "Аккуратное снятие гель-лака без вреда ногтю.", 300, 0, 20),
    ("extra", "Парафинотерапия рук", "Тёплый парафин, увлажнение и мягкость кожи.", 500, 0, 20),
]

PORTFOLIO_SECTIONS = [
    ("nude", "Нюдовый", "🤍"),
    ("french", "Французский", "🕊"),
    ("red", "Красный", "🍒"),
    ("design", "Дизайн", "🎨"),
    ("ext", "Наращивание", "💎"),
    ("pedi", "Педикюр", "🦶"),
    ("ba", "До/После", "✨"),
]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._settings: dict[str, str] = {}

    # ---------- низкий уровень ----------
    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path, isolation_level=None)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA busy_timeout=10000")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.executescript(SCHEMA)
        await self._seed()
        await self.reload_settings()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    @asynccontextmanager
    async def _guard(self) -> AsyncIterator[None]:
        if self._owner is asyncio.current_task():
            yield
            return
        async with self.lock:
            yield

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[aiosqlite.Connection]:
        """Эксклюзивная транзакция. Внутри неё можно вызывать любые методы DB."""
        async with self.lock:
            self._owner = asyncio.current_task()
            try:
                await self.conn.execute("BEGIN IMMEDIATE")
                try:
                    yield self.conn
                except BaseException:
                    await self.conn.execute("ROLLBACK")
                    raise
                else:
                    await self.conn.execute("COMMIT")
            finally:
                self._owner = None

    async def execute(self, sql: str, params: tuple | list = ()) -> int:
        async with self._guard():
            cur = await self.conn.execute(sql, params)
            rowid = cur.lastrowid
            await cur.close()
            return rowid

    async def execute_rc(self, sql: str, params: tuple | list = ()) -> int:
        """Выполнить и вернуть число изменённых строк."""
        async with self._guard():
            cur = await self.conn.execute(sql, params)
            n = cur.rowcount
            await cur.close()
            return n

    async def fetchone(self, sql: str, params: tuple | list = ()) -> dict | None:
        async with self._guard():
            cur = await self.conn.execute(sql, params)
            row = await cur.fetchone()
            await cur.close()
            return dict(row) if row else None

    async def fetchall(self, sql: str, params: tuple | list = ()) -> list[dict]:
        async with self._guard():
            cur = await self.conn.execute(sql, params)
            rows = await cur.fetchall()
            await cur.close()
            return [dict(r) for r in rows]

    async def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        row = await self.fetchone(sql, params)
        return next(iter(row.values())) if row else None

    # ---------- начальные данные ----------
    async def _seed(self) -> None:
        for k, v in DEFAULT_SETTINGS.items():
            await self.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        for cid, title, emoji, group, sort in CATEGORIES:
            await self.execute(
                "INSERT OR IGNORE INTO categories(id, title, emoji, book_group, sort) VALUES(?,?,?,?,?)",
                (cid, title, emoji, group, sort),
            )
        if not await self.scalar("SELECT COUNT(*) FROM services"):
            for i, (cat, title, desc, price, pfrom, dur) in enumerate(SERVICES):
                await self.execute(
                    "INSERT INTO services(category, title, description, price, price_from, duration, sort, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (cat, title, desc, price, pfrom, dur, i, now_str()),
                )

    # ---------- настройки ----------
    async def reload_settings(self) -> None:
        rows = await self.fetchall("SELECT key, value FROM settings")
        self._settings = {r["key"]: r["value"] for r in rows}

    def get(self, key: str, default: str = "") -> str:
        return self._settings.get(key, DEFAULT_SETTINGS.get(key, default))

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, str(default)))
        except ValueError:
            return default

    def flag(self, key: str) -> bool:
        return self.get(key, "0") == "1"

    async def set(self, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._settings[key] = value

    # ---------- журнал действий ----------
    async def log(self, user_id: int | None, action: str, **data: Any) -> None:
        await self.execute(
            "INSERT INTO events(user_id, action, data, created_at) VALUES(?,?,?,?)",
            (user_id, action, json.dumps(data, ensure_ascii=False, default=str) if data else None, now_str()),
        )

    # ---------- пользователи ----------
    async def touch_user(self, user_id: int, username: str | None, first_name: str | None) -> dict:
        ts = now_str()
        await self.execute(
            "INSERT INTO users(id, username, first_name, created_at, last_seen) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, "
            "last_seen=excluded.last_seen, blocked=0",
            (user_id, username, first_name, ts, ts),
        )
        return await self.user(user_id)

    async def user(self, user_id: int) -> dict | None:
        return await self.fetchone("SELECT * FROM users WHERE id=?", (user_id,))

    async def save_contacts(self, user_id: int, name: str, phone: str) -> None:
        await self.execute("UPDATE users SET name=?, phone=? WHERE id=?", (name, phone, user_id))

    # ---------- категории и услуги ----------
    async def categories(self) -> list[dict]:
        return await self.fetchall("SELECT * FROM categories ORDER BY sort")

    async def category(self, cid: str) -> dict | None:
        return await self.fetchone("SELECT * FROM categories WHERE id=?", (cid,))

    async def services(self, category: str | None = None, group: str | None = None, include_hidden: bool = False) -> list[dict]:
        sql = "SELECT s.* FROM services s JOIN categories c ON c.id=s.category WHERE 1=1"
        params: list = []
        if not include_hidden:
            sql += " AND s.active=1"
        if category:
            sql += " AND s.category=?"
            params.append(category)
        if group:
            sql += " AND c.book_group=?"
            params.append(group)
        sql += " ORDER BY c.sort, s.sort, s.id"
        return await self.fetchall(sql, params)

    async def service(self, sid: int) -> dict | None:
        return await self.fetchone("SELECT * FROM services WHERE id=?", (sid,))

    # ---------- записи ----------
    async def booking(self, bid: int) -> dict | None:
        return await self.fetchone("SELECT * FROM bookings WHERE id=?", (bid,))

    async def user_bookings(self, user_id: int, active: bool = True) -> list[dict]:
        if active:
            return await self.fetchall(
                "SELECT * FROM bookings WHERE user_id=? AND status IN ('pending','confirmed') ORDER BY start", (user_id,)
            )
        return await self.fetchall(
            "SELECT * FROM bookings WHERE user_id=? AND status NOT IN ('pending','confirmed') ORDER BY start DESC LIMIT 30",
            (user_id,),
        )

    async def set_status(self, bid: int, status: str, reason: str | None = None) -> None:
        await self.execute(
            "UPDATE bookings SET status=?, cancel_reason=COALESCE(?, cancel_reason), updated_at=? WHERE id=?",
            (status, reason, now_str(), bid),
        )

    # ---------- избранное ----------
    async def toggle_favorite(self, user_id: int, sid: int) -> bool:
        if await self.fetchone("SELECT 1 AS x FROM favorites WHERE user_id=? AND service_id=?", (user_id, sid)):
            await self.execute("DELETE FROM favorites WHERE user_id=? AND service_id=?", (user_id, sid))
            return False
        await self.execute("INSERT INTO favorites(user_id, service_id, created_at) VALUES(?,?,?)", (user_id, sid, now_str()))
        return True

    async def favorites(self, user_id: int) -> list[dict]:
        return await self.fetchall(
            "SELECT s.* FROM favorites f JOIN services s ON s.id=f.service_id WHERE f.user_id=? AND s.active=1 ORDER BY f.created_at DESC",
            (user_id,),
        )

    async def is_favorite(self, user_id: int, sid: int) -> bool:
        return bool(await self.fetchone("SELECT 1 AS x FROM favorites WHERE user_id=? AND service_id=?", (user_id, sid)))

    # ---------- портфолио ----------
    async def portfolio(self, section: str) -> list[dict]:
        return await self.fetchall("SELECT * FROM portfolio WHERE section=? ORDER BY id DESC", (section,))

    async def portfolio_counts(self) -> dict[str, int]:
        rows = await self.fetchall("SELECT section, COUNT(*) AS n FROM portfolio GROUP BY section")
        return {r["section"]: r["n"] for r in rows}

    # ---------- кэш file_id для сгенерированных обложек ----------
    async def cached_file(self, key: str) -> str | None:
        return await self.scalar("SELECT file_id FROM media_cache WHERE key=?", (key,))

    async def cache_file(self, key: str, file_id: str) -> None:
        await self.execute(
            "INSERT INTO media_cache(key, file_id) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET file_id=excluded.file_id",
            (key, file_id),
        )
