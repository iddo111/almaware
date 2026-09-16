"""alma-larynx / make_silicone_fold_mold.py — mould to cast a REAL silicone vocal fold.

Not the water-tube hack. This casts a soft SILICONE fold in the true M5 vocal-fold shape
(Titze/Scherer M5; the same medial-surface geometry the self-oscillating synthetic folds
in the literature use). One fold per cast; cast twice for a pair.

WHY SILICONE, NOT LATEX-AND-WATER (Iddo's correction, honoured)
  A real vocal fold is layered soft TISSUE, not a bag of water. Cast soft silicone is the
  biomimetic match: it is a soft SOLID that can carry the mucosal wave. Silicone also
  CURES CHEMICALLY (not by drying), so unlike latex it cures fully even when thick - which
  is why this is a proper cavity mould, poured and cured, not an open dry-in-air trough.

THE M5 MEDIAL PROFILE (published parameter set; coordinates a=medial-lateral, b=inferior-
superior, mm). This is the fold's cross-section; it is extruded 17 mm anterior-posterior.
  (6.08,0.00)(4.89,1.00)(3.70,2.00)(2.50,3.00)(1.31,4.00)(0.12,5.00)  <- 40deg subglottal line
  (0.00,6.40)                                                         <- medial band (5deg)
  (0.289,7.098)(0.987,7.387)                                          <- r=0.987 turn, 90deg
  (9.00,8.40)(9.00,0.00)                                              <- superior + lateral wall

FIRST-CAST TARGET (honest): a SINGLE layer of Shore-10A silicone THINNED toward ~10-15 kPa
with silicone thinner (neat Shore-10A ~150 kPa is far too stiff - it squeals). The two-layer
soft-cover-over-body fold that gives a true mucosal wave comes later; the ultra-soft cover
tears on demould and is not a first-cast job.

    python make_silicone_fold_mold.py
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

# M5 cross-section polygon, (a=medial-lateral, b=inferior-superior)
M5 = np.array([
    (6.08, 0.00), (4.89, 1.00), (3.70, 2.00), (2.50, 3.00), (1.31, 4.00), (0.12, 5.00),
    (0.00, 6.40), (0.289, 7.098), (0.987, 7.387), (9.00, 8.40), (9.00, 0.00),
], dtype=np.float32)

FOLD_LEN = 17.0            # anterior-posterior extrusion
FLANGE = 3.0              # a base lip so the cast fold clamps into the collar


def poly_sdf(pts, verts):
    """Signed distance to a closed 2D polygon. pts: (...,2). Negative inside. iq's method."""
    p = pts.astype(np.float32)
    n = len(verts)
    d = np.sum((p - verts[0]) ** 2, axis=-1)
    sign = np.ones(p.shape[:-1], dtype=np.float32)
    j = n - 1
    for i in range(n):
        e = verts[j] - verts[i]
        w = p - verts[i]
        t = np.clip((w @ e) / float(e @ e), 0.0, 1.0)
        b = w - e[None, ...] * t[..., None]
        d = np.minimum(d, np.sum(b * b, axis=-1))
        c1 = p[..., 1] >= verts[i, 1]
        c2 = p[..., 1] < verts[j, 1]
        c3 = (e[0] * w[..., 1] - e[1] * w[..., 0]) > 0
        allc = c1 & c2 & c3
        nonec = (~c1) & (~c2) & (~c3)
        sign = np.where(allc | nonec, -sign, sign)
        j = i
    return sign * np.sqrt(d)


def fold_solid(P):
    """The fold we cast. Map profile (a,b) -> mould (Z=a up, Y=b depth), extrude along X.

    Lateral flat face (a=9) sits at the TOP (Z=9) = the open pour face; the contoured
    medial surface (a~0) is the cavity FLOOR, so it prints/casts crisply.
    """
    a = P[..., 2]                       # medial-lateral -> up
    b = P[..., 1]                       # inferior-superior -> depth
    pts = np.stack([a, b], axis=-1)
    d2 = poly_sdf(pts, M5)
    dx = np.abs(P[..., 0]) - FOLD_LEN / 2.0
    return np.minimum(np.maximum(d2, dx), 0.0) + np.hypot(np.maximum(d2, 0), np.maximum(dx, 0))


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


