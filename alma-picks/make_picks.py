#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA PICKS - stylized guitar picks branded iddoperez.ai, built for the Creality K2 Plus.
ALMA PICKS - מפרטים מעוצבים עם iddoperez.ai, מוכנים להדפסה בתלת-מימד.

Black = RAISED on the print. White = the flat base.
Single-colour printing, so all contrast comes from geometry, not paint.

    python make_picks.py            -> design sheet (PNG)
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))

# --- real pick geometry, standard 351 -------------------------------------
PICK_W_MM = 26.0          # shoulder to shoulder
PICK_H_MM = 31.0          # shoulder line to tip
# Shoulder radius is capped by geometry: the two shoulder arcs must not overlap
# along the top edge. For this triangle the ceiling is ~8.6 mm - go past it and
# the arcs cross, which is what produced the spike in the first draft.
R_SHOULDER_MM = 8.0
R_TIP_MM = 5.0            # tighter playing tip
PPM = 22                  # pixels per mm when drawing

FONTS = {
    "black": "C:/Windows/Fonts/ariblk.ttf",    # no Hebrew glyphs
    "bold": "C:/Windows/Fonts/arialbd.ttf",    # has Hebrew
    "impact": "C:/Windows/Fonts/impact.ttf",
}


def font(name, px):
    return ImageFont.truetype(FONTS[name], px)


def fit_font(d, text, name, start_px, max_w):
    """Largest size of `name` at which `text` still fits inside max_w pixels."""
    px = start_px
    while px > 6:
        f = font(name, px)
        l, _t, r, _b = d.textbbox((0, 0), text, font=f)
        if r - l <= max_w:
            return f
        px -= 1
    return font(name, 6)


def pick_width_at(poly, y):
    """True width of the silhouette at height y, by intersecting every edge
    with the horizontal line y. Scanline, not nearest-point guessing."""
    xs = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
        if lo <= y <= hi:
            xs.append(x1 + (x2 - x1) * (y - y1) / (y2 - y1))
    if len(xs) < 2:
        return 0.0
    return max(xs) - min(xs)


# --------------------------------------------------------------------------
# Rounded-triangle outline = an honest 351 pick silhouette
# --------------------------------------------------------------------------

def _round_corner(v, p, n, r, steps=48):
    """Arc that replaces vertex v, given neighbours p and n and radius r."""
    vx, vy = v
    u = (p[0] - vx, p[1] - vy)
    w = (n[0] - vx, n[1] - vy)
    lu = math.hypot(*u) or 1.0
    lw = math.hypot(*w) or 1.0
    u = (u[0] / lu, u[1] / lu)
    w = (w[0] / lw, w[1] / lw)

    cosang = max(-1.0, min(1.0, u[0] * w[0] + u[1] * w[1]))
    theta = math.acos(cosang)
    if theta < 1e-6 or abs(math.pi - theta) < 1e-6:
        return [v]

    d = r / math.tan(theta / 2.0)
    t1 = (vx + u[0] * d, vy + u[1] * d)
    t2 = (vx + w[0] * d, vy + w[1] * d)

    bis = (u[0] + w[0], u[1] + w[1])
    lb = math.hypot(*bis) or 1.0
    bis = (bis[0] / lb, bis[1] / lb)
    c = (vx + bis[0] * (r / math.sin(theta / 2.0)),
         vy + bis[1] * (r / math.sin(theta / 2.0)))

    a1 = math.atan2(t1[1] - c[1], t1[0] - c[0])
    a2 = math.atan2(t2[1] - c[1], t2[0] - c[0])
    while a2 - a1 > math.pi:
        a2 -= 2 * math.pi
    while a1 - a2 > math.pi:
        a2 += 2 * math.pi

    return [(c[0] + r * math.cos(a1 + (a2 - a1) * i / steps),
             c[1] + r * math.sin(a1 + (a2 - a1) * i / steps))
            for i in range(steps + 1)]


def _max_radius(v, p, n):
    """Largest corner radius at v before its arc collides with a neighbour's."""
    def half_ang(a, b, c):
        u = (b[0] - a[0], b[1] - a[1])
        w = (c[0] - a[0], c[1] - a[1])
        lu = math.hypot(*u) or 1.0
        lw = math.hypot(*w) or 1.0
        cosang = max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (lu * lw)))
        return math.acos(cosang) / 2.0
    lim = 1e9
    for other in (p, n):
        L = math.hypot(other[0] - v[0], other[1] - v[1])
        lim = min(lim, (L / 2.0) * math.tan(half_ang(v, p, n)))
    return lim


