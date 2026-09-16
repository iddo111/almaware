# -*- coding: utf-8 -*-
"""feather_socket_test.py -- the one experiment that decides whether DORON can have wings.

Iddo, 2026-08-23: "אפשר להדפיס מגרעות וחורים מיוחדים ותעלות לנוצות ואז למלא בדבק או
אפוקסי משהו שנקשר כימית לשני הדברים."

He is right about the principle and reinvented the follicle: a bird's feather is not glued
on, it sits SOCKETED in. But the chemistry only works on one side -- epoxy bonds beautifully
to keratin and badly to nylon, and PA12 is nylon. So the joint must not depend on adhesion
to the plastic at all. It must TRAP the epoxy.

WHAT THIS PRINTS. Four coupons, 40 mm each, every one a groove for a feather quill:

    A  CONTROL      straight 3 mm groove, no undercut.
                    Whatever this holds is what plain adhesion is worth. Without it the
                    other three numbers mean nothing.
    B  DOVETAIL     3 mm at the mouth widening to 6 mm at the floor. The cured plug is
                    wider than the hole it would have to come out of.
    C  T-SLOT       narrow neck, then a wide chamber. A more aggressive trap.
    D  CROSS-PIN    straight groove plus a hole THROUGH the bar. The epoxy forms a rivet
                    across the whole part; the plug and the bar become one piece.

THE TEST. Glue a feather into each with the same epoxy and the same cure. Pull each one
until something fails, and WRITE DOWN WHAT FAILED -- the feather tearing, the plug sliding
out, or the plastic itself breaking. If the plastic breaks first, the joint is stronger than
the wing needs and the design is finished.

PRINTABLE TONIGHT, WITHOUT THE HARDENED NOZZLE. Every groove opens UPWARD and every
overhang is at 45 degrees or shallower, so this needs no supports and no exotic head. Print
it in PETG now; the geometry is what is being tested, not the material. When the hardened
head arrives, print the winner again in PA12-CF and it will already be known to work.

    python feather_socket_test.py        ->  doron_feather_sockets.stl
"""
from __future__ import annotations

import math
import os
import struct

# ---- dimensions, mm. A goose/duck quill is ~2.5-3.5 mm across at the calamus. ----
LEN = 40.0          # how far the quill is buried, along X
W = 16.0            # coupon width
H = 12.0            # coupon height
MOUTH = 3.2         # groove opening -- the quill slides in through this
DEPTH = 7.0         # how deep the groove runs
FLOOR_W = 6.4       # dovetail floor width: twice the mouth, so the plug cannot rise
NECK = 2.5          # T-slot neck depth
CHAMBER_W = 8.0     # T-slot chamber width
CHAMBER_H = 3.5
PIN_D = 3.0         # cross-pin hole diameter
GAP = 6.0           # spacing between coupons on the plate


def profile(kind):
    """The YZ cross-section, counter-clockwise, as (y, z). Z up, groove opens upward.

    Every inward-leaning wall is kept at 45 degrees or shallower so the printer bridges it
    with no support: a steeper undercut would grip better and be unprintable, which is not
    a better joint.
    """
    y0, y1 = -W / 2, W / 2
    top = H
    m0, m1 = -MOUTH / 2, MOUTH / 2
    floor = H - DEPTH

    if kind == "control":
        inner = [(m1, top), (m1, floor), (m0, floor), (m0, top)]
    elif kind == "dovetail":
        f0, f1 = -FLOOR_W / 2, FLOOR_W / 2
        inner = [(m1, top), (f1, floor), (f0, floor), (m0, top)]
    elif kind == "tslot":
        c0, c1 = -CHAMBER_W / 2, CHAMBER_W / 2
        neck_z = top - NECK
        cham_z = neck_z - CHAMBER_H
        inner = [(m1, top), (m1, neck_z), (c1, neck_z - (c1 - m1)),   # 45 deg flare out
                 (c1, cham_z), (c0, cham_z), (c0, neck_z - (c1 - m1)),
                 (m0, neck_z), (m0, top)]
    elif kind == "crosspin":
        inner = [(m1, top), (m1, floor), (m0, floor), (m0, top)]
    else:
        raise ValueError(kind)

    # outline: up the right wall, across the top to the groove, down into it, out, and back
    return [(y0, 0.0), (y1, 0.0), (y1, top)] + inner + [(y0, top)]


