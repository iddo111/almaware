# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

SWEEP 4 - WHAT THE TEXTURE IS WORTH ONCE THE COMPOSITOR STOPS ERASING IT.

On the soft path, world-space texture bought +3% (10.1 -> 10.4). That was never a
verdict on the texture; it was the averaging eating it. Each stroke carries ONE
colour, and pass 2 replaces that colour with the mean of its neighbours' - which
is precisely what a texture is not.

So the texture is re-measured on the HARD path, and its finest octave is swept,
because the cap of 3.5 cm was chosen for a brush that was blending. If the
compositor keeps one stroke per pixel, the painter can carry detail down to the
brush itself.
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

import occlusion                                           # noqa: E402
import workshop as W                                       # noqa: E402
from sharpness import lapvar_array, lapvar_norm_array      # noqa: E402

OUT = os.path.join(HERE, "sweep4")
os.makedirs(OUT, exist_ok=True)
WD, HT, T = 1600, 900, 0.30
rows = []


def shot(name, pt, nr, rgb, state, save=False, **kw):
    img, secs, cov = W.paint(pt, nr, rgb, 0.021, WD, HT, state, t=T, **kw)
    r = {"name": name, "state": state, "lapvar": round(lapvar_array(img), 1),
         "lapvar_norm": round(lapvar_norm_array(img), 1),
         "coverage": round(cov, 4), "render_s": round(secs, 1)}
    rows.append(r)
    print(f"  {name:<46} lapvar {r['lapvar']:8.1f} (norm {r['lapvar_norm']:8.1f})"
          f"  cov {cov*100:5.1f}%  {secs:5.1f}s", flush=True)
    if save:
        from PIL import Image
        p = os.path.join(OUT, f"{name}.jpg")
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            p, quality=94, subsampling=0)
        r["file"] = p
    del img
    return r


def main():
    t0 = time.time()
    a = W.anchors(0.0090, 1_200_000)
    st = a.pop("stage")
    pt, nr, bx = a["point"], a["normal"], a["box"]
    occ = W.occlude_anchors(st, pt, nr)

    print("\n== Q. TEXTURE STRENGTH on the hard path ==", flush=True)
    for state in ("dark", "lit"):
        for ts in (0.0, 0.15, 0.30, 0.45, 0.60):
            rgb = W.colours(st, pt, nr, bx, state, occ, texture_strength=ts)
            shot(f"Q tex={ts} [{state}]", pt, nr, rgb, state, soft=False,
                 kwargs_tangent=True, save=(ts in (0.0, 0.30, 0.60)))

    print("\n== R. shadow and AO, re-measured on the hard path ==", flush=True)
    for state in ("dark", "lit"):
        for tag, kw in (("none", dict(shadow_strength=0, ao_strength=0,
                                      texture_strength=0)),
                        ("shadow", dict(ao_strength=0, texture_strength=0)),
                        ("AO", dict(shadow_strength=0, texture_strength=0)),
                        ("all", {})):
            rgb = W.colours(st, pt, nr, bx, state, occ, **kw)
            shot(f"R {tag} [{state}]", pt, nr, rgb, state, soft=False,
                 kwargs_tangent=True)

    print("\n== S. how fine may the texture go, now the painter can carry it ==",
          flush=True)
    base = occlusion.texture
    for scale in (1.0, 0.6, 0.35, 0.2):
        def tex(point, normal, strength=0.30, salt=0, _s=scale):
            return base(np.asarray(point) / _s, normal, strength, salt)
        occlusion.texture = tex
        rgb = W.colours(st, pt, nr, bx, "lit", occ, texture_strength=0.30)
        shot(f"S finest={3.5*scale:.2f}cm", pt, nr, rgb, "lit", soft=False,
             kwargs_tangent=True, save=True)
    occlusion.texture = base

    with open(os.path.join(OUT, "sweep4.json"), "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows,
                   "seconds": round(time.time() - t0, 1)}, f, indent=2)
    print("\nwrote " + os.path.join(OUT, "sweep4.json"), flush=True)


if __name__ == "__main__":
    main()
