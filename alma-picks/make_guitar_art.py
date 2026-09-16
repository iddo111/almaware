#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA GUITARS - bold graphic guitar prints, branded iddoperez.ai.
ALMA GUITARS - פוסטרים גרפיים של גיטרות.

High contrast, flat colour, no gradients - the same language as the picks.
Bodies are drawn as closed Catmull-Rom splines so the curves are real curves,
not polygons pretending.

    python make_guitar_art.py     -> poster PNG
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
F = {"blk": "C:/Windows/Fonts/ariblk.ttf",
     "bd": "C:/Windows/Fonts/arialbd.ttf",
     "imp": "C:/Windows/Fonts/impact.ttf"}

INK = (18, 20, 24)
TEAL = (15, 118, 110)
WARM = (201, 96, 42)
PAPER = (252, 251, 246)
MUTE = (140, 146, 152)


def font(k, px):
    return ImageFont.truetype(F[k], int(px))


# ---------------------------------------------------------------------------
# Smooth closed curve through control points
# ---------------------------------------------------------------------------

def catmull(pts, steps=26, closed=True):
    """Closed Catmull-Rom spline -> dense polygon."""
    n = len(pts)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n]
        p1 = pts[i % n]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        for s in range(steps):
            t = s / float(steps)
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def mirror(half, cx):
    """Build a symmetric body from a right-hand profile."""
    return half + [(2 * cx - x, y) for x, y in reversed(half)]


# ---------------------------------------------------------------------------
# Guitar parts. u = one unit, everything scales off it.
# ---------------------------------------------------------------------------

def neck(d, cx, y_body_top, u, col=INK, frets=True, headstock="strat"):
    nw = 0.30 * u                      # neck width
    y_nut = y_body_top - 3.05 * u
    d.polygon([(cx - nw / 2, y_body_top), (cx + nw / 2, y_body_top),
               (cx + nw * 0.40, y_nut), (cx - nw * 0.40, y_nut)], fill=col)
    if frets:
        for i in range(1, 15):
            t = 1 - (0.94 ** i)
            y = y_body_top - t * 3.0 * u
            w = nw / 2 * (1 - 0.20 * t)
            d.line([(cx - w, y), (cx + w, y)], fill=PAPER, width=max(2, int(u * 0.018)))
    # nut
    d.rectangle([cx - nw * 0.44, y_nut - u * 0.05, cx + nw * 0.44, y_nut], fill=col)

    hw, hh = 0.46 * u, 1.05 * u
    if headstock == "strat":
        pts = [(cx - hw * 0.30, y_nut), (cx + hw * 0.34, y_nut - hh * 0.08),
               (cx + hw * 0.44, y_nut - hh * 0.55), (cx + hw * 0.10, y_nut - hh),
               (cx - hw * 0.52, y_nut - hh * 0.86), (cx - hw * 0.60, y_nut - hh * 0.30)]
        d.polygon(catmull(pts, 22), fill=col)
        for i in range(6):
            side = -1 if i < 3 else 1
            k = i % 3
            px = cx + side * hw * 0.36
            py = y_nut - hh * (0.28 + 0.24 * k)
            r = u * 0.055
            d.ellipse([px - r, py - r, px + r, py + r], fill=PAPER)
    else:
        pts = [(cx - hw * 0.42, y_nut), (cx + hw * 0.42, y_nut),
               (cx + hw * 0.52, y_nut - hh * 0.72), (cx, y_nut - hh * 0.95),
               (cx - hw * 0.52, y_nut - hh * 0.72)]
        d.polygon(catmull(pts, 20), fill=col)
        for i in range(6):
            side = -1 if i < 3 else 1
            k = i % 3
            px = cx + side * hw * 0.40
            py = y_nut - hh * (0.22 + 0.22 * k)
            r = u * 0.05
            d.ellipse([px - r, py - r, px + r, py + r], fill=PAPER)


def strings(d, cx, y_top, y_bot, u, col=PAPER, n=6, spread_top=0.20, spread_bot=0.34):
    for i in range(n):
        f = (i / (n - 1.0)) - 0.5
        d.line([(cx + f * spread_top * u, y_top), (cx + f * spread_bot * u, y_bot)],
               fill=col, width=max(1, int(u * 0.010)))


# ---------------------------------------------------------------------------
# The six bodies
# ---------------------------------------------------------------------------

