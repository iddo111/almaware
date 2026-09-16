#!/usr/bin/env python3
"""Draw a REAL Hebrew aleph into a photographic plate.

LTX and FLUX both render Latin letters when asked for Hebrew ones (verified
2026-08-21: a prompt for a chalk aleph produced a prop reading "AH").  So the
glyph is never generated - it is drawn here from a real Hebrew font and
composited into the plate, and only then handed to image-to-video.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ALEF = "\u05d0"
FONT_CANDIDATES = [
    "C:/Windows/Fonts/david.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
]


def glyph_mask(size_px: int, font_path: str | None = None,
               char: str = ALEF) -> Image.Image:
    """Tight L-mode mask of the glyph, `size_px` tall, white on black."""
    path = font_path or next(p for p in FONT_CANDIDATES if _exists(p))
    # oversample then trim, so the mask is exactly the requested height
    f = ImageFont.truetype(path, int(size_px * 1.6))
    tmp = Image.new("L", (int(size_px * 3), int(size_px * 3)), 0)
    d = ImageDraw.Draw(tmp)
    d.text((int(size_px * 1.5), int(size_px * 1.5)), char, fill=255,
           font=f, anchor="mm")
    bb = tmp.getbbox()
    g = tmp.crop(bb)
    scale = size_px / g.height
    return g.resize((max(1, int(g.width * scale)), size_px), Image.LANCZOS)


def _exists(p: str) -> bool:
    try:
        open(p, "rb").close()
        return True
    except OSError:
        return False


def _noise(size: tuple[int, int], seed: int, blur: float = 1.2) -> Image.Image:
    rnd = random.Random(seed)
    n = Image.new("L", (size[0] // 4 or 1, size[1] // 4 or 1))
    n.putdata([rnd.randint(0, 255) for _ in range(n.width * n.height)])
    return n.resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(blur))


def _ragged(mask: Image.Image, seed: int, amount: float = 0.55) -> Image.Image:
    """Eat the edges of a mask with noise so it stops looking like vector art."""
    n = _noise(mask.size, seed, blur=1.0)
    n = n.point(lambda v: 255 if v > int(120 - 60 * amount) else 0)
    edge = mask.filter(ImageFilter.MaxFilter(5))
    edge = ImageChops.difference(edge, mask.filter(ImageFilter.MinFilter(5)))
    bite = ImageChops.multiply(edge, ImageChops.invert(n))
    return ImageChops.subtract(mask, bite)


def draw_chalk(plate: Image.Image, height_frac: float, centre: tuple[float, float],
               seed: int, opacity: float = 0.88, rotate: float = 0.0,
               chalk_rgb: tuple[int, int, int] = (247, 245, 238)) -> Image.Image:
    """Dry white chalk on a hard surface — bright, dusty, broken at the edges."""
    W, H = plate.size
    g = glyph_mask(int(H * height_frac), char=ALEF)
    g = _ragged(g, seed)
    # chalk is laid down unevenly: modulate the fill with low-frequency noise
    tex = _noise(g.size, seed + 7, blur=3.0).point(lambda v: 120 + v // 2)
    g = ImageChops.multiply(g, tex)
    g = g.filter(ImageFilter.GaussianBlur(max(1.0, H * 0.0012)))
    if rotate:
        g = g.rotate(rotate, resample=Image.BICUBIC, expand=True)

    layer = Image.new("RGB", g.size, chalk_rgb)
    out = plate.convert("RGB").copy()
    x = int(centre[0] * W - g.width / 2)
    y = int(centre[1] * H - g.height / 2)
    a = g.point(lambda v: int(v * opacity))
    out.paste(layer, (x, y), a)
    # a faint halo of chalk dust around the stroke
    halo = g.filter(ImageFilter.GaussianBlur(H * 0.010)).point(
        lambda v: int(v * 0.28 * opacity))
    out.paste(Image.new("RGB", g.size, chalk_rgb), (x, y), halo)
    return out


def draw_groove(plate: Image.Image, height_frac: float,
                centre: tuple[float, float], seed: int,
                depth: float = 0.75, rotate: float = 0.0,
                light: tuple[int, int] = (-1, -1),
                erode_frac: float = 0.0,
                dark: tuple[int, int, int] = (18, 12, 7),
                mid: tuple[int, int, int] = (26, 18, 11),
                lip_rgb: tuple[int, int, int] = (255, 240, 210),
                lip_a: float = 0.55) -> Image.Image:
    """A channel pressed or cut into a surface: dark in the cut, a lit lip on
    the light side.  Colours are parameterised so the same geometry serves
    carved olive wood and an impression pressed into pale dough."""
    W, H = plate.size
    g = glyph_mask(int(H * height_frac), char=ALEF)
    thin = g.filter(ImageFilter.MinFilter(3))
    g = ImageChops.blend(g, thin, 0.5)
    if erode_frac:
        g = _erode(g, int(H * height_frac * erode_frac))
    g = g.filter(ImageFilter.GaussianBlur(max(1.0, H * 0.0016)))
    if rotate:
        g = g.rotate(rotate, resample=Image.BICUBIC, expand=True)

    off = max(2, int(H * 0.004))
    shade = ImageChops.offset(g, -light[0] * off, -light[1] * off)
    lip = ImageChops.subtract(ImageChops.offset(g, light[0] * off, light[1] * off), g)
    lip = lip.filter(ImageFilter.GaussianBlur(off * 0.8))

    out = plate.convert("RGB").copy()
    x = int(centre[0] * W - g.width / 2)
    y = int(centre[1] * H - g.height / 2)
    out.paste(Image.new("RGB", g.size, mid),
              (x, y), shade.point(lambda v: int(v * depth)))
    out.paste(Image.new("RGB", g.size, dark),
              (x, y), g.point(lambda v: int(v * depth * 0.92)))
    out.paste(Image.new("RGB", g.size, lip_rgb),
              (x, y), lip.point(lambda v: int(v * lip_a)))
    return out


def _erode(mask: Image.Image, px: int) -> Image.Image:
    """Shrink a mask by roughly `px` pixels — a fingertip furrow is far thinner
    than a display font's stroke, and pasting the raw glyph reads as a cutout."""
    out = mask
    while px > 0:
        k = 5 if px >= 2 else 3
        out = out.filter(ImageFilter.MinFilter(k))
        px -= 2 if k == 5 else 1
    return out


