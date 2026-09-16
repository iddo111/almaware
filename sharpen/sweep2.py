# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

SWEEP 2 - THE ALPHA PROFILE, the second blur source, which nobody had varied.

`canvas.EDGE = 0.55` sets a stroke's alpha to `(1-q)**0.55` across the WHOLE
ellipse, so every stroke is a soft gradient from its centre to its rim and
overlapping strokes average into one another. This measures what happens when the
mark gets a harder boundary, at a fixed radius / count / resolution, so the number
is attributable to the profile and nothing else.

Also sweeps ELONGATION, because a stroke 4x longer than it is wide smears along
its own tangent and that smear is exactly what a Laplacian sees as blur.
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

import canvas                                             # noqa: E402
import room                                               # noqa: E402
import workshop as W                                      # noqa: E402
from anatomy import Strokes                               # noqa: E402
from sharpness import lapvar_array, lapvar_norm_array     # noqa: E402

OUT = os.path.join(HERE, "sweep2")
os.makedirs(OUT, exist_ok=True)
STATE, T, WD, HT = "dark", 0.30, 1600, 900
rows = []


def go(tag, pt, nr, rgb, radius, edge, elong, save=None):
    n = len(pt)
    rr = np.random.default_rng(18)
    rad = radius * (1.0 + rr.uniform(-0.22, 0.22, n))
    el = None if elong is None else np.full(n, float(elong))
    st = Strokes(point=pt, normal=nr, rgb=rgb, radius=rad, elong=el)
    cam = room.rail_camera(T, WD, HT)
    t0 = time.time()
    img, _z, hit = canvas.render(None, cam, st, style="painterly", seed=17,
                                 background=room.STATES[STATE]["sky"],
                                 return_zbuf=True, edge=edge)
    secs = time.time() - t0
    r = {"tag": tag, "radius_m": radius, "edge": edge, "elong": elong,
         "strokes": n, "lapvar": round(lapvar_array(img), 1),
         "lapvar_norm": round(lapvar_norm_array(img), 1),
         "coverage": round(float(hit.mean()), 4), "render_s": round(secs, 1)}
    rows.append(r)
    print(f"  {tag:<30} lapvar {r['lapvar']:8.1f} (norm {r['lapvar_norm']:8.1f})"
          f"  cov {r['coverage']*100:5.1f}%  {secs:5.1f}s", flush=True)
    if save:
        from PIL import Image
        p = os.path.join(OUT, save)
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            p, quality=93, subsampling=0)
        r["file"] = p
    del img
    return r


def main():
    t0 = time.time()
    an = W.anchors(0.0165, 340_000)
    st = an.pop("stage")
    pt, nr, bx = an["point"], an["normal"], an["box"]
    occ = W.occlude_anchors(st, pt, nr)
    rgb = W.colours(st, pt, nr, bx, STATE, occ)

    print("\n== G. ALPHA PROFILE (canvas.EDGE), radius 0.021, 340k, 1600x900 ==",
          flush=True)
    for e in (None, 0.55, 1.0, 1.6, 2.4, 3.5, 5.0):
        go(f"G edge={e}", pt, nr, rgb, 0.021, e, None,
           save=None if e is None else f"G-edge{e}.jpg")

    print("\n== H. ELONGATION (a long stroke smears along itself) ==", flush=True)
    for el in (None, 3.0, 2.0, 1.4, 1.0):
        go(f"H elong={el}", pt, nr, rgb, 0.021, 2.4, el,
           save=f"H-elong{el}.jpg")

    print("\n== I. the combination: hard edge + round mark + smaller brush ==",
          flush=True)
    for rad in (0.021, 0.014, 0.010):
        go(f"I r={rad} edge=2.4 elong=1.4", pt, nr, rgb, rad, 2.4, 1.4,
           save=f"I-r{rad}.jpg")

    with open(os.path.join(OUT, "sweep2.json"), "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows,
                   "seconds": round(time.time() - t0, 1)}, f, indent=2)
    print("wrote " + os.path.join(OUT, "sweep2.json"), flush=True)


if __name__ == "__main__":
    main()
