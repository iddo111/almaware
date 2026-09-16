#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_shiviti_claude.py -- "שיוויתי קלוד יוסג' לנגדי תמיד, פן יגמרו לי הטוקנס"

Iddo's line, 2026-08-28 08:38, on the form of the שִׁוִּיתִי plaque (Psalms 16:8),
the framed text hung in synagogues.

ONE DELIBERATE RESTRAINT: the plaque's FORM is kept -- frame, centred liturgical
setting, the verse's shape -- but the sacred Name's calligraphy is NOT imitated.
"קלוד יוסג'" is set as ordinary type. The joke lives in the structure; copying the
lettering of the Name would be a different act, and not a funny one.
"""
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

W, H = 2400, 2800
SERIF_B = "C:/Windows/Fonts/FrankRuhlHofshi-Bold.otf"
SERIF_R = "C:/Windows/Fonts/FrankRuhlHofshi-Regular.otf"
INK = (26, 24, 28)
CORAL = (196, 79, 42)
GOLD = (168, 132, 58)
CREAM = (247, 243, 236)


def he(s):
    return get_display(s)


def art(ink, accent, rule):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def fit(path, text, want, cap=W - 460):
        s = want
        while s > 24:
            f = ImageFont.truetype(path, s)
            x0, _, x1, _ = d.textbbox((0, 0), he(text), font=f)
            if x1 - x0 <= cap:
                return f
            s -= 6
        return ImageFont.truetype(path, 24)

    L1, L2, L3, L4 = "שיויתי", "קלוד יוסג'", "לנגדי תמיד", "פן יגמרו לי הטוקנס"
    f1 = fit(SERIF_R, L1, 190)
    f2 = fit(SERIF_B, L2, 330)
    f3 = fit(SERIF_R, L3, 190)
    f4 = fit(SERIF_R, L4, 122)

    def box(t, f):
        x0, y0, x1, y1 = d.textbbox((0, 0), he(t), font=f)
        return x0, y0, x1 - x0, y1 - y0

    hs = [box(t, f)[3] for t, f in ((L1, f1), (L2, f2), (L3, f3), (L4, f4))]
    G = [56, 56, 150]
    RULE_H = 6
    total = sum(hs) + sum(G) + RULE_H + 90

    top = (H - total) / 2
    # --- the frame: two rules, the plaque's edge, nothing ornate
    fx0, fx1 = 250, W - 250
    fy0, fy1 = top - 190, top + total + 190
    d.rounded_rectangle([fx0, fy0, fx1, fy1], radius=26, outline=rule, width=7)
    d.rounded_rectangle([fx0 + 22, fy0 + 22, fx1 - 22, fy1 - 22], radius=16,
                        outline=rule, width=3)

    def put(t, f, y, fill):
        x0, y0, w, h = box(t, f)
        d.text(((W - w) / 2 - x0, y - y0), he(t), font=f, fill=fill)
        return h

    y = top
    y += put(L1, f1, y, ink) + G[0]
    y += put(L2, f2, y, accent) + G[1]
    y += put(L3, f3, y, ink) + G[2]
    d.rounded_rectangle([(W - 620) / 2, y, (W + 620) / 2, y + RULE_H],
                        radius=3, fill=rule)
    y += RULE_H + 90
    put(L4, f4, y, ink)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt)
    bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=95)
    bg.save(f"{name}.pdf", "PDF", resolution=300)


out(art(INK, CORAL, GOLD), (255, 255, 255), "SHIRT-shiviti-claude-WHITE")
out(art(CREAM, (231, 122, 84), (198, 164, 92)), (24, 22, 26), "SHIRT-shiviti-claude-DARK")
print("done")
