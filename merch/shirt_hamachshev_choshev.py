#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_hamachshev_choshev.py -- "המחשב חושב"

Iddo's own line, 2026-08-27 07:07:
  "פעם היינו צוחקים אומרים המחשב חושב - היום זה אשכרה ככה."

The mark is the thinking indicator -- the burst that turns while a model works.
Drawn here as MY OWN radial burst, not Anthropic's trademarked asterisk: a burst
is an old, generic form, and the association does the work without copying a
logo he would then be selling.

The small line under it carries the whole joke, so the big line can stay flat.
"""
import math
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

W, H = 2400, 2800
FONT = "C:/Windows/Fonts/Rubik-Bold.ttf"
FONT_L = "C:/Windows/Fonts/Rubik-Regular.ttf"
INK = (26, 26, 30, 255)
CORAL = (196, 79, 42, 255)
CREAM = (247, 243, 236, 255)
CORAL_D = (231, 122, 84, 255)


def he(s):
    return get_display(s)


def burst(d, cx, cy, r_out, r_in, n, fill, phase=0.0):
    """A radial burst: n tapered rays. Ray k is drawn as a thin quadrilateral."""
    for k in range(n):
        a = phase + 2 * math.pi * k / n
        half = (math.pi / n) * 0.34          # ray thickness at the hub
        pts = [
            (cx + r_in * math.cos(a - half), cy + r_in * math.sin(a - half)),
            (cx + r_out * math.cos(a - half * 0.16), cy + r_out * math.sin(a - half * 0.16)),
            (cx + r_out * math.cos(a + half * 0.16), cy + r_out * math.sin(a + half * 0.16)),
            (cx + r_in * math.cos(a + half), cy + r_in * math.sin(a + half)),
        ]
        d.polygon(pts, fill=fill)


def art(ink, accent, muted):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    SAFE = W - 300

    def fit(path, text, want):
        s = want
        while s > 24:
            f = ImageFont.truetype(path, s)
            x0, _, x1, _ = d.textbbox((0, 0), he(text), font=f)
            if x1 - x0 <= SAFE:
                return f
            s -= 6
        return ImageFont.truetype(path, 24)

    # Iddo, 07:09: "רק תכתוב פשוט המחשב חושב...". Nothing under it -- the three
    # dots ARE the thinking indicator, and an explanation would kill them.
    BIG = "המחשב חושב..."
    f_big = fit(FONT, BIG, 520)

    def box(t, f):
        x0, y0, x1, y1 = d.textbbox((0, 0), he(t), font=f)
        return x0, y0, x1 - x0, y1 - y0

    _, _, _, h1 = box(BIG, f_big)
    R, GAP = 430, 230
    total = 2 * R + GAP + h1

    y = (H - total) / 2
    burst(d, W / 2, y + R, R, 78, 8, accent)                 # 8 rays, turning
    burst(d, W / 2, y + R, R * 0.62, 60, 8, accent, math.pi / 8)
    y += 2 * R + GAP

    x0, y0, w, _ = box(BIG, f_big)
    d.text(((W - w) / 2 - x0, y - y0), he(BIG), font=f_big, fill=ink)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt); bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=94); bg.save(f"{name}.pdf", "PDF", resolution=300)


out(art(INK, CORAL, (150, 150, 158, 255)), (255, 255, 255), "SHIRT-hamachshev-choshev-WHITE")
out(art(CREAM, CORAL_D, (140, 136, 130, 255)), (24, 24, 28), "SHIRT-hamachshev-choshev-DARK")
print("done")
