# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE RE-RENDER: the exact two published stills, before and after, same camera,
same size, so the numbers sit next to the ones Iddo already judged (126 for LIT,
10.2 for DARK).

The AFTER is not one clever trick. It is, in order of what the sweep says each is
worth on the ruler:

    1. the HARD compositor (`soft=False`)   x3.8   the blur was alpha averaging
    2. exposure                             x5.7   on DARK only, and it is a GRADE
    3. more strokes, now that they help     x1.2   340k -> 1.2M
    4. world-space texture                  x1.03  small on the ruler, large to the eye
    5. contact shadow + ambient occlusion   x1.00  nothing on the ruler. Kept anyway,
                                                   because the picture is visibly better
                                                   and the ruler is not the judge.

Every variant below is saved and measured; nothing is picked before it is seen.
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

OUT = os.path.join(HERE, "final")
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
    print(f"  {name:<40} lapvar {r['lapvar']:8.1f} (norm {r['lapvar_norm']:8.1f})"
          f"  cov {cov*100:5.1f}%  {secs:5.1f}s", flush=True)
    del img
    return r


def main():
    t0 = time.time()
    print("== BEFORE: the published still, exactly as paint.py makes it ==",
          flush=True)
    a0 = W.anchors(0.0165, 340_000)
    st0 = a0.pop("stage")
    for state in ("dark", "lit"):
        rgb = W.colours(st0, a0["point"], a0["normal"], a0["box"], state, None)
        shot(f"BEFORE-{state}", a0["point"], a0["normal"], rgb, state)
    del a0, st0

    print("\n== AFTER: hard compositor, 1.2M strokes, shadow+AO+texture ==",
          flush=True)
    a = W.anchors(0.0090, 1_200_000)
    st = a.pop("stage")
    pt, nr, bx = a["point"], a["normal"], a["box"]
    occ = W.occlude_anchors(st, pt, nr)
    for state in ("dark", "lit"):
        rgb = W.colours(st, pt, nr, bx, state, occ)
        shot(f"AFTER-{state}", pt, nr, rgb, state, soft=False)
        shot(f"AFTER-{state}-AA2", pt, nr, rgb, state, soft=False, supersample=2)
        shot(f"AFTER-{state}-soft", pt, nr, rgb, state, soft=True, edge=8.0)

    print("\n== the GRADE: the night scene given an exposure it can be seen in ==",
          flush=True)
    for g in (1.6, 2.2, 3.0):
        rgb = W.colours(st, pt, nr, bx, "dark", occ, gain=g)
        shot(f"AFTER-dark-grade{g}", pt, nr, rgb, "dark", soft=False)
        shot(f"AFTER-dark-grade{g}-AA2", pt, nr, rgb, "dark", soft=False,
             supersample=2)

    with open(os.path.join(OUT, "final.json"), "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "camera": f"room.rail_camera(t={T}) at {WD}x{HT}",
                   "published_reference": {"lit": 125.7, "dark": 10.2},
                   "rows": rows, "seconds": round(time.time() - t0, 1)},
                  f, indent=2)
    print("\nwrote " + os.path.join(OUT, "final.json"), flush=True)


if __name__ == "__main__":
    main()
