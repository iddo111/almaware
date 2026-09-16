#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_hayta_li_achot.py -- "היתה לי אחות"

Iddo said it in the middle of a run of joke slogans, 2026-08-27 07:20. It is not
one of them. It is עלמה ז״ל, the sister ALMAWARE is named for.

So the design does the opposite of every other shirt in this folder: no heavy
sans, no coral accent, no rule, no English. Frank Ruhl -- the Hebrew of books and
of stones -- set SMALL, with the whole print area left as air around it.
Understatement is the entire design. Anything louder would be a lie.

Her name is deliberately NOT on it. Whether עלמה's name goes on a shirt is
Iddo's decision alone, and a plain version has to exist first so he can decide
against the other one. The `--name` variant is built but not delivered.
"""
import sys
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

W, H = 2400, 2800
SERIF = "C:/Windows/Fonts/FrankRuhlHofshi-Regular.otf"
INK = (32, 30, 34, 255)
CREAM = (243, 239, 233, 255)


def he(s):
    return get_display(s)


def art(ink, with_name=False):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(SERIF, 250)
    t = he("היתה לי אחות")
    x0, y0, x1, y1 = d.textbbox((0, 0), t, font=f)
    w, h = x1 - x0, y1 - y0

    block = h
    if with_name:
        fn = ImageFont.truetype(SERIF, 86)
        tn = he("עלמה ז״ל")
        nx0, ny0, nx1, ny1 = d.textbbox((0, 0), tn, font=fn)
        block += 150 + (ny1 - ny0)

    y = (H - block) / 2
    d.text(((W - w) / 2 - x0, y - y0), t, font=f, fill=ink)
    if with_name:
        y += h + 150
        faint = (ink[0], ink[1], ink[2], 130)
        d.text(((W - (nx1 - nx0)) / 2 - nx0, y - ny0), tn, font=fn, fill=faint)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt); bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=95); bg.save(f"{name}.pdf", "PDF", resolution=300)


out(art(INK), (255, 255, 255), "SHIRT-hayta-li-achot-WHITE")
out(art(CREAM), (26, 25, 28), "SHIRT-hayta-li-achot-DARK")
out(art(INK, with_name=True), (255, 255, 255), "SHIRT-hayta-li-achot-WITH-NAME-WHITE")
print("done")