def tri(a, b, c):
    return (a, b, c)


def extrude(poly, x0, x1):
    """Extrude a closed 2D polygon (y,z) along X. Returns triangles as ((x,y,z),...)."""
    tris = []
    n = len(poly)
    # side walls
    for i in range(n):
        y0, z0 = poly[i]
        y1, z1 = poly[(i + 1) % n]
        p00 = (x0, y0, z0); p01 = (x0, y1, z1)
        p10 = (x1, y0, z0); p11 = (x1, y1, z1)
        tris.append(tri(p00, p10, p11))
        tris.append(tri(p00, p11, p01))
    # caps by fan triangulation from vertex 0. The profiles here are all star-shaped from
    # their first vertex, so a fan is valid; a general polygon would need ear clipping.
    for i in range(1, n - 1):
        y0, z0 = poly[0]; y1, z1 = poly[i]; y2, z2 = poly[i + 1]
        tris.append(tri((x0, y0, z0), (x0, y2, z2), (x0, y1, z1)))
        tris.append(tri((x1, y0, z0), (x1, y1, z1), (x1, y2, z2)))
    return tris


def cylinder_hole(cx, cy, cz, d, axis_len, seg=24):
    """A through-hole as an inward-facing cylinder wall, drilled along Y."""
    tris = []
    r = d / 2
    for i in range(seg):
        a0 = 2 * math.pi * i / seg
        a1 = 2 * math.pi * (i + 1) / seg
        p0 = (cx + r * math.cos(a0), cy - axis_len / 2, cz + r * math.sin(a0))
        p1 = (cx + r * math.cos(a1), cy - axis_len / 2, cz + r * math.sin(a1))
        q0 = (cx + r * math.cos(a0), cy + axis_len / 2, cz + r * math.sin(a0))
        q1 = (cx + r * math.cos(a1), cy + axis_len / 2, cz + r * math.sin(a1))
        tris.append(tri(p0, q0, q1))
        tris.append(tri(p0, q1, p1))
    return tris


def translate(tris, dx, dy, dz):
    return [tuple((x + dx, y + dy, z + dz) for (x, y, z) in t) for t in tris]


def write_stl(path, tris, name="doron_feather_sockets"):
    with open(path, "wb") as f:
        f.write(struct.pack("<80sI", name.encode()[:80].ljust(80, b" "), len(tris)))
        for a, b, c in tris:
            ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<3f", nx / m, ny / m, nz / m))
            for p in (a, b, c):
                f.write(struct.pack("<3f", *p))
            f.write(struct.pack("<H", 0))


if __name__ == "__main__":
    kinds = ["control", "dovetail", "tslot", "crosspin"]
    all_tris = []
    for i, k in enumerate(kinds):
        t = extrude(profile(k), 0.0, LEN)
        if k == "crosspin":
            # the rivet hole: through the bar, below the groove floor, at mid-length
            t += cylinder_hole(LEN / 2, 0.0, (H - DEPTH) / 2 + 1.0, PIN_D, W + 2)
        all_tris += translate(t, 0.0, i * (W + GAP), 0.0)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "doron_feather_sockets.stl")
    write_stl(out, all_tris)

    print("wrote %s  (%d triangles)" % (out, len(all_tris)))
    print()
    print("four coupons, %.0f mm long, %.0f x %.0f mm each:" % (LEN, W, H))
    print("  A control   straight %.1f mm groove          <- what plain adhesion is worth" % MOUTH)
    print("  B dovetail  %.1f mm mouth -> %.1f mm floor" % (MOUTH, FLOOR_W))
    print("  C t-slot    %.1f mm neck, %.1f mm chamber" % (NECK, CHAMBER_W))
    print("  D cross-pin straight groove + %.1f mm rivet hole through the bar" % PIN_D)
    print()
    print("plate footprint: %.0f x %.0f mm, ~%.0f g in PETG" %
          (LEN, len(kinds) * (W + GAP), len(kinds) * LEN * W * H * 0.35 / 1000 * 1.27))
    print("no supports needed: every groove opens upward, every overhang <= 45 deg")
    print()
    print("THE TEST: same feather, same epoxy, same cure in all four. Pull each until")
    print("something gives, and write down WHICH THING FAILED -- feather, plug, or plastic.")
    print("If the plastic breaks first, the joint is finished and DORON has wings.")
