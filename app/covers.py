"""Генерация эстетичных обложек разделов (молочный / пудровый / шампань / золото).

Обложки рисуются один раз при старте и кладутся в data/covers. Мастер может заменить
любую обложку своим фото через админ-панель — тогда используется её фото.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import APP_DIR

FONTS = APP_DIR / "assets" / "fonts"
W, H = 1280, 800
SS = 2  # суперсэмплинг для гладких краёв

MILK = (251, 247, 244)
POWDER = (242, 220, 220)
PEARL = (244, 239, 236)
BEIGE = (233, 220, 207)
CHAMPAGNE = (232, 213, 181)
GOLD = (184, 151, 90)
INK = (74, 56, 52)

NAIL_PALETTES = {
    "nude": [(236, 205, 196), (226, 190, 178), (241, 216, 206), (219, 178, 166), (233, 200, 190)],
    "pink": [(240, 196, 200), (233, 176, 186), (246, 214, 214), (226, 160, 172), (238, 190, 196)],
    "red": [(150, 32, 46), (172, 40, 56), (128, 24, 38), (160, 36, 50), (140, 28, 42)],
    "french": [(244, 222, 216)] * 5,
    "milk": [(250, 244, 240), (246, 236, 230), (252, 248, 245), (243, 232, 226), (248, 240, 236)],
    "mocha": [(196, 160, 140), (178, 140, 120), (210, 178, 160), (188, 150, 130), (202, 168, 148)],
    "chrome": [(228, 214, 200), (238, 226, 214), (220, 204, 188), (234, 220, 206), (226, 212, 198)],
}

# ключ -> (заголовок, подзаголовок, палитра ногтей, вариант композиции)
COVERS: dict[str, tuple[str, str, str, str]] = {
    "welcome": ("beauty world", "nails · care · love", "nude", "fan"),
    "booking": ("Запись", "выбери свою процедуру", "pink", "fan"),
    "subscribe": ("Маленькая просьба", "подпишись на канал", "milk", "row"),
    "prices": ("Прайс-лист", "услуги и цены", "mocha", "row"),
    "portfolio": ("Портфолио", "мои работы", "red", "fan"),
    "about": ("Обо мне", "мастер маникюра", "nude", "row"),
    "address": ("Адрес студии", "жду тебя в гости", "chrome", "row"),
    "contact": ("Связь с мастером", "всегда на связи", "pink", "row"),
    "calendar": ("Выбери дату", "свободные окошки", "milk", "row"),
    "time": ("Выбери время", "только свободные слоты", "nude", "row"),
    "contacts": ("Твои контакты", "чтобы я могла связаться", "pink", "row"),
    "confirm": ("Почти готово", "проверь детали", "french", "fan"),
    "success": ("До встречи!", "запись создана", "pink", "fan"),
    "my": ("Мои записи", "визиты и история", "mocha", "row"),
    "reviews": ("Отзывы", "слова моих клиенток", "nude", "fan"),
    "favorites": ("Избранное", "любимые услуги", "pink", "row"),
    "cat_mani": ("Маникюр", "manicure", "nude", "fan"),
    "cat_pedi": ("Педикюр", "pedicure", "pink", "row"),
    "cat_ext": ("Наращивание", "extensions", "french", "fan"),
    "cat_combo": ("Комплекс", "manicure + pedicure", "mocha", "fan"),
    "cat_design": ("Дизайн", "nail art", "red", "fan"),
    "cat_extra": ("Доп. услуги", "care & extras", "milk", "row"),
    "pf_nude": ("Нюдовый", "portfolio", "nude", "fan"),
    "pf_french": ("Французский", "portfolio", "french", "fan"),
    "pf_red": ("Красный", "portfolio", "red", "fan"),
    "pf_design": ("Дизайн", "portfolio", "pink", "fan"),
    "pf_ext": ("Наращивание", "portfolio", "chrome", "fan"),
    "pf_pedi": ("Педикюр", "portfolio", "mocha", "row"),
    "pf_ba": ("До / После", "portfolio", "nude", "row"),
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size * SS)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _background(seed: int) -> Image.Image:
    """Фон считается в 1/4 разрешения (размытие дёшево) и масштабируется."""
    rnd = random.Random(seed)
    w, h = W // 4, H // 4
    base = Image.new("RGB", (w, h))
    px = base.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = _lerp(MILK, PEARL, x / w * 0.6 + y / h * 0.4)
    base = base.convert("RGBA")
    for color, alpha in ((POWDER, 170), (CHAMPAGNE, 120), (BEIGE, 80), (POWDER, 130)):
        r = rnd.randint(70, 120)
        cx, cy = rnd.randint(-20, w + 20), rnd.randint(-20, h + 20)
        layer = Image.new("RGBA", (w, h), (*color, 0))
        ImageDraw.Draw(layer).ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, alpha))
        base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(32)))
    return base.resize((W * SS, H * SS), Image.BICUBIC)


def _almond(length: float, width: float) -> list[tuple[float, float]]:
    """Контур миндалевидного ногтя; (0,0) — центр основания, кончик вверх (y<0)."""
    n = 48
    pts = []
    for i in range(n + 1):  # основание: дуга слева направо через низ
        a = math.pi * i / n
        pts.append((-width / 2 * math.cos(a), width * 0.42 * math.sin(a)))
    for i in range(1, n):  # правый бок вверх
        t = i / n
        pts.append((width / 2 * (1 - t ** 2.2) ** 0.75, -length * t))
    pts.append((0, -length))
    for i in range(n - 1, 0, -1):  # левый бок вниз
        t = i / n
        pts.append((-width / 2 * (1 - t ** 2.2) ** 0.75, -length * t))
    return pts


def _transform(pts, angle_deg, cx, cy):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def _local(pts, pad):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = int(min(xs) - pad), int(min(ys) - pad)
    size = (int(max(xs) - x0 + pad), int(max(ys) - y0 + pad))
    return [(x - x0, y - y0) for x, y in pts], (x0, y0), size


def _nail(canvas: Image.Image, cx, cy, length, width, angle, color, french=False, chrome=False):
    base = _almond(length, width)
    shape_g = _transform(base, angle, cx, cy)
    pad = 60 * SS
    shape, off, size = _local(shape_g, pad)
    # мягкая тень (размываем в уменьшенном виде)
    sh = Image.new("RGBA", (size[0] // 4, size[1] // 4), (110, 70, 60, 0))
    ImageDraw.Draw(sh).polygon([((x + 10 * SS) / 4, (y + 18 * SS) / 4) for x, y in shape], fill=(110, 70, 60, 75))
    sh = sh.filter(ImageFilter.GaussianBlur(4 * SS)).resize(size, Image.BICUBIC)
    canvas.alpha_composite(sh, off)
    layer = Image.new("RGBA", size, (*color, 0))
    d = ImageDraw.Draw(layer)
    d.polygon(shape, fill=(*color, 255))
    if french:
        tip = [(x, y) for x, y in base if y < -length * 0.7]
        tip, _, _ = _local(_transform(tip, angle, cx, cy), 0)
        tip_g = _transform([(x, y) for x, y in base if y < -length * 0.7], angle, cx, cy)
        d.polygon([(x - off[0], y - off[1]) for x, y in tip_g], fill=(253, 251, 249, 255))
    # объём: тонкий мягкий блик вдоль ногтя
    hl = Image.new("RGBA", size, (255, 255, 255, 0))
    streak = _transform([(-width * 0.2, -length * 0.12), (-width * 0.13, -length * 0.12),
                         (-width * 0.06, -length * 0.7), (-width * 0.1, -length * 0.66)], angle, cx, cy)
    ImageDraw.Draw(hl).polygon([(x - off[0], y - off[1]) for x, y in streak], fill=(255, 255, 255, 150 if chrome else 95))
    hl = hl.filter(ImageFilter.GaussianBlur(4 * SS))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(shape, fill=255)
    hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", size, 0), mask))
    layer.alpha_composite(hl)
    canvas.alpha_composite(layer, off)


def _sparkle(d: ImageDraw.ImageDraw, x, y, r, color=GOLD, alpha=200):
    d.polygon([(x, y - r), (x + r * 0.22, y - r * 0.22), (x + r, y), (x + r * 0.22, y + r * 0.22),
               (x, y + r), (x - r * 0.22, y + r * 0.22), (x - r, y), (x - r * 0.22, y - r * 0.22)], fill=(*color, alpha))


def _pearl(canvas, x, y, r):
    size = int(r * 2 + 40 * SS)
    ox, oy = int(x - size / 2), int(y - size / 2)
    c = size / 2
    sh = Image.new("RGBA", (size, size), (150, 110, 100, 0))
    ImageDraw.Draw(sh).ellipse((c - r + 4 * SS, c - r + 8 * SS, c + r + 4 * SS, c + r + 8 * SS), fill=(150, 110, 100, 60))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6 * SS)), (ox, oy))
    layer = Image.new("RGBA", (size, size), (250, 244, 240, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((c - r, c - r, c + r, c + r), fill=(250, 244, 240, 255))
    d.ellipse((c - r * 0.55, c - r * 0.65, c + r * 0.05, c - r * 0.05), fill=(255, 255, 255, 230))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.2 * SS)), (ox, oy))


def _frame(d: ImageDraw.ImageDraw):
    m = 34 * SS
    d.rectangle((m, m, W * SS - m, H * SS - m), outline=(*GOLD, 170), width=2 * SS)
    m2 = 44 * SS
    d.rectangle((m2, m2, W * SS - m2, H * SS - m2), outline=(*GOLD, 90), width=1 * SS)


def _text_center(d, y, text, font, fill, x_center=None):
    x_center = x_center if x_center is not None else W * SS / 2
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    d.text((x_center - w / 2 - bbox[0], y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def render_cover(key: str, title: str, subtitle: str, palette: str, layout: str) -> Image.Image:
    seed = sum(ord(c) for c in key)
    rnd = random.Random(seed)
    img = _background(seed)
    colors = NAIL_PALETTES.get(palette, NAIL_PALETTES["nude"])
    french = palette == "french"
    chrome = palette == "chrome"

    # композиция ногтей — справа, текст — слева
    if layout == "fan":
        base_x, base_y = 930 * SS, 760 * SS
        for i, ang in enumerate((-38, -19, 0, 19, 38)):
            L = (300 + (40 if i == 2 else 20 if i in (1, 3) else 0)) * SS
            Wd = 118 * SS
            rad = math.radians(ang)
            cx = base_x + math.sin(rad) * 210 * SS
            cy = base_y - math.cos(rad) * 210 * SS + 60 * SS
            _nail(img, cx, cy, L, Wd, ang, colors[i], french, chrome)
    else:
        for i in range(4):
            cx = (720 + i * 128) * SS
            cy = (650 - (i % 2) * 40) * SS
            _nail(img, cx, cy, 300 * SS, 110 * SS, rnd.uniform(-8, 8), colors[i], french, chrome)

    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for _ in range(3):
        _pearl(img, rnd.randint(560, 1180) * SS, rnd.randint(90, 260) * SS, rnd.randint(9, 16) * SS)
    for _ in range(5):
        _sparkle(d, rnd.randint(520, 1200) * SS, rnd.randint(80, 330) * SS, rnd.randint(8, 18) * SS, alpha=rnd.randint(140, 220))
    _frame(d)

    # типографика
    serif = _font("Cormorant-MediumItalic.ttf", 104 if len(title) < 13 else 84)
    small = _font("Manrope-SemiBold.ttf", 22)
    label = _font("Manrope-Medium.ttf", 20)
    x0 = 110 * SS
    d.text((x0, 150 * SS), "BEAUTY  STUDIO", font=label, fill=(*GOLD, 255))
    d.line((x0, 192 * SS, x0 + 70 * SS, 192 * SS), fill=(*GOLD, 200), width=2 * SS)
    words = title.split(" ")
    lines, cur = [], ""
    fw = lambda s: d.textbbox((0, 0), s, font=serif)[2]
    for w in words:
        test = (cur + " " + w).strip()
        if fw(test) > 560 * SS and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    lines.append(cur)
    y = 230 * SS
    for ln in lines:
        d.text((x0, y), ln, font=serif, fill=(*INK, 255))
        y += serif.size * 1.02
    d.text((x0 + 4 * SS, y + 26 * SS), subtitle.upper(), font=small, fill=(*INK, 150), spacing=8)
    img.alpha_composite(over)
    return img.convert("RGB").resize((W, H), Image.LANCZOS)


def ensure_covers(out_dir: Path, force: bool = False) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, (title, sub, pal, layout) in COVERS.items():
        p = out_dir / f"{key}.jpg"
        if force or not p.exists():
            render_cover(key, title, sub, pal, layout).save(p, "JPEG", quality=90, optimize=True, progressive=True)
        paths[key] = p
    return paths


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/covers")
    ensure_covers(target, force=True)
    print("covers ->", target)