def pick_outline(ppm=PPM):
    """Pick polygon in pixels, origin at top-left of its bounding box."""
    w, h = PICK_W_MM, PICK_H_MM
    a = (-w / 2.0, 0.0)      # left shoulder
    b = (w / 2.0, 0.0)       # right shoulder
    c = (0.0, h)             # tip
    # Corner radii MUST be clamped. Too large and neighbouring arcs overlap, the
    # outline self-intersects, and every inward normal along that stretch flips
    # outward - which silently grows the part instead of shrinking it.
    rs = min(R_SHOULDER_MM, _max_radius(a, c, b) * 0.98, _max_radius(b, a, c) * 0.98)
    rt = min(R_TIP_MM, _max_radius(c, b, a) * 0.98)
    pts = []
    pts += _round_corner(a, c, b, rs)
    pts += _round_corner(b, a, c, rs)
    pts += _round_corner(c, b, a, rt)

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ox, oy = min(xs), min(ys)
    return [((p[0] - ox) * ppm, (p[1] - oy) * ppm) for p in pts], \
           (max(xs) - ox) * ppm, (max(ys) - oy) * ppm


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def centred(d, cx, y, text, f, fill):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text((cx - (r - l) / 2 - l, y - t), text, font=f, fill=fill)
    return b - t


def fitted(d, cx, y, text, name, start_px, max_w, fill, poly=None, margin=0.84):
    """Centre text with its TOP at y, shrunk until it fits the silhouette.

    Measures the pick's width at both the top and the bottom of the glyph box
    and obeys the narrower of the two - otherwise text near the tapering tip
    fits at its top edge and still runs off at its bottom edge.
    """
    px = int(start_px)
    while px > 6:
        f = font(name, px)
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        w, h = r - l, b - t
        limit = max_w
        if poly is not None:
            limit = min(pick_width_at(poly, y) * margin,
                        pick_width_at(poly, y + h) * margin)
        if w <= limit:
            break
        px -= 1
    return centred(d, cx, y, text, font(name, px), fill)


def grip_dots(d, cx, cy, rings=3, fill=0):
    """Concentric dot grip - real function, not decoration."""
    for ring in range(1, rings + 1):
        rad = ring * 9 * PPM / 10
        n = 6 * ring
        for i in range(n):
            a = 2 * math.pi * i / n + ring * 0.3
            x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
            r = 1.15 * PPM / 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def ridges(d, x0, y0, x1, y1, n=7, fill=0):
    step = (y1 - y0) / n
    for i in range(n):
        y = y0 + i * step
        d.rounded_rectangle([x0, y, x1, y + step * 0.5],
                            radius=step * 0.25, fill=fill)


# --------------------------------------------------------------------------
# The six designs. Black = raised.
# --------------------------------------------------------------------------

def design(idx, W, H, poly):
    img = Image.new("L", (int(W), int(H)), 255)
    d = ImageDraw.Draw(img)
    cx = W / 2
    OUTLINE = [0.35]        # stroke width in mm, thicker for outline-only designs

    def usable(y, margin=0.80):
        """Safe text width at height y, kept inside the silhouette."""
        return pick_width_at(poly, y) * margin

    if idx == 0:      # WORDMARK - domain across the face, biggest possible
        d.polygon(poly, fill=0)
        fitted(d, cx, H * 0.17, "iddo", "black", int(5.0 * PPM), usable(H*0.22), 255, poly)
        fitted(d, cx, H * 0.36, "perez", "black", int(5.0 * PPM), usable(H*0.41), 255, poly)
        fitted(d, cx, H * 0.55, ".ai", "black", int(3.4 * PPM), usable(H*0.58), 255, poly)
        ridges(d, cx - 4.2 * PPM, H * 0.72, cx + 4.2 * PPM, H * 0.80, 4, 255)

    elif idx == 1:    # MONOGRAM - huge IP, unmistakable at arm's length
        d.polygon(poly, fill=255)
        OUTLINE[0] = 0.9
        fitted(d, cx, H * 0.16, "IP", "impact", int(12 * PPM), usable(H*0.30), 0, poly)
        fitted(d, cx, H * 0.64, "IDDOPEREZ.AI", "black", int(2.2 * PPM),
               usable(H*0.66), 0, poly)

    elif idx == 2:    # NEURON - the ALMAWARE motif, nodes and links
        d.polygon(poly, fill=0)
        nodes = [(cx, H * 0.20), (cx - 4.6 * PPM, H * 0.36), (cx + 4.6 * PPM, H * 0.36),
                 (cx - 2.6 * PPM, H * 0.53), (cx + 2.6 * PPM, H * 0.53)]
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                d.line([a, b], fill=255, width=int(0.5 * PPM))
        for i, (x, y) in enumerate(nodes):
            r = (2.2 if i == 0 else 1.6) * PPM / 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        fitted(d, cx, H * 0.64, "iddoperez.ai", "black", int(2.4 * PPM),
               usable(H*0.66), 255, poly)

    elif idx == 3:    # HEBREW - עידו, reversed for PIL (no bidi engine here)
        d.polygon(poly, fill=0)
        heb = "\u05e2\u05d9\u05d3\u05d5"[::-1]   # manual RTL: PIL has no bidi engine
        # Arial Bold, not Arial Black - only Bold ships Hebrew glyphs on Windows
        fitted(d, cx, H * 0.19, heb, "bold", int(7.0 * PPM), usable(H*0.30), 255, poly)
        d.rounded_rectangle([cx - 5.5 * PPM, H * 0.505, cx + 5.5 * PPM, H * 0.525],
                            radius=PPM * 0.1, fill=255)
        fitted(d, cx, H * 0.57, "iddoperez.ai", "black", int(2.4 * PPM),
               usable(H*0.59), 255, poly)

    elif idx == 4:    # GRIP - function first, dots you can actually feel
        d.polygon(poly, fill=255)
        OUTLINE[0] = 0.8
        grip_dots(d, cx, H * 0.36, rings=3, fill=0)
        fitted(d, cx, H * 0.62, "iddoperez.ai", "black", int(2.6 * PPM),
               usable(H*0.64), 0, poly)

    else:             # WAVE - sound made visible
        d.polygon(poly, fill=0)
        y0 = H * 0.34
        for i in range(11):
            x = cx - 6.6 * PPM + i * 1.32 * PPM
            amp = (1.8 + 5.2 * abs(math.sin(i * 0.62 + 0.4))) * PPM
            d.rounded_rectangle([x - 0.36 * PPM, y0 - amp / 2,
                                 x + 0.36 * PPM, y0 + amp / 2],
                                radius=0.34 * PPM, fill=255)
        fitted(d, cx, H * 0.60, "iddoperez.ai", "black", int(2.4 * PPM),
               usable(H*0.62), 255, poly)

    # every design gets the outline crisp on top
    d.line(poly + [poly[0]], fill=0, width=max(2, int(OUTLINE[0] * PPM)),
           joint="curve")
    return img


