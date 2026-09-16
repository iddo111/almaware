# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

RE-RENDER THE WORKSHOP: the exact two published stills, before and after.

Same camera (`room.rail_camera(0.30)`), same size (1600x900) as
`_deliverables/hub/oneroom-workshop-{dark,lit}.jpg`, so the before/after numbers
are directly against the ones Iddo judged: 126 for LIT, 10.2 for DARK.

Everything the AFTER adds is named on the command line, so nothing is hidden:
contact shadow from where the light actually is, ambient occlusion, world-space
texture, a smaller brush, more strokes, and the exposure that occlusion costs
being given back. Run with `--plain` to reproduce the BEFORE exactly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import room                                              # noqa: E402
import workshop as W                                     # noqa: E402
from sharpness import lapvar_array, lapvar_norm_array    # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "rerender"))
    ap.add_argument("--voxel", type=float, default=0.0165)
    ap.add_argument("--strokes", type=int, default=340_000)
    ap.add_argument("--radius", type=float, default=0.021)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--t", type=float, default=0.30)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--ao-rays", type=int, default=12)
    ap.add_argument("--tag", default="AFTER")
    ap.add_argument("--plain", action="store_true",
                    help="no occlusion, no texture: the picture he rejected")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    t0 = time.time()
    an = W.anchors(a.voxel, a.strokes)
    st = an.pop("stage")
    pt, nr, bx = an["point"], an["normal"], an["box"]
    occ = None if a.plain else W.occlude_anchors(st, pt, nr, ao_rays=a.ao_rays)

    from PIL import Image
    rows = []
    for state in ("dark", "lit"):
        rgb = W.colours(st, pt, nr, bx, state, occ, gain=a.gain)
        img, secs, cov = W.paint(pt, nr, rgb, a.radius, a.width, a.height, state,
                                 t=a.t)
        p = os.path.join(a.out, f"workshop-{a.tag}-{state}.jpg")
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            p, quality=93, subsampling=0)
        r = {"state": state, "tag": a.tag, "file": p,
             "lapvar": round(lapvar_array(img), 1),
             "lapvar_norm": round(lapvar_norm_array(img), 1),
             "coverage": round(cov, 4), "strokes": int(len(pt)),
             "radius_m": a.radius, "voxel": a.voxel, "gain": a.gain,
             "size": [a.width, a.height], "render_s": round(secs, 1),
             "occlusion": not a.plain}
        rows.append(r)
        print(f"  {state:<5} lapvar {r['lapvar']:8.1f} (norm {r['lapvar_norm']:8.1f})"
              f"  cov {cov*100:5.1f}%  {secs:.0f}s -> {p}", flush=True)
        del img

    j = os.path.join(a.out, f"rerender-{a.tag}.json")
    with open(j, "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "argv": vars(a), "rows": rows,
                   "seconds": round(time.time() - t0, 1)}, f, indent=2)
    print("wrote " + j, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
