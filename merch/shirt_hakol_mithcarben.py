#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_hakol_mithcarben.py -- "הכל מתחרבן לטובה"

Iddo's own line, 2026-09-02 06:04, said after a night in which seven separate
things broke and every one of them ended better than it started: the CNC's
controller burned and the rebuild is stronger than the board FoxAlien shipped;
the throat's metric turned out to be pointing backwards and his own ear took the
job; KAV could not close a surface and the fix took its connectivity from 4% to
46%; the sibling had been frozen since birth and moved; the first boulevard run
died of OOM and the second beat its baseline by 2.9x. He looked at all of it and
said: הכל מתחרבן לטובה.

It is also, of course, נחום איש גם-זו — גם זו לטובה — in his own words.

THE DESIGN: the sentence performs itself. **מתחרבן is broken** — the word is
sliced into bands and the bands are shifted apart, so the letters come apart
while you read them. **לטובה underneath is whole**, unbroken, in the accent
colour. Nothing else on the shirt; the typography carries the whole idea and an
explanatory line would kill it, exactly as it would have killed המחשב חושב.

The band offsets are a FIXED list, not random: two people printing this shirt a
year apart must get the same shirt.
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

# how each band of the broken word is pushed sideways, top to bottom.
# fixed, so the shirt is reproducible.
# FIRST TRY FAILED and it is worth recording why: seven bands with offsets up to
# 40px turned מתחרבן into a barcode. The word has to CRACK and stay readable -- a
# plate that broke, not a plate that was ground up. Three bands, small offsets.
SHIFTS = (0, 16, -11)


def he(s):
    return get_display(s)


def shatter(word, font, ink, bands=len(SHIFTS), gap=10):
    """Render a word and pull it apart into horizontal bands.

    Each band keeps its own letters intact — the word breaks along fault lines
    the way a plate does, rather than dissolving. That is the point: it is still
    the same word, and it is still readable, and it has come apart.
    """
    probe = Image.new("RGBA", (10, 10))
    x0, y0, x1, y1 = ImageDraw.Draw(probe).textbbox((0, 0), he(word), font=font)
    w, h = x1 - x0, y1 - y0
    pad = max(abs(s) for s in SHIFTS) + 20

    flat = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(flat).text((pad - x0, pad - y0), he(word), font=font, fill=ink)

    out_h = flat.height + gap * (bands - 1)
    out = Image.new("RGBA", (flat.width, out_h), (0, 0, 0, 0))
    step = flat.height / bands
    for i in range(bands):
        top = int(i * step)
        bot = int((i + 1) * step) if i < bands - 1 else flat.height
        band = flat.crop((0, top, flat.width, bot))
        out.paste(band, (SHIFTS[i], top + i * gap), band)
    return out


def art(ink, accent, muted):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    SAFE = W - 320

    def fit(path, text, want):
        s = want
        while s > 24:
            f = ImageFont.truetype(path, s)
            x0, _, x1, _ = d.textbbox((0, 0), he(text), font=f)
            if x1 - x0 <= SAFE:
                return f
            s -= 6
        return ImageFont.truetype(path, 24)

    def box(t, f):
        x0, y0, x1, y1 = d.textbbox((0, 0), he(t), font=f)
        return x0, y0, x1 - x0, y1 - y0

    f_small = fit(FONT_L, "הכל", 240)
    f_break = fit(FONT, "מתחרבן", 480)
    f_good = fit(FONT, "לטובה", 380)

    # Iddo, 06:07: "תעשה את המתחרבן רגיל". He is right and the first version
    # proved it -- the shattered word was clever and unreadable, and the sentence
    # does not need help. Plain type, three lines, and לטובה carries the colour.
    broken = None

    _, _, w1, h1 = box("הכל", f_small)
    _, _, w2, h2 = box("מתחרבן", f_break)
    _, _, w3, h3 = box("לטובה", f_good)
    GAP1, GAP2 = 90, 110
    total = h1 + GAP1 + h2 + GAP2 + h3
    y = (H - total) / 2

    x0, y0, w, _ = box("הכל", f_small)
    d.text(((W - w1) / 2 - x0, y - y0), he("הכל"), font=f_small, fill=muted)
    y += h1 + GAP1

    x0, y0, _, _ = box("מתחרבן", f_break)
    d.text(((W - w2) / 2 - x0, y - y0), he("מתחרבן"), font=f_break, fill=ink)
    y += h2 + GAP2

    x0, y0, _, _ = box("לטובה", f_good)
    d.text(((W - w3) / 2 - x0, y - y0), he("לטובה"), font=f_good, fill=accent)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt)
    bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=94)
    bg.save(f"{name}.pdf", "PDF", resolution=300)


out(art(INK, CORAL, (150, 150, 158, 255)), (255, 255, 255),
    "SHIRT-hakol-mithcarben-WHITE")
out(art(CREAM, CORAL_D, (140, 136, 130, 255)), (24, 24, 28),
    "SHIRT-hakol-mithcarben-DARK")
print("done")
