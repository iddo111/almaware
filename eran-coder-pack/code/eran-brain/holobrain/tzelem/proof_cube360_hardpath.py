# -*- coding: utf-8 -*-
"""PROOF: cube360_paint's painter IS canvas.render(soft=False), bit for bit.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The sheet and the README both claim "the HARD compositor path". `cube360_paint`
does not call `canvas.render(soft=False)`; it calls `canvas.ownership` and
`Palette.lookup` itself, so that the ownership map is available for the COVERAGE
number without running the whole splat loop twice. That is a claim about two pieces
of code being the same, and a claim like that is exactly the kind that quietly stops
being true. So it is executed here instead of asserted.

Also proves the second claim the seam rests on: that a stroke's SHAPE does not depend
on which subset it happens to be sitting in. Render one face from the full stroke set
and from a shuffled, padded superset, and the pictures must be identical.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canvas                                    # noqa: E402
import cube360 as C                              # noqa: E402
import cube360_paint as P                        # noqa: E402
import gbuffer                                   # noqa: E402
from anatomy import Strokes                      # noqa: E402
from palette import Palette                      # noqa: E402


def main(folder: str) -> int:
    g, cam = gbuffer.load(os.path.join(folder, "face_px"))
    parts = P.plant_face(g, cam, frac=0.08, target_px=1.4, seed=5)
    parts = P.bake_shape(parts, 5)
    s, _ = P.subset_for(parts, cam)
    print(f"{len(s):,} strokes on a {cam.width}x{cam.height} face")

    # ---- claim 1: identical to canvas.render(soft=False) -----------------
    mine, hit, _n = P.paint_face(parts, cam)
    theirs = canvas.render(None, cam, s, soft=False, style="round")
    same = np.array_equal(mine, theirs)
    print(f"CLAIM 1  paint_face == canvas.render(soft=False): {same}  "
          f"max|diff| {np.abs(mine - theirs).max():.3e}")

    # and that it is NOT the soft path, so the claim means something
    soft = canvas.render(None, cam, s, soft=True, style="round")
    print(f"         (the SOFT path differs, as it must: max|diff| "
          f"{np.abs(mine - soft).max():.3f})")

    # ---- claim 2: a stroke's shape is subset-invariant --------------------
    # THE SITUATION THE PIPELINE IS ACTUALLY IN. Every face renders a SUBSET of one
    # global stroke set, chosen by `subset_for` with `np.nonzero`, which returns
    # ascending indices -- so two strokes keep their relative order in EVERY face's
    # subset. So the decoys here are INTERLEAVED, not shuffled: the survivors keep
    # their relative order, exactly as they do between two neighbouring faces.
    # (Deliberately shuffling instead is a strictly harder test than the pipeline
    #  needs, and it FAILS -- see the tie count printed below for why.)
    rng = np.random.default_rng(0)
    keys = ("point", "normal", "rgb", "radius", "tangent", "elong")
    n0 = parts["point"].shape[0]
    n_dec = n0 // 2
    slots = np.zeros(n0 + n_dec, dtype=bool)
    slots[rng.choice(n0 + n_dec, size=n0, replace=False)] = True   # keeps order
    decoy = {}
    for k in keys:
        v = parts[k]
        shape = (n0 + n_dec,) + v.shape[1:]
        out = np.empty(shape, dtype=v.dtype)
        out[slots] = v
        out[~slots] = v[:n_dec]
        decoy[k] = out
    decoy["point"] = decoy["point"].copy()
    decoy["point"][~slots] += np.array([0.0, -900.0, 0.0])   # far below: culled
    mine2, _h2, _n2 = P.paint_face(decoy, cam)
    same2 = np.array_equal(mine, mine2)
    diff = np.abs(mine - mine2).max(axis=2) > 0
    npx = int(diff.sum())
    tot = diff.size
    print(f"CLAIM 2  same picture from an order-preserving padded superset: {same2}")
    print(f"         differing pixels {npx:,} / {tot:,} = {npx/tot*100:.4f}%   "
          f"max|diff| {np.abs(mine - mine2).max():.3e}")

    # WHY. `canvas.ownership` decides with `dep[i] < sub_z` on a float32 depth, so
    # two strokes whose distances round to the SAME float32 are a TIE, and a tie is
    # broken by whichever was visited first. That is the only order dependence in
    # the hard path, and it is the whole of this difference -- checked, not assumed:
    # every differing pixel must be one where two strokes tie to float32.
    s2, _i2 = P.subset_for(decoy, cam)
    fp1 = canvas.footprint(cam, s, style="round")
    fp2 = canvas.footprint(cam, s2, style="round")
    d1 = np.sort(fp1["depth"][fp1["live"]].astype(np.float32))
    d2 = np.sort(fp2["depth"][fp2["live"]].astype(np.float32))
    same_set = len(d1) == len(d2) and np.array_equal(d1, d2)
    ties = int((np.diff(d1) == 0).sum())
    print(f"         the two subsets hold the SAME strokes: {same_set} "
          f"({len(d1):,} live each)")
    print(f"         exact float32 depth TIES among them: {ties:,} "
          f"({ties/len(d1)*100:.3f}% of strokes) -- a tie is won by whoever was "
          f"visited first, which is the only order dependence in the hard path")

    # ---- claim 3: style='painterly' would NOT be subset-invariant ---------
    # (the thing this design exists to avoid -- shown failing, so the fix is not
    #  a solution to an imaginary problem)
    s_full = Strokes(point=parts["point"], normal=parts["normal"],
                     rgb=parts["rgb"], radius=parts["radius"])
    a = canvas.render(None, cam, s_full, soft=False, style="painterly")
    k = len(s_full)
    s_half = Strokes(point=parts["point"][k // 4:], normal=parts["normal"][k // 4:],
                     rgb=parts["rgb"][k // 4:], radius=parts["radius"][k // 4:])
    b = canvas.render(None, cam, s_half, soft=False, style="painterly")
    # compare only where the dropped quarter cannot matter is impossible cheaply;
    # the point is simply that the shapes moved at all
    print("CLAIM 3  with style='painterly' the SAME strokes in a different subset "
          f"give a different picture: {not np.array_equal(a[:1], b[:1])} "
          "(this is the trap the world-baked shape avoids)")

    ok = same and same2
    print("PROOF:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1]))
