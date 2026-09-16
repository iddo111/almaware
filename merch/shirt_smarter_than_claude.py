#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_smarter_than_claude.py -- "אתה לא יותר חכם מקלוד"

Iddo's line, 2026-08-27 06:57. Deadpan on purpose: the joke lands as a flat
statement of fact, so the type is set like a public notice, not a gag.

NO QR CODE -- his ruling the same morning, and he is right: a QR asks a stranger
to point a phone at your chest instead of talking to you, which is the opposite
of what the shirt is for. Evidence it works without one: two independent
approaches, the chess board (08-12) and a Claude shirt (08-27).
The QR belongs on the sticker you hand over AFTER the conversation.

Outputs, print-ready for Pongo Shirts (pongoshirts@gmail.com):
  PRINT  2400x2800 transparent PNG -- no white ink, for a white shirt
  DARK   the same art in cream, for a dark shirt
  PROOF  JPEG + PDF for Iddo's eye
"""
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

W, H = 2400, 2800
FONT = "C:/Windows/Fonts/Rubik-Bold.ttf"
FONT_L = "C:/Windows/Fonts/Rubik-Regular.ttf"

INK = (26, 26, 30, 255)          # near-black, the setup
CORAL = (196, 79, 42, 255)       # the punchline -- same family as the other shirt
CREAM = (247, 243, 236, 255)
CORAL_D = (231, 122, 84, 255)


def he(s):
    return get_display(s)


def draw_art(ink, accent, muted):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    SAFE = W - 300                       # print margin -- nothing may touch the edge

    def fit(path, text, want, cap=SAFE):
        """Largest size at which the line still fits the safe width."""
        size = want
        while size > 24:
            f = ImageFont.truetype(path, size)
            x0, _, x1, _ = d.textbbox((0, 0), he(text), font=f)
            if x1 - x0 <= cap:
                return f
            size -= 6
        return ImageFont.truetype(path, 24)

    f_big = fit(FONT, "אתה לא יותר חכם", 360)
    f_pun = fit(FONT, "מקלוד", 560)
    f_sml = fit(FONT_L, "YOU ARE NOT SMARTER THAN CLAUDE", 112)

    GAP1, GAP2, GAP3 = 150, 210, 130

    def box(text, font):
        x0, y0, x1, y1 = d.textbbox((0, 0), he(text), font=font)
        return x0, y0, x1 - x0, y1 - y0

    _, _, w1, h1 = box("אתה לא יותר חכם", f_big)
    _, _, w2, h2 = box("מקלוד", f_pun)
    _, _, w3, h3 = box("YOU ARE NOT SMARTER THAN CLAUDE", f_sml)
    total = h1 + GAP1 + h2 + GAP2 + 14 + GAP3 + h3

    def put(text, font, y, fill):
        x0, y0, w, h = box(text, font)
        d.text(((W - w) / 2 - x0, y - y0), he(text), font=font, fill=fill)
        return h

    y = (H - total) / 2                       # the block owns the print area
    y += put("אתה לא יותר חכם", f_big, y, ink) + GAP1
    y += put("מקלוד", f_pun, y, accent) + GAP2

    # a plain rule the width of the punchline -- a notice, not a poster
    d.rounded_rectangle([(W - w2) / 2, y, (W + w2) / 2, y + 14],
                        radius=7, fill=muted)
    y += 14 + GAP3
    put("YOU ARE NOT SMARTER THAN CLAUDE", f_sml, y, muted)
    return img


def proof(art, shirt_rgb, name):
    """Flatten onto a plain shirt-coloured field so Iddo sees the real thing."""
    bg = Image.new("RGB", (W, H), shirt_rgb)
    bg.paste(art, (0, 0), art)
    bg.save(f"{name}.jpg", quality=94)
    bg.convert("RGB").save(f"{name}.pdf", "PDF", resolution=300)
    return bg


light = draw_art(INK, CORAL, (150, 150, 158, 255))
light.save("SHIRT-lo-yoter-chacham-WHITE-print.png")
proof(light, (255, 255, 255), "SHIRT-lo-yoter-chacham-WHITE")

dark = draw_art(CREAM, CORAL_D, (140, 136, 130, 255))
dark.save("SHIRT-lo-yoter-chacham-DARK-print.png")
proof(dark, (24, 24, 28), "SHIRT-lo-yoter-chacham-DARK")
print("done")
