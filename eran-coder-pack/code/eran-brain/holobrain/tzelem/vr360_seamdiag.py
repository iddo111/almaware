# -*- coding: utf-8 -*-
"""Where does the cube seam actually come from? Separate the engine from the painter.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A seam in the finished plate can be born in two completely different places and the
fix is different for each:

  ENGINE   the six beauty renders disagree at the shared edge to begin with. Godot's
           SDFGI, SSAO, volumetric fog and TAA are all VIEW dependent, so the same
           world point lit through two different cameras is not the same colour. No
           amount of painter cleverness removes this; it is in the input.

  PAINTER  the strokes disagree even though the input agreed -- e.g. a stroke's
           screen ellipse is built per-face and the two faces build it differently.

So: measure the seam on the RAW BEAUTY faces first. That number is the FLOOR. Only the
excess above it is the painter's fault, and only that part is worth chasing.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import vr360                                     # noqa: E402


def main(folder: str) -> None:
    faces = vr360.load_faces(folder)
    beauty = [f["g"]["albedo"] for f in faces]
    rows = vr360.seam_report(faces, beauty)
    for r in rows:
        print(f"  {r['edge']:>8}  mean {r['mean_abs_diff_255']:8.4f}   "
              f"max {r['max_abs_diff_255']:8.3f}")
    print(f"RAW BEAUTY seam mean = "
          f"{np.mean([r['mean_abs_diff_255'] for r in rows]):.4f} / 255")

    # A second, independent question: how much of that is just the two faces
    # disagreeing about WHAT IS THERE (a depth/geometry mismatch) rather than about
    # colour? If depth agrees, the geometry tiles and the disagreement is lighting.
    by = {f["name"]: f for f in faces}
    t = np.linspace(-1.0, 1.0, 2048)
    dd = []
    for a, b in vr360.EDGES:
        na, nb = vr360.AXIS[a], vr360.AXIS[b]
        third = np.cross(na, nb)
        d = na[None, :] + nb[None, :] + t[:, None] * third[None, :]
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        out = []
        for nm in (a, b):
            f = by[nm]
            cam = f["cam"]
            px, py, _ = cam.project(cam.eye + d)
            dep = f["g"]["depth"].copy()
            dep[~np.isfinite(dep)] = 0.0
            v = vr360._bilinear(np.repeat(dep[..., None], 3, axis=2)
                                .astype(np.float32), px, py)[:, 0]
            out.append(v)
        ok = (out[0] > 0) & (out[1] > 0)
        if ok.any():
            dd.append(float(np.abs(out[0][ok] - out[1][ok]).mean()))
    print(f"DEPTH at the same edge directions, mean |A-B| = {np.mean(dd):.4f} m "
          f"(over {len(dd)} edges)")


if __name__ == "__main__":
    main(sys.argv[1])