NAMES = ["WORDMARK", "MONOGRAM", "NEURON", "\u05e2\u05d9\u05d3\u05d5 HEBREW",
         "GRIP DOTS", "WAVE"]
NOTES = ["domain fills the face", "reads from across a room", "ALMAWARE motif",
         "your name, bold", "textured, real grip", "sound made visible"]


def sheet():
    poly, W, H = pick_outline()
    cols, rows = 3, 2
    pad, top, gap = int(2.2 * PPM), int(7.5 * PPM), int(5.0 * PPM)
    cw, ch = int(W) + gap, int(H) + gap + int(3.4 * PPM)
    SW = cols * cw + pad * 2
    SH = top + rows * ch + int(7 * PPM)

    sh = Image.new("RGB", (SW, SH), (255, 255, 255))
    d = ImageDraw.Draw(sh)

    def line(y, text, name, px, fill):
        """Draw a header/footer line, shrunk if it would run off the sheet."""
        f = fit_font(d, text, name, int(px), SW - pad * 2)
        d.text((pad, y), text, font=f, fill=fill)

    line(int(0.9 * PPM), "ALMA PICKS", "black", 3.6 * PPM, (15, 118, 110))
    line(int(4.6 * PPM),
         "iddoperez.ai  -  guitar picks for the Creality K2 Plus  -  "
         "%.0f x %.0f mm, 1.0 mm thick  -  black = raised"
         % (PICK_W_MM, PICK_H_MM),
         "bold", 1.7 * PPM, (90, 95, 105))
    d.line([pad, top - int(1.6 * PPM), SW - pad, top - int(1.6 * PPM)],
           fill=(225, 225, 218), width=2)

    for i in range(cols * rows):
        r, c = divmod(i, cols)
        x = pad + c * cw + gap // 2
        y = top + r * ch
        sh.paste(design(i, W, H, poly).convert("RGB"), (int(x), int(y)))
        # label font must be Arial Bold - Arial Black has no Hebrew glyphs
        lab = fit_font(d, "%d. %s" % (i + 1, NAMES[i]), "bold",
                       int(2.0 * PPM), cw - gap)
        d.text((x, y + int(H) + int(0.9 * PPM)), "%d. %s" % (i + 1, NAMES[i]),
               font=lab, fill=(15, 118, 110))
        nf = fit_font(d, NOTES[i], "bold", int(1.5 * PPM), cw - gap)
        d.text((x, y + int(H) + int(3.2 * PPM)), NOTES[i],
               font=nf, fill=(120, 125, 132))

    line(SH - int(5.2 * PPM),
         "Print flat, no supports. PLA or PETG. 0.4 mm nozzle, 0.2 mm layers "
         "= 5 layers. About 40 fit on one plate.",
         "bold", 1.6 * PPM, (90, 95, 105))
    line(SH - int(3.0 * PPM),
         "PA-CF works too and is stiffer - dry it first, and expect a rougher face.",
         "bold", 1.6 * PPM, (90, 95, 105))
    return sh


if __name__ == "__main__":
    img = sheet()
    p = os.path.join(OUT, "alma-picks-sheet.png")
    img.save(p, "PNG")
    print("sheet:", p, img.size)
