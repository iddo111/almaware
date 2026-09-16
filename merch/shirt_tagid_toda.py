#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_tagid_toda.py -- "קמת בבוקר, עומד לך הזין — תגיד תודה. כל השאר בונוס."

Iddo's line, 2026-09-02 14:24. His words, verbatim, his shirt.

WHY THE TYPOGRAPHY IS BUILT THE WAY IT IS
------------------------------------------
The sentence is a joke with a hinge in it, so it is set in three beats and not
as one block of text:

    קמת בבוקר, עומד לך הזין      the setup   - quiet, regular weight
    תגיד תודה                    the punch   - huge, in the accent colour
    כל השאר בונוס                the landing - small, muted

Setting the whole thing at one size would flatten it into a paragraph and kill
the timing. A shirt is read at three metres by someone walking past: they get
the big words first and the small ones only if they keep looking, which is
exactly the order the joke wants.

The comma and the full stop are dropped from the artwork. Punctuation at 500px
reads as debris; the line breaks already do that work.

Same 2400x2800 transparent-background print file as every other shirt here, so
it drops straight into PONGO-PRINT-FILES.zip with no special handling.
"""
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

W, H = 2400, 2800
FONT = "C:/Windows/Fonts/Rubik-Bold.ttf"
FONT_L = "C:/Windows/Fonts/Rubik-Regular.ttf"

INK = (26, 26, 30, 255)
CORAL = (196, 79, 42, 255)
CREAM = (247, 243, 236, 255)
CORAL_D = (231, 122, 84, 255)

SETUP = "קמת בבוקר, עומד לך הזין"
PUNCH = "תגיד תודה"
LAND = "כל השאר בונוס"


def he(s):
    return get_display(s)


def _tools(d):
    SAFE = W - 300

    def fit(path, text, want):
        s = want
        while s > 20:
            f = ImageFont.truetype(path, s)
            x0, _, x1, _ = d.textbbox((0, 0), he(text), font=f)
            if x1 - x0 <= SAFE:
                return f
            s -= 6
        return ImageFont.truetype(path, 20)

    def box(t, f):
        x0, y0, x1, y1 = d.textbbox((0, 0), he(t), font=f)
        return x0, y0, x1 - x0, y1 - y0

    def line(t, f, y, fill):
        x0, y0, w, h = box(t, f)
        d.text(((W - w) / 2 - x0, y - y0), he(t), font=f, fill=fill)
        return h

    return fit, box, line


def art(ink, accent, muted):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fit, box, line = _tools(d)

    f_setup = fit(FONT_L, SETUP, 250)
    f_punch = fit(FONT, PUNCH, 660)
    f_land = fit(FONT_L, LAND, 190)

    _, _, _, h_setup = box(SETUP, f_setup)
    _, _, _, h_punch = box(PUNCH, f_punch)
    _, _, _, h_land = box(LAND, f_land)

    G1, G2 = 110, 130
    total = h_setup + G1 + h_punch + G2 + h_land
    y = (H - total) / 2

    y += line(SETUP, f_setup, y, ink) + G1
    y += line(PUNCH, f_punch, y, accent) + G2

    # a hairline above the landing, the width of the small line plus a margin.
    # It separates the coda from the punch without adding another word.
    _, _, w_land, _ = box(LAND, f_land)
    rule = min(w_land + 160, W - 300)
    ry = y - G2 / 2
    d.line([((W - rule) / 2, ry), ((W + rule) / 2, ry)], fill=muted, width=6)

    line(LAND, f_land, y, muted)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt)
    bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=94)
    bg.save(f"{name}.pdf", "PDF", resolution=300)
    print("wrote", name)


out(art(INK, CORAL, (150, 150, 158, 255)), (255, 255, 255), "SHIRT-tagid-toda-WHITE")
out(art(CREAM, CORAL_D, (140, 136, 130, 255)), (24, 24, 28), "SHIRT-tagid-toda-DARK")
print("done")
