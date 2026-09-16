"""alma-figure / make_iddo.py — a caricature bobblehead of Iddo, printable.

Built as a signed distance field and polygonised with marching cubes, so the mesh is
CLOSED BY CONSTRUCTION - no grid artefacts, no holes to patch afterwards. Every part
is a smooth-union of primitives, which is what gives it the soft, moulded, toy-like
look rather than a pile of visible spheres.

THE BRIEF, in Iddo's words: "full body figure of me, but the head is enlarged in a
comical way, and certain features are enlarged in a comical way. Make it funny, not
demeaning."

So the exaggeration is aimed at the things that make him HIM and that he plainly likes
about himself - read off his own head-scan video: the big bald dome, the enormous
expressive eyebrows, the strong nose, the grin he keeps breaking into, the builder's
hands. Nothing is aimed at anything he might wince at. A caricature is affectionate
when it exaggerates what a friend would recognise across a room, and cruel when it
exaggerates what someone would rather you had not noticed. This one stays on the first
side of that line.

    python make_iddo.py                    # default 120 mm figure
    python make_iddo.py --height 150 --exaggeration 1.3
    python make_iddo.py --voxel 0.35       # finer (slower, bigger file)

Output: iddo-figure.stl  + a watertightness and volume report.
"""
from __future__ import annotations

import argparse
import struct
import sys
import time

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---------------------------------------------------------------- SDF toolbox
def sphere(P, c, r):
    return np.linalg.norm(P - np.asarray(c, dtype=np.float32), axis=-1) - r


