#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ALMA JAZZ - a Jazz III-shaped plectrum. / מפרט בסגנון ג'אז 3.

A Jazz III is NOT a small 351. Three things define it:

  1. SMALL      ~24.5 x 27.5 mm, against 26 x 31 for a standard 351
  2. THICK      1.38 mm, stiff enough that the pick does not flex at all
  3. SHARP TIP  a ~1.6 mm tip radius instead of ~5 mm - this is the whole point

The sharpness people mean by "Jazz III" is the TIP RADIUS, not the edge bevel.
A blunt-tipped pick with a beautiful bevel still will not feel like one.

        351 tip  (R 5.0)          Jazz III tip  (R 1.6)
             __                          /\
           /    \                       /  \
          |      |                     |    |

On top of the small radius the tip also gets a long bevel, so the taper runs
right out to the point and the attack is precise.

FDM REALITY: the rim still cannot go below one nozzle width. The geometry gets
you the Jazz III shape and taper; the last bit of bite comes from sandpaper.

    python make_jazz.py     -> STL + comparison render
"""
import math
import os

import make_picks as mp
import make_stl as ms

OUT = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(OUT, "stl")

# --- Jazz III geometry ------------------------------------------------------
JZ_W = 24.5        # mm wide
JZ_H = 27.5        # mm long
JZ_R_SHOULDER = 9.0
JZ_R_TIP = 1.6     # THE defining number - a real point, not a round nose
JZ_CORE = 1.38     # mm, the classic Jazz III thickness
JZ_RIM = 0.40      # mm, one nozzle - the FDM floor
JZ_BEVEL = 2.60    # mm around the body
JZ_TIP_BEVEL = 6.50  # mm - long taper running out to the point


def apply_jazz():
    """Point the shared outline + solid builders at Jazz III numbers."""
    mp.PICK_W_MM = JZ_W
    mp.PICK_H_MM = JZ_H
    mp.R_SHOULDER_MM = JZ_R_SHOULDER
    mp.R_TIP_MM = JZ_R_TIP

    ms.PICK_W = JZ_W
    ms.PICK_H = JZ_H
    ms.T_CORE = JZ_CORE
    ms.T_RIM = JZ_RIM
    ms.BEVEL_W = JZ_BEVEL
    ms.TIP_BEVEL_W = JZ_TIP_BEVEL
    ms.LOGO_H = 0.35
    ms.RINGS = 18            # more loft steps - the long tip taper needs them


def restore_351():
    mp.PICK_W_MM = 26.0
    mp.PICK_H_MM = 31.0
    mp.R_SHOULDER_MM = 8.0
    mp.R_TIP_MM = 5.0
    ms.PICK_W = 26.0
    ms.PICK_H = 31.0
    ms.T_CORE = 1.20
    ms.T_RIM = 0.40
    ms.BEVEL_W = 3.20
    ms.TIP_BEVEL_W = 5.00
    ms.LOGO_H = 0.40
    ms.RINGS = 14


def tip_angle():
    """Included angle at the tip, in degrees - the number that says 'sharp'."""
    poly = ms.outline_mm()
    ys = [p[1] for p in poly]
    tip = max(ys)
    # two points a little back from the point, one each side
    back = [p for p in poly if tip - p[1] < ms.PICK_H * 0.30]
    left = min(back, key=lambda p: p[0])
    right = max(back, key=lambda p: p[0])
    apex = max(poly, key=lambda p: p[1])
    a1 = math.atan2(left[1] - apex[1], left[0] - apex[0])
    a2 = math.atan2(right[1] - apex[1], right[0] - apex[0])
    d = abs(math.degrees(a1 - a2))
    return d if d <= 180 else 360 - d


def main():
    os.makedirs(STL_DIR, exist_ok=True)
    apply_jazz()
    print("JAZZ  %.1f x %.1f mm | core %.2f  rim %.2f | tip radius %.1f mm"
          % (JZ_W, JZ_H, JZ_CORE, JZ_RIM, JZ_R_TIP))
    print("      tip included angle: %.0f deg" % tip_angle())
    m = ms.build_pick(0)
    p = os.path.join(STL_DIR, "alma-jazz3-sharp.stl")
    n = m.write_stl(p, "alma_jazz3")
    print("      %s  %d triangles  %d KB"
          % (os.path.basename(p), n, os.path.getsize(p) // 1024))

    # a plate of them
    m2 = ms.Mesh()
    for r in range(3):
        for c in range(5):
            ms.build_pick(0, dx=c * 28.0, dy=r * 31.0, mesh=m2)
    q = os.path.join(STL_DIR, "alma-jazz3-PLATE-5x3.stl")
    n2 = m2.write_stl(q, "alma_jazz3_plate")
    print("      %s  %d triangles  %d KB"
          % (os.path.basename(q), n2, os.path.getsize(q) // 1024))
    restore_351()


if __name__ == "__main__":
    main()
