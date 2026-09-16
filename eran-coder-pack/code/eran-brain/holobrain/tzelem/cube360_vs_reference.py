# -*- coding: utf-8 -*-
"""Put the plate next to the flat shot Iddo has already seen, at MATCHED framing.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

`alma-vr/shots/boulevard-02-cafe-claude.png` is the same eye and the same target, so
it is the only honest reference for "does the 360 plate look like the boulevard".

MATCHING THE FRAMING, which is the whole job here. `boulevard_shots.gd` sets
`_cam.fov = 62.0` on a 3840x2160 viewport. Godot's default keep_aspect is KEEP_HEIGHT,
so 62 is the VERTICAL fov and the horizontal one is
    2*atan(tan(31 deg) * 3840/2160) = 93.78 deg.
So: cut a square view at 93.78 deg horizontal out of the equirect and keep the central
9/16 of its rows. That is the reference's exact frustum, resampled from the plate.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "sharpen"))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cube360 as C                              # noqa: E402
import sharpness                                 # noqa: E402

Image.MAX_IMAGE_PIXELS = None
EYE = np.array([-5.20, 1.62, 10.5])
TARGET = np.array([2.40, 1.55, 12.6])
REF = r"D:\CLAUDE\alma-vr\shots\boulevard-02-cafe-claude.png"


def main(plate: str, yaw0_deg: float, out: str) -> int:
    with Image.open(plate) as im:
        equi = np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
    fov_h = np.degrees(2.0 * np.arctan(np.tan(np.radians(31.0)) * 3840.0 / 2160.0))
    size = equi.shape[1] // 4
    v = C.cut_view(equi, TARGET - EYE, fov_h, size, yaw0=np.radians(yaw0_deg))
    keep = int(round(size * 9 / 16))
    top = (size - keep) // 2
    v = v[top:top + keep]
    print(f"cut at h-fov {fov_h:.2f} deg, {v.shape[1]}x{v.shape[0]}")

    ref = Image.open(REF).convert("RGB")
    lap_mine = sharpness.lapvar_array(v)
    lap_ref = sharpness.lapvar_array(np.asarray(ref, dtype=np.uint8))
    print(f"lapvar   360 plate, this cut : {lap_mine:8.1f}")
    print(f"lapvar   the flat 4K shot    : {lap_ref:8.1f}   (a DIFFERENT render, "
          "not a before/after -- the boulevard rebuilds itself every run)")

    mine = Image.fromarray((np.clip(v, 0, 1) * 255 + 0.5).astype(np.uint8))
    w = 1800
    a = mine.resize((w, round(mine.height * w / mine.width)), Image.LANCZOS)
    b = ref.resize((w, round(ref.height * w / ref.width)), Image.LANCZOS)
    sheet = Image.new("RGB", (w, a.height + b.height + 96), (255, 255, 255))
    from PIL import ImageDraw, ImageFont
    try:
        f = ImageFont.truetype("segoeui.ttf", 26)
    except OSError:
        f = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    d.text((8, 6), "THE 360 PLATE, cut to the reference shot's exact frustum "
                   f"(93.78 deg h-fov)   lapvar {lap_mine:.0f}", (24, 24, 28), f)
    sheet.paste(a, (0, 40))
    d.text((8, 40 + a.height + 8), "alma-vr/shots/boulevard-02-cafe-claude.png -- "
           f"the flat 4K shot, same eye and target   lapvar {lap_ref:.0f}",
           (24, 24, 28), f)
    sheet.paste(b, (0, 40 + a.height + 48))
    sheet.save(out, quality=93, subsampling=0)
    print(out)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1], float(sys.argv[2]), sys.argv[3]))