def ellipsoid(P, c, r):
    """Not a true distance (it is a bound), but exact enough at the zero level."""
    r = np.asarray(r, dtype=np.float32)
    q = (P - np.asarray(c, dtype=np.float32)) / r
    k0 = np.linalg.norm(q, axis=-1)
    k1 = np.linalg.norm(q / r, axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def capsule(P, a, b, r):
    a = np.asarray(a, dtype=np.float32); b = np.asarray(b, dtype=np.float32)
    pa = P - a
    ba = b - a
    h = np.clip((pa @ ba) / float(ba @ ba), 0.0, 1.0)[..., None]
    return np.linalg.norm(pa - ba * h, axis=-1) - r


def smin(d1, d2, k):
    """Smooth minimum — the union that MELTS parts together instead of creasing them."""
    h = np.clip(0.5 + 0.5 * (d2 - d1) / k, 0.0, 1.0)
    return d2 * (1 - h) + d1 * h - k * h * (1.0 - h)


def smax(d1, d2, k):
    h = np.clip(0.5 - 0.5 * (d2 - d1) / k, 0.0, 1.0)
    return d2 * (1 - h) + d1 * h + k * h * (1.0 - h)


def ssub(d, cut, k):
    """Smooth subtraction: carve `cut` out of `d` with a soft rim (eye sockets, mouth)."""
    return smax(d, -cut, k)


# ---------------------------------------------------------------- the figure
def build(P, E=1.0, oud=True):
    """Signed distance to the figure. P is (...,3) in mm, z up, feet at z=0, nose toward +y.

    E is the exaggeration dial. E=1 is the intended caricature; E=1.3 pushes it toward
    a bobblehead; E=0.7 pulls back toward a portrait.
    """
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    mirror = np.stack([np.abs(x), y, z], axis=-1)      # left/right symmetry, one build

    # ---- base: a FLAT oval pad ------------------------------------------
    # Not a capsule. capsule(a,b,r) with a≈b is a SPHERE of radius r, so the first
    # version had him balancing on a 20 mm ball. A squashed ellipsoid is the pad.
    d = ellipsoid(P, (0, 1.0, 2.6), (21.0, 19.0, 2.8))

    # ---- feet: shoes poking forward off the pad --------------------------
    feet = ellipsoid(mirror, (7.5, 3.0, 5.0), (5.6, 8.5, 4.2))
    d = smin(d, feet, 2.0)

    # ---- legs: short and stumpy — that is the joke of the proportions ----
    # Small blend radius so they stay two legs instead of melting into a skirt.
    leg = capsule(mirror, (7.4, 0, 8.0), (6.6, 0, 33.0), 5.6)
    d = smin(d, leg, 1.6)

    # ---- torso: compact, slightly barrel — a builder, not a mannequin ----
    pelvis = ellipsoid(P, (0, 0, 39.0), (12.5, 10.0, 8.5))
    belly = ellipsoid(P, (0, 1.5, 50.0), (13.8, 11.5, 11.0))
    chest = ellipsoid(P, (0, -0.5, 62.0), (15.5, 11.0, 10.5))
    d = smin(d, pelvis, 2.4)
    d = smin(d, belly, 3.0)
    d = smin(d, chest, 3.0)

    # ---- arms: down and close to the body so they print support-free -----
    shoulder = sphere(mirror, (14.0, -0.5, 65.0), 5.8)
    upper = capsule(mirror, (14.8, 0, 63.0), (16.2, 1.5, 50.0), 4.0)
    fore = capsule(mirror, (16.2, 1.5, 50.0), (14.5, 5.5, 39.5), 3.5)
    # BIG HANDS. He builds things with them; the figure should say so.
    hand = ellipsoid(mirror, (14.2, 6.5, 35.5), (5.0 * E, 5.8 * E, 6.0 * E))
    d = smin(d, shoulder, 2.0)
    d = smin(d, upper, 1.4)
    d = smin(d, fore, 1.4)
    d = smin(d, hand, 1.6)

    # ---- neck: short and thick. A scale bobblehead neck snaps in PLA -----
    neck = capsule(P, (0, 0.5, 69.0), (0, 0.5, 78.0), 7.0)
    d = smin(d, neck, 2.6)

    # ---- clothes ---------------------------------------------------------
    # A figure of a person wearing nothing reads as unfinished rather than as a
    # portrait. The trick: take the shapes already built, grow them ~1.3 mm, and keep
    # only a horizontal band. The grown shell union'd back on leaves a visible hem and
    # collar edge — that is a T-shirt, in four lines and no new geometry.
    def slab(lo, hi):
        return np.maximum(lo - z, z - hi)

    torso_only = smin(smin(pelvis, belly, 3.0), chest, 3.0)
    sleeve = smin(smin(shoulder, upper, 1.4), torso_only, 3.0)
    shirt = smax(sleeve - 1.35, slab(36.5, 68.5), 0.5)
    d = smin(d, shirt, 0.5)

    legs_only = smin(leg, pelvis, 2.4)
    shorts = smax(legs_only - 1.35, slab(24.0, 43.0), 0.5)
    d = smin(d, shorts, 0.5)

    # ================= THE HEAD — where the comedy lives ==================
    HZ = 100.0                      # head centre height
    HR = 25.0 * E                   # head radius

    # The dome: taller than wide and a touch longer front-to-back, which is the
    # actual shape in his scan, just dialled up.
    dome = ellipsoid(P, (0, 0, HZ), (HR * 0.96, HR * 1.02, HR * 1.06))
    jaw = ellipsoid(P, (0, 5.0, HZ - 15.0), (HR * 0.80, HR * 0.82, HR * 0.60))
    head = smin(dome, jaw, 9.0)

    # brow ridge — heavy and shelf-like, the anchor of every expression he makes
    brow = ellipsoid(mirror, (9.0, HR * 0.80, HZ + 4.0),
                     (10.0, 5.0, 4.0 * E))
    head = smin(head, brow, 3.0)

    # EYEBROWS: the single most exaggerated feature. Thick, arched, unmistakable.
    eyebrow = ellipsoid(mirror, (9.5, HR * 0.83, HZ + 6.5 * E),
                        (9.0, 3.2, 2.4 * E))
    head = smin(head, eyebrow, 1.2)

    # eye sockets carved under the brow — the deep-set look, kept friendly
    socket = ellipsoid(mirror, (8.6, HR * 0.90, HZ + 0.5), (5.4, 4.6, 4.4))
    head = ssub(head, socket, 1.6)
    # eyeballs put back, smaller than the socket so a rim of shadow survives
    eye = sphere(mirror, (8.6, HR * 0.80, HZ + 0.6), 3.8)
    head = smin(head, eye, 0.5)

    # NOSE: strong, generous, rounded at the tip. Enlarged, never beaked.
    nose = capsule(P, (0, HR * 0.86, HZ - 1.0), (0, HR * 1.06 + 3.0 * E, HZ - 9.0),
                   4.0 * E**0.8)
    head = smin(head, nose, 2.4)

    # GRIN. He is mid-laugh in almost every frame of that video, so the figure is too.
    #
    # First attempt carved with the TOP cap of a sphere, whose edges curve DOWNWARD —
    # it produced a frown, which is the one thing this figure must not have. The curve
    # has to open upward at the corners.
    #
    # So: take the arc of a circle in the (x,z) plane centred ABOVE the mouth, keep
    # only its LOWER portion (that arc rises at both ends — a smile), extrude it back
    # through the face, and carve that out.
    cz = HZ - 3.0
    ring = np.abs(np.sqrt(x * x + (z - cz) ** 2) - 13.0 * E**0.4) - 1.7   # the arc
    lower = z - (cz - 6.0)                     # keep only below the nose
    front = 4.0 - y                            # and only through the front of the face
    grin = smax(smax(ring, lower, 0.7), front, 0.7)
    head = ssub(head, grin, 0.9)

    # ears — a little oversized, sitting proud of the skull, level with the eyes
    ear = ellipsoid(mirror, (HR * 0.90, 1.0, HZ - 7.0),
                    (3.0, 5.0 * E**0.5, 7.5 * E**0.5))
    head = smin(head, ear, 1.4)

    d = smin(d, head, 5.0)

    # ---- the oud, held across the chest ----------------------------------
    if oud:
        bowl = ellipsoid(P, (-3.0, 14.0, 47.0), (11.0, 6.5, 13.0))
        neck_o = capsule(P, (2.0, 13.0, 56.0), (16.0, 11.0, 74.0), 2.2)
        head_o = capsule(P, (16.0, 11.0, 74.0), (19.0, 10.5, 78.0), 2.8)
        instrument = smin(smin(bowl, neck_o, 1.5), head_o, 1.5)
        d = smin(d, instrument, 2.0)

    return d


# ---------------------------------------------------------------- meshing
def polygonise(fn, lo, hi, voxel):
    from skimage import measure
    nx, ny, nz = [max(8, int(np.ceil((hi[i] - lo[i]) / voxel)) + 6) for i in range(3)]
    gx = lo[0] - 3 * voxel + np.arange(nx, dtype=np.float32) * voxel
    gy = lo[1] - 3 * voxel + np.arange(ny, dtype=np.float32) * voxel
    gz = lo[2] - 3 * voxel + np.arange(nz, dtype=np.float32) * voxel
    print("  grid %d x %d x %d = %.1f M samples" % (nx, ny, nz, nx * ny * nz / 1e6))

    vol = np.empty((nx, ny, nz), dtype=np.float32)
    X, Y = np.meshgrid(gx, gy, indexing="ij")
    for k, zz in enumerate(gz):                      # slice by slice: bounded memory
        P = np.stack([X, Y, np.full_like(X, zz)], axis=-1)
        vol[:, :, k] = fn(P)

    # Force the border positive so the isosurface always closes into a solid.
    vol[0, :, :] = vol[-1, :, :] = 1e3
    vol[:, 0, :] = vol[:, -1, :] = 1e3
    vol[:, :, 0] = vol[:, :, -1] = 1e3

    verts, faces, _n, _v = measure.marching_cubes(vol, level=0.0)
    verts = verts * voxel + np.array([gx[0], gy[0], gz[0]], dtype=np.float32)
    return verts.astype(np.float32), faces.astype(np.int64)


def check(verts, faces):
    """Watertight means every edge is shared by exactly two triangles. Count them."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.sort(e, axis=1)
    _u, counts = np.unique(e, axis=0, return_counts=True)
    bad = int((counts != 2).sum())
    # signed volume via the divergence theorem
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    vol = float(np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)
    return bad, vol


def write_stl(path, verts, faces):
    tri = verts[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(ln, 1e-12)
    with open(path, "wb") as f:
        f.write(b"ALMA-FIGURE  iddo caricature  " + b" " * 50)
        f.write(struct.pack("<I", len(faces)))
        buf = bytearray()
        for i in range(len(faces)):
            buf += struct.pack("<12fH", *n[i], *tri[i, 0], *tri[i, 1], *tri[i, 2], 0)
        f.write(bytes(buf))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--height", type=float, default=120.0, help="target height in mm")
    ap.add_argument("--exaggeration", type=float, default=1.0)
    ap.add_argument("--voxel", type=float, default=0.5)
    ap.add_argument("--no-oud", action="store_true")
    ap.add_argument("--out", default="iddo-figure.stl")
    a = ap.parse_args()

    E = a.exaggeration
    print("ALMA FIGURE — Iddo caricature")
    print("=" * 64)
    print("  exaggeration %.2f   voxel %.2f mm" % (E, a.voxel))

    fn = lambda P: build(P, E=E, oud=not a.no_oud)
    lo = (-40.0 * max(E, 1.0), -40.0, -2.0)
    hi = (40.0 * max(E, 1.0), 45.0, 132.0 * max(E, 1.0))

    t0 = time.time()
    verts, faces = polygonise(fn, lo, hi, a.voxel)
    print("  %d vertices, %d triangles (%.0f s)" % (len(verts), len(faces), time.time() - t0))

    # scale to the requested height
    zmin, zmax = float(verts[:, 2].min()), float(verts[:, 2].max())
    s = a.height / (zmax - zmin)
    verts = (verts - np.array([0, 0, zmin], dtype=np.float32)) * s
    verts[:, 0] -= (verts[:, 0].min() + verts[:, 0].max()) / 2.0
    verts[:, 1] -= (verts[:, 1].min() + verts[:, 1].max()) / 2.0

    bad, vol = check(verts, faces)
    bb = verts.max(axis=0) - verts.min(axis=0)
    print("-" * 64)
    print("  bounding box : %.1f x %.1f x %.1f mm" % tuple(bb))
    print("  volume       : %.1f cm3  (~%.0f g in PLA at 1.24 g/cm3, 100%% infill)"
          % (vol / 1000.0, vol / 1000.0 * 1.24))
    print("  non-manifold edges : %d   %s" % (bad, "WATERTIGHT" if bad == 0 else "*** LEAKS ***"))

    write_stl(a.out, verts, faces)
    print("  wrote %s" % a.out)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