def draw_trail(plate: Image.Image, height_frac: float,
               centre: tuple[float, float], seed: int,
               rotate: float = 0.0, erode_frac: float = 0.035,
               opacity: float = 0.72) -> Image.Image:
    """A finger-wide furrow ploughed through coarse salt: dark trail, bright banks."""
    W, H = plate.size
    g = glyph_mask(int(H * height_frac), char=ALEF)
    g = _erode(g, int(H * height_frac * erode_frac))
    g = _ragged(g, seed, amount=0.75)
    g = g.filter(ImageFilter.GaussianBlur(max(1.0, H * 0.0025)))
    if rotate:
        g = g.rotate(rotate, resample=Image.BICUBIC, expand=True)

    off = max(2, int(H * 0.004))
    core = _erode(g, max(1, int(H * 0.006)))
    banks = ImageChops.subtract(g.filter(ImageFilter.MaxFilter(9)), g)
    banks = ImageChops.multiply(banks, _noise(g.size, seed + 3, blur=1.2)
                                .point(lambda v: 120 + v // 2))
    grain = _noise(g.size, seed + 11, blur=0.8).point(lambda v: 150 + v // 3)

    out = plate.convert("RGB").copy()
    x = int(centre[0] * W - g.width / 2)
    y = int(centre[1] * H - g.height / 2)
    # the walls of the furrow: soft shadow, then the darker floor of the cut
    out.paste(Image.new("RGB", g.size, (150, 138, 124)), (x, y),
              ImageChops.multiply(g, grain).point(lambda v: int(v * opacity * 0.8)))
    out.paste(Image.new("RGB", g.size, (86, 74, 62)), (x, y),
              ImageChops.multiply(core, grain).point(lambda v: int(v * opacity)))
    out.paste(Image.new("RGB", g.size, (255, 253, 248)), (x, y),
              banks.point(lambda v: int(v * 0.8)))
    shadow = ImageChops.offset(g, off, off)
    out.paste(Image.new("RGB", g.size, (60, 50, 40)), (x, y),
              ImageChops.subtract(shadow, g).point(lambda v: int(v * 0.35)))
    return out


def draw_cut(plate: Image.Image, height_frac: float, centre: tuple[float, float],
             seed: int, rotate: float = 0.0) -> Image.Image:
    """A letter stamped clean out of a slab of dough."""
    W, H = plate.size
    g = glyph_mask(int(H * height_frac), char=ALEF)
    g = g.filter(ImageFilter.GaussianBlur(max(1.0, H * 0.0018)))
    if rotate:
        g = g.rotate(rotate, resample=Image.BICUBIC, expand=True)
    off = max(2, int(H * 0.006))
    rim = ImageChops.subtract(g.filter(ImageFilter.MaxFilter(7)), g)
    out = plate.convert("RGB").copy()
    x = int(centre[0] * W - g.width / 2)
    y = int(centre[1] * H - g.height / 2)
    out.paste(Image.new("RGB", g.size, (72, 54, 38)), (x, y),
              g.point(lambda v: int(v * 0.9)))
    out.paste(Image.new("RGB", g.size, (252, 246, 232)), (x, y),
              rim.point(lambda v: int(v * 0.5)))
    return out


STYLES = {"chalk": draw_chalk, "groove": draw_groove,
          "trail": draw_trail, "cut": draw_cut}


def apply(plate: Image.Image, style: str, **kw) -> Image.Image:
    return STYLES[style](plate, **kw)
