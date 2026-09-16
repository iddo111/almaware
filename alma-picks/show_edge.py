#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slice the real STL and draw the edge profile. Proof, not a promise."""
import math
import os
import struct

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
STL = os.path.join(OUT, "stl", "alma-pick-1-wordmark.stl")
F = {"b": "C:/Windows/Fonts/arialbd.ttf", "k": "C:/Windows/Fonts/ariblk.ttf"}


def load(path):
    f = open(path, "rb")
    f.read(80)
    n = struct.unpack("<I", f.read(4))[0]
    tris = []
    for _ in range(n):
        f.read(12)
        tris.append([struct.unpack("<3f", f.read(12)) for _ in range(3)])
        f.read(2)
    return tris


def slice_plane(tris, axis, value):
    """Segments where the mesh crosses axis == value."""
    segs = []
    for t in tris:
        d = [p[axis] - value for p in t]
        pts = []
        for i in range(3):
            j = (i + 1) % 3
            if (d[i] > 0) != (d[j] > 0):
                f = d[i] / (d[i] - d[j])
                pts.append(tuple(t[i][k] + (t[j][k] - t[i][k]) * f for k in range(3)))
        if len(pts) == 2:
            segs.append(pts)
    return segs


def draw_section(segs, axis, title, sub, w=1500, h=620):
    """axis 0 -> section runs along Y; axis 1 -> along X."""
    ax = 1 if axis == 0 else 0
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    fb = ImageFont.truetype(F["b"], 22)
    fk = ImageFont.truetype(F["k"], 34)
    fs = ImageFont.truetype(F["b"], 19)

    us = [p[ax] for s in segs for p in s]
    zs = [p[2] for s in segs for p in s]
    if not us:
        return img
    u0, u1 = min(us), max(us)
    pad, top = 80, 165
    SX = (w - pad * 2) / (u1 - u0)
    z_base = h - 118
    # exaggerate vertically as much as will still FIT - never let it overflow
    room = z_base - top
    SZ = min(SX * 6.0, room / max(0.001, max(zs)))

    d.text((pad, 26), title, font=fk, fill=(15, 118, 110))
    d.text((pad, 74), sub, font=fb, fill=(90, 95, 105))
    d.text((pad, 106), "vertical scale exaggerated 6x so the taper is visible",
           font=fs, fill=(150, 155, 162))

    def P(u, z):
        return (pad + (u - u0) * SX, z_base - z * SZ)

    for s in segs:
        d.line([P(s[0][ax], s[0][2]), P(s[1][ax], s[1][2])],
               fill=(15, 118, 110), width=3)

    # measured extremes
    d.line([pad, z_base, w - pad, z_base], fill=(220, 220, 214), width=2)
    for z, lab in ((0.40, "rim 0.40 mm"), (1.20, "core 1.20 mm"), (1.60, "logo top 1.60 mm")):
        y = z_base - z * SZ
        d.line([pad, y, w - pad, y], fill=(232, 232, 226), width=1)
        d.text((w - pad - 190, y - 24), lab, font=fs, fill=(150, 155, 162))

    d.text((pad, h - 96),
           "measured from the STL: %d slice segments,  thickness %.2f - %.2f mm"
           % (len(segs), min(zs), max(zs)), font=fb, fill=(90, 95, 105))
    d.text((pad, h - 66),
           "rim 0.40 mm = one nozzle, the thinnest FDM can do. Sand 400/800/1500 to finish sharp.",
           font=fb, fill=(90, 95, 105))
    return img


if __name__ == "__main__":
    tris = load(STL)
    a = draw_section(slice_plane(tris, 0, 0.0), 0,
                     "EDGE PROFILE  -  lengthwise through the tip",
                     "shoulder (left)  ->  playing tip (right).  5.0 mm tip bevel, flat bottom")
    b = draw_section(slice_plane(tris, 1, -6.0), 1,
                     "EDGE PROFILE  -  across the shoulders",
                     "3.2 mm bevel each side into a 1.20 mm core. Bottom is flat - sits on the bed.")
    sheet = Image.new("RGB", (a.width, a.height + b.height + 20), (255, 255, 255))
    sheet.paste(a, (0, 0))
    sheet.paste(b, (0, a.height + 20))
    p = os.path.join(OUT, "alma-picks-edge.png")
    sheet.save(p)
    print("edge profile:", p, sheet.size)
