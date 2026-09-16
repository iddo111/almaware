"""EINAYIM / עֵינַיִם — WHAT WAS CAPTURED, SEEN BY TZELEM. (PC, numpy)

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A mesh is a file until somebody looks at it. TZELEM's MeshStage already knows how
to look at triangles, so a captured shape gets rendered by ERAN's own eye rather
than by a viewer we would then have to keep alive. Two outputs:

    <stem>.gif    a turntable, so the shape can be judged as a shape
    <stem>.png    one still
    <stem>.tzg    the G-buffer, so TZELEM's painter can take it from here

No torch. Nothing under tzelem/ is modified — stage.py and meshstage.py are
imported and used as they are.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_TZELEM = os.path.join(os.path.dirname(_HERE), "tzelem")
for _p in (_TZELEM, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from meshstage import MeshStage, frame           # noqa: E402
import gbuffer as GB                             # noqa: E402
from truthviews import read_stl                  # noqa: E402

# PC courtesy (2026-09-03 scar: renders starved the KESHEV mic): run below normal priority.
try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass



def turntable(stl_path, out_stem, frames=24, width=384, height=288,
              albedo=(0.80, 0.72, 0.58), ms_per_frame=90):
    from PIL import Image
    tris = read_stl(stl_path)
    st = MeshStage(tris, albedo=albedo)
    imgs = []
    for k in range(frames):
        cam = frame(tris, width=width, height=height,
                    step_deg=360.0 * k / frames)
        g = st.gbuffer(cam)
        img = (np.clip(st.shade(g), 0, 1) * 255).astype(np.uint8)
        imgs.append(Image.fromarray(img))
        if k == 0:
            imgs[0].save(out_stem + ".png")
            GB.write(out_stem, cam, g["depth"], g["normal"], st.shade(g))
        print(f"  frame {k+1}/{frames}", end="\r", flush=True)
    imgs[0].save(out_stem + ".gif", save_all=True, append_images=imgs[1:],
                 duration=ms_per_frame, loop=0, optimize=True)
    print(f"\n  {len(tris)} triangles -> {out_stem}.gif / .png / .tzg")
    return out_stem + ".gif"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stl"); ap.add_argument("out_stem")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--width", type=int, default=384)
    ap.add_argument("--height", type=int, default=288)
    a = ap.parse_args()
    turntable(a.stl, a.out_stem, a.frames, a.width, a.height)
