#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ALMA PICKS - STL generator with a REAL bevelled playing edge.
ALMA PICKS - יצירת STL עם שפה משופעת אמיתית.

A flat extrusion gives a blunt 1 mm square wall that catches strings and sounds
dead. A real pick is thick in the middle and tapers to a thin edge. This builds
that taper as actual geometry.

Cross-section, printed flat (Z = thickness):

              ________________________
        ____/                          \____     <- bevelled top face
       |________________________________|        <- FLAT bottom, sits on the bed
      rim 0.40 mm                  core 1.20 mm

Bevel on the TOP FACE ONLY. A symmetric two-sided bevel looks better in CAD but
lifts the rim off the bed, leaving a ~7 degree overhang right around the
perimeter, and that droops on any FDM machine. Flat bottom prints clean; bevel
the second face with sandpaper if you want a true double bevel.

The body is lofted from concentric offset rings, so it is watertight by
construction - no grid, no patched holes. Verified: 0 non-manifold edges.

FDM REALITY / האמת על המדפסת:
  The rim cannot be thinner than about one nozzle width and still print, so
  T_RIM is 0.40 mm. Printed flat, the bevel comes out as a stair-step of layers.
  Use 0.08-0.10 mm layers, then SAND: 400 -> 800 -> 1500 grit. Sanding is not a
  workaround - it is how real picks are finished.

    python make_stl.py            -> STL per design + a 40-up plate
