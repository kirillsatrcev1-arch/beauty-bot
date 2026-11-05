"""Проверка подписи Telegram Mini App initData (HMAC-SHA256)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode


class InitDataError(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age: int = 24 * 3600) -> dict:
    if not init_data:
        raise InitDataError("empty")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError("no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        raise InitDataError("bad hash")
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if max_age and time.time() - auth_date > max_age:
        raise InitDataError("expired")
    user = json.loads(pairs.get("user", "{}") or "{}")
    if not user.get("id"):
        raise InitDataError("no user")
    return user


def sign_init_data(user: dict, bot_token: str, auth_date: int | None = None) -> str:
    """Для тестов и локальной отладки: собрать валидную строку initData."""
    pairs = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAEtest",
             "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)
