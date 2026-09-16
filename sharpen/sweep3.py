# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

SWEEP 3 - THE COMPOSITOR, which is where the blur actually lives.

Sweeps 1 and 2 killed the obvious explanations. Measured, on the workshop's own
camera at 1600x900:

  * contact shadow + AO bought NOTHING on the ruler (dark 10.1 -> 9.1).
  * shrinking the brush looked like a 25x win (9.1 -> 231) but the coverage column
    said 100% -> 73%: it was HOLES, not detail.
  * putting the strokes back to close the holes put the softness back with them:
    r=0.007 with 1.88M strokes is 10.6 at 99.9% coverage, the same picture.
  * ADDING strokes at a fixed brush makes it BLURRIER, 40k -> 340k is 79 -> 9.

That last line is the diagnosis. Every pixel of a covered frame is the
alpha-weighted MEAN of many overlapping strokes (`canvas.render` pass 2), and
averaging k samples of a surface divides its variance by about k. The picture is
not painted with a brush that is too big. It is painted with too many coats.

So this file varies the COMPOSITOR:
  * `soft=False` - the hard path that already exists in canvas.py: pass 1's
    ownership only, one stroke per pixel, no blending anywhere.
  * `edge` far past anything anyone has tried, which walks the soft path toward
    the hard one continuously.
  * both at the stroke counts that actually cover, so nothing is bought with holes.
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

OUT = os.path.join(HERE, "sweep3")
os.makedirs(OUT, exist_ok=True)
T, WD, HT = 0.30, 1600, 900
rows = []


def go(tag, pt, nr, rgb, radius, state, edge=None, elong=None, soft=True,
       save=None):
    n = len(pt)
    rr = np.random.default_rng(18)
    rad = radius * (1.0 + rr.uniform(-0.22, 0.22, n))
    el = None if elong is None else np.full(n, float(elong))
    st = Strokes(point=pt, normal=nr, rgb=rgb, radius=rad, elong=el)
    cam = room.rail_camera(T, WD, HT)
    t0 = time.time()
    if soft:
        img, _z, hit = canvas.render(None, cam, st, style="painterly", seed=17,
                                     background=room.STATES[state]["sky"],
                                     return_zbuf=True, edge=edge)
        cov = float(hit.mean())
    else:
        owner, _z, _fp = canvas.ownership(cam, st, style="painterly", seed=17)
        from palette import Palette
        img = Palette.of(st).lookup(owner, room.STATES[state]["sky"])
        cov = float((owner >= 0).mean())
    secs = time.time() - t0
    r = {"tag": tag, "state": state, "radius_m": radius, "edge": edge,
         "elong": elong, "soft": soft, "strokes": n,
         "lapvar": round(lapvar_array(img), 1),
         "lapvar_norm": round(lapvar_norm_array(img), 1),
         "coverage": round(cov, 4), "render_s": round(secs, 1)}
    rows.append(r)
    print(f"  {tag:<38} lapvar {r['lapvar']:8.1f} (norm {r['lapvar_norm']:8.1f})"
          f"  cov {cov*100:5.1f}%  {secs:5.1f}s", flush=True)
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
    fine = W.anchors(0.0090, 2_000_000)
    st = fine.pop("stage")
    P, N, B = fine["point"], fine["normal"], fine["box"]
    occ = W.occlude_anchors(st, P, N)
    rgb = {s: W.colours(st, P, N, B, s, occ) for s in ("dark", "lit")}

    def thin(n, seed=3):
        m = len(P)
        if n >= m:
            return P, N, np.arange(m)
        i = np.random.default_rng(seed).permutation(m)[:n]
        i.sort()
        return P[i], N[i], i

    p340, n340, i340 = thin(340_000)
    for state in ("dark", "lit"):
        print(f"\n== J. THE HARD PATH (soft=False), {state} ==", flush=True)
        for n in (340_000, 680_000, 1_200_000, len(P)):
            p, nn, i = thin(n)
            go(f"J hard n={n} [{state}]", p, nn, rgb[state][i], 0.021, state,
               soft=False, save=f"J-hard-{state}-n{n}.jpg")

        print(f"\n== K. edge pushed far, at full coverage, {state} ==", flush=True)
        for e in (0.55, 3.5, 8.0, 16.0, 32.0):
            go(f"K edge={e} n=340k [{state}]", p340, n340, rgb[state][i340],
               0.021, state, edge=e, save=f"K-edge{e}-{state}.jpg")

    print("\n== L. round dabs, coverage restored by count ==", flush=True)
    for n, el in ((680_000, 1.0), (1_200_000, 1.0), (len(P), 1.0),
                  (len(P), 1.4)):
        p, nn, i = thin(n)
        go(f"L elong={el} n={n}", p, nn, rgb["dark"][i], 0.021, "dark",
           edge=3.5, elong=el, save=f"L-elong{el}-n{n}.jpg")

    print("\n== M. the best combination found, both states ==", flush=True)
    for state in ("dark", "lit"):
        for n in (680_000, len(P)):
            p, nn, i = thin(n)
            go(f"M hard elong=1.4 n={n} [{state}]", p, nn, rgb[state][i], 0.021,
               state, soft=False, elong=1.4,
               save=f"M-hard-elong14-{state}-n{n}.jpg")

    with open(os.path.join(OUT, "sweep3.json"), "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows,
                   "anchors": int(len(P)),
                   "seconds": round(time.time() - t0, 1)}, f, indent=2)
    print("wrote " + os.path.join(OUT, "sweep3.json"), flush=True)


if __name__ == "__main__":
    main()
