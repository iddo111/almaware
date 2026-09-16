"""alma-figure / make_sheet.py — the printable handout: JPEG + PDF, bright, for the Desktop.

Workspace law: deliverables land on the Desktop as JPEG + PDF, never as a raw .html and
never as a bare C:\\ path pasted into chat. Composed directly with PIL because that is
what reliably renders here — no browser, no headless Chrome, no CDN.
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(os.path.expanduser("~"), "Desktop")

PAPER = (253, 252, 248)
INK = (22, 24, 28)
MUTE = (128, 134, 142)
TEAL = (13, 130, 120)
WARM = (216, 118, 42)
RULE = (226, 224, 216)

F = {"blk": "C:/Windows/Fonts/ariblk.ttf",
     "bd": "C:/Windows/Fonts/arialbd.ttf",
     "rg": "C:/Windows/Fonts/arial.ttf"}


def font(k, px):
    return ImageFont.truetype(F[k], int(px))


def heb(s: str) -> str:
    """PIL has no bidi engine. Reverse the Hebrew run so it reads right-to-left."""
    return s[::-1]


def main() -> int:
    W, H = 2000, 2828                       # A4 ratio at ~240 dpi
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    M = 110

    # ---- header ----
    d.text((M, 96), "ALMA FIGURE", font=font("blk", 104), fill=INK)
    d.text((M, 214), "caricature bobblehead  ·  Iddo Perez", font=font("bd", 44), fill=TEAL)
    d.text((W - M - 330, 120), heb("דמות עידו"), font=font("bd", 58), fill=MUTE)
    d.line([(M, 300), (W - M, 300)], fill=RULE, width=4)

    # ---- the four views ----
    views = Image.open(os.path.join(HERE, "iddo-figure.png"))
    vw = W - 2 * M
    vh = int(views.height * vw / views.width)
    img.paste(views.resize((vw, vh), Image.LANCZOS), (M, 340))
    y = 340 + vh + 40

    # ---- what was exaggerated ----
    d.text((M, y), "WHAT IS EXAGGERATED — and why it is affectionate",
           font=font("blk", 50), fill=INK)
    y += 78
    d.text((M, y), "A caricature is warm when it exaggerates what a friend would recognise "
                   "across a room,", font=font("rg", 34), fill=INK)
    y += 46
    d.text((M, y), "and cruel when it exaggerates what someone would rather you had not "
                   "noticed. Everything", font=font("rg", 34), fill=INK)
    y += 46
    d.text((M, y), "below is off the first list, read straight from your own head-scan video.",
           font=font("rg", 34), fill=INK)
    y += 76

    rows = [
        ("The bald dome", "41% of total height. The single most recognisable thing about you."),
        ("The eyebrows", "Thickest exaggeration on the figure. You talk with them."),
        ("The nose", "Strong and generous, rounded at the tip — never beaked."),
        ("The grin", "You are mid-laugh in nearly every frame of that clip."),
        ("The hands", "Oversized. You build things; the figure should say so."),
        ("The ears", "Slightly proud of the skull, level with the eyes."),
    ]
    for name, why in rows:
        d.ellipse([M + 6, y + 14, M + 22, y + 30], fill=WARM)
        d.text((M + 44, y), name, font=font("bd", 36), fill=INK)
        d.text((M + 420, y), why, font=font("rg", 33), fill=(70, 74, 80))
        y += 56

    y += 34
    d.line([(M, y), (W - M, y)], fill=RULE, width=3)
    y += 42

    # ---- specs, two columns ----
    d.text((M, y), "THE MODEL", font=font("blk", 50), fill=INK)
    d.text((W // 2 + 40, y), "PRINTING IT", font=font("blk", 50), fill=INK)
    y += 80

    left = [
        ("height", "120 mm  (parametric — any size)"),
        ("bounding box", "48.3 x 55.9 x 120.0 mm"),
        ("volume", "96.3 cm3   (~119 g PLA solid)"),
        ("triangles", "180,284"),
        ("watertight", "YES — 0 non-manifold edges"),
        ("built as", "signed distance field + marching cubes"),
    ]
    right = [
        ("printer", "Creality K2 Plus"),
        ("material", "PLA, or PLA-CF for a matte finish"),
        ("layer height", "0.16 mm  (face detail lives here)"),
        ("walls / infill", "3 walls, 12% gyroid"),
        ("supports", "TREE — required under chin + head"),
        ("bed", "brim, 6 mm — the base is a thin oval"),
    ]
    yy = y
    for k, v in left:
        d.text((M, yy), k, font=font("bd", 32), fill=MUTE)
        d.text((M + 300, yy), v, font=font("rg", 32), fill=INK)
        yy += 50
    yy = y
    for k, v in right:
        d.text((W // 2 + 40, yy), k, font=font("bd", 32), fill=MUTE)
        d.text((W // 2 + 340, yy), v, font=font("rg", 32), fill=INK)
        yy += 50
    y = max(yy, yy) + 30

    # ---- the honest note ----
    box = [M, y, W - M, y + 250]
    d.rounded_rectangle(box, radius=18, fill=(252, 246, 236), outline=(238, 214, 178), width=3)
    d.text((M + 34, y + 28), "READ THIS BEFORE YOU PRINT",
           font=font("bd", 38), fill=WARM)
    notes = [
        "The head is a heavy sphere on a short neck. It WILL need tree supports under the",
        "chin and the underside of the skull — printing it unsupported will fail there.",
        "For the best face, print head and body separately and glue at the collar: the",
        "face then prints with no support scarring at all. Nothing here is glued in code —",
        "the STL is one solid watertight body, so slicing it in two is your choice, not mine.",
    ]
    ny = y + 82
    for line in notes:
        d.text((M + 34, ny), line, font=font("rg", 31), fill=(72, 62, 48))
        ny += 34
    y = box[3] + 40

    # ---- footer ----
    d.line([(M, H - 132), (W - M, H - 132)], fill=RULE, width=3)
    d.text((M, H - 106), "iddoperez.ai   ·   ALMAWARE   ·   make_iddo.py --exaggeration 1.3",
           font=font("bd", 30), fill=MUTE)
    d.text((W - M - 300, H - 106), "2026-08-06", font=font("bd", 30), fill=MUTE)

    jpg = os.path.join(DESK, "ALMA-Figure-Iddo.jpg")
    pdf = os.path.join(DESK, "ALMA-Figure-Iddo.pdf")
    img.convert("RGB").save(jpg, "JPEG", quality=92, optimize=True)
    img.convert("RGB").save(pdf, "PDF", resolution=240.0)
    print("wrote %s" % jpg)
    print("wrote %s" % pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
