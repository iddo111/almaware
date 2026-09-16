# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

4K, AND THE TENSION IT EXPOSES.

Measured tonight: rendering the SAME strokes bigger makes the picture measurably
softer (1280 11.5 -> 4096 3.2), because a stroke's radius is in WORLD units, so 4K
is the same painting seen closer. That is not a bug — it is exactly the property
`tests/test_gate2.py` exists to defend, and TZELEM's whole "resolution-free" claim
rests on it.

But coverage is ALSO a world property: a stroke's pixel radius and the pixel count
both scale with resolution, so the covered FRACTION does not move. Which means the
finer brush that would be a disaster at 1600x900 (holes) is free at 4K — the same
1.2M strokes at a smaller world radius cover 4K exactly as well.

So the honest statement is not "4K is blurrier". It is: **4K needs a finer brush,
and a finer brush is a different painting, not a bigger rendering of the same one.**
This file measures both so the choice is made with numbers.
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

OUT = os.path.join(HERE, "fourk")
os.makedirs(OUT, exist_ok=True)
rows = []


def shot(name, pt, nr, rgb, state, w, h, radius):
    img, secs, cov = W.paint(pt, nr, rgb, radius, w, h, state, t=0.30,
                             soft=False, kwargs_tangent=True)
    from PIL import Image
    p = os.path.join(OUT, f"{name}.jpg")
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
        p, quality=94, subsampling=0)
    r = {"name": name, "state": state, "width": w, "height": h,
         "radius_m": radius, "strokes": int(len(pt)),
         "lapvar": round(lapvar_array(img), 1),
         "lapvar_norm": round(lapvar_norm_array(img), 1),
         "coverage": round(cov, 4), "render_s": round(secs, 1), "file": p}
    rows.append(r)
    print(f"  {name:<40} {w}x{h} r={radius:.4f} lapvar {r['lapvar']:8.1f}"
          f"  cov {cov*100:5.1f}%  {secs:5.1f}s", flush=True)
    del img


def main():
    t0 = time.time()
    a = W.anchors(0.0090, 1_881_992)
    st = a.pop("stage")
    pt, nr, bx = a["point"], a["normal"], a["box"]
    occ = W.occlude_anchors(st, pt, nr)
    rgb = W.colours(st, pt, nr, bx, "lit", occ)

    print("\n== 4K: the same brush, then a brush scaled to the frame ==", flush=True)
    shot("4K-r0.021-samebrush", pt, nr, rgb, "lit", 3840, 2160, 0.021)
    for r in (0.012, 0.009, 0.0075):
        shot(f"4K-r{r}", pt, nr, rgb, "lit", 3840, 2160, r)
    shot("1600-r0.021-reference", pt, nr, rgb, "lit", 1600, 900, 0.021)

    with open(os.path.join(OUT, "fourk.json"), "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows,
                   "seconds": round(time.time() - t0, 1)}, f, indent=2)
    print("wrote " + os.path.join(OUT, "fourk.json"), flush=True)


if __name__ == "__main__":
    main()
