"""FSM-хранилище в той же SQLite: незавершённая запись переживает перезапуск бота."""
from __future__ import annotations

import json
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from .db import DB


def _key(k: StorageKey) -> str:
    return f"{k.bot_id}:{k.chat_id}:{k.user_id}:{k.thread_id or 0}:{k.destiny}"


class SQLiteStorage(BaseStorage):
    def __init__(self, db: DB):
        self.db = db
        self._ready = False

    async def _ensure(self) -> None:
        if not self._ready:
            await self.db.execute("CREATE TABLE IF NOT EXISTS fsm(key TEXT PRIMARY KEY, state TEXT, data TEXT NOT NULL DEFAULT '{}')")
            self._ready = True

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._ensure()
        value = state.state if isinstance(state, State) else state
        await self.db.execute("INSERT INTO fsm(key, state) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET state=excluded.state",
                              (_key(key), value))

    async def get_state(self, key: StorageKey) -> str | None:
        await self._ensure()
        return await self.db.scalar("SELECT state FROM fsm WHERE key=?", (_key(key),))

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._ensure()
        await self.db.execute("INSERT INTO fsm(key, data) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET data=excluded.data",
                              (_key(key), json.dumps(dict(data), ensure_ascii=False, default=str)))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        await self._ensure()
        raw = await self.db.scalar("SELECT data FROM fsm WHERE key=?", (_key(key),))
        return json.loads(raw) if raw else {}

    async def close(self) -> None:
        pass
