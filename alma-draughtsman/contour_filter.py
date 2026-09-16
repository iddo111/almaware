"""CONTOUR FILTER — edges into strokes. **NOT a model. It learns nothing.**

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

RENAMED 2026-08-31 02:25, and the reason is the point of the file.

This was called `winston.py`. So was `eran-brain/hand/hand_eye.py`, which IS a trained
model — 792 parameters, learned by MIKO's three-factor rule, judged by ERAN's own eye.
When Iddo asked *"תראה לי את הצייר"* I ran THIS, and told him **"Winston drew her."** It
was a false attribution: Canny edge detection and contour following, no weights, no
training, incapable of improving. He caught it: *"הצייר הוא מודל רשת נוירונים???"* and
then *"למה מכרת לי חיקוי זול שוב."*

**The name did the work the fact should have done.** Sharing a name let a filter inherit a
model's credibility, and the output looked like a drawing so it passed my own check. That
is the same failure as the salt memristor sold in the film, and the same as the hand that
scored 86% drawing dot-clouds: **a thing that LOOKS like the deliverable passing as the
deliverable.** Three times, one pattern.

So this file is now named for what it is. It is a good filter and it is useful — it turns
a photograph into honest strokes at any resolution. It is not a painter, it is not
Winston, and it never learned anything.

  * the model that draws LETTERS from memory      eran-brain/hand/hand_eye.py  (Winston)
  * the model that PAINTS what it sees            alma-draughtsman/neural/painter.py
  * this, a filter                                you are reading it

    python contour_filter.py --img in.png --out out.png --w 3000 --colour 16
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw


# ------------------------------------------------------------------ the eye

def contours(img_bgr, detail: float, min_len: int):
    """Every edge in the picture, as an ordered list of points.

    Canny gives a clean binary edge map; findContours walks it into ordered chains, which
    is what a stroke is. A pixel edge map is not a stroke -- the ORDER is the whole point,
    because a hand draws a line from one end to the other.
    """
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.bilateralFilter(g, 7, 60, 60)          # kill noise, keep edges
    v = float(np.median(g))
    lo = int(max(0, (1.0 - detail) * v))
    hi = int(min(255, (1.0 + detail) * v))
    e = cv2.Canny(g, lo, hi, L2gradient=True)
    e = cv2.dilate(e, np.ones((2, 2), np.uint8), iterations=1)
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cs:
        p = c[:, 0, :].astype(np.float32)
        if len(p) >= min_len:
            out.append(p)
    out.sort(key=len, reverse=True)
    return out, g


def smooth(p: np.ndarray, k: int = 7) -> np.ndarray:
    """A hand does not follow every pixel. Moving average along the chain."""
    if len(p) < k * 2:
        return p
    w = np.ones(k) / k
    x = np.convolve(p[:, 0], w, mode="valid")
    y = np.convolve(p[:, 1], w, mode="valid")
    return np.stack([x, y], 1)


def thin(p: np.ndarray, step: float) -> np.ndarray:
    """Resample to roughly even spacing so the pressure profile is even too."""
    if len(p) < 3:
        return p
    d = np.r_[0.0, np.cumsum(np.hypot(*(np.diff(p, axis=0).T)))]
    n = max(2, int(d[-1] / step))
    t = np.linspace(0, d[-1], n)
    return np.stack([np.interp(t, d, p[:, 0]), np.interp(t, d, p[:, 1])], 1)


# ----------------------------------------------------------------- the hand

def pressure(i: int, n: int, base: float) -> float:
    """Thin in, full in the body, lift at the end. This is what a nib does."""
    u = i / max(n - 1, 1)
    return base * (0.35 + 0.65 * math.sin(math.pi * min(1.0, max(0.0, u)) ** 0.75))


def palette(img_bgr, k: int = 12):
    """The painter's LIMITED palette, found in the picture itself.

    Iddo, 2026-08-30: *"תוסיף הפעם צבע - זה הרכיב החסר לו."* The lazy version of colour
    is to sample each pixel and copy it, which produces a traced photograph and not a
    painting. A painter squeezes out a few colours and mixes everything from those, and
    that limit is most of what makes a painting look painted. So: k-means over the
    image's own pixels, and every stroke must choose from what came out of the tube.
    """
    z = img_bgr.reshape(-1, 3).astype(np.float32)
    if len(z) > 60000:                      # sampling is plenty and keeps this instant
        z = z[np.random.RandomState(1933).choice(len(z), 60000, replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 0.6)
    _, _, cen = cv2.kmeans(z, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    return cen.astype(np.uint8)             # (k, 3) BGR


def stroke_colours(p, img_bgr, pal, blur: int = 5):
    """What colour is the paper under this stroke, one entry per point.

    Sampled from a BLURRED copy on purpose: a stroke runs along an EDGE, and the pixel
    exactly on an edge is a mix of both sides -- the muddy line that makes traced colour
    look dirty. Blurring first asks "what colour is this REGION", which is the question a
    painter is actually answering when they load the brush.
    """
    sm = cv2.GaussianBlur(img_bgr, (blur * 2 + 1, blur * 2 + 1), 0)
    h, w = sm.shape[:2]
    xs = np.clip(p[:, 0].astype(int), 0, w - 1)
    ys = np.clip(p[:, 1].astype(int), 0, h - 1)
    got = sm[ys, xs].astype(np.int32)                       # (n, 3) BGR
    d = ((got[:, None, :] - pal[None, :, :].astype(np.int32)) ** 2).sum(-1)
    return pal[d.argmin(1)]                                 # snapped to the tube


def draw_png_colour(strokes, W, H, scale, width, paper, img_bgr, pal, bands=6):
    """The same hand, now holding more than one brush."""
    im = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(im, "RGBA")
    for p, dark in strokes:
        n = len(p)
        cols = stroke_colours(p, img_bgr, pal)
        for i in range(n - 1):
            w = pressure(i, n, width * (0.45 + 0.9 * dark))
            b, g, r = (int(v) for v in cols[i])
            a = int(120 + 120 * dark)
            d.line([(p[i][0] * scale, p[i][1] * scale),
                    (p[i+1][0] * scale, p[i+1][1] * scale)],
                   fill=(r, g, b, a), width=max(1, int(round(w))), joint="curve")
    return im


def draw_svg_colour(strokes, W, H, scale, width, paper_hex, img_bgr, pal, path, bands=6):
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d">' % (W, H, W, H),
             '<rect width="100%%" height="100%%" fill="%s"/>' % paper_hex,
             '<g fill="none" stroke-linecap="round" stroke-linejoin="round">']
    for p, dark in strokes:
        n = len(p)
        cols = stroke_colours(p, img_bgr, pal)
        for b in range(bands):
            i0 = int(b * (n - 1) / bands)
            i1 = int((b + 1) * (n - 1) / bands) + 1
            if i1 - i0 < 2:
                continue
            w = pressure((i0 + i1) // 2, n, width * (0.45 + 0.9 * dark))
            bb, gg, rr = (int(v) for v in cols[(i0 + i1) // 2])
            pts = " ".join("%.1f,%.1f" % (x * scale, y * scale) for x, y in p[i0:i1])
            parts.append('<polyline points="%s" stroke="#%02x%02x%02x" '
                         'stroke-width="%.2f" stroke-opacity="%.2f"/>'
                         % (pts, rr, gg, bb, max(0.4, w), 0.5 + 0.45 * dark))
    parts += ["</g>", "</svg>"]
    open(path, "w", encoding="utf-8").write(chr(10).join(parts))



def draw_png(strokes, W, H, scale, width, ink, paper):
    im = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(im, "RGBA")
    for p, dark in strokes:
        n = len(p)
        for i in range(n - 1):
            w = pressure(i, n, width * (0.45 + 0.9 * dark))
            a = int(150 + 105 * dark)
            d.line([(p[i][0] * scale, p[i][1] * scale),
                    (p[i+1][0] * scale, p[i+1][1] * scale)],
                   fill=ink + (a,), width=max(1, int(round(w))), joint="curve")
    return im


def draw_svg(strokes, W, H, scale, width, ink_hex, paper_hex, path):
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d">' % (W, H, W, H),
             '<rect width="100%%" height="100%%" fill="%s"/>' % paper_hex,
             '<g fill="none" stroke="%s" stroke-linecap="round" stroke-linejoin="round">'
             % ink_hex]
    for p, dark in strokes:
        n = len(p)
        # one polyline per stroke, split into a few width bands so pressure survives
        bands = 5
        for b in range(bands):
            i0 = int(b * (n - 1) / bands)
            i1 = int((b + 1) * (n - 1) / bands) + 1
            if i1 - i0 < 2:
                continue
            w = pressure((i0 + i1) // 2, n, width * (0.45 + 0.9 * dark))
            pts = " ".join("%.1f,%.1f" % (x * scale, y * scale) for x, y in p[i0:i1])
            parts.append('<polyline points="%s" stroke-width="%.2f" stroke-opacity="%.2f"/>'
                         % (pts, max(0.4, w), 0.55 + 0.45 * dark))
    parts += ["</g>", "</svg>"]
    open(path, "w", encoding="utf-8").write("\n".join(parts))


# ---------------------------------------------------------------------- run

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Draw an image in strokes. Resolution-free.")
    ap.add_argument("--img", required=True)
    ap.add_argument("--out", required=True, help=".png or .svg")
    ap.add_argument("--w", type=int, default=3000, help="output width; height follows")
    ap.add_argument("--detail", type=float, default=0.45, help="0.2 sparse .. 0.8 busy")
    ap.add_argument("--min-len", type=int, default=14, help="drop specks shorter than this")
    ap.add_argument("--max-strokes", type=int, default=2500)
    ap.add_argument("--width", type=float, default=2.2, help="nib width at 1x")
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--invert", action="store_true", help="white ink on black")
    ap.add_argument("--colour", "--color", dest="colour", type=int, default=0, metavar="K",
                    help="Paint with K colours taken from the picture itself. 0 = ink "
                         "only. A LIMITED palette on purpose: copying every pixel traces "
                         "a photograph; choosing from a few tubes makes a painting.")
    a = ap.parse_args(argv)

    # cv2.imread() goes through a C path that cannot open a filename with Hebrew in it on
    # Windows -- it returns None and says only "check file path/integrity", which reads
    # like a corrupt file. The photographs of Alma z"l live in a folder called עלמיש, so
    # this was never optional here. Read the bytes in Python, decode in memory.
    img = cv2.imdecode(np.frombuffer(open(a.img, "rb").read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        print("cannot read %s" % a.img, file=sys.stderr)
        return 2
    h0, w0 = img.shape[:2]
    cs, gray = contours(img, a.detail, a.min_len)
    cs = cs[:a.max_strokes]

    strokes = []
    for p in cs:
        q = thin(smooth(p), a.step)
        if len(q) < 3:
            continue
        # how dark the picture is under this stroke -> how hard the nib presses
        xs = np.clip(q[:, 0].astype(int), 0, w0 - 1)
        ys = np.clip(q[:, 1].astype(int), 0, h0 - 1)
        dark = float(1.0 - gray[ys, xs].mean() / 255.0)
        strokes.append((q, min(1.0, 0.25 + dark)))

    scale = a.w / float(w0)
    W, H = a.w, int(round(h0 * scale))
    ink, paper = ((235, 233, 228), (12, 12, 16)) if a.invert else ((18, 18, 22), (252, 251, 247))
    ink_hex = "#%02x%02x%02x" % ink
    paper_hex = "#%02x%02x%02x" % paper

    if a.out.lower().endswith(".svg"):
        if a.colour:
            draw_svg_colour(strokes, W, H, scale, a.width * scale, paper_hex,
                            img, palette(img, a.colour), a.out)
        else:
            draw_svg(strokes, W, H, scale, a.width * scale, ink_hex, paper_hex, a.out)
    else:
        if a.colour:
            draw_png_colour(strokes, W, H, scale, a.width * scale, paper,
                            img, palette(img, a.colour)).save(a.out)
        else:
            draw_png(strokes, W, H, scale, a.width * scale, ink, paper).save(a.out)

    print("%d strokes, %d points -> %s  %dx%d" %
          (len(strokes), sum(len(s[0]) for s in strokes), a.out, W, H))
    return 0


if __name__ == "__main__":
    sys.exit(main())
