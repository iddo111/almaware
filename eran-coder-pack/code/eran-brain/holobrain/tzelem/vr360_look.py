# -*- coding: utf-8 -*-
"""OPEN IT AND LOOK. Crops at the exact places a 360 plate fails.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

"Never ship a number without opening the image" (sharpen/README-FINDINGS). A seam mean
of 6/255 and a coverage of 99.999% are both compatible with a plate that looks broken,
so this cuts 1:1 crops exactly where the six faces meet -- computed from the projection,
not eyeballed -- plus both poles and the horizon.

Where the boundaries land in an equirect with u = atan2(x,-z)/TAU + 0.5, v = acos(y)/PI:
  vertical (side face | side face) at |x| == |z|  ->  u = 0.125, 0.375, 0.625, 0.875
  horizontal (side | pole face)   at |y| == 1/sqrt(2)  ->  v = 0.25 and 0.75
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None

V_SEAMS = [(0.125, "nx|pz"), (0.375, "nx|nz"), (0.625, "px|nz"), (0.875, "px|pz")]
H_SEAMS = [(0.25, "side|py  (+45 deg)"), (0.75, "side|ny  (-45 deg)")]


def main(path: str, out_dir: str) -> None:
    im = Image.open(path)
    W, H = im.size
    os.makedirs(out_dir, exist_ok=True)
    a = np.asarray(im)

    # 1) the whole sphere, small enough to take in at once
    im.resize((1800, 900), Image.LANCZOS).save(os.path.join(out_dir, "look_whole.png"))

    # 2) every VERTICAL seam, 1:1, 260 px wide, at the horizon
    CW, CH = 260, 420
    tiles, labels = [], []
    for u, name in V_SEAMS:
        x = int(round(u * W))
        crop = a[H // 2 - CH // 2:H // 2 + CH // 2,
                 max(0, x - CW // 2):max(0, x - CW // 2) + CW]
        tiles.append(crop)
        labels.append(name)
    sheet = np.concatenate([np.concatenate([t, np.full((CH, 8, 3), 255, np.uint8)], 1)
                            for t in tiles], 1)
    img = Image.fromarray(sheet)
    dr = ImageDraw.Draw(img)
    for i, name in enumerate(labels):
        dr.text((i * (CW + 8) + 6, 6), name + "  (join is dead centre)",
                fill=(255, 40, 40))
    img.save(os.path.join(out_dir, "look_vseams.png"))

    # 3) both HORIZONTAL seams, 1:1, a wide strip so a line would be obvious
    strips = []
    for v, name in H_SEAMS:
        y = int(round(v * H))
        s = a[y - 90:y + 90, W // 2 - 700:W // 2 + 700]
        img = Image.fromarray(s)
        ImageDraw.Draw(img).text((6, 6), name + "  (join is the middle row)",
                                 fill=(255, 40, 40))
        strips.append(np.asarray(img))
        strips.append(np.full((10, 1400, 3), 255, np.uint8))
    Image.fromarray(np.concatenate(strips, 0)).save(
        os.path.join(out_dir, "look_hseams.png"))

    # 4) THE POLES. The classic equirect failure is a smeared or twisted pole, and it
    #    is invisible in the unrolled plate because that is where the stretch is worst.
    for name, sl in (("zenith", slice(0, 300)), ("nadir", slice(H - 300, H))):
        band = a[sl]
        Image.fromarray(band).resize((1400, 105), Image.LANCZOS).save(
            os.path.join(out_dir, f"look_{name}_band.png"))

    # 5) a 1:1 patch of ordinary picture, so brush marks can be judged
    Image.fromarray(a[H // 2 - 200:H // 2 + 200,
                      int(0.03 * W):int(0.03 * W) + 700]).save(
        os.path.join(out_dir, "look_detail_1to1.png"))
    print("wrote crops to", out_dir)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
