#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_murphy.py -- "מרפי צדק"  and  "כוס אימא של מרפי"

Iddo, 2026-09-02 06:06, after a night of being proved right by a sceptic.

MURPHY is not only the law here. It is an ORGAN in this lab: a witness that runs
at the end of every round in three of ERAN's organs and asks one question — did
you fool yourself? It answers with named witnesses, and tonight it was right
every single time:

  * on the throat search it ruled FOOLING ITSELF (below_floor, circularity,
    unlooked) — and then Iddo judged three clips blind and the metric turned out
    to be exactly backwards, its best sound being noise to his ear.
  * on SARID it refused the round: no headroom, the learnable object is the bug.
  * `unlooked` — "it made something and no person ever looked at what it made" —
    turned out to be the missing measurement of the whole project.

So the first shirt carries the three witnesses in small type under the line.
Anyone who knows what they mean is inside the joke; anyone who does not just
reads three English words and a Hebrew sentence, which is the right amount.

The second shirt is the other half of the same feeling, in the language a man
uses at six in the morning when the sceptic has been right all night. His line,
his shirt.
"""
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

W, H = 2400, 2800
FONT = "C:/Windows/Fonts/Rubik-Bold.ttf"
FONT_L = "C:/Windows/Fonts/Rubik-Regular.ttf"
MONO = "C:/Windows/Fonts/consola.ttf"
INK = (26, 26, 30, 255)
CORAL = (196, 79, 42, 255)
CREAM = (247, 243, 236, 255)
CORAL_D = (231, 122, 84, 255)

WITNESSES = "below_floor · circularity · unlooked"


def he(s):
    return get_display(s)


def _tools(d):
    SAFE = W - 320

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


def art_tzadak(ink, accent, muted):
    """מרפי צדק — the line, and the three witnesses under it."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fit, box, line = _tools(d)

    f_big = fit(FONT, "מרפי צדק", 560)
    f_wit = ImageFont.truetype(MONO, 86)

    _, _, _, h_big = box("מרפי צדק", f_big)
    x0, y0, x1, y1 = d.textbbox((0, 0), WITNESSES, font=f_wit)
    w_wit, h_wit = x1 - x0, y1 - y0

    GAP = 150
    y = (H - (h_big + GAP + h_wit)) / 2
    y += line("מרפי צדק", f_big, y, ink) + GAP
    d.text(((W - w_wit) / 2 - x0, y - y0), WITNESSES, font=f_wit, fill=muted)
    return img


def art_kus(ink, accent, muted):
    """The other half, in the language of six in the morning."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fit, box, line = _tools(d)

    top, bottom = "כוס אימא", "של מרפי"
    f1 = fit(FONT_L, top, 360)
    f2 = fit(FONT, bottom, 520)
    _, _, _, h1 = box(top, f1)
    _, _, _, h2 = box(bottom, f2)

    GAP = 70
    y = (H - (h1 + GAP + h2)) / 2
    y += line(top, f1, y, muted) + GAP
    line(bottom, f2, y, accent)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt)
    bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=94)
    bg.save(f"{name}.pdf", "PDF", resolution=300)


for maker, stem in ((art_tzadak, "SHIRT-murphy-tzadak"),
                    (art_kus, "SHIRT-murphy-kus")):
    out(maker(INK, CORAL, (150, 150, 158, 255)), (255, 255, 255), stem + "-WHITE")
    out(maker(CREAM, CORAL_D, (140, 136, 130, 255)), (24, 24, 28), stem + "-DARK")
print("done")
