# -*- coding: utf-8 -*-
"""IS THERE A LINE AT THE JOIN? An objective test, immune to the world rebuilding.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WHY THIS EXISTS. The obvious seam metric -- last column of face A against first column
of face B -- is badly contaminated here by two things:

  1. boulevard_cafe.gd does not rebuild the same world twice (its own documented
     defect: runs give 810,468 / 982,944 / 985,542 triangles). So two runs cannot be
     compared, and a change that helps can read as a change that hurts.
  2. At a cube edge the projection is at its most stretched, so one face's edge pixel
     and its neighbour's cover different solid angles. On tree canopy -- high-frequency
     leaf edges -- that alone produces a large mean |A-B| that is pure resampling, not
     a seam. It is invisible to the eye and it dominates the number.

What the EYE actually sees is a LINE: a discontinuity that runs the whole height of the
plate at one column, in the smooth regions where nothing else is happening. So measure
exactly that, in the finished equirect, with no reference to the faces at all:

    for every column x, e(x) = mean |I(:, x) - I(:, x+1)|  restricted to SMOOTH rows
    is e(x_join) an outlier against its own neighbourhood?

A join column that is not an outlier is a join you cannot see. This needs one image and
no second run, so the world rebuilding cannot touch it.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

V_JOINS = {0.125: "nx|pz", 0.375: "nx|nz", 0.625: "px|nz", 0.875: "px|pz"}
H_JOINS = {0.25: "side|py", 0.75: "side|ny"}


def _profile(a: np.ndarray, axis: int, smooth_win: int = 9) -> np.ndarray:
    """Mean |first difference| along `axis`, restricted to locally SMOOTH pixels.

    Smooth = the pixel's neighbourhood on the OTHER axis is quiet, so canopy and
    foliage (which are noisy everywhere and would drown the signal) drop out and
    pavement, facades and sky -- where a line would be glaring -- remain.
    """
    g = a.astype(np.float32).mean(axis=2)
    if axis == 1:
        d = np.abs(np.diff(g, axis=1))
        # local roughness measured ALONG the join direction (down the column)
        rough = np.abs(np.diff(g, axis=0))
        rough = np.pad(rough, ((0, 1), (0, 0)), mode="edge")[:, :-1]
    else:
        d = np.abs(np.diff(g, axis=0))
        rough = np.abs(np.diff(g, axis=1))
        rough = np.pad(rough, ((0, 0), (0, 1)), mode="edge")[:-1, :]
    thr = np.percentile(rough, 40)
    m = rough <= thr
    num = (d * m).sum(axis=1 - axis)
    den = m.sum(axis=1 - axis).astype(np.float32)
    return num / np.maximum(den, 1.0)


def report(path: str) -> dict:
    a = np.asarray(Image.open(path))
    H, W = a.shape[:2]
    out = {"file": os.path.basename(path), "px": f"{W}x{H}", "joins": []}

    for axis, joins, n in ((1, V_JOINS, W), (0, H_JOINS, H)):
        p = _profile(a, axis)
        for frac, name in joins.items():
            i = int(round(frac * n))
            i = min(max(i, 2), len(p) - 3)
            # the join column itself vs a band either side of it, excluding the join
            lo, hi = max(0, i - 60), min(len(p), i + 61)
            nb = np.concatenate([p[lo:i - 1], p[i + 2:hi]])
            here = float(p[max(0, i - 1):i + 2].max())
            med = float(np.median(nb))
            sd = float(nb.std()) + 1e-6
            out["joins"].append({
                "join": name, "at": i,
                "step_at_join_255": round(here, 3),
                "local_median_255": round(med, 3),
                "z_score": round((here - med) / sd, 2),
                "excess_255": round(here - med, 3),
            })
    z = [j["z_score"] for j in out["joins"]]
    out["worst_z"] = round(max(z), 2)
    out["worst_join"] = out["joins"][int(np.argmax(z))]["join"]
    # A z of 3 is the usual "that is not noise" line; on a smooth field a line the eye
    # picks up sits far above it. Reported, not asserted.
    out["verdict"] = ("NO VISIBLE LINE" if max(z) < 3.0
                      else "SUSPECT" if max(z) < 6.0 else "VISIBLE LINE")
    return out


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]:
        r = report(p)
        print(f"\n{r['file']}  ({r['px']})   -> {r['verdict']}  "
              f"worst z={r['worst_z']} at {r['worst_join']}")
        for j in r["joins"]:
            print(f"   {j['join']:>9} @{j['at']:>5}  step {j['step_at_join_255']:6.3f}  "
                  f"local median {j['local_median_255']:6.3f}  "
                  f"excess {j['excess_255']:+6.3f}  z {j['z_score']:+6.2f}")
