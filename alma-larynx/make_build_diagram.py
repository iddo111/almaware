"""alma-larynx / make_build_diagram.py — the whole talking throat on one bright page.

Shows the real printed parts in the real airflow order, plus the vocal tract, the ear,
and the learning loop that makes it say /a/. JPEG + PDF onto the Desktop (workspace law:
deliverables are JPEG+PDF, never a raw .html, never a bare path handed over as a link).
"""
from __future__ import annotations

import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from view import load_stl, render                     # reuse the STL renderer

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(os.path.expanduser("~"), "Desktop")

PAPER = (253, 252, 248); INK = (22, 24, 28); MUTE = (120, 126, 134)
TEAL = (13, 130, 120); WARM = (216, 118, 42); RED = (198, 52, 44)
BLUE = (44, 108, 200); AIR = (150, 205, 225); PANEL = (244, 246, 243)
F = {"blk": "C:/Windows/Fonts/ariblk.ttf", "bd": "C:/Windows/Fonts/arialbd.ttf",
     "rg": "C:/Windows/Fonts/arial.ttf"}


def font(k, px): return ImageFont.truetype(F[k], int(px))
def heb(s): return s[::-1]


def part_img(stl, size=300, yaw=None, pitch=-0.35):
    import numpy as _np
    tris = load_stl(os.path.join(HERE, stl))
    return render(tris, size, size, _np.pi if yaw is None else yaw, pitch)


def centered(d, cx, y, text, fnt, fill):
    w = d.textbbox((0, 0), text, font=fnt)[2]
    d.text((cx - w / 2, y), text, font=fnt, fill=fill)


def arrow(d, x0, y0, x1, y1, col=AIR, w=16):
    d.line([(x0, y0), (x1, y1)], fill=col, width=w)
    import math
    a = math.atan2(y1 - y0, x1 - x0)
    for s in (2.5, -2.5):
        d.line([(x1, y1), (x1 - 22 * math.cos(a - s / 6), y1 - 22 * math.sin(a - s / 6))],
               fill=col, width=w)


