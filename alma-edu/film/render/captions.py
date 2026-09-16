#!/usr/bin/env python3
"""Burned-in AI disclosure + head/tail title cards.

Iddo's instruction, 2026-08-21: "make the movie with caption saying 'produced by
AI'".  So the disclosure is not a nicety here, it is the condition on which the
film exists.  It is rendered as RGBA PNGs and overlaid on EVERY frame, and the
head and tail cards state it in full.  There is deliberately no clean version.

Hebrew is laid out with python-bidi before it reaches PIL — PIL draws in logical
order, which renders Hebrew backwards.
"""
from __future__ import annotations

from pathlib import Path

from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 3840, 2160
HERE = Path(__file__).parent
OUT = HERE / "overlays"

EN = "PRODUCED BY AI"
HE = "הופק על ידי בינה מלאכותית"
SEP = "\u00b7"

FONT_HE = "C:/Windows/Fonts/arialbd.ttf"
FONT_EN = "C:/Windows/Fonts/arialbd.ttf"
FONT_LIGHT = "C:/Windows/Fonts/arial.ttf"


def he(s: str) -> str:
    return get_display(s)


def _shadowed(img: Image.Image, draw_fn) -> Image.Image:
    """Draw once into a black layer, blur it, then draw the real text on top —
    the strip has to stay legible over white walls AND over dusk concrete."""
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(sh), (0, 0, 0, 235))
    sh = sh.filter(ImageFilter.GaussianBlur(9))
    img.alpha_composite(sh)
    img.alpha_composite(sh)
    draw_fn(ImageDraw.Draw(img), (255, 255, 255, 242))
    return img


def strip() -> Path:
    """The always-on bar. Every frame of the film carries this."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = ImageFont.truetype(FONT_EN, 46)
    text = f"{EN}  {SEP}  {he(HE)}"
    y = H - 108

    band = Image.new("RGBA", (W, 150), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for i in range(150):
        bd.line([(0, i), (W, i)], fill=(0, 0, 0, int(96 * (i / 150) ** 1.4)))
    img.alpha_composite(band, (0, H - 150))

    def go(d: ImageDraw.ImageDraw, fill) -> None:
        d.text((W // 2, y), text, font=f, fill=fill, anchor="mm")

    _shadowed(img, go)
    OUT.mkdir(exist_ok=True)
    p = OUT / "disclosure_strip.png"
    img.save(p)
    return p


def card(path: Path, lines: list[tuple[str, int, bool]], bg=(14, 12, 10)) -> Path:
    """A full-screen card. lines = [(text, size, is_hebrew)]"""
    img = Image.new("RGBA", (W, H), bg + (255,))
    d = ImageDraw.Draw(img)
    total = sum(sz * 1.75 for _, sz, _ in lines)
    y = (H - total) / 2 + lines[0][1] * 0.8
    for text, sz, is_he in lines:
        f = ImageFont.truetype(FONT_HE if is_he else FONT_LIGHT, sz)
        d.text((W // 2, y), he(text) if is_he else text, font=f,
               fill=(246, 240, 228, 255), anchor="mm")
        y += sz * 1.75
    img.convert("RGB").save(path)
    return path


def head_card() -> Path:
    OUT.mkdir(exist_ok=True)
    p = OUT / "card_head.png"
    return card(p, [
        ("אותיות רצות", 168, True),
        ("LETTERS THAT RUN", 60, False),
        ("ALMIDO \u00b7 ALMA-EDU", 38, False),
        ("", 70, False),
        ("THIS FILM WAS PRODUCED BY AI.", 58, False),
        ("No real children were filmed. Every person and place shown is generated.", 38, False),
        ("הסרט הזה הופק על ידי בינה מלאכותית \u00b7 לא צולמו ילדים אמיתיים", 42, True),
    ])


def tail_card() -> Path:
    OUT.mkdir(exist_ok=True)
    p = OUT / "card_tail.png"
    return card(p, [
        ("PRODUCED BY AI", 78, False),
        ("הופק על ידי בינה מלאכותית", 66, True),
        ("", 30, False),
        ("Every frame is synthetic. No real child, teacher, school or place is depicted.", 38, False),
        ("The method shown is real · ALMIDO / ALMA-EDU", 38, False),
        ("אותיות רצות", 44, True),
        ("", 30, False),
        ("לזכרה של עלמה ז\"ל", 46, True),
    ])


if __name__ == "__main__":
    print(strip())
    print(head_card())
    print(tail_card())
