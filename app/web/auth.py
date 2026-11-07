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


# ---------- сессии веб-админки (вход по одноразовой ссылке из бота) ----------
def _sig(secret: str, payload: str) -> str:
    key = hashlib.sha256(("admin-session:" + secret).encode()).digest()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:40]


def sign_admin_token(user_id: int, bot_token: str, ttl: int, kind: str = "s") -> str:
    payload = f"{kind}.{user_id}.{int(time.time()) + ttl}"
    return f"{payload}.{_sig(bot_token, payload)}"


def verify_admin_token(token: str, bot_token: str, kind: str = "s") -> int | None:
    try:
        k, uid, exp, sig = token.split(".")
    except ValueError:
        return None
    payload = f"{k}.{uid}.{exp}"
    if k != kind or not hmac.compare_digest(sig, _sig(bot_token, payload)) or int(exp) < time.time():
        return None
    return int(uid)


def ics_sig(booking_id: int, bot_token: str) -> str:
    return _sig(bot_token, f"ics:{booking_id}")[:16]
