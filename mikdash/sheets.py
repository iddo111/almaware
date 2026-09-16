# -*- coding: utf-8 -*-
"""
Compose the Desktop deliverable: a PDF and a contact-sheet JPEG.

The standing law is JPEG + PDF on the Desktop, never a raw .html — so the page is
authored here and only the rendered pair is delivered.

Hebrew note: Pillow lays glyphs out in logical order, left to right, so a Hebrew
string comes out mirrored. `vis()` below reverses it into visual order and then
un-reverses any embedded Latin or digits. That is a small bidi approximation, not
a real one; it is correct for the short captions used here and is checked by eye.
"""
from __future__ import annotations
import json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STILLS = os.path.join(HERE, "stills")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

W, H = 2480, 1754                       # A4 landscape at 210 dpi
MARGIN = 96
INK = (26, 24, 20)
DIM = (110, 102, 90)
GOLD = (138, 106, 31)
AMBER = (194, 97, 10)
PAPER = (252, 250, 245)
LINE = (214, 205, 190)

F = "C:/Windows/Fonts/"
def font(name, size):
    return ImageFont.truetype(F + name, size)

HEB = re.compile(r"[\u0590-\u05FF]")
LATIN = re.compile(r"[A-Za-z0-9()\[\].,:;\-/×'\"]+")


def vis(s: str) -> str:
    """Hebrew logical order -> visual order, for Pillow."""
    if not HEB.search(s):
        return s
    return LATIN.sub(lambda m: m.group(0)[::-1], s[::-1])


def wrap(draw, text, ft, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=ft) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def page():
    im = Image.new("RGB", (W, H), PAPER)
    return im, ImageDraw.Draw(im)


def fit(img, box_w, box_h):
    r = min(box_w / img.width, box_h / img.height)
    return img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)


DISPUTES = [
 ("How big is a cubit?",
  "Yechezkel's is the LONG cubit of 7 handbreadths (40:5, 43:13). The handbreadth "
  "itself is disputed: R' Chaim Naeh 8.0 cm, Chazon Ish 9.6 cm. Taken: 8.0 cm."),
 ("42:16 — five hundred cubits, or five hundred REEDS?",
  "Ketiv says cubits, qere says hundreds-of-reeds. Both are used: the courts come out "
  "to 500 CUBITS from their own arithmetic; the 500-REED wall is modelled far off, as Rashi has it."),
 ("40:14 — 'and he made the posts, sixty cubits'",
  "Famously obscure; the Septuagint reads twenty. NOT USED — no element here derives "
  "from it. The gates close to 50 x 25 without it."),
 ("How thick is the porch's front wall?",
  "Yechezkel never says. Derived, not borrowed: 41:13's total of 100 minus the 94 he "
  "itemises leaves 6 — and 41:5 independently gives the house wall as 6."),
 ("How tall is any of it?",
  "Yechezkel gives ONE height in the whole survey (the outer wall, 40:5). Every other "
  "height is inferred, marked amber in the walkthrough, and listed in SOURCES.md."),
 ("Yechezkel's House does not sum the way Middot's does",
  "Middot 4:7 has a side chamber of 6 and a partition of 1; Yechezkel has 4 (41:5) and "
  "2 (41:3). Different buildings. This follows Yechezkel throughout."),
]


