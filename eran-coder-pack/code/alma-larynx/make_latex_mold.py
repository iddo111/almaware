"""alma-larynx / make_latex_mold.py — a printable mold to CAST a soft latex vocal fold.

Iddo has LIQUID LATEX (the pour-and-air-dry kind) and wants a printed mold to cast a soft
fold from it. This makes that mold: an OPEN-TOP trough whose curved floor forms the fold's
vibrating (medial) surface. He brushes/pours liquid latex in, it air-dries, he peels out a
soft fold with a flange to clamp into the buzz collar.

WHY OPEN-TOP, NOT A CLOSED 2-PART MOLD (this matters for LATEX specifically)
  Liquid latex cures by the WATER EVAPORATING, not by a chemical reaction. A thick closed
  pour stays gooey inside for DAYS because the water can't get out. An open trough dries
  from the top down and is done in hours. So for latex the mould is deliberately open, and
  the cast is deliberately THIN (a few mm) - which is also exactly what a vibrating fold
  wants. Build it up in 2-3 thin brushed coats, not one deep pour.

  Two folds are needed (they sit in a pair). Cast the same mould twice, or print two.

    python make_latex_mold.py
"""
from __future__ import annotations

import math
import struct
import sys
import time

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---- SDF primitives ----
def box(P, c, h):
    q = np.abs(P - np.asarray(c, dtype=np.float32)) - np.asarray(h, dtype=np.float32)
    return np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(np.max(q, axis=-1), 0.0)


def cyl_x(P, c, r, h):
    p = P - np.asarray(c, dtype=np.float32)
    d = np.hypot(p[..., 1], p[..., 2]) - r
    dx = np.abs(p[..., 0]) - h
    return np.minimum(np.maximum(d, dx), 0.0) + np.hypot(np.maximum(d, 0), np.maximum(dx, 0))


def U(a, b): return np.minimum(a, b)
def S(a, b): return np.maximum(a, -b)


def mold(P):
    """One open-top latex-fold mould.

    Coordinates: X = fold length (anterior-posterior), Y = depth, Z = up.
    The block is solid; the fold cavity is carved from the TOP so it is open for pouring
    and drying. The cavity floor is a rounded channel = the fold's medial surface.
    """
    # outer block
    d = box(P, (0, 0, 9.0), (16.0, 11.0, 9.0))

    # the fold CAVITY - an X-axis rounded channel, open to the top.
    # A cylinder makes the curved medial floor; a box above it opens the mouth.
    CH_LEN = 12.0                      # fold length (A-P) ~ 24 mm
    ch_r = 4.6                         # channel radius -> ~4.6 mm fold half-depth
    cav = cyl_x(P, (0, 1.0, 10.5), ch_r, CH_LEN)
    cav = U(cav, box(P, (0, 1.0, 14.0), (CH_LEN, ch_r, 4.0)))   # open the top
    d = S(d, cav)

    # FLANGE SEAT: a shallow wider ledge at the cavity mouth so the cast fold ends in a
    # lip you can clamp into the buzz collar instead of a raw torn edge.
    ledge = box(P, (0, 1.0, 13.2), (CH_LEN + 1.0, ch_r + 2.2, 1.4))
    ledge = S(ledge, box(P, (0, 1.0, 13.2), (CH_LEN + 4, ch_r - 0.2, 3.0)))
    d = S(d, ledge)

    # DRAIN/PEEL notch at one end - a finger slot so a thin dried latex fold peels out
    # without tearing (latex grabs; give it a lift point).
    d = S(d, box(P, (14.0, 1.0, 11.0), (3.0, 3.0, 3.5)))

    # registration notches on the outside (so two moulds or a lid align) + a flat base
    d = S(d, cyl_x(P, (0, 11.0, 3.0), 1.6, 20.0))
    return d


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
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _u, c = np.unique(e, axis=0, return_counts=True)
    parent = np.arange(len(V))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, j in _u:
        ri, rj = find(int(i)), find(int(j))
        if ri != rj:
            parent[ri] = rj
    pieces = len({find(i) for i in range(len(V))})
    return int((c != 2).sum()), pieces


def write_stl(path, V, F):
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    with open(path, "wb") as fh:
        fh.write(b"ALMA-LATEX-MOLD" + b" " * 65)
        fh.write(struct.pack("<I", len(F)))
        buf = bytearray()
        for i in range(len(F)):
            buf += struct.pack("<12fH", *n[i], *tri[i, 0], *tri[i, 1], *tri[i, 2], 0)
        fh.write(bytes(buf))


def main() -> int:
    print("ALMA — latex fold casting mould")
    print("=" * 60)
    t0 = time.time()
    V, F = polygonise(mold, (-18, -13, -1), (18, 13, 20), 0.25)
    bad, pieces = check(V, F)
    bb = V.max(axis=0) - V.min(axis=0)
    print("  size   : %.1f x %.1f x %.1f mm" % tuple(bb))
    print("  mesh   : %d tri, %d piece(s), %d open edges  %s (%.0fs)"
          % (len(F), pieces, bad,
             "OK" if (bad == 0 and pieces == 1) else "*** CHECK ***", time.time() - t0))
    write_stl("latex-fold-mold.stl", V, F)
    print("  wrote latex-fold-mold.stl")
    print("-" * 60)
    print("  PRINT: PLA, 0.16 mm, 3 walls. Sand the cavity smooth, or brush one coat of")
    print("         wipe-on poly so the latex peels clean.")
    return 0 if (bad == 0 and pieces == 1) else 1


if __name__ == "__main__":
    sys.exit(main())