def strat(d, cx, cy, u, col):
    half = [(cx, cy - 1.02 * u), (cx + 0.42 * u, cy - 1.06 * u),
            (cx + 0.66 * u, cy - 0.74 * u), (cx + 0.86 * u, cy - 0.16 * u),
            (cx + 0.80 * u, cy + 0.52 * u), (cx + 0.46 * u, cy + 0.98 * u),
            (cx + 0.02 * u, cy + 1.04 * u), (cx - 0.40 * u, cy + 0.96 * u),
            (cx - 0.78 * u, cy + 0.60 * u), (cx - 0.92 * u, cy - 0.04 * u),
            (cx - 0.80 * u, cy - 0.66 * u), (cx - 0.50 * u, cy - 1.10 * u),
            (cx - 0.18 * u, cy - 0.86 * u)]
    d.polygon(catmull(half, 26), fill=col)
    neck(d, cx, cy - 0.95 * u, u, col, headstock="strat")
    # pickguard - a slim sweep, not a slab covering the whole body
    pg = [(cx - 0.16 * u, cy - 0.70 * u), (cx + 0.30 * u, cy - 0.50 * u),
          (cx + 0.28 * u, cy + 0.10 * u), (cx - 0.02 * u, cy + 0.40 * u),
          (cx - 0.40 * u, cy + 0.18 * u), (cx - 0.46 * u, cy - 0.40 * u)]
    d.polygon(catmull(pg, 20), fill=PAPER)
    for k in range(3):
        y = cy - 0.34 * u + k * 0.20 * u
        d.rounded_rectangle([cx - 0.16 * u, y, cx + 0.20 * u, y + 0.07 * u],
                            radius=u * 0.022, fill=col)
    strings(d, cx, cy - 3.9 * u, cy + 0.55 * u, u, col)


def lespaul(d, cx, cy, u, col):
    half = [(cx, cy - 1.04 * u), (cx + 0.52 * u, cy - 0.92 * u),
            (cx + 0.82 * u, cy - 0.40 * u), (cx + 0.86 * u, cy + 0.30 * u),
            (cx + 0.52 * u, cy + 0.94 * u), (cx, cy + 1.06 * u),
            (cx - 0.52 * u, cy + 0.94 * u), (cx - 0.86 * u, cy + 0.30 * u),
            (cx - 0.84 * u, cy - 0.34 * u), (cx - 0.58 * u, cy - 0.98 * u),
            (cx - 0.26 * u, cy - 0.72 * u)]
    d.polygon(catmull(half, 26), fill=col)
    neck(d, cx, cy - 0.95 * u, u, col, headstock="lp")
    for k in range(2):
        y = cy - 0.34 * u + k * 0.46 * u
        d.rounded_rectangle([cx - 0.26 * u, y, cx + 0.26 * u, y + 0.17 * u],
                            radius=u * 0.04, fill=PAPER)
    for k in range(4):
        px = cx + (-0.34 + 0.24 * k) * u
        r = u * 0.075
        d.ellipse([px - r, cy + 0.58 * u - r, px + r, cy + 0.58 * u + r], fill=PAPER)
    strings(d, cx, cy - 3.9 * u, cy + 0.34 * u, u, col)


def flyingv(d, cx, cy, u, col):
    # straight polygon, NOT catmull - a V has to keep its points sharp
    pts = [(cx - 0.16 * u, cy - 1.02 * u), (cx + 0.16 * u, cy - 1.02 * u),
           (cx + 0.94 * u, cy + 0.86 * u), (cx + 0.60 * u, cy + 1.12 * u),
           (cx, cy + 0.10 * u),
           (cx - 0.60 * u, cy + 1.12 * u), (cx - 0.94 * u, cy + 0.86 * u)]
    d.polygon(pts, fill=col)
    neck(d, cx, cy - 0.92 * u, u, col, headstock="lp")
    for k in range(2):
        y = cy - 0.42 * u + k * 0.40 * u
        d.rounded_rectangle([cx - 0.22 * u, y, cx + 0.22 * u, y + 0.15 * u],
                            radius=u * 0.04, fill=PAPER)
    strings(d, cx, cy - 3.85 * u, cy + 0.30 * u, u, col)


def acoustic(d, cx, cy, u, col):
    half = [(cx, cy - 1.10 * u), (cx + 0.56 * u, cy - 0.92 * u),
            (cx + 0.70 * u, cy - 0.40 * u), (cx + 0.48 * u, cy - 0.02 * u),
            (cx + 0.80 * u, cy + 0.42 * u), (cx + 0.72 * u, cy + 0.98 * u),
            (cx + 0.16 * u, cy + 1.22 * u)]
    d.polygon(catmull(mirror(half, cx), 26), fill=col)
    neck(d, cx, cy - 1.02 * u, u, col, headstock="lp")
    r = u * 0.30
    d.ellipse([cx - r, cy + 0.10 * u - r, cx + r, cy + 0.10 * u + r], fill=PAPER)
    r2 = u * 0.245
    d.ellipse([cx - r2, cy + 0.10 * u - r2, cx + r2, cy + 0.10 * u + r2], fill=col)
    d.rounded_rectangle([cx - 0.34 * u, cy + 0.62 * u, cx + 0.34 * u, cy + 0.76 * u],
                        radius=u * 0.03, fill=PAPER)
    strings(d, cx, cy - 4.0 * u, cy + 0.66 * u, u, PAPER)


