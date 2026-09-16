"""alma-headscan / make_capture_guide.py — the one page that decides the scan quality.

JPEG + PDF onto the Desktop, per workspace law. Composed with PIL: no browser, no HTML.
"""
from __future__ import annotations

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

DESK = os.path.join(os.path.expanduser("~"), "Desktop")
PAPER = (253, 252, 248)
INK = (20, 22, 26)
MUTE = (132, 138, 146)
TEAL = (12, 128, 118)
RED = (198, 52, 44)
WARM = (216, 118, 42)
RULE = (228, 226, 218)
F = {"blk": "C:/Windows/Fonts/ariblk.ttf", "bd": "C:/Windows/Fonts/arialbd.ttf",
     "rg": "C:/Windows/Fonts/arial.ttf"}


def font(k, px):
    return ImageFont.truetype(F[k], int(px))


def heb(s):
    return s[::-1]                      # PIL has no bidi engine


def orbit_diagram(d, cx, cy, R):
    """Head with the three orbits the capture needs. A picture beats four sentences."""
    d.ellipse([cx - R * 0.42, cy - R * 0.52, cx + R * 0.42, cy + R * 0.46],
              fill=(238, 214, 190), outline=(206, 176, 148), width=3)
    d.ellipse([cx - R * 0.12, cy - R * 0.18, cx - R * 0.04, cy - R * 0.10], fill=INK)
    d.ellipse([cx + R * 0.04, cy - R * 0.18, cx + R * 0.12, cy - R * 0.10], fill=INK)
    d.arc([cx - R * 0.18, cy - R * 0.06, cx + R * 0.18, cy + R * 0.24], 20, 160, fill=INK, width=4)

    rings = [(-R * 0.55, R * 1.00, R * 0.26, TEAL, "1  above  —  looking DOWN"),
             (0.0, R * 1.12, R * 0.30, WARM, "2  eye level  —  straight on"),
             (R * 0.52, R * 1.00, R * 0.26, (86, 96, 190), "3  below  —  looking UP")]
    for dy, rx, ry, col, _lab in rings:
        for k in range(0, 360, 9):
            a0 = math.radians(k)
            a1 = math.radians(k + 5)
            x0, y0 = cx + rx * math.cos(a0), cy + dy + ry * math.sin(a0)
            x1, y1 = cx + rx * math.cos(a1), cy + dy + ry * math.sin(a1)
            d.line([x0, y0, x1, y1], fill=col, width=5)
        d.ellipse([cx + rx - 13, cy + dy - 13, cx + rx + 13, cy + dy + 13], fill=col)
    ly = cy - R * 0.95
    for _dy, _rx, _ry, col, lab in rings:
        d.rectangle([cx + R * 1.35, ly + 6, cx + R * 1.35 + 26, ly + 26], fill=col)
        d.text((cx + R * 1.35 + 44, ly), lab, font=font("bd", 30), fill=INK)
        ly += 52


