#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_doctor_feelgood.py --  DOCTOR  ^   /   FEEL GOOD  v

Iddo, 2026-09-02 14:26: "DOCTOR וחץ למעלה FEEL GOOD חץ למטה".

The whole joke is the two arrows, so the arrows are the artwork and the words
are the caption -- not the other way round. They are drawn as POLYGONS, never as
a font glyph. An arrow taken from a typeface is at the mercy of whatever fallback
the print shop has installed, and a missing glyph prints as a hollow box; a
polygon is the same shape on every machine on earth. The same reasoning is why
the Hebrew on the other shirts is flattened to shapes before it leaves here.

The two arrows are deliberately NOT mirror images. The upper one is drawn
slightly shorter and lighter than the lower one, so the eye lands on DOCTOR
first and travels down. Perfect symmetry would make the two halves compete and
the gag would arrive in whichever order the reader happened to start.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 2400, 2800
FONT = "C:/Windows/Fonts/Rubik-Bold.ttf"

INK = (26, 26, 30, 255)
CORAL = (196, 79, 42, 255)
CREAM = (247, 243, 236, 255)
CORAL_D = (231, 122, 84, 255)

TOP = "DOCTOR"
BOTTOM = "FEEL GOOD"


def _fit(d, text, want, safe):
    s = want
    while s > 20:
        f = ImageFont.truetype(FONT, s)
        x0, _, x1, _ = d.textbbox((0, 0), text, font=f)
        if x1 - x0 <= safe:
            return f
        s -= 6
    return ImageFont.truetype(FONT, 20)


def _centre(d, text, f, y, fill):
    x0, y0, x1, y1 = d.textbbox((0, 0), text, font=f)
    d.text(((W - (x1 - x0)) / 2 - x0, y - y0), text, font=f, fill=fill)
    return y1 - y0


def _arrow(d, cx, top, height, shaft_w, head_w, head_h, fill, down):
    """A solid block arrow, drawn as one polygon. `down` flips it."""
    bot = top + height
    hw, hh = head_w / 2.0, head_h
    sw = shaft_w / 2.0
    if not down:
        pts = [(cx, top),                       # tip
               (cx + hw, top + hh),
               (cx + sw, top + hh),
               (cx + sw, bot),
               (cx - sw, bot),
               (cx - sw, top + hh),
               (cx - hw, top + hh)]
    else:
        pts = [(cx, bot),                       # tip
               (cx + hw, bot - hh),
               (cx + sw, bot - hh),
               (cx + sw, top),
               (cx - sw, top),
               (cx - sw, bot - hh),
               (cx - hw, bot - hh)]
    d.polygon(pts, fill=fill)


def art(ink, accent):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    SAFE = W - 300

    f_top = _fit(d, TOP, 460, SAFE)
    f_bot = _fit(d, BOTTOM, 460, SAFE)

    def th(t, f):
        x0, y0, x1, y1 = d.textbbox((0, 0), t, font=f)
        return y1 - y0

    h_top, h_bot = th(TOP, f_top), th(BOTTOM, f_bot)

    UP_H, DN_H = 300, 380          # the lower arrow is the longer one, on purpose
    G = 90
    total = h_top + G + UP_H + G + h_bot + G + DN_H
    y = (H - total) / 2

    y += _centre(d, TOP, f_top, y, ink) + G
    _arrow(d, W / 2, y, UP_H, 90, 250, 150, ink, down=False)
    y += UP_H + G
    y += _centre(d, BOTTOM, f_bot, y, accent) + G
    _arrow(d, W / 2, y, DN_H, 110, 300, 190, accent, down=True)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt)
    bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=94)
    bg.save(f"{name}.pdf", "PDF", resolution=300)
    print("wrote", name)


out(art(INK, CORAL), (255, 255, 255), "SHIRT-doctor-feelgood-WHITE")
out(art(CREAM, CORAL_D), (24, 24, 28), "SHIRT-doctor-feelgood-DARK")
print("done")
