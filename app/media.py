"""Фотографии: Telegram file_id или файлы, загруженные через веб-админку (upload:<имя>)."""
from __future__ import annotations

import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps

UPLOAD_PREFIX = "upload:"
MAX_SIDE = 2000
UPLOAD_DIR = Path("data/uploads")


def set_upload_dir(path: Path) -> None:
    global UPLOAD_DIR
    UPLOAD_DIR = path
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def is_upload(value: str | None) -> bool:
    return bool(value) and value.startswith(UPLOAD_PREFIX)


def upload_path(value: str) -> Path | None:
    name = value[len(UPLOAD_PREFIX):]
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    return UPLOAD_DIR / name


def url_of(value: str | None) -> str | None:
    """Публичный URL фото для Mini App."""
    if not value:
        return None
    if is_upload(value):
        return f"/uploads/{value[len(UPLOAD_PREFIX):]}"
    return f"/media/{value}"


def save_image(data: bytes) -> str:
    """Проверяет, что это картинка, поворачивает по EXIF, уменьшает до 2000px и сохраняет как JPEG."""
    img = Image.open(io.BytesIO(data))
    img.verify()  # бросит исключение, если файл не изображение
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    name = f"{secrets.token_hex(10)}.jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    img.save(UPLOAD_DIR / name, "JPEG", quality=88, optimize=True, progressive=True)
    return UPLOAD_PREFIX + name
