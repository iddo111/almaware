# -*- coding: utf-8 -*-
"""
poyke_pawn_qr.py — classic chess pawn on a QR plinth, encoding https://iddoperez.ai
Night-shift build 2026-08-26. Output: poyke-pawn-qr.stl next to this file.

Design (all mm):
  - plinth 36 x 36 x 4, flat bottom at z=0
  - pawn ~40 tall (revolved profile: base disc, stem, collar, sphere head),
    standing at the BACK of the plinth, fused 0.8 into it
  - QR code (qrcode lib, border=1, fit -> version 2, 25x25 data) embossed
    0.8 raised on the plinth TOP in front of the pawn; module = 1.15 (>= 1.15
    required); dark modules as row-merged boxes, boolean-unioned
  - geometry constraint stated honestly: 27 modules * 1.15 = 31.05 wide on a
    36 plinth, so the pawn base (8 dia) clips the last QR rows; modules under
    the base footprint (+0.3 clearance) are SKIPPED, dark ones among them are
    lost to error correction (level L). The count is printed.
"""
import math
import os

import numpy as np
import qrcode
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "poyke-pawn-qr.stl")

URL = "https://iddoperez.ai"

# ---------------- parameters (mm) ----------------
# FIX 2026-08-26 23:52: plinth lengthened front-to-back so the pawn stands
# fully BEHIND the QR — zero modules skipped, full QR integrity (was: 30
# modules lost under the pawn keep-out, leaning on ECC-L).
PLINTH_X = 36.0
PLINTH_Y = 42.0
PLINTH_H = 4.0
MODULE = 1.15          # spec: each module >= 1.15
QR_RAISE = 0.8         # embossed height above plinth top
EMBED = 0.8            # how deep parts sink into the plinth (fusion)
ROW_OVERLAP = 0.03     # tiny y-overlap between rows: no coplanar/shared faces
PAWN_H = 40.0
PAWN_BASE_R = 4.0
FRONT_MARGIN = 0.4     # QR (incl. its 1-module border) to plinth front edge
BACK_MARGIN = 0.4      # pawn base to plinth back edge
CLEARANCE = 0.3        # QR module to pawn base


def qr_matrix():
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L,
                       border=1)
    qr.add_data(URL)
    qr.make(fit=True)
    return qr.version, qr.get_matrix()   # matrix includes the border


def pawn_profile():
    """(radius, z) polyline, z=0 at pawn bottom, closed on the axis."""
    head_r = 4.3
    head_cz = PAWN_H - head_r            # sphere center -> top exactly at 40
    neck_r = 1.8
    pts = [
        (0.00, 0.0),
        (4.00, 0.0),                     # base disc
        (4.00, 1.8),
        (3.30, 2.6),                     # base chamfer
        (2.90, 3.2),
        (2.20, 4.8),                     # cove into stem
        (1.65, 23.0),                    # tapered stem
        (1.65, 24.0),
        (2.70, 25.8),                    # flare
        (2.95, 26.8),                    # collar
        (2.95, 28.4),
        (neck_r, 29.6),                  # neck
    ]
    phi0 = math.asin(neck_r / head_r)
    pts.append((neck_r, head_cz - head_r * math.cos(phi0)))
    steps = 28
    for i in range(1, steps):
        phi = phi0 + (math.pi - phi0) * i / steps
        pts.append((head_r * math.sin(phi),
                    head_cz - head_r * math.cos(phi)))
    pts.append((0.0, PAWN_H))            # close on the axis
    return np.array(pts, dtype=float)


def box_at(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return b


def main():
    version, matrix = qr_matrix()
    n = len(matrix)                      # 27 = 25 data + 1-module border
    qr_side = n * MODULE
    half_x = PLINTH_X / 2.0
    half_y = PLINTH_Y / 2.0

    # layout: plinth centered on origin; front edge = -Y, back edge = +Y.
    # QR row 0 (finder-heavy top edge) faces the front; pawn fully behind it.
    qr_x0 = -qr_side / 2.0
    qr_y0 = -half_y + FRONT_MARGIN
    pawn_cy = half_y - PAWN_BASE_R - BACK_MARGIN
    keepout_r = PAWN_BASE_R + CLEARANCE

    # ---- QR module boxes: filter keep-out, then run-length merge per row ----
    boxes, skipped_dark, skipped_all = [], 0, 0
    z0, z1 = PLINTH_H - EMBED, PLINTH_H + QR_RAISE
    for r, row in enumerate(matrix):
        ry0 = qr_y0 + r * MODULE
        ry1 = ry0 + MODULE
        keep = []
        for c, dark in enumerate(row):
            cx0 = qr_x0 + c * MODULE
            # nearest point of the module rect to the pawn base center
            nx = min(max(0.0, cx0), cx0 + MODULE)
            ny = min(max(pawn_cy, ry0), ry1)
            hit = math.hypot(nx - 0.0, ny - pawn_cy) < keepout_r
            if hit:
                skipped_all += 1
                if dark:
                    skipped_dark += 1
            keep.append(bool(dark) and not hit)
        c = 0
        while c < n:                     # merge consecutive dark modules
            if keep[c]:
                c2 = c
                while c2 + 1 < n and keep[c2 + 1]:
                    c2 += 1
                boxes.append(box_at(qr_x0 + c * MODULE,
                                    qr_x0 + (c2 + 1) * MODULE,
                                    ry0 - ROW_OVERLAP, ry1 + ROW_OVERLAP,
                                    z0, z1))
                c = c2 + 1
            else:
                c += 1

    # ---- plinth + pawn ----
    plinth = box_at(-half_x, half_x, -half_y, half_y, 0.0, PLINTH_H)
    pawn = trimesh.creation.revolve(pawn_profile(), sections=96)
    pawn.apply_translation((0.0, pawn_cy, PLINTH_H - EMBED))

    parts = [plinth, pawn] + boxes
    method = None
    solid = None
    try:
        solid = trimesh.boolean.union(parts)
        if not solid.is_watertight:
            raise ValueError("boolean union produced non-watertight mesh")
        method = "boolean union (manifold)"
    except BaseException as exc:         # honest fallback, still printable
        solid = trimesh.util.concatenate(parts)
        method = "concatenate fallback ({}: {})".format(type(exc).__name__, exc)

    solid.export(OUT)

    # ---- verify by RELOADING the exported STL ----
    m = trimesh.load(OUT, force="mesh")
    lo, hi = m.bounds
    print("wrote:", OUT)
    print("method:", method)
    print("URL:", URL)
    print("QR: version {v}, {d}x{d} data + border=1 -> {n}x{n}; "
          "module {s} mm; footprint {f:.2f} mm".format(
              v=version, d=n - 2, n=n, s=MODULE, f=qr_side))
    print("QR boxes: {} (row-merged), raise {} mm".format(len(boxes), QR_RAISE))
    print("modules skipped under pawn keep-out: {} total, {} dark "
          "(lost to ECC level L)".format(skipped_all, skipped_dark))
    print("reloaded: {} faces, {} vertices".format(len(m.faces),
                                                   len(m.vertices)))
    print("bbox min [{:.2f} {:.2f} {:.2f}] max [{:.2f} {:.2f} {:.2f}]  "
          "extents [{:.2f} {:.2f} {:.2f}] mm".format(*lo, *hi, *m.extents))
    print("watertight:", m.is_watertight)
    print("flat bottom at z=0:", abs(lo[2]) < 1e-6)
    if not m.is_watertight:
        print("HONEST STATUS: exported STL is NOT watertight as a single "
              "shell; bodies = {}".format(m.body_count))


if __name__ == "__main__":
    main()
