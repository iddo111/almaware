#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ALMA RISHA - a custom oud plectrum. / מפרט עוד מותאם אישית.

An oud risha is NOTHING like a guitar pick. It is a long flexible strip -
traditionally an eagle quill, today plastic - held between the fingers with a
long tail. The flex IS the instrument's voice. A stiff risha kills the tone.

    <------------------------ 120 mm ------------------------>
     ______________________________________________________
    (  grip ridges ::::   iddoperez.ai                      )   11 -> 9 mm wide
     ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
    thick 1.00 mm at the grip  ---->  0.55 mm at the tip

Edges are ROUNDED here, not sharpened. A sharp risha edge chews nylon strings
and sounds harsh - the opposite of what you want. The tip is a smooth radius.

PRINT: flat, no supports, PETG (never PLA - it snaps at this thickness).
       0.10 mm layers. Sand the edges smooth, 400 -> 800.

    python make_oud.py      -> STL + spec drawing
"""
import math
import os
import struct

from PIL import Image, ImageDraw, ImageFont

import make_stl as ms

OUT = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(OUT, "stl")
F = {"blk": "C:/Windows/Fonts/ariblk.ttf", "bd": "C:/Windows/Fonts/arialbd.ttf"}

# --- the numbers that decide how it plays -----------------------------------
LEN = 120.0        # mm, overall length
W_GRIP = 11.0      # mm, width at the held end
W_TIP = 9.0        # mm, width at the playing end
T_GRIP = 1.00      # mm, thick where you hold it - control
T_TIP = 0.55       # mm, thin at the tip - this is the flex
T_RIM = 0.35       # mm, at the rounded edge
BEVEL = 1.60       # mm, how far in the edge rounding runs
RIDGE_H = 0.35     # mm, grip ridges standing proud
LOGO_H = 0.30      # mm, lettering
RINGS = 9
RES = 0.20         # mm per sample for the lettering mask


def font(k, px):
    return ImageFont.truetype(F[k], int(px))


# ---------------------------------------------------------------------------
# Outline: a tapered stadium. y = 0 at the grip, y = LEN at the tip.
# ---------------------------------------------------------------------------

def half_width(y):
    t = max(0.0, min(1.0, y / LEN))
    return (W_GRIP + (W_TIP - W_GRIP) * t) / 2.0


def outline(n_side=150, n_cap=40):
    pts = []
    r_tip = W_TIP / 2.0
    r_grip = W_GRIP / 2.0
    y0, y1 = r_grip, LEN - r_tip

    for i in range(n_side + 1):                       # right side, grip -> tip
        y = y0 + (y1 - y0) * i / n_side
        pts.append((half_width(y), y))
    # tip cap: must START where the right side ended, at (r, y1) = angle 0,
    # sweep over the top (0, y1+r) and finish at (-r, y1) = angle pi.
    # Starting at -pi/2 puts the arc in the middle of the side and folds the
    # outline back on itself.
    for i in range(1, n_cap):
        a = math.pi * i / n_cap
        pts.append((r_tip * math.cos(a), y1 + r_tip * math.sin(a)))
    for i in range(n_side + 1):                       # left side, tip -> grip
        y = y1 - (y1 - y0) * i / n_side
        pts.append((-half_width(y), y))
    for i in range(1, n_cap):                         # grip cap: pi -> 2pi
        a = math.pi + math.pi * i / n_cap
        pts.append((r_grip * math.cos(a), y0 + r_grip * math.sin(a)))
    return pts


def thickness_at(y):
    t = max(0.0, min(1.0, y / LEN))
    return T_GRIP + (T_TIP - T_GRIP) * t


def dist_to_edge(x, y, poly):
    best = 1e9
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        s = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        d = math.hypot(x - (x1 + s * dx), y - (y1 + s * dy))
        if d < best:
            best = d
    return best


def inside(x, y, poly):
    ins = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                ins = not ins
        j = i
    return ins


def signed_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def offset_point(poly, i, d, ccw=None):
    """Move vertex i inward by d. Direction depends on winding - get this wrong
    and the part grows instead of shrinking."""
    n = len(poly)
    if ccw is None:
        ccw = signed_area(poly) > 0
    xp, yp = poly[(i - 1) % n]
    x, y = poly[i]
    xn, yn = poly[(i + 1) % n]
    tx, ty = xn - xp, yn - yp
    L = math.hypot(tx, ty) or 1.0
    tx, ty = tx / L, ty / L
    nx, ny = (-ty, tx) if ccw else (ty, -tx)
    return x + nx * d, y + ny * d


# ---------------------------------------------------------------------------
# Lettering + grip ridges, as rectangles on the flat top
# ---------------------------------------------------------------------------

def top_features():
    """Raised rectangles: grip ridges near the held end, name along the body."""
    rects = []

    # grip ridges - real function, a risha is slippery
    for k in range(7):
        y = 8.0 + k * 3.2
        hw = half_width(y) - 2.0
        rects.append(("ridge", -hw, y, hw, y + 1.3))

    # name, running lengthwise. Render sideways then read the pixels back.
    txt = "iddoperez.ai"
    fh = int(5.2 / RES)
    f = font("blk", fh)
    tmp = Image.new("L", (10, 10), 255)
    l, t, r, b = ImageDraw.Draw(tmp).textbbox((0, 0), txt, font=f)
    img = Image.new("L", (r - l + 8, b - t + 8), 255)
    ImageDraw.Draw(img).text((4 - l, 4 - t), txt, font=f, fill=0)
    img = img.rotate(-90, expand=True)          # now tall and narrow
    px = img.load()
    w, h = img.size
    y_start = 40.0
    x_off = -(w * RES) / 2.0
    for j in range(h):
        i = 0
        while i < w:
            if px[i, j] >= 128:
                i += 1
                continue
            i2 = i
            while i2 + 1 < w and px[i2 + 1, j] < 128:
                i2 += 1
            rects.append(("logo",
                          x_off + i * RES, y_start + j * RES,
                          x_off + (i2 + 1) * RES, y_start + (j + 1) * RES))
            i = i2 + 1
    return rects


# ---------------------------------------------------------------------------

def build(mesh=None):
    poly = outline()
    n = len(poly)
    m = mesh if mesh is not None else ms.Mesh()

    ccw = signed_area(poly) > 0
    rings_t, rings_b = [], []
    for k in range(RINGS + 1):
        f = k / float(RINGS)
        rt, rb = [], []
        for i in range(n):
            px, py = offset_point(poly, i, BEVEL * f, ccw)
            full = thickness_at(py)
            th = T_RIM + (full - T_RIM) * f
            rt.append((px, py, th))
            rb.append((px, py, 0.0))
        rings_t.append(rt)
        rings_b.append(rb)

    for k in range(RINGS):
        a, b = rings_t[k], rings_t[k + 1]
        c, e = rings_b[k], rings_b[k + 1]
        for i in range(n):
            j = (i + 1) % n
            m.quad(a[i], a[j], b[j], b[i])
            m.quad(c[j], c[i], e[i], e[j])

    # cap the core along the spine
    it, ib = rings_t[-1], rings_b[-1]
    cx = sum(p[0] for p in it) / n
    cy = sum(p[1] for p in it) / n
    zt = sum(p[2] for p in it) / n
    ct, cb = (cx, cy, zt), (cx, cy, 0.0)
    for i in range(n):
        j = (i + 1) % n
        m.tri(ct, it[i], it[j])
        m.tri(cb, ib[j], ib[i])

    for i in range(n):
        j = (i + 1) % n
        m.quad(rings_b[0][i], rings_b[0][j], rings_t[0][j], rings_t[0][i])

    for kind, x0, y0, x1, y1 in top_features():
        ym = (y0 + y1) / 2.0
        if not (inside((x0 + x1) / 2.0, ym, poly)
                and dist_to_edge((x0 + x1) / 2.0, ym, poly) > BEVEL + 0.3):
            continue
        z = thickness_at(ym)
        h = RIDGE_H if kind == "ridge" else LOGO_H
        m.box(x0, y0, x1, y1, z - 0.02, z + h)
    return m


def spec_drawing():
    poly = outline()
    S = 9.0
    pad, top = 90, 190
    W = int(LEN * S) + pad * 2
    H = top + int(W_GRIP * S) + 400

    img = Image.new("RGB", (W, H), (252, 251, 246))
    d = ImageDraw.Draw(img)
    TEAL, INK, MUTE = (15, 118, 110), (18, 20, 24), (140, 146, 152)

    d.text((pad, 44), "ALMA RISHA", font=font("blk", 74), fill=TEAL)
    d.text((pad, 128),
           "custom oud plectrum  -  iddoperez.ai  -  drawn %.1fx larger than life"
           % (S / 150.0 * 25.4), font=font("bd", 26), fill=MUTE)

    cy = top + W_GRIP * S / 2
    pts = [(pad + y * S, cy - x * S) for x, y in poly]
    d.polygon(pts, fill=TEAL)
    for kind, x0, y0, x1, y1 in top_features():
        d.rectangle([pad + y0 * S, cy - x1 * S, pad + y1 * S, cy - x0 * S],
                    fill=(252, 251, 246))

    yb = top + int(W_GRIP * S) + 70
    d.line([pad, yb, pad + LEN * S, yb], fill=INK, width=3)
    for xx in (pad, pad + LEN * S):
        d.line([xx, yb - 12, xx, yb + 12], fill=INK, width=3)
    d.text((pad + LEN * S / 2 - 60, yb + 16), "%.0f mm" % LEN,
           font=font("blk", 30), fill=INK)

    rows = [("width", "%.0f mm at the grip  ->  %.0f mm at the tip" % (W_GRIP, W_TIP)),
            ("thickness", "%.2f mm at the grip  ->  %.2f mm at the tip  (the flex)"
             % (T_GRIP, T_TIP)),
            ("edge", "rounded to %.2f mm over %.1f mm  -  NOT sharpened" % (T_RIM, BEVEL)),
            ("grip", "7 ridges, %.2f mm proud" % RIDGE_H),
            ("print", "PETG only, 0.10 mm layers, flat, no supports")]
    for i, (k, v) in enumerate(rows):
        y = yb + 70 + i * 38
        d.text((pad, y), k, font=font("blk", 25), fill=TEAL)
        d.text((pad + 170, y), v, font=font("bd", 25), fill=(60, 64, 70))
    return img


def main():
    os.makedirs(STL_DIR, exist_ok=True)
    m = build()
    p = os.path.join(STL_DIR, "alma-risha-oud.stl")
    n = m.write_stl(p, "alma_risha_oud")
    print("risha: %d triangles, %d KB" % (n, os.path.getsize(p) // 1024))
    img = spec_drawing()
    q = os.path.join(OUT, "alma-risha-spec.png")
    img.save(q)
    print("spec :", q, img.size)


if __name__ == "__main__":
    main()
