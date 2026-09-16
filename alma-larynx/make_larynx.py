"""alma-larynx / make_larynx.py — the printable parts that get to FIRST BUZZ.

Milestone 0 is not "ah". Milestone 0 is ONE STABLE PERIODIC SOUND. Three printed parts
and a soda bottle get you there:

    pump -> [PLENUM CAP on a 1.5 L bottle] -> [BLEED TEE] -> [BUZZ COLLAR + latex] -> sound

WHY EACH PART EXISTS — none of these is decoration

  PLENUM CAP   An AC diaphragm pump does not blow, it PUFFS, at mains frequency (50 Hz).
               That sits directly on top of the vocal f0 band, so the rig would "sing"
               the mains and you would never know whether the latex was doing anything.
               A 1.5 L bottle in the line is a low-pass filter that flattens it.

  BLEED TEE    THE ONLY PRESSURE PROTECTION ON THIS RIG. A fixed drilled hole, no valve,
               no spring, nothing to adjust and nothing that can be left shut. Phonation
               needs 300-1000 Pa; a hobby pump dead-heads at 20 000 Pa, i.e. 20-65x more
               than needed, and will burst a membrane. The hole vents the excess and
               cannot be defeated by any firmware bug, because it is a hole.

               Size it to YOUR pump:   d(mm) = 0.62 * sqrt(Q)     Q = flow in L/min
               Measure Q by water displacement, do not trust the box. At Q = 5 L/min
               that is 1.39 mm. The part prints a 1.0 mm pilot — DRILL it to size. A
               printed small hole is never its nominal diameter.

  BUZZ COLLAR  Holds the latex. The rim is a 1.5 mm ROUND, never a knife edge: a sharp
               clamp edge cuts thin latex under tension, which is how you lose a membrane
               mid-experiment and blame the physics.

HONEST EXPECTATION, up front: a single stretched condom will BUZZ like a reed. It will
almost certainly not phonate like a larynx — the published threshold equation is
Pth ~ xi0/T, and a 0.07 mm film has effectively no vertical thickness T, so the mucosal
wave that drives real phonation has nothing to travel through. Double the latex, and
treat the buzz as the win it is: it proves the air path, the plenum, the seal and the
ear all work. The water-filled fold that actually phonates comes after, and it reuses
every one of these parts.

    python make_larynx.py                 # all three
    python make_larynx.py --flow 8        # size the bleed orifice for an 8 L/min pump
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
import time

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ------------------------------------------------------------------ SDF toolbox
def cyl(P, c, r, h):
    """Z-axis cylinder centred at c, radius r, half-height h."""
    p = P - np.asarray(c, dtype=np.float32)
    d = np.hypot(p[..., 0], p[..., 1]) - r
    dz = np.abs(p[..., 2]) - h
    return np.minimum(np.maximum(d, dz), 0.0) + np.hypot(np.maximum(d, 0), np.maximum(dz, 0))


def cone(P, c, r0, r1, h):
    """Tapered z-axis cylinder: radius r0 at the bottom, r1 at the top, height 2h."""
    p = P - np.asarray(c, dtype=np.float32)
    t = np.clip((p[..., 2] + h) / (2 * h), 0.0, 1.0)
    r = r0 + (r1 - r0) * t
    d = np.hypot(p[..., 0], p[..., 1]) - r
    dz = np.abs(p[..., 2]) - h
    return np.minimum(np.maximum(d, dz), 0.0) + np.hypot(np.maximum(d, 0), np.maximum(dz, 0))


def torus(P, c, R, r):
    p = P - np.asarray(c, dtype=np.float32)
    q = np.hypot(np.hypot(p[..., 0], p[..., 1]) - R, p[..., 2])
    return q - r


def cyl_x(P, c, r, h):
    """X-axis cylinder — for the side bleed stub."""
    p = P - np.asarray(c, dtype=np.float32)
    d = np.hypot(p[..., 1], p[..., 2]) - r
    dx = np.abs(p[..., 0]) - h
    return np.minimum(np.maximum(d, dx), 0.0) + np.hypot(np.maximum(d, 0), np.maximum(dx, 0))


def U(a, b):
    return np.minimum(a, b)


def S(a, b):
    return np.maximum(a, -b)


def I(a, b):
    return np.maximum(a, b)


def barb(P, c, h, r_out=2.9, ribs=3):
    """Push-fit barb for 4 mm ID aquarium airline. Ribs stop it blowing off."""
    z0 = c[2]
    d = cone(P, (c[0], c[1], z0 + h / 2), r_out - 0.5, r_out - 0.9, h / 2)
    for k in range(ribs):
        zz = z0 + h * (0.22 + 0.28 * k)
        d = U(d, torus(P, (c[0], c[1], zz), r_out - 0.85, 0.75))
    return d


# ------------------------------------------------------------------ the parts
def buzz_collar(P):
    """Latex holder. Air enters the barb, leaves through the membrane on the rim."""
    RIM_R = 17.0                    # membrane mouth radius
    WALL = 2.4
    d = cyl(P, (0, 0, 21.0), RIM_R + WALL, 9.0)          # upper barrel
    d = U(d, cone(P, (0, 0, 8.0), 7.5, RIM_R + WALL, 4.0))
    d = U(d, cyl(P, (0, 0, 3.0), 7.5, 3.0))              # spigot base
    d = U(d, barb(P, (0, 0, -14.0), 14.0))               # inlet, pointing DOWN

    # Bore. TWO subtractions, not one: the wide chamber must stay INSIDE the barrel.
    # A single tall wide cut (r=15.2 from z=-4 to 36) removed the spigot and most of
    # the cone, leaving the barb floating unattached to the barrel — still watertight,
    # so the edge check passed it. Only rendering it showed two separate objects.
    d = S(d, cyl(P, (0, 0, 22.0), RIM_R - WALL + 0.6, 9.0))     # chamber, z 13..31
    d = S(d, cone(P, (0, 0, 9.0), 2.6, 14.0, 5.0))              # throat, z 4..14
    d = S(d, cyl(P, (0, 0, -8.0), 2.0, 15.0))                   # airline bore

    # ROUNDED RIM. A knife edge cuts latex under tension.
    d = U(d, torus(P, (0, 0, 30.0), RIM_R + WALL / 2, 1.5))
    # clamp groove for a zip tie or a fat rubber band — no printed clamp needed
    d = S(d, torus(P, (0, 0, 24.5), RIM_R + WALL + 0.6, 2.0))
    return d


def plenum_cap(P):
    """Tapered plug for a 1.5 L soda bottle neck (PCO-1881, ~21.7 mm ID).

    A taper plus PTFE tape beats a printed thread every time: printed threads on a
    28 mm cap need tolerances an FDM machine will not hold, and a leaking plenum is
    indistinguishable from a pump that is too weak.
    """
    d = cone(P, (0, 0, -9.0), 20.6, 22.6, 9.0)           # the plug, wide at the top
    d = U(d, cyl(P, (0, 0, 2.0), 15.0, 2.0))             # stop flange, sits on the neck
    d = U(d, barb(P, (-7.0, 0, 4.0), 14.0))              # IN, from the pump
    d = U(d, barb(P, (7.0, 0, 4.0), 14.0))               # OUT, to the larynx
    d = S(d, cyl(P, (-7.0, 0, 0.0), 2.0, 26.0))
    d = S(d, cyl(P, (7.0, 0, 0.0), 2.0, 26.0))
    return d


def bleed_tee(P, orifice_pilot=1.0):
    """The pressure limiter. Inline on the way to the larynx, with a vent to atmosphere.

    The vent stub is deliberately a bare boss with a pilot hole. It gets DRILLED, and
    nothing may ever be fitted to it that restricts flow — no valve, no foam, no muffler.
    A restricted relief is not a relief.
    """
    d = cyl(P, (0, 0, 0.0), 6.0, 11.0)                   # body
    d = U(d, barb(P, (0, 0, 11.0), 14.0))                # to the larynx
    d = U(d, cone(P, (0, 0, -18.0), 2.4, 2.9, 7.0))      # from the pump (push-on)
    d = S(d, cyl(P, (0, 0, 0.0), 2.0, 30.0))             # the through bore

    # the vent boss, sideways so the jet never points up at your face
    d = U(d, cyl_x(P, (9.0, 0, 3.0), 3.2, 5.0))
    d = S(d, cyl_x(P, (9.0, 0, 3.0), orifice_pilot / 2.0, 12.0))
    return d


PARTS = {
    "buzz-collar": (buzz_collar, (-24, -24, -20), (24, 24, 34)),
    "plenum-cap": (plenum_cap, (-18, -18, -20), (18, 18, 20)),
    "bleed-tee": (bleed_tee, (-9, -9, -26), (16, 9, 26)),
}


# ------------------------------------------------------------------ meshing
def polygonise(fn, lo, hi, voxel):
    from skimage import measure
    n = [int(math.ceil((hi[i] - lo[i]) / voxel)) + 6 for i in range(3)]
    g = [lo[i] - 3 * voxel + np.arange(n[i], dtype=np.float32) * voxel for i in range(3)]
    vol = np.empty(n, dtype=np.float32)
    X, Y = np.meshgrid(g[0], g[1], indexing="ij")
    for k, zz in enumerate(g[2]):
        vol[:, :, k] = fn(np.stack([X, Y, np.full_like(X, zz)], axis=-1))
    vol[0, :, :] = vol[-1, :, :] = 1e3
    vol[:, 0, :] = vol[:, -1, :] = 1e3
    vol[:, :, 0] = vol[:, :, -1] = 1e3
    v, f, _n, _val = measure.marching_cubes(vol, level=0.0)
    v = v * voxel + np.array([g[0][0], g[1][0], g[2][0]], dtype=np.float32)
    return v.astype(np.float32), f.astype(np.int64)


def check(V, F):
    """Open edges, volume, AND number of separate solids.

    The piece count is not padding. The first buzz-collar came out watertight and in
    TWO PIECES — a bore subtraction had severed the barb from the barrel. Every edge
    was still shared by exactly two triangles, so the manifold test passed it happily.
    Watertight says the surface is closed; it says nothing about whether the thing is
    one object. Print that and you get two useless parts and no idea why.
    """
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _u, c = np.unique(e, axis=0, return_counts=True)
    a, b, cc = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    vol = abs(float(np.einsum("ij,ij->i", a, np.cross(b, cc)).sum()) / 6.0)

    # union-find over vertices joined by an edge -> how many connected shells?
    parent = np.arange(len(V))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in _u:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    pieces = len({find(i) for i in range(len(V))})
    return int((c != 2).sum()), vol, pieces


def write_stl(path, V, F):
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    with open(path, "wb") as fh:
        fh.write(b"ALMA-LARYNX" + b" " * 69)
        fh.write(struct.pack("<I", len(F)))
        buf = bytearray()
        for i in range(len(F)):
            buf += struct.pack("<12fH", *n[i], *tri[i, 0], *tri[i, 1], *tri[i, 2], 0)
        fh.write(bytes(buf))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voxel", type=float, default=0.25)
    ap.add_argument("--flow", type=float, default=5.0,
                    help="YOUR pump's measured flow in L/min — sets the bleed orifice")
    a = ap.parse_args()

    d_req = 0.62 * math.sqrt(a.flow)
    print("ALMA LARYNX — Milestone 0 parts")
    print("=" * 70)
    print("  bleed orifice for %.1f L/min : DRILL TO %.2f mm  (printed pilot 1.0 mm)"
          % (a.flow, d_req))
    print("  measure your pump by water displacement. Do not trust the box.")
    print("-" * 70)

    ok = True
    for name, (fn, lo, hi) in PARTS.items():
        t0 = time.time()
        V, F = polygonise(fn, lo, hi, a.voxel)
        bad, vol, pieces = check(V, F)
        bb = V.max(axis=0) - V.min(axis=0)
        good = (bad == 0 and pieces == 1)
        print("  %-13s %5.1f x %5.1f x %5.1f mm  %6.2f cm3  %6d tri  %d piece%s  %s (%.0fs)"
              % (name, bb[0], bb[1], bb[2], vol / 1000, len(F), pieces,
                 "" if pieces == 1 else "s", "OK" if good else
                 ("*** %d OPEN EDGES ***" % bad if bad else "*** NOT CONNECTED ***"),
                 time.time() - t0))
        write_stl(name + ".stl", V, F)
        ok = ok and good

    print("-" * 70)
    print("  PRINT: PETG (it gets wet and warm). 0.2 mm layers, 4 walls, 40% infill.")
    print("         Airtight matters more than pretty — under-walled parts weep air.")
    print("  THEN : drill the bleed stub to %.2f mm and TEST IT before any latex goes on:" % d_req)
    print("         block the outlet completely, run the pump for 60 s, and watch a water")
    print("         manometer. It must stabilise. If it climbs, the hole is too small.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