def main() -> int:
    W, H = 2600, 1800
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    M = 70

    # header
    d.text((M, 46), "THE TALKING THROAT", font=font("blk", 90), fill=INK)
    d.text((M, 150), "ALMA vocal folds  ·  air becomes a voice, and learns to say /a/",
           font=font("bd", 40), fill=TEAL)
    d.text((W - 430, 66), heb("מיתרי הקול"), font=font("bd", 58), fill=MUTE)
    d.line([(M, 226), (W - M, 226)], fill=(228, 226, 218), width=4)

    # ---- the airflow row: pump -> plenum -> bleed -> collar -> BUZZ ----
    row_y = 300
    box_w, box_h = 300, 300
    xs = [M + 40, M + 470, M + 900, M + 1330]
    parts = [
        (None, "AIR PUMP", "your aquarium pump", "the wind", RED),
        ("plenum-cap.stl", "PLENUM CAP", "on a 1.5 L bottle", "smooths the 50 Hz puffing", TEAL),
        ("bleed-tee.stl", "BLEED TEE", "drill vent to 1.39 mm", "the ONLY pressure limit", WARM),
        ("buzz-collar.stl", "BUZZ COLLAR", "+ doubled latex", "the folds — this makes sound", BLUE),
    ]
    for i, (stl, name, sub, role, col) in enumerate(parts):
        x = xs[i]
        d.rounded_rectangle([x, row_y, x + box_w, row_y + box_h], radius=18,
                            fill=PANEL, outline=(226, 224, 216), width=3)
        if stl:
            pi = part_img(stl, 270)
            img.paste(pi, (x + 15, row_y + 15))
        else:  # pump: draw a simple box + coil
            d.rounded_rectangle([x + 70, row_y + 90, x + 230, row_y + 210], radius=14,
                                fill=(232, 232, 236), outline=(150, 150, 160), width=4)
            d.ellipse([x + 120, row_y + 120, x + 180, row_y + 180], outline=RED, width=8)
            d.text((x + 108, row_y + 132), "≈", font=font("blk", 60), fill=RED)
        centered(d, x + box_w / 2, row_y + box_h + 14, name, font("blk", 34), col)
        centered(d, x + box_w / 2, row_y + box_h + 56, sub, font("bd", 26), INK)
        centered(d, x + box_w / 2, row_y + box_h + 90, role, font("rg", 24), MUTE)
        if i < len(parts) - 1:
            arrow(d, x + box_w + 8, row_y + box_h / 2, xs[i + 1] - 8, row_y + box_h / 2)

    # BUZZ burst out of the collar, heading up into the tract
    bx = xs[3] + box_w + 40
    arrow(d, bx, row_y + box_h / 2, bx + 150, row_y + box_h / 2, col=(240, 190, 90), w=18)
    d.text((bx + 20, row_y + box_h / 2 - 80), "BUZZ", font=font("blk", 46), fill=(212, 150, 40))

    # ---- second row: tract -> ear -> brain -> back ----
    y2 = 900
    # vocal tract (a printed tube shaping /a/)
    tx = M + 40
    d.rounded_rectangle([tx, y2, tx + 520, y2 + 300], radius=18, fill=PANEL,
                        outline=(226, 224, 216), width=3)
    # draw an /a/ area-function tube: narrow pharynx -> open mouth
    prof = [(0, 34), (40, 30), (90, 26), (140, 40), (200, 70), (260, 96), (320, 104), (380, 96)]
    cx0, cy0 = tx + 70, y2 + 150
    top = [(cx0 + px, cy0 - r) for px, r in prof]
    bot = [(cx0 + px, cy0 + r) for px, r in prof]
    d.polygon(top + bot[::-1], fill=(226, 236, 244), outline=BLUE)
    d.line(top, fill=BLUE, width=5); d.line(bot, fill=BLUE, width=5)
    centered(d, tx + 260, y2 + 310, "VOCAL TRACT", font("blk", 34), BLUE)
    centered(d, tx + 260, y2 + 352, "printed tube, shaped for /a/", font("rg", 26), MUTE)
    d.text((cx0 + 300, cy0 - 20), "\u201cah\u201d", font=font("blk", 54), fill=BLUE)

    # ear / mic
    ex = tx + 640
    d.rounded_rectangle([ex, y2, ex + 300, y2 + 300], radius=18, fill=PANEL,
                        outline=(226, 224, 216), width=3)
    d.ellipse([ex + 90, y2 + 70, ex + 210, y2 + 190], outline=TEAL, width=10)
    d.ellipse([ex + 125, y2 + 105, ex + 175, y2 + 155], fill=TEAL)
    for rr in (150, 190, 230):
        d.arc([ex + 150 - rr / 2, y2 + 130 - rr / 2, ex + 150 + rr / 2, y2 + 130 + rr / 2],
              -50, 50, fill=(150, 200, 190), width=5)
    centered(d, ex + 150, y2 + 310, "MICROPHONE", font("blk", 34), TEAL)
    centered(d, ex + 150, y2 + 352, "it hears itself", font("rg", 26), MUTE)

    # brain / learning loop
    brx = ex + 420
    d.rounded_rectangle([brx, y2, brx + 520, y2 + 300], radius=18, fill=(240, 249, 247),
                        outline=(178, 218, 210), width=3)
    centered(d, brx + 260, y2 + 30, "THE LEARNING LOOP", font("blk", 34), TEAL)
    lines = ["hears the sound  →  scores it", "is it PERIODIC?  (a voice, not a hiss)",
             "then: does it sound like /a/ ?", "nudges pressure + fold tension",
             "babbles until it lands on \u201cah\u201d"]
    for k, t in enumerate(lines):
        d.ellipse([brx + 34, y2 + 92 + k * 40, brx + 50, y2 + 108 + k * 40], fill=WARM)
        d.text((brx + 66, y2 + 84 + k * 40), t, font=font("rg", 27), fill=INK)

    # loop arrows connecting the second row, and back up to the pump
    arrow(d, tx + 520 + 8, y2 + 150, ex - 8, y2 + 150, col=(240, 190, 90), w=14)
    arrow(d, ex + 300 + 8, y2 + 150, brx - 8, y2 + 150, col=TEAL, w=14)
    # feedback arrow: brain back to the pump (routed through the empty band at y~820,
    # clear of the row-1 sub-labels which end near y=720)
    fb = 824
    d.line([(brx + 260, y2 - 6), (brx + 260, fb), (xs[0] + 150, fb),
            (xs[0] + 150, row_y + box_h + 160)], fill=(210, 170, 90), width=8)
    arrow(d, xs[0] + 150, fb - 30, xs[0] + 150, row_y + box_h + 6, col=(210, 170, 90), w=8)
    centered(d, W / 2 - 40, fb - 40, "the loop adjusts the wind and the folds",
             font("bd", 30), (180, 140, 70))

    # ---- honest note ----
    ny = 1300
    d.rounded_rectangle([M, ny, W - M, ny + 210], radius=20, fill=(253, 244, 240),
                        outline=(232, 190, 176), width=4)
    d.text((M + 40, ny + 26), "THE HONEST PART — read before you build",
           font=font("blk", 40), fill=RED)
    notes = [
        "A single stretched condom will WHISTLE, not talk — a 0.07 mm film has no thickness for the",
        "vocal wave to travel through (Titze: Pth grows as thickness shrinks). That buzz still proves the",
        "air, the seal and the ear all work. The part that truly TALKS is a latex tube FILLED WITH WATER —",
        "fat and soft like a real cord (110-170 Hz, a man's voice; Ruty 2007). Same printed parts hold both.",
    ]
    for k, t in enumerate(notes):
        d.text((M + 40, ny + 92 + k * 30), t, font=font("rg", 27), fill=(90, 66, 60))

    # ---- safety strip ----
    sy = ny + 250
    d.text((M, sy), "⚠ BEFORE THE PUMP GOES ON:", font=font("bd", 32), fill=WARM)
    saf = ("drill the bleed to 1.39 mm and TEST it (block the outlet 60 s, pressure must hold) · "
           "a power strip within reach = your E-STOP · goggles · judge the sound from RECORDINGS, "
           "not live · the servo water-driver is VETOED (use a hand-raised reservoir).")
    # wrap
    words = saf.split(" "); linew = ""; yy = sy + 44
    for w in words:
        if d.textbbox((0, 0), linew + w + " ", font=font("rg", 26))[2] > W - 2 * M:
            d.text((M, yy), linew, font=font("rg", 26), fill=(70, 74, 80)); yy += 34; linew = ""
        linew += w + " "
    d.text((M, yy), linew, font=font("rg", 26), fill=(70, 74, 80))

    d.line([(M, H - 70), (W - M, H - 70)], fill=(228, 226, 218), width=3)
    d.text((M, H - 56), "ALMA vocal folds  ·  " + heb("לע\"נ שיפרה ז\"ל") + "  ·  iddoperez.ai  ·  3 printed parts, all watertight",
           font=font("bd", 26), fill=MUTE)

    jpg = os.path.join(DESK, "ALMA-Talking-Throat.jpg")
    pdf = os.path.join(DESK, "ALMA-Talking-Throat.pdf")
    img.save(jpg, "JPEG", quality=92, optimize=True)
    img.save(pdf, "PDF", resolution=200.0)
    img.save(os.path.join(HERE, "talking-throat.png"))
    print("wrote", jpg); print("wrote", pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