def title_page(checks, model):
    im, d = page()
    f_h1 = font("arialbd.ttf", 78)
    f_h1h = font("arialbd.ttf", 84)
    f_h2 = font("arialbd.ttf", 34)
    f_b = font("arial.ttf", 27)
    f_m = ImageFont.truetype(F + "consola.ttf", 24)
    f_s = font("arial.ttf", 22)

    y = MARGIN
    d.text((MARGIN, y), vis("סיור בבית המקדש העתידי"), INK, f_h1h); y += 96
    d.text((MARGIN, y), "A walk through the Temple of Yechezkel 40–43", INK, f_h1); y += 92
    d.text((MARGIN, y), "built only from the measurements the text itself states",
           DIM, font("arial.ttf", 36)); y += 74
    d.line([(MARGIN, y), (W - MARGIN, y)], LINE, 3); y += 44

    col2 = W // 2 + 40
    yl = y
    d.text((MARGIN, yl), "THE SCALE", GOLD, f_h2); yl += 50
    for t in [f"1 cubit = {model['cubit_m']:.3f} m — the long cubit of "
              f"{model['cubit_tefachim']} handbreadths (Yech 40:5, 43:13),",
              "at 8.0 cm to the handbreadth (R' Chaim Naeh). The Chazon Ish's 9.6 cm",
              "would give 0.672 m; one constant in temple.py switches it.",
              f"1 reed = {model['reed_cubits']} cubits = "
              f"{model['reed_cubits']*model['cubit_m']:.2f} m (Yech 40:5).",
              f"The blue figure inside the east gate is 1.80 m = "
              f"{model['person_cubits']:.2f} cubits."]:
        d.text((MARGIN, yl), t, INK, f_b); yl += 38
    yl += 22
    d.text((MARGIN, yl), "WHAT IS AND IS NOT IN THE TEXT", GOLD, f_h2); yl += 50
    for t in ["Yechezkel gives exactly ONE height in the whole survey: the outer",
              "wall, one reed (40:5). Every other height here is inferred and is",
              "marked as such. In the walkthrough, press I and every element",
              "carrying an inferred dimension lights up amber.",
              "SOURCES.md maps each measurement to its verse, and names each",
              "place the commentators disagree and which reading was taken."]:
        d.text((MARGIN, yl), t, INK, f_b); yl += 38

    yr = y
    d.text((col2, yr), "THE ARITHMETIC THE TEXT ASSERTS ABOUT ITSELF", GOLD, f_h2); yr += 46
    for t in ["Each line adds numbers Yechezkel states separately against a",
              "total Yechezkel also states separately. The build refuses to",
              "write any geometry if one of them fails."]:
        d.text((col2, yr), t, DIM, f_s); yr += 30
    yr += 14
    for name, got, want, ref, work in checks:
        ok = abs(got - want) < 1e-9
        d.text((col2, yr), name[:34], INK, font("arialbd.ttf", 24))
        d.text((col2, yr + 30), work, DIM, f_m)
        d.text((W - MARGIN - 250, yr + 12), f"= {got:g}", INK, font("arialbd.ttf", 28))
        d.text((W - MARGIN - 130, yr + 14), "MATCH" if ok else "FAIL",
               (34, 110, 70) if ok else (170, 30, 30), font("arialbd.ttf", 26))
        yr += 70

    yb = max(yl, yr) + 40
    d.line([(MARGIN, yb), (W - MARGIN, yb)], LINE, 3); yb += 34
    d.text((MARGIN, yb), "WHERE THE TEXT IS AMBIGUOUS — AND WHAT WAS CHOSEN", GOLD, f_h2)
    yb += 52
    f_q = font("arialbd.ttf", 25)
    f_a = font("arial.ttf", 24)
    cols = [MARGIN, W // 2 + 20]
    cw = W // 2 - MARGIN - 40
    for i, (q, a) in enumerate(DISPUTES):
        cx = cols[i % 2]
        cy = yb + (i // 2) * 132
        d.text((cx, cy), q, INK, f_q)
        yy = cy + 34
        for ln in wrap(d, a, f_a, cw)[:3]:
            d.text((cx, yy), ln, DIM, f_a); yy += 31

    d.text((MARGIN, H - MARGIN + 10),
           "Text: Tanach with Text Only, tanach.us — Public Domain.  "
           "Geometry: KAV.  Rendering: TZELEM.  Nothing was downloaded to build this.  "
           "Full mapping: SOURCES.md",
           DIM, f_s)
    return im


def view_page(v, n, total):
    im, d = page()
    f_h = font("arialbd.ttf", 52)
    f_hh = font("arialbd.ttf", 46)
    f_c = font("arial.ttf", 28)
    f_s = font("arial.ttf", 22)

    y = MARGIN - 20
    d.text((MARGIN, y), vis(v["he"]), INK, f_hh)
    d.text((W - MARGIN - 60, y + 8), f"{n}/{total}", DIM, font("arialbd.ttf", 34))
    y += 62
    d.text((MARGIN, y), v["en"], GOLD, f_h); y += 74

    big = fit(Image.open(v["truth"]), W - 2 * MARGIN, 1150)
    bx = (W - big.width) // 2
    d.rectangle([bx - 2, y - 2, bx + big.width + 1, y + big.height + 1], outline=LINE)
    im.paste(big, (bx, y))
    y += big.height + 34

    small = fit(Image.open(v["painted"]), 560, 315)
    sx = W - MARGIN - small.width
    im.paste(small, (sx, y))
    d.rectangle([sx - 2, y - 2, W - MARGIN + 1, y + small.height + 1], outline=LINE)
    d.text((sx, y + small.height + 10),
           "the same view through TZELEM's brushstrokes", DIM, f_s)

    tw = sx - MARGIN - 70
    cy = y + 6
    for ln in wrap(d, v["cap"], f_c, tw):
        d.text((MARGIN, cy), ln, INK, f_c); cy += 42
    return im


def main():
    views = json.load(open(os.path.join(STILLS, "views.json"), encoding="utf-8"))
    model = json.load(open(os.path.join(HERE, "web", "model.json"), encoding="utf-8"))
    sys.path.insert(0, HERE)
    import temple as T

    pages = [title_page(T.checks(), model)]
    for i, v in enumerate(views, 1):
        pages.append(view_page(v, i, len(views)))

    if os.environ.get("MIKDASH_DEBUG"):        # page proofs, only when asked for
        for i, pg in enumerate(pages):
            pg.save(os.path.join(STILLS, f"_page{i+1}.png"))
    pdf = os.path.join(DESKTOP, "MIKDASH-yechezkel.pdf")
    pages[0].save(pdf, save_all=True, append_images=pages[1:], resolution=210.0)
    print(f"PDF   {pdf}  ({len(pages)} pages, {os.path.getsize(pdf)/1e6:.1f} MB)")

    # contact sheet: the hero on top, the other four beneath
    CW, CH, PAD = 2480, 1900, 60
    sheet = Image.new("RGB", (CW, CH), PAPER)
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 40), vis("סיור בבית המקדש העתידי — יחזקאל מ׳–מ״ג"), INK, font("arialbd.ttf", 58))
    d.text((PAD, 106), "The future Temple, built from the text's own measurements  ·  "
                       "1 cubit = 0.56 m  ·  the blue figure is 1.80 m",
           DIM, font("arial.ttf", 28))
    hero = fit(Image.open(views[0]["truth"]), CW - 2 * PAD, 1330)
    hx = (CW - hero.width) // 2
    sheet.paste(hero, (hx, 160))
    d.rectangle([hx - 2, 158, hx + hero.width + 1, 161 + hero.height], outline=LINE)
    d.text((PAD, 160 + hero.height + 10), views[0]["en"], INK, font("arialbd.ttf", 26))
    tw = (CW - 2 * PAD - 3 * 20) // 4
    x, yy = PAD, 160 + hero.height + 66
    for v in views[1:]:
        t = fit(Image.open(v["truth"]), tw, 420)
        sheet.paste(t, (x, yy))
        d.rectangle([x - 2, yy - 2, x + t.width + 1, yy + t.height + 1], outline=LINE)
        d.text((x, yy + t.height + 8), v["en"][:48], DIM, font("arial.ttf", 22))
        x += tw + 20
    jpg = os.path.join(DESKTOP, "MIKDASH-yechezkel.jpg")
    sheet.save(jpg, quality=94, subsampling=0)
    print(f"JPEG  {jpg}  ({os.path.getsize(jpg)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
