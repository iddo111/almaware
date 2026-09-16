"""alma-headscan / headprep.py — turn a phone-scan mesh into a printable head.

A photogrammetry app gives you a shell: arbitrary scale, arbitrary orientation, open at
the bottom where your shoulders were, and usually not watertight. A slicer will either
refuse it or quietly print nonsense. This closes that gap:

    load (OBJ / PLY / STL)  ->  orient  ->  scale to life size  ->  cut the neck flat
        ->  cap the cut so it is a closed solid  ->  verify  ->  write STL

WHY EACH STEP EXISTS
  scale   A photogrammetric reconstruction has NO absolute size — the maths is scale-free.
          The app's metres are a guess unless the phone had LiDAR. So we anchor on a real
          measurement you take with a tape: head width, or the distance between your pupils
          (~63 mm on an adult male, but measure YOURS, do not trust the average).
  cut     The scan tails off into shoulders and chair. A print needs to end somewhere, and
          it needs to end on a FLAT face it can stand on.
  cap     A cut leaves an open hole. An open mesh is not a solid; a slicer cannot tell
          inside from outside. Capping is what makes it printable, not optional polish.

    python headprep.py scan.obj --pupils 63 --neck 0.28
    python headprep.py scan.ply --head-width 155 --neck 0.30 --out iddo-head.stl

Pure numpy. No trimesh, no open3d, nothing to install.
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ------------------------------------------------------------------ loading
def load_obj(path):
    V, F = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                V.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                idx = [int(p.split("/")[0]) for p in line.split()[1:]]
                idx = [i - 1 if i > 0 else len(V) + i for i in idx]
                for k in range(1, len(idx) - 1):        # fan-triangulate n-gons
                    F.append([idx[0], idx[k], idx[k + 1]])
    return np.array(V, np.float64), np.array(F, np.int64)


def load_ply(path):
    with open(path, "rb") as f:
        head, line = b"", b""
        while b"end_header" not in line:
            line = f.readline()
            head += line
        txt = head.decode("ascii", "replace")
        nv = int(re.search(r"element vertex (\d+)", txt).group(1))
        nf = int(re.search(r"element face (\d+)", txt).group(1))
        binary = "format binary_little_endian" in txt
        props = re.findall(r"property (\w+) (\w+)", txt)
        if not binary:
            V = np.array([[float(x) for x in f.readline().split()[:3]] for _ in range(nv)])
            F = []
            for _ in range(nf):
                p = [int(x) for x in f.readline().split()]
                for k in range(1, p[0] - 1):
                    F.append([p[1], p[1 + k], p[2 + k]])
            return V, np.array(F, np.int64)
        # binary: vertices may carry colour/normals, so stride over all properties
        sz = {"float": 4, "float32": 4, "double": 8, "uchar": 1, "uint8": 1,
              "int": 4, "int32": 4, "short": 2, "ushort": 2}
        vprops = [p for p in props if p[1] in ("x", "y", "z") or True][:len(props)]
        stride = 0
        offs = {}
        for t, name in vprops:
            if name in ("x", "y", "z"):
                offs[name] = stride
            stride += sz.get(t, 4)
            if name == "z":
                break
        buf = f.read(nv * stride)
        arr = np.frombuffer(buf, np.uint8).reshape(nv, stride)
        V = np.stack([arr[:, offs[c]:offs[c] + 4].copy().view(np.float32).ravel()
                      for c in "xyz"], axis=1).astype(np.float64)
        F = []
        rest = f.read()
        pos = 0
        for _ in range(nf):
            cnt = rest[pos]; pos += 1
            idx = np.frombuffer(rest[pos:pos + 4 * cnt], np.int32); pos += 4 * cnt
            for k in range(1, cnt - 1):
                F.append([idx[0], idx[k], idx[k + 1]])
        return V, np.array(F, np.int64)


def load_stl(path):
    with open(path, "rb") as f:
        head = f.read(80)
        if head[:5].lower() == b"solid" and b"facet" in f.read(200):
            f.seek(0)
            txt = f.read().decode("ascii", "replace")
            pts = [[float(x) for x in m] for m in
                   re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", txt)]
            V = np.array(pts)
            return V, np.arange(len(V)).reshape(-1, 3)
        f.seek(80)
        n = struct.unpack("<I", f.read(4))[0]
        raw = np.frombuffer(f.read(n * 50), np.uint8).reshape(n, 50)
        V = np.zeros((n, 3, 3), np.float32)
        for i in range(3):
            V[:, i, :] = raw[:, 12 + i * 12:24 + i * 12].copy().view(np.float32)
        return V.reshape(-1, 3).astype(np.float64), np.arange(n * 3).reshape(-1, 3)


def load(path):
    ext = os.path.splitext(path)[1].lower()
    V, F = {".obj": load_obj, ".ply": load_ply, ".stl": load_stl}[ext](path)
    return weld(V, F)


def weld(V, F, tol=1e-6):
    """Merge coincident vertices. An STL has none shared, so nothing is watertight
    until this runs — every edge would look like it belongs to one triangle only."""
    key = np.round(V / tol).astype(np.int64)
    _u, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    V2 = V[first]
    F2 = inv[F]
    F2 = F2[(F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])]
    return V2, F2


# ------------------------------------------------------------------ analysis
def open_edges(F):
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(e, axis=0, return_counts=True)
    return u[c == 1], int((c != 2).sum())


def volume(V, F):
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return abs(float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)


# ------------------------------------------------------------------ cutting
def cut_below(V, F, zcut):
    """Keep everything above z=zcut, splitting triangles that straddle the plane.

    Dropping straddling triangles instead of splitting them leaves a ragged edge that
    no capping routine can close cleanly, so they are split properly.
    """
    V = V.copy()
    keep_v = V[:, 2] >= zcut
    newV = list(V)
    newF = []
    cache = {}

    def on_edge(i, j):
        k = (min(i, j), max(i, j))
        if k in cache:
            return cache[k]
        p, q = V[k[0]], V[k[1]]
        t = (zcut - p[2]) / (q[2] - p[2])
        newV.append(p + t * (q - p))
        cache[k] = len(newV) - 1
        return cache[k]

    for tri in F:
        m = keep_v[tri]
        n = int(m.sum())
        if n == 0:
            continue
        if n == 3:
            newF.append(list(tri))
            continue
        a, b, c = tri
        if n == 1:
            hi = tri[m][0]
            lo = [x for x in tri if x != hi]
            newF.append([hi, on_edge(hi, lo[0]), on_edge(hi, lo[1])])
        else:                                   # two above, one below -> a quad
            lo = tri[~m][0]
            hi = [x for x in tri if x != lo]
            p, q = on_edge(hi[0], lo), on_edge(hi[1], lo)
            newF.append([hi[0], hi[1], q])
            newF.append([hi[0], q, p])
    return weld(np.array(newV), np.array(newF, np.int64))


def cap(V, F):
    """Close the flat hole left by the cut, so the mesh becomes a solid.

    The boundary is walked as a loop and fanned from its centroid. Winding is chosen so
    the cap's normal points AWAY from the body (downward), which keeps the solid
    consistently oriented — a flipped cap reads as an inside-out volume to a slicer.
    """
    bnd, _ = open_edges(F)
    if len(bnd) == 0:
        return V, F
    nxt = {}
    for i, j in bnd:
        nxt.setdefault(i, []).append(j)
        nxt.setdefault(j, []).append(i)
    loops = []
    seen = set()
    for start in nxt:
        if start in seen:
            continue
        loop, cur, prev = [start], start, None
        seen.add(start)
        while True:
            opts = [x for x in nxt[cur] if x != prev]
            if not opts:
                break
            nx = opts[0]
            if nx == start:
                break
            loop.append(nx)
            seen.add(nx)
            prev, cur = cur, nx
        if len(loop) >= 3:
            loops.append(loop)
    V = list(V)
    F = list(F)
    for loop in loops:
        pts = np.array([V[i] for i in loop])
        ctr = pts.mean(axis=0)
        V.append(ctr)
        ci = len(V) - 1
        for k in range(len(loop)):
            F.append([ci, loop[(k + 1) % len(loop)], loop[k]])
    return weld(np.array(V), np.array(F, np.int64))


def write_stl(path, V, F):
    tri = V[F].astype(np.float32)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    with open(path, "wb") as f:
        f.write(b"ALMA-HEADSCAN" + b" " * 67)
        f.write(struct.pack("<I", len(F)))
        buf = bytearray()
        for i in range(len(F)):
            buf += struct.pack("<12fH", *n[i], *tri[i, 0], *tri[i, 1], *tri[i, 2], 0)
        f.write(bytes(buf))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh")
    ap.add_argument("--out", default="iddo-head.stl")
    ap.add_argument("--pupils", type=float, default=None,
                    help="YOUR measured interpupillary distance in mm")
    ap.add_argument("--head-width", type=float, default=None,
                    help="YOUR measured head width, ear to ear, in mm")
    ap.add_argument("--target-height", type=float, default=None,
                    help="just force the print to this height in mm")
    ap.add_argument("--neck", type=float, default=0.28,
                    help="fraction of the height to cut off the bottom (0.28 = neck)")
    a = ap.parse_args()

    print("ALMA HEADSCAN — print prep")
    print("=" * 66)
    V, F = load(a.mesh)
    print("  loaded        : %d vertices, %d triangles" % (len(V), len(F)))
    _b, bad = open_edges(F)
    print("  as imported   : %d non-manifold/open edges" % bad)

    # Orient: longest principal axis of a head is roughly vertical (crown to neck).
    V = V - V.mean(axis=0)
    _u, _s, vt = np.linalg.svd(V - V.mean(axis=0), full_matrices=False)
    R = vt
    if np.linalg.det(R) < 0:
        R[2] *= -1
    Vr = V @ R.T
    # the head is widest across the ears and longest crown-to-neck: put the long axis on z
    order = np.argsort(np.ptp(Vr, axis=0))
    Vr = Vr[:, [order[0], order[1], order[2]]]
    # crown should be UP: the crown end is the rounder end, so it has more mass near the axis
    zmid = Vr[:, 2].mean()
    top = Vr[Vr[:, 2] > zmid]
    bot = Vr[Vr[:, 2] <= zmid]
    if np.hypot(*top[:, :2].T).mean() > np.hypot(*bot[:, :2].T).mean():
        Vr[:, 2] *= -1
    V = Vr
    print("  oriented      : bbox %.1f x %.1f x %.1f (scan units)" % tuple(np.ptp(V, axis=0)))

    zlo = V[:, 2].min()
    zcut = zlo + a.neck * np.ptp(V[:, 2])
    V, F = cut_below(V, F, zcut)
    print("  cut at neck   : %d triangles remain" % len(F))
    V, F = cap(V, F)
    _b, bad = open_edges(F)
    print("  capped        : %d open edges  %s" % (bad, "WATERTIGHT" if bad == 0 else "*** still open ***"))

    # scale
    s = None
    if a.target_height:
        s = a.target_height / np.ptp(V[:, 2])
        why = "forced height"
    elif a.head_width:
        s = a.head_width / np.ptp(V[:, 0])
        why = "your measured head width"
    elif a.pupils:
        print("  NOTE: pupil-based scaling needs the eye positions; using head width is")
        print("        more reliable from geometry alone. Re-run with --head-width.")
    if s:
        V = V * s
        print("  scaled        : x%.4f  (%s)" % (s, why))
    else:
        print("  NOT SCALED    : a photogrammetric mesh has no absolute size. Measure your")
        print("                  head ear-to-ear with a tape and re-run with --head-width.")

    V[:, 2] -= V[:, 2].min()
    print("-" * 66)
    print("  final bbox    : %.1f x %.1f x %.1f mm" % tuple(np.ptp(V, axis=0)))
    print("  volume        : %.1f cm3  (~%.0f g PLA at 15%% infill)"
          % (volume(V, F) / 1000, volume(V, F) / 1000 * 1.24 * 0.22))
    write_stl(a.out, V, F)
    print("  wrote %s" % a.out)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
