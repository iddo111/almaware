# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

FINAL 2 - the vortex fix, the grade, and the antialiasing choice, all measured.

Found by OPENING THE PICTURE: with the hard compositor on, the pegboard grew a
spiral of brushstrokes centred on the middle of the frame. That is
`canvas._tangent_dir`'s fallback -- `cross(normal, view)` -- and it has been there
the whole time; the soft path was averaging it into invisibility.
`workshop.world_tangent` gives every stroke a direction that belongs to the WALL.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import workshop as W                                       # noqa: E402
from sharpness import lapvar_array, lapvar_norm_array      # noqa: E402

OUT = os.path.join(HERE, "final2")
os.makedirs(OUT, exist_ok=True)
WD, HT, T = 1600, 900, 0.30
rows = []


def shot(name, pt, nr, rgb, state, **kw):
    img, secs, cov = W.paint(pt, nr, rgb, kw.pop("radius", 0.021), WD, HT, state,
                             t=T, **kw)
    from PIL import Image
    p = os.path.join(OUT, f"{name}.jpg")
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
        p, quality=94, subsampling=0)
    r = {"name": name, "state": state, "file": p, "strokes": int(len(pt)),
         "lapvar": round(lapvar_array(img), 1),
         "lapvar_norm": round(lapvar_norm_array(img), 1),
         "coverage": round(cov, 4), "render_s": round(secs, 1)}
    rows.append(r)
    print(f"  {name:<44} lapvar {r['lapvar']:8.1f} (norm {r['lapvar_norm']:8.1f})"
          f"  cov {cov*100:5.1f}%  {secs:5.1f}s", flush=True)
    del img
    return r


def main():
    t0 = time.time()
    a = W.anchors(0.0090, 1_200_000)
    st = a.pop("stage")
    pt, nr, bx = a["point"], a["normal"], a["box"]
    occ = W.occlude_anchors(st, pt, nr)

    print("\n== N. the vortex fix: a stroke lies along the WALL, not the eye ==",
          flush=True)
    for state in ("dark", "lit"):
        rgb = W.colours(st, pt, nr, bx, state, occ)
        shot(f"N-{state}-viewTangent", pt, nr, rgb, state, soft=False)
        shot(f"N-{state}-worldTangent", pt, nr, rgb, state, soft=False,
             kwargs_tangent=True)
        shot(f"N-{state}-worldTangent-AA2", pt, nr, rgb, state, soft=False,
             kwargs_tangent=True, supersample=2)

    print("\n== O. the night, graded so it can be seen ==", flush=True)
    for g in (1.6, 2.2, 3.0):
        rgb = W.colours(st, pt, nr, bx, "dark", occ, gain=g)
        shot(f"O-dark-grade{g}", pt, nr, rgb, "dark", soft=False,
             kwargs_tangent=True)
        if g == 2.2:
            shot(f"O-dark-grade{g}-AA2", pt, nr, rgb, "dark", soft=False,
                 kwargs_tangent=True, supersample=2)

    print("\n== P. 4K, to see whether the hard path still holds up big ==",
          flush=True)
    global WD, HT
    WD, HT = 3840, 2160
    rgb = W.colours(st, pt, nr, bx, "lit", occ)
    shot("P-lit-4K-worldTangent", pt, nr, rgb, "lit", soft=False,
         kwargs_tangent=True)
    WD, HT = 1600, 900

    with open(os.path.join(OUT, "final2.json"), "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows,
                   "seconds": round(time.time() - t0, 1)}, f, indent=2)
    print("\nwrote " + os.path.join(OUT, "final2.json"), flush=True)


if __name__ == "__main__":
    main()