def mould(P):
    """Cavity mould with a clear pour opening at the top.

    The block is 2 mm taller than the fold (Z = -4 to 11). A pour slot
    punches through the top wall above the cavity so marching cubes sees
    one connected surface — the bug that made 96.5%-solid blocks was
    keep_largest throwing away the disconnected inner cavity sheet when
    the fold and block shared the same Z = 9 surface.
    """
    blk = box(P, (0, 2.5, 3.5), (13.0, 9.0, 7.5))     # Z from -4 to 11
    d = S(blk, fold_solid(P))
    # POUR OPENING: rectangular slot connecting the cavity to outside.
    # Overlaps the cavity top (Z=8-9) and extends through the block top (Z=11).
    pour = box(P, (0.0, 4.25, 10.0), (FOLD_LEN / 2 + 0.5, 4.75, 2.0))
    d = S(d, pour)
    # peel notch at one end so the cured fold lifts out without tearing
    d = S(d, box(P, (12.5, 2.5, 4.0), (2.0, 3.0, 6.0)))
    # a shallow finger-scoop on the OUTSIDE long face (grip; does not reach the cavity)
    d = S(d, cyl_x(P, (0, 12.0, -2.0), 2.0, 6.0))
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


def drop_dust(V, F, min_tris=50):
    """Drop tiny marching-cubes dust (< min_tris triangles). Keep everything
    significant — the old keep_largest was the 96.5%-solid bug: it threw away
    the entire inner cavity surface because it was a separate piece."""
    parent = np.arange(len(V))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for tri in F:
        a = find(int(tri[0]))
        for k in (1, 2):
            b = find(int(tri[k]))
            if a != b:
                parent[b] = a
    roots = np.array([find(int(f[0])) for f in F])
    vals, counts = np.unique(roots, return_counts=True)
    keep = vals[counts >= min_tris]
    mask = np.isin(roots, keep)
    Fk = F[mask]
    used = np.unique(Fk)
    remap = -np.ones(len(V), dtype=np.int64); remap[used] = np.arange(len(used))
    return V[used], remap[Fk]


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
        fh.write(b"ALMA-SILICONE-FOLD-MOLD" + b" " * 57)
        fh.write(struct.pack("<I", len(F)))
        buf = bytearray()
        for i in range(len(F)):
            buf += struct.pack("<12fH", *n[i], *tri[i, 0], *tri[i, 1], *tri[i, 2], 0)
        fh.write(bytes(buf))


def main() -> int:
    print("ALMA — REAL silicone vocal-fold mould (M5 shape)")
    print("=" * 60)
    t0 = time.time()
    V, F = polygonise(mould, (-16, -6, -1), (16, 15, 14), 0.25)
    V, F = drop_dust(V, F)
    bad, pieces = check(V, F)
    bb = V.max(axis=0) - V.min(axis=0)
    tri = V[F]
    vol = abs(np.sum(np.cross(tri[:, 0], tri[:, 1]) * tri[:, 2]) / 6.0)
    bbox_vol = bb[0] * bb[1] * bb[2]
    solid_pct = vol / bbox_vol * 100 if bbox_vol > 0 else 0
    print("  size : %.1f x %.1f x %.1f mm" % tuple(bb))
    print("  mesh : %d tri, %d piece(s), %d open edges" % (len(F), pieces, bad))
    print("  solid: %.1f%%  (volume %.0f / bbox %.0f mm3)" % (solid_pct, vol, bbox_vol))
    ok = (bad == 0 and solid_pct < 85)
    if solid_pct > 85:
        print("  *** SOLID BLOCK — not a mold! cavity missing ***")
    print("  %s (%.0fs)" % ("OK" if ok else "*** CHECK ***", time.time() - t0))
    if ok:
        write_stl("silicone-fold-mold.stl", V, F)
        print("  wrote silicone-fold-mold.stl")
    else:
        print("  REFUSED to write — fix the geometry first.")
        return 1
    print("-" * 60)
    print("  CAST: Ecoflex 00-30 or Shore-10A + thinner. Mould release, pour,")
    print("        vacuum-degas if you can (or pour thin + tap), cure, peel from the notch.")
    print("  PLA is fine - it does NOT inhibit platinum silicone. KEEP LATEX AWAY (it does).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