def main() -> int:
    W, H = 2000, 2828
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    M = 110

    d.text((M, 92), "SCAN YOUR HEAD", font=font("blk", 100), fill=INK)
    d.text((M, 206), "phone capture guide  ·  for a life-size 3D print",
           font=font("bd", 42), fill=TEAL)
    d.text((W - M - 300, 116), heb("סריקת ראש"), font=font("bd", 56), fill=MUTE)
    d.line([(M, 292), (W - M, 292)], fill=RULE, width=4)

    # --- the one rule ---
    y = 330
    d.rounded_rectangle([M, y, W - M, y + 220], radius=20,
                        fill=(253, 240, 238), outline=(232, 176, 168), width=4)
    d.text((M + 36, y + 26), "THE ONE RULE THAT DECIDES EVERYTHING",
           font=font("blk", 42), fill=RED)
    d.text((M + 36, y + 88), "DO NOT CHANGE YOUR EXPRESSION. Not once, not for a second.",
           font=font("bd", 38), fill=INK)
    d.text((M + 36, y + 140),
           "Photogrammetry assumes the subject is rigid. Every smile, blink or word moves",
           font=font("rg", 32), fill=(90, 70, 68))
    d.text((M + 36, y + 178),
           "your face and the maths cannot solve it. Neutral. Mouth closed. Eyes on one spot.",
           font=font("rg", 32), fill=(90, 70, 68))
    y += 268

    # --- diagram ---
    orbit_diagram(d, M + 420, y + 300, 330)
    y += 640

    # --- steps ---
    d.text((M, y), "HOW", font=font("blk", 52), fill=INK)
    y += 84
    steps = [
        ("App", "RealityScan (Epic, free) or Polycam photo mode. Your Galaxy A70 has no"),
        ("", "LiDAR, so use PHOTO / photogrammetry mode, not the depth mode."),
        ("Light", "Even and soft. Daylight from a window, or ceiling light. No hard shadow,"),
        ("", "no direct lamp on one side, and nothing that moves while you shoot."),
        ("Distance", "40-60 cm. Fill the frame with your head, leave a little background."),
        ("Motion", "Move the CAMERA, keep your head still relative to the room. Slow."),
        ("Coverage", "Three orbits: above / eye level / below. 60-100 photos, or 60-90 s"),
        ("", "of slow video. Overlap every shot with the last by about 70%."),
        ("Keep", "The bookshelf IN FRAME. That texture is what locks the camera positions."),
        ("Do NOT", "shave first. Your stubble is the texture the reconstruction lives on -"),
        ("", "I measured 1,843 trackable points per frame on it. A bare scalp fails."),
    ]
    for k, t in steps:
        if k:
            d.ellipse([M + 6, y + 12, M + 22, y + 28], fill=WARM)
            d.text((M + 44, y), k, font=font("bd", 34), fill=INK)
        d.text((M + 300, y), t, font=font("rg", 32), fill=(64, 68, 74))
        y += 50

    y += 30
    d.line([(M, y), (W - M, y)], fill=RULE, width=3)
    y += 40

    # --- what to send back ---
    d.text((M, y), "THEN SEND ME TWO THINGS", font=font("blk", 52), fill=INK)
    y += 88
    for n, t in [("1", "The exported mesh — OBJ, PLY or STL. Any of them."),
                 ("2", "Your head width, ear to ear, measured with a tape. In mm.")]:
        d.ellipse([M, y - 2, M + 44, y + 42], fill=TEAL)
        d.text((M + 15, y + 2), n, font=font("bd", 32), fill=PAPER)
        d.text((M + 74, y), t, font=font("bd", 34), fill=INK)
        y += 62
    d.text((M + 74, y),
           "A photogrammetric mesh has NO real size — the maths is scale-free. Your tape",
           font=font("rg", 31), fill=MUTE)
    y += 40
    d.text((M + 74, y),
           "measurement is the only thing that makes the print life-size rather than a guess.",
           font=font("rg", 31), fill=MUTE)
    y += 76

    d.rounded_rectangle([M, y, W - M, y + 170], radius=18,
                        fill=(240, 249, 247), outline=(178, 218, 210), width=3)
    d.text((M + 34, y + 26), "I DO THE REST", font=font("bd", 38), fill=TEAL)
    d.text((M + 34, y + 82),
           "headprep.py  ->  orient, cut the neck flat, cap it into a closed solid, scale to",
           font=font("rg", 31), fill=(46, 78, 74))
    d.text((M + 34, y + 120),
           "your tape measurement, verify watertight, write the STL. Already built and tested.",
           font=font("rg", 31), fill=(46, 78, 74))

    d.line([(M, H - 132), (W - M, H - 132)], fill=RULE, width=3)
    d.text((M, H - 106), "ALMAWARE  ·  alma-headscan  ·  iddoperez.ai",
           font=font("bd", 30), fill=MUTE)
    d.text((W - M - 300, H - 106), "2026-08-06", font=font("bd", 30), fill=MUTE)

    jpg = os.path.join(DESK, "ALMA-Head-Scan-Guide.jpg")
    pdf = os.path.join(DESK, "ALMA-Head-Scan-Guide.pdf")
    img.save(jpg, "JPEG", quality=92, optimize=True)
    img.save(pdf, "PDF", resolution=240.0)
    print("wrote %s" % jpg)
    print("wrote %s" % pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
