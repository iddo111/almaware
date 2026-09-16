#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirt_democracy_lexicon.py -- "דמוקרטיה = שלטון העם", set as a dictionary entry.

Iddo, 2026-08-27 07:13: "לעשות כמו מילון עם המילה ביוונית".

The design accuses nobody. It quotes the definition and stops. Whatever the
wearer's country is doing supplies the punchline by itself, which is why this is
the strongest of the morning's ideas -- you cannot argue with a lexicon entry.
δημοκρατία < δῆμος (people) + κράτος (rule).
"""
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display
import arabic_reshaper

W, H = 2400, 2800
HE_B = "C:/Windows/Fonts/FrankRuhlHofshi-Bold.otf"
HE_R = "C:/Windows/Fonts/FrankRuhlHofshi-Regular.otf"
GR = "C:/Windows/Fonts/times.ttf"
GR_I = "C:/Windows/Fonts/timesi.ttf"
INK = (26, 26, 30, 255)
CORAL = (196, 79, 42, 255)
GREY = (122, 122, 132, 255)
CREAM = (247, 243, 236, 255)


def he(s):
    if any("؀" <= c <= "ۿ" for c in s):
        s = arabic_reshaper.reshape(s)
    return get_display(s)


ENTRIES = {
    "democratia": {
        "head": "דמוקרטיה", "greek": "δημοκρατία", "gram": "שם עצם, נקבה",
        "roots": [("δῆμος", "עם"), ("κράτος", "שלטון")],
        "lang": "יוונית:", "sense": "1. שלטון העם.", "note": None,
    },
    # The word everyone believes means chaos. an- + arkhos is "without a RULER",
    # not "without order" -- so the lexicon rehabilitates it without arguing.
    "anarchismos": {
        "head": "אנרכיזם", "greek": "ἀναρχία", "gram": "שם עצם, זכר",
        "roots": [("ἀν-", "בלי"), ("ἀρχός", "שליט")],
        "lang": "יוונית:", "sense": "1. חברה בלי שליט.", "note": "≠ אי־סדר. ≠ כאוס.",
    },
    # The pun Iddo built: dimokratia + חארטה (Israeli slang for hot air). He
    # caught the orthography himself, 07:21: a Hebrew form ending in -ה needs the
    # ta marbuta, so خرطة, not the bare root خرط. (Not a hamza -- that belongs
    # nowhere here.) The root خ-ر-ط "to talk nonsense" is solid; the precise
    # etymology of the Israeli slang is contested, so the entry prints the form
    # and claims nothing more.
    "demokharta": {
        "head": "דמוחארטה", "greek": "δῆμος + خرطة", "gram": "שם עצם, נקבה · עגה",
        "roots": [("δῆμος", "עם"), ("خرطة", "קשקוש")],
        "lang": "יוונית־ערבית:", "sense": "1. מה שמספרים לעם.", "note": "ר׳ דמוקרטיה.",
    },
}


def art(E, ink, accent, grey):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    R_EDGE = W - 210                      # right margin: a Hebrew page is right-set
    L_EDGE = 210

    f_head = ImageFont.truetype(HE_B, 300)
    # Times italic carries no Arabic -- an entry with an Arabic root gets the
    # roman cut, or the headword line renders as tofu boxes.
    has_ar = any("؀" <= c <= "ۿ" for c in E["greek"])
    f_grk = ImageFont.truetype(GR if has_ar else GR_I, 150)
    f_gram = ImageFont.truetype(HE_R, 92)
    f_ety = ImageFont.truetype(HE_R, 100)
    f_grk_s = ImageFont.truetype(GR, 100)
    f_sense = ImageFont.truetype(HE_B, 168)

    def right(t, f, y, fill, txt=None):
        s = txt if txt is not None else he(t)
        x0, y0, x1, y1 = d.textbbox((0, 0), s, font=f)
        d.text((R_EDGE - (x1 - x0) - x0, y - y0), s, font=f, fill=fill)
        return y1 - y0

    def measure(t, f, raw=False):
        s = he(t) if (raw and any("؀" <= c <= "ۿ" for c in t)) else (t if raw else he(t))
        x0, y0, x1, y1 = d.textbbox((0, 0), s, font=f)
        return x1 - x0, y1 - y0

    # --- lay the block out first so it can be centred as a whole
    hs = []
    hs.append(measure(E["head"], f_head)[1])
    hs.append(measure(E["greek"], f_grk, raw=True)[1])
    hs.append(measure(E["gram"], f_gram)[1])
    hs.append(max(measure("יוונית:", f_ety)[1],
                  measure(E["roots"][0][0], f_grk_s, raw=True)[1]))
    hs.append(measure(E["sense"], f_sense)[1])
    GAPS = [34, 70, 60, 96]
    RULE = 12
    extra = (measure(E["note"], f_gram)[1] + 46) if E["note"] else 0
    total = sum(hs) + sum(GAPS) + RULE + 70 + extra

    y = (H - total) / 2
    y += right(E["head"], f_head, y, ink) + GAPS[0]
    y += right(None, f_grk, y, accent, txt=he(E["greek"])
               if any("؀" <= c <= "ۿ" for c in E["greek"]) else E["greek"]) + GAPS[1]
    y += right(E["gram"], f_gram, y, grey) + GAPS[2]

    # etymology line, built right-to-left piece by piece so the Greek sits upright
    (g1, m1), (g2, m2) = E["roots"]
    parts = [(E["lang"] + " ", f_ety, grey, False),
             (g1, f_grk_s, ink, True),
             (f" ({m1}) + ", f_ety, grey, False),
             (g2, f_grk_s, ink, True),
             (f" ({m2})", f_ety, grey, False)]
    widths = [measure(t, f, raw=raw)[0] for t, f, _, raw in parts]
    x = R_EDGE
    base = y
    for (t, f, col, raw), wpt in zip(parts, widths):
        s = he(t) if (raw and any("؀" <= c <= "ۿ" for c in t)) else (t if raw else he(t))
        x0, y0, _, _ = d.textbbox((0, 0), s, font=f)
        x -= wpt
        d.text((x - x0, base - y0), s, font=f, fill=col)
    y += hs[3] + GAPS[3]

    d.rectangle([L_EDGE, y, R_EDGE, y + RULE], fill=ink)
    y += RULE + 70
    y += right(E["sense"], f_sense, y, ink)
    if E["note"]:
        right(E["note"], f_gram, y + 46, accent)
    return img


def out(a, shirt, name):
    a.save(f"{name}-print.png")
    bg = Image.new("RGB", (W, H), shirt); bg.paste(a, (0, 0), a)
    bg.save(f"{name}.jpg", quality=94); bg.save(f"{name}.pdf", "PDF", resolution=300)


for key, E in ENTRIES.items():
    out(art(E, INK, CORAL, GREY), (255, 255, 255), f"SHIRT-{key}-lexicon-WHITE")
    out(art(E, CREAM, (231, 122, 84, 255), (150, 146, 140, 255)),
        (24, 24, 28), f"SHIRT-{key}-lexicon-DARK")
print("done")
