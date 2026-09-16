"""alma-larynx / make_lips.py — rough glue-on lip ends: one for "ah", one for "ooh".

KISS first build (Iddo's call): vocal folds buzz, a short tube carries the buzz, and a
LIP END on the tube shapes the vowel. Swap/glue the end to change the sound:
  - mouth-ah  : opens WIDE  -> the buzz comes out as "ah"
  - mouth-ooh : necks to a small ROUND hole with a short lip -> "ooh"

Both are just a glue SOCKET (slips over the ~24 mm tract/collar tube) plus the mouth shape.
Deliberately rough - glue fills any gap. Print, glue on, blow air, hear the vowel change.

    python make_lips.py
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


def cyl(P, c, r, h):
    p = P - np.asarray(c, dtype=np.float32)
    d = np.hypot(p[..., 0], p[..., 1]) - r
    dz = np.abs(p[..., 2]) - h
    return np.minimum(np.maximum(d, dz), 0.0) + np.hypot(np.maximum(d, 0), np.maximum(dz, 0))


def cone(P, c, r0, r1, h):
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


def U(a, b): return np.minimum(a, b)
def S(a, b): return np.maximum(a, -b)

SOCK_OUT = 14.0     # socket outer radius
SOCK_IN = 12.0      # socket inner radius -> slips over a ~24 mm OD tube; glue fills the rest
SOCK_H = 7.0


def mouth_ah(P):
    """Wide bell = 'ah'. Flares from the socket out to a big open mouth."""
    d = cyl(P, (0, 0, 0.0), SOCK_OUT, SOCK_H)                 # glue socket
    d = U(d, cone(P, (0, 0, 14.0), SOCK_OUT, 22.0, 7.0))      # flare out
    d = U(d, torus(P, (0, 0, 21.0), 21.0, 1.6))              # rounded lip rim
    d = S(d, cyl(P, (0, 0, -1.0), SOCK_IN, SOCK_H + 2))       # glue bore
    d = S(d, cone(P, (0, 0, 14.0), SOCK_IN, 20.0, 8.0))       # open throat
    return d


def mouth_ooh(P):
    """Necks to a small round hole + a short protruding lip = 'ooh'."""
    d = cyl(P, (0, 0, 0.0), SOCK_OUT, SOCK_H)                 # glue socket
    d = U(d, cone(P, (0, 0, 12.0), SOCK_OUT, 8.5, 5.0))       # neck IN
    d = U(d, cyl(P, (0, 0, 19.0), 8.5, 3.0))                 # short protruding lip tube
    d = U(d, torus(P, (0, 0, 22.0), 6.5, 2.0))               # rounded lip ring
    d = S(d, cyl(P, (0, 0, -1.0), SOCK_IN, SOCK_H + 2))       # glue bore
    d = S(d, cone(P, (0, 0, 12.0), SOCK_IN, 5.0, 6.0))        # narrowing throat
    d = S(d, cyl(P, (0, 0, 20.0), 5.0, 6.0))                 # the small round OOH hole (~10 mm)
    return d


PARTS = {"mouth-ah": (mouth_ah, 26), "mouth-ooh": (mouth_ooh, 18)}


def polygonise(fn, half_xy, ztop, voxel):
    from skimage import measure
    lo = (-half_xy, -half_xy, -2.0); hi = (half_xy, half_xy, ztop)
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
    return int((c != 2).sum()), len({find(i) for i in range(len(V))})


def write_stl(path, V, F):
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    with open(path, "wb") as fh:
        fh.write(b"ALMA-LIPS" + b" " * 71)
        fh.write(struct.pack("<I", len(F)))
        buf = bytearray()
        for i in range(len(F)):
            buf += struct.pack("<12fH", *n[i], *tri[i, 0], *tri[i, 1], *tri[i, 2], 0)
        fh.write(bytes(buf))


def main() -> int:
    print("ALMA — rough glue-on lips (ah / ooh)")
    print("=" * 56)
    ok = True
    for name, (fn, ztop) in PARTS.items():
        t0 = time.time()
        V, F = polygonise(fn, 26.0, ztop, 0.3)
        bad, pieces = check(V, F)
        bb = V.max(axis=0) - V.min(axis=0)
        good = bad == 0 and pieces == 1
        print("  %-11s %.0f x %.0f x %.0f mm  %6d tri  %d pc  %s (%.0fs)"
              % (name, bb[0], bb[1], bb[2], len(F), pieces,
                 "OK" if good else "*** %d open ***" % bad, time.time() - t0))
        write_stl(name + ".stl", V, F)
        ok = ok and good
    print("-" * 56)
    print("  PRINT: PLA, 0.2 mm. Glue the socket onto the tract tube. Swap ah<->ooh.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
