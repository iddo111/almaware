"""EINAYIM / עֵינַיִם — CUT THE OBJECT OUT OF THE SCENE. (PC, numpy)

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A fused scene is mostly FLOOR. Decimating all of it to 2,000 faces gave a shredded
terrace — 42 metres of room across 2,000 triangles is 30 cm per triangle, and the
picture showed exactly that. The face budget belongs to the OBJECT, so the object
is cut out first and only then decimated. Stated plainly because it is a choice:
EINAYIM does not segment anything yet; the crop box is given by hand (or taken from
the ground truth when there is one).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from truthviews import read_stl               # noqa: E402
from fuse import write_stl, decimate_faces, watertight   # noqa: E402


def crop_tris(tris, lo, hi, mode="centroid"):
    c = tris.mean(axis=1) if mode == "centroid" else tris.reshape(-1, 3)
    keep = np.all((c >= lo) & (c <= hi), axis=-1)
    return tris[keep]


def to_indexed(tris, weld=1e-9):
    flat = tris.reshape(-1, 3)
    q = np.round(flat / max(weld, 1e-12)).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    return flat[first], inv.ravel().reshape(-1, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stl"); ap.add_argument("out_stl")
    ap.add_argument("--bbox", required=True, help="x0,y0,z0,x1,y1,z1")
    ap.add_argument("--faces", type=int, default=2000)
    a = ap.parse_args()
    b = np.array([float(x) for x in a.bbox.split(",")])
    tris = read_stl(a.stl)
    kept = crop_tris(tris, b[:3], b[3:])
    if not len(kept):
        raise SystemExit("the crop box contains no triangles")
    span = float(np.linalg.norm(kept.reshape(-1, 3).max(0) - kept.reshape(-1, 3).min(0)))
    V, F = to_indexed(kept, weld=span * 1e-6)
    Vd, Fd = decimate_faces(V, F, a.faces)
    write_stl(a.out_stl, Vd, Fd)
    print(f"{len(tris)} tris -> crop {len(kept)} -> weld {len(F)} -> {len(Fd)} faces, "
          f"{len(Vd)} verts, span {span:.3f}")
    print(" ", watertight(Vd, Fd))


if __name__ == "__main__":
    main()
