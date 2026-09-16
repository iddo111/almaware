# -*- coding: utf-8 -*-
"""OPEN THE PLATE AND LOOK AT IT. Cuts the views where a 360 plate actually fails.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A number nobody looked at is not a measurement. Every cut here exists because it is
where one specific failure mode lives, and each one is written out at the plate's own
native resolution so nothing is hidden by a downscale:

  centre    the pose's own look direction -- what a viewer opens on, and the view the
            sharpness ruler is run on
  edge-*    dead-centred on a VERTICAL CUBE EDGE at the horizon. If the two faces
            disagree, the line runs straight down the middle of this picture.
  corner    dead-centred on a cube CORNER, where THREE faces meet -- the hardest point
  zenith    straight up: equirect poles smear, and this is where you see it
  nadir     straight down: the same, plus the ground right under the eye
  behind    180 degrees from centre, because half a panorama is behind you
  horizon   a 1:1 strip across the whole equator, so the horizon can be checked LEVEL
            and every vertical cube edge inspected in one image
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "sharpen"))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cube360 as C                              # noqa: E402
import sharpness                                 # noqa: E402


def dir_of(az_deg: float, el_deg: float) -> np.ndarray:
    a, e = np.radians(az_deg), np.radians(el_deg)
    return np.array([np.sin(a) * np.cos(e), np.sin(e), -np.cos(a) * np.cos(e)])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plate", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fov", type=float, default=90.0)
    a = ap.parse_args()

    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(a.plate) as im:
        equi = np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
    rep = json.load(open(a.report, encoding="utf-8"))
    yaw0 = np.radians(rep["yaw0_deg"])
    h, w = equi.shape[:2]
    size = w // 4
    os.makedirs(a.out, exist_ok=True)
    print(f"plate {w}x{h}, PPD at the equator {w/360.0:.2f}, yaw0 "
          f"{rep['yaw0_deg']:.3f} deg, cutting {a.fov:.0f}-deg views at {size} px")

    # THESE ARE WORLD AZIMUTHS, NOT PLATE COLUMNS. `cut_view` takes a WORLD direction
    # and SUBTRACTS yaw0 itself to find the column, so anything subtracting yaw0 here
    # too would rotate every view by -yaw0. It did, on the first run: "centre" came
    # back looking 105 degrees off the cafe, straight down the boulevard. The plate was
    # right and the inspection tool was wrong, which is exactly the failure that only
    # OPENING THE PICTURE catches -- every number in the run was unaffected.
    y0 = float(np.degrees(yaw0))
    cuts = {
        "centre": (y0, 0.0),            # the plate's centre column = the cafe
        "behind": (y0 + 180.0, 0.0),
        "left90": (y0 - 90.0, 0.0),
        "right90": (y0 + 90.0, 0.0),
    }
    # the four VERTICAL cube edges. A cube edge sits where two face axes meet, and the
    # face axes are the world axes, so the edges are at world azimuth 45/135/225/315.
    for world_az in (45.0, 135.0, 225.0, 315.0):
        cuts[f"edge-{int(world_az)}"] = (world_az, 0.0)
    # a cube CORNER: the +X+Y+Z octant, elevation atan(1/sqrt(2)) = 35.264 deg
    cuts["corner"] = (45.0, 35.264)
    cuts["zenith"] = (0.0, 89.999)
    cuts["nadir"] = (0.0, -89.999)

    rows = []
    for name, (az, el) in cuts.items():
        d = dir_of(az, el)
        up = (0.0, 1.0, 0.0)
        if abs(d[1]) > 0.999:
            up = (0.0, 0.0, -1.0)      # the poles: world up is parallel to the view
        v = C.cut_view(equi, d, a.fov, size, yaw0=yaw0, up=up)
        p = os.path.join(a.out, f"cut-{name}.png")
        C.save_png(p, v)
        lv = sharpness.lapvar_array(v)
        # how flat is it? a cut that is all sky is not evidence of anything
        rows.append((name, az, el, lv, float(v.std()), float(v.mean())))
        print(f"  {name:<10} az {az:8.2f}  el {el:7.2f}   lapvar {lv:8.1f}   "
              f"mean {v.mean():.3f}  std {v.std():.3f}   -> {os.path.basename(p)}")

    # the whole equator at 1:1, 240 rows tall: the level check and every vertical
    # cube edge in one strip
    band = equi[h // 2 - 120: h // 2 + 120]
    C.save_png(os.path.join(a.out, "horizon-strip-1to1.png"), band)
    print(f"  horizon strip {band.shape[1]}x{band.shape[0]} at 1:1")

    # a 1:1 crop of the centre, so the STROKES themselves can be seen
    cx = w // 2
    crop = equi[h // 2 - 300: h // 2 + 300, cx - 500: cx + 500]
    C.save_png(os.path.join(a.out, "centre-crop-1to1.png"), crop)
    print(f"  centre crop {crop.shape[1]}x{crop.shape[0]} at 1:1")

    with open(os.path.join(a.out, "cuts.json"), "w", encoding="utf-8") as f:
        json.dump([{"name": r[0], "az": r[1], "el": r[2], "lapvar": r[3],
                    "std": r[4], "mean": r[5]} for r in rows], f, indent=1)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