def headstock_hero(d, cx, cy, u, col):
    """Close-up: the headstock as a graphic object in its own right."""
    hw, hh = 1.5 * u, 2.3 * u
    pts = [(cx - hw * 0.30, cy + hh * 0.46), (cx + hw * 0.34, cy + hh * 0.40),
           (cx + hw * 0.46, cy - hh * 0.06), (cx + hw * 0.10, cy - hh * 0.48),
           (cx - hw * 0.54, cy - hh * 0.36), (cx - hw * 0.62, cy + hh * 0.16)]
    d.polygon(catmull(pts, 24), fill=col)
    for i in range(6):
        side = -1 if i < 3 else 1
        k = i % 3
        px = cx + side * hw * 0.34
        py = cy + hh * (0.20 - 0.22 * k)
        r = u * 0.14
        d.ellipse([px - r, py - r, px + r, py + r], fill=PAPER)
        d.ellipse([px - r * 0.42, py - r * 0.42, px + r * 0.42, py + r * 0.42], fill=col)
    d.rectangle([cx - 0.30 * u, cy + hh * 0.46, cx + 0.30 * u, cy + hh * 0.62], fill=col)
    strings(d, cx, cy + hh * 0.30, cy + hh * 0.62, u, PAPER, spread_top=0.5, spread_bot=0.5)


def wave_guitar(d, cx, cy, u, col):
    """The ALMAWARE tie-in: a body that dissolves into a waveform."""
    half = [(cx, cy - 1.02 * u), (cx + 0.42 * u, cy - 1.06 * u),
            (cx + 0.66 * u, cy - 0.74 * u), (cx + 0.86 * u, cy - 0.16 * u),
            (cx + 0.80 * u, cy + 0.52 * u), (cx + 0.46 * u, cy + 0.98 * u),
            (cx + 0.02 * u, cy + 1.04 * u), (cx - 0.40 * u, cy + 0.96 * u),
            (cx - 0.78 * u, cy + 0.60 * u), (cx - 0.92 * u, cy - 0.04 * u),
            (cx - 0.80 * u, cy - 0.66 * u), (cx - 0.50 * u, cy - 1.10 * u),
            (cx - 0.18 * u, cy - 0.86 * u)]
    d.polygon(catmull(half, 26), fill=col)
    neck(d, cx, cy - 0.95 * u, u, col, frets=False, headstock="strat")
    for i in range(17):
        x = cx - 0.72 * u + i * 0.09 * u
        a = (0.14 + 0.62 * abs(math.sin(i * 0.58 + 0.3))) * u
        d.rounded_rectangle([x - 0.024 * u, cy + 0.12 * u - a / 2,
                             x + 0.024 * u, cy + 0.12 * u + a / 2],
                            radius=u * 0.024, fill=PAPER)


# A full guitar spans from the headstock tip (cy - 5.05u) to the body bottom
# (cy + 1.25u) = 6.3u tall. The headstock close-up is only ~1.6u. Each entry
# carries its own span so nothing overflows its cell.
#   name, subtitle, draw fn, colour, vertical span in units, top offset in units
GUITARS = [
    ("STRAT", "double cutaway", strat, INK, 6.30, 5.05),
    ("LES PAUL", "single cutaway", lespaul, TEAL, 6.30, 5.05),
    ("FLYING V", "all angles", flyingv, WARM, 6.30, 5.00),
    ("ACOUSTIC", "dreadnought", acoustic, INK, 6.45, 5.15),
    ("HEADSTOCK", "six in a row", headstock_hero, TEAL, 2.60, 1.15),
    ("WAVEFORM", "sound made visible", wave_guitar, WARM, 6.30, 5.05),
]


# ---------------------------------------------------------------------------

def poster(cols=3, rows=2, cell=560):
    pad = 74
    top = 250
    LABEL_H = 110                       # reserved strip under each cell
    W = cols * cell + pad * 2
    H = top + rows * (cell + LABEL_H) + 130

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    d.text((pad, 46), "ALMA GUITARS", font=font("blk", 84), fill=INK)
    d.text((pad + 6, 150), "iddoperez.ai", font=font("blk", 34), fill=TEAL)
    d.text((pad + 250, 158), "six shapes  -  flat colour, no gradients",
           font=font("bd", 26), fill=MUTE)
    d.line([pad, top - 30, W - pad, top - 30], fill=(228, 226, 218), width=3)

    for i, (name, sub, fn, col, span, head) in enumerate(GUITARS):
        r, c = divmod(i, cols)
        x = pad + c * cell
        y = top + r * (cell + LABEL_H)
        cx = x + cell / 2
        # scale so the WHOLE instrument fits the cell, then sit it on the
        # vertical centre of what is left over
        u = cell * 0.88 / span
        cy = y + cell * 0.06 + head * u
        fn(d, cx, cy, u, col)
        d.text((x + 14, y + cell + 10), name, font=font("blk", 32), fill=col)
        d.text((x + 14, y + cell + 54), sub, font=font("bd", 24), fill=MUTE)

    d.line([pad, H - 92, W - pad, H - 92], fill=(228, 226, 218), width=3)
    d.text((pad, H - 70), "iddoperez.ai", font=font("blk", 30), fill=INK)
    d.text((W - pad - 360, H - 64), "ALMAWARE  -  100% our own code",
           font=font("bd", 24), fill=MUTE)
    return img


if __name__ == "__main__":
    img = poster()
    p = os.path.join(OUT, "alma-guitars.png")
    img.save(p)
    print("poster:", p, img.size)