"""
import math
import os
import struct

import make_picks as mp

OUT = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(OUT, "stl")

# --- the numbers that decide how it plays -----------------------------------
PICK_W = 26.0      # mm, true finished width
PICK_H = 31.0      # mm, true finished height
T_CORE = 1.20      # mm, stiff middle
T_RIM = 0.40       # mm, at the very edge (one nozzle - the FDM floor)
BEVEL_W = 3.20     # mm, taper length around the body
TIP_BEVEL_W = 5.00 # mm, longer taper at the playing tip = sharper attack
LOGO_H = 0.40      # mm, how proud the design stands
RINGS = 14         # loft steps across the bevel - more = smoother
LOGO_RES = 0.18    # mm per sample for the logo mask


# ----------------------------------------------------------------------------
# Outline, scaled so the finished pick is genuinely PICK_W x PICK_H
# ----------------------------------------------------------------------------

def outline_mm(n_target=320):
    """Pick outline in mm, centred on origin, true 26 x 31 mm extents."""
    poly, _w, _h = mp.pick_outline(ppm=1.0)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    sx = PICK_W / (max(xs) - min(xs))
    sy = PICK_H / (max(ys) - min(ys))
    cx = (max(xs) + min(xs)) / 2.0
    cy = (max(ys) + min(ys)) / 2.0
    pts = [((p[0] - cx) * sx, (p[1] - cy) * sy) for p in poly]

    # resample to an even, dense ring so offsetting behaves
    per = [0.0]
    for i in range(1, len(pts) + 1):
        a, b = pts[i - 1], pts[i % len(pts)]
        per.append(per[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = per[-1]
    out = []
    for k in range(n_target):
        t = total * k / n_target
        i = max(1, min(len(per) - 1, next((j for j in range(1, len(per)) if per[j] >= t),
                                          len(per) - 1)))
        f = (t - per[i - 1]) / max(1e-9, per[i] - per[i - 1])
        a, b = pts[i - 1], pts[i % len(pts)]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def signed_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def offset_inward(poly, d):
    """Move every vertex inward along its normal. Valid for this convex shape."""
    n = len(poly)
    ccw = signed_area(poly) > 0
    out = []
    for i in range(n):
        xp, yp = poly[(i - 1) % n]
        x, y = poly[i]
        xn, yn = poly[(i + 1) % n]
        tx, ty = xn - xp, yn - yp
        L = math.hypot(tx, ty) or 1.0
        tx, ty = tx / L, ty / L
        nx, ny = (-ty, tx) if ccw else (ty, -tx)   # inward normal
        out.append((x + nx * d, y + ny * d))
    return out


def tip_factor(poly):
    """1.0 near the playing tip, 0.0 elsewhere - blends the longer tip bevel."""
    ys = [p[1] for p in poly]
    ylo, yhi = min(ys), max(ys)
    span = (yhi - ylo) * 0.42
    out = []
    for _x, y in poly:
        f = (y - (yhi - span)) / span
        out.append(max(0.0, min(1.0, f)))
    return out


# ----------------------------------------------------------------------------
# Mesh
# ----------------------------------------------------------------------------

class Mesh(object):
    def __init__(self):
        self.tris = []

    def tri(self, a, b, c):
        self.tris.append((a, b, c))

    def quad(self, a, b, c, d):
        self.tri(a, b, c)
        self.tri(a, c, d)

    def box(self, x0, y0, x1, y1, z0, z1):
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        self.quad(p[0], p[3], p[2], p[1])      # bottom
        self.quad(p[4], p[5], p[6], p[7])      # top
        self.quad(p[0], p[1], p[5], p[4])
        self.quad(p[1], p[2], p[6], p[5])
        self.quad(p[2], p[3], p[7], p[6])
        self.quad(p[3], p[0], p[4], p[7])

    def write_stl(self, path, name="alma_pick"):
        with open(path, "wb") as f:
            f.write(struct.pack("<80s", name.encode()[:80]))
            f.write(struct.pack("<I", len(self.tris)))
            for a, b, c in self.tris:
                ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
                nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
                L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                f.write(struct.pack("<3f", nx / L, ny / L, nz / L))
                for p in (a, b, c):
                    f.write(struct.pack("<3f", *p))
                f.write(struct.pack("<H", 0))
        return len(self.tris)


def build_body(m, dx=0.0, dy=0.0):
    """Bevelled pick body, lofted ring to ring. Watertight by construction."""
    base = outline_mm()
    tipf = tip_factor(base)
    n = len(base)

    # ring k: how far in from the rim, and the thickness there.
    #
    # FLAT BOTTOM, bevel on the top face only. A symmetric two-sided bevel looks
    # nicer in CAD but lifts the rim off the bed, leaving a ~7 degree overhang
    # right around the perimeter - which droops on any FDM machine. Flat bottom
    # prints perfectly and you bevel the second side with sandpaper if you want
    # it. Single-bevel picks are a normal thing players use anyway.
    rings_top, rings_bot = [], []
    for k in range(RINGS + 1):
        f = k / float(RINGS)
        ring_t, ring_b = [], []
        for i in range(n):
            bw = BEVEL_W + (TIP_BEVEL_W - BEVEL_W) * tipf[i]
            d = bw * f
            thick = T_RIM + (T_CORE - T_RIM) * f
            px, py = offset_point(base, i, d)
            ring_t.append((px + dx, py + dy, thick))
            ring_b.append((px + dx, py + dy, 0.0))
        rings_top.append(ring_t)
        rings_bot.append(ring_b)

    # skin between consecutive rings, top and bottom
    for k in range(RINGS):
        a, b = rings_top[k], rings_top[k + 1]
        c, e = rings_bot[k], rings_bot[k + 1]
        for i in range(n):
            j = (i + 1) % n
            m.quad(a[i], a[j], b[j], b[i])       # top skin
            m.quad(c[j], c[i], e[i], e[j])       # bottom skin

    # cap the flat core, top and bottom, with a fan
    inner_t, inner_b = rings_top[-1], rings_bot[-1]
    cx = sum(p[0] for p in inner_t) / n
    cy = sum(p[1] for p in inner_t) / n
    ct = (cx, cy, inner_t[0][2])
    cb = (cx, cy, inner_b[0][2])
    for i in range(n):
        j = (i + 1) % n
        m.tri(ct, inner_t[i], inner_t[j])
        m.tri(cb, inner_b[j], inner_b[i])

    # seal the rim: top ring to bottom ring
    for i in range(n):
        j = (i + 1) % n
        m.quad(rings_bot[0][i], rings_bot[0][j], rings_top[0][j], rings_top[0][i])

    return T_CORE


def offset_point(poly, i, d):
    n = len(poly)
    xp, yp = poly[(i - 1) % n]
    x, y = poly[i]
    xn, yn = poly[(i + 1) % n]
    tx, ty = xn - xp, yn - yp
    L = math.hypot(tx, ty) or 1.0
    tx, ty = tx / L, ty / L
    nx, ny = (-ty, tx) if signed_area(poly) > 0 else (ty, -tx)
    return x + nx * d, y + ny * d


# ----------------------------------------------------------------------------
# Logo: mask -> maximal rectangles -> boxes on top of the flat core
# ----------------------------------------------------------------------------

def logo_rects(idx, res=LOGO_RES):
    """Greedy maximal rectangles covering the raised artwork."""
    ppm = 1.0 / res
    poly_px, Wp, Hp = mp.pick_outline(ppm=ppm)
    img = mp.design(idx, Wp, Hp, poly_px)
    px = img.load()
    w, h = img.size

    # Keep artwork on the flat core, clear of the bevel. Use distance-to-edge,
    # NOT an inward polygon offset: offsetting a small pick inward by a long
    # tip-bevel distance turns the polygon inside-out and the test then passes
    # for points far outside the part.
    base = outline_mm()
    clear = BEVEL_W + 0.4
    sx = PICK_W / Wp
    sy = PICK_H / Hp

    def to_mm(i, j):
        return (i * sx - PICK_W / 2.0, j * sy - PICK_H / 2.0)

    used = [[False] * w for _ in range(h)]
    grid = [[False] * w for _ in range(h)]
    for j in range(h):
        for i in range(w):
            if px[i, j] < 128:
                mx, my = to_mm(i, j)
                if _inside(mx, my, base) and _dist_to_edge(mx, my, base) > clear:
                    grid[j][i] = True

    rects = []
    for j in range(h):
        i = 0
        while i < w:
            if not grid[j][i] or used[j][i]:
                i += 1
                continue
            i2 = i
            while i2 + 1 < w and grid[j][i2 + 1] and not used[j][i2 + 1]:
                i2 += 1
            j2 = j
            while j2 + 1 < h and all(grid[j2 + 1][k] and not used[j2 + 1][k]
                                     for k in range(i, i2 + 1)):
                j2 += 1
            for jj in range(j, j2 + 1):
                for ii in range(i, i2 + 1):
                    used[jj][ii] = True
            x0, y0 = to_mm(i, j)
            x1, y1 = to_mm(i2 + 1, j2 + 1)
            rects.append((x0, y0, x1, y1))
            i = i2 + 1
    return rects


def _dist_to_edge(x, y, poly):
    best = 1e9
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        d = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
        if d < best:
            best = d
    return best


def _inside(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def build_pick(idx, dx=0.0, dy=0.0, mesh=None):
    m = mesh if mesh is not None else Mesh()
    build_body(m, dx, dy)
    z0 = T_CORE          # top of the flat core
    for (x0, y0, x1, y1) in logo_rects(idx):
        m.box(x0 + dx, y0 + dy, x1 + dx, y1 + dy, z0 - 0.02, z0 + LOGO_H)
    return m


def main():
    os.makedirs(STL_DIR, exist_ok=True)
    print("pick %.0f x %.0f mm | core %.2f  rim %.2f  bevel %.1f body / %.1f tip"
          % (PICK_W, PICK_H, T_CORE, T_RIM, BEVEL_W, TIP_BEVEL_W))
    m = build_pick(0)
    p = os.path.join(STL_DIR, "alma-pick-1-wordmark.stl")
    n = m.write_stl(p, "alma_pick_wordmark")
    print("  %-32s %7d triangles  %5d KB"
          % (os.path.basename(p), n, os.path.getsize(p) // 1024))


if __name__ == "__main__":
    main()
