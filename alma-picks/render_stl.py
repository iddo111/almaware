#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software renderer for the STL files. Z-buffer + flat shading, pure numpy.
Renders the ACTUAL mesh - what you see is the geometry that will print.
"""
import math
import os
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
F = {"blk": "C:/Windows/Fonts/ariblk.ttf", "bd": "C:/Windows/Fonts/arialbd.ttf"}
PAPER = (252, 251, 246)
TEAL = (15, 118, 110)
INK = (18, 20, 24)
MUTE = (140, 146, 152)


def font(k, px):
    return ImageFont.truetype(F[k], int(px))


def load_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        data = np.frombuffer(f.read(n * 50), dtype=np.uint8)
    data = data.reshape(n, 50)
    verts = np.zeros((n, 3, 3), dtype=np.float32)
    for k in range(3):
        chunk = data[:, 12 + k * 12: 24 + k * 12].copy()
        verts[:, k, :] = chunk.view(np.float32).reshape(n, 3)
    return verts


def rot(ax, ay, az):
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def render(tris, W, H, ax, ay, az, base_rgb, zoom=0.86, light=(0.35, -0.5, 0.78)):
    V = tris.reshape(-1, 3) @ rot(ax, ay, az).T
    V = V.reshape(-1, 3, 3)

    mn, mx = V.reshape(-1, 3).min(0), V.reshape(-1, 3).max(0)
    ctr = (mn + mx) / 2.0
    sx_span = (mx[0] - mn[0]) or 1.0
    sy_span = (mx[1] - mn[1]) or 1.0
    s = min(W * zoom / sx_span, H * zoom / sy_span)
    P = (V - ctr) * s
    P[:, :, 0] += W / 2.0
    P[:, :, 1] = H / 2.0 + P[:, :, 1]   # +Y is toward the tip; keep it screen-down

    # face normals + Lambert
    e1 = V[:, 1] - V[:, 0]
    e2 = V[:, 2] - V[:, 0]
    N = np.cross(e1, e2)
    ln = np.linalg.norm(N, axis=1)
    ln[ln == 0] = 1.0
    N = N / ln[:, None]
    L = np.array(light, dtype=np.float64)
    L = L / np.linalg.norm(L)
    lam = np.clip(N @ L, 0, 1)
    shade = 0.46 + 0.54 * lam                       # ambient + diffuse

    zbuf = np.full((H, W), -1e18, dtype=np.float64)
    cbuf = np.zeros((H, W), dtype=np.float64)
    hit = np.zeros((H, W), dtype=bool)

    x0 = np.floor(P[:, :, 0].min(1)).astype(int)
    x1 = np.ceil(P[:, :, 0].max(1)).astype(int)
    y0 = np.floor(P[:, :, 1].min(1)).astype(int)
    y1 = np.ceil(P[:, :, 1].max(1)).astype(int)

    for i in range(P.shape[0]):
        if N[i, 2] <= 0:                            # back-face cull
            continue
        ax0, ax1 = max(0, x0[i]), min(W - 1, x1[i])
        ay0, ay1 = max(0, y0[i]), min(H - 1, y1[i])
        if ax1 < ax0 or ay1 < ay0:
            continue
        a, b, c = P[i]
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        xs = np.arange(ax0, ax1 + 1)
        ys = np.arange(ay0, ay1 + 1)
        gx, gy = np.meshgrid(xs, ys)
        w0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
        w1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
        w2 = 1.0 - w0 - w1
        m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not m.any():
            continue
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        sub = zbuf[ay0:ay1 + 1, ax0:ax1 + 1]
        upd = m & (z > sub)
        if not upd.any():
            continue
        sub[upd] = z[upd]
        cbuf[ay0:ay1 + 1, ax0:ax1 + 1][upd] = shade[i]
        hit[ay0:ay1 + 1, ax0:ax1 + 1][upd] = True

    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:, :] = PAPER
    base = np.array(base_rgb, dtype=np.float64)
    px = np.clip(cbuf[hit][:, None] * base[None, :], 0, 255)
    img[hit] = px.astype(np.uint8)
    return Image.fromarray(img)


def panel(path, W, H, ax, ay, az, col, title, sub):
    tris = load_stl(path)
    body = render(tris, W, H - 92, ax, ay, az, col)
    out = Image.new("RGB", (W, H), PAPER)
    out.paste(body, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((16, H - 84), title, font=font("blk", 30), fill=col)
    d.text((16, H - 44), sub, font=font("bd", 21), fill=MUTE)
    return out


if __name__ == "__main__":
    S = os.path.join(OUT, "stl")
    R = math.radians
    panels = [
        panel(os.path.join(S, "alma-pick-1-wordmark.stl"), 620, 640,
              R(-58), R(0), R(0), (168, 174, 182),
              "PICK  -  face", "26 x 31 mm, wordmark raised 0.40 mm"),
        panel(os.path.join(S, "alma-pick-1-wordmark.stl"), 620, 640,
              R(-80), R(0), R(0), (168, 174, 182),
              "PICK  -  low angle", "the bevel: 1.20 mm core down to 0.40 mm rim"),
        panel(os.path.join(S, "alma-risha-oud.stl"), 1256, 340,
              R(-60), R(0), R(-90), (34, 168, 156),
              "RISHA  -  oud plectrum", "120 mm, grip ridges + name, 1.00 -> 0.55 mm taper"),
    ]

    Wtot = 1256
    Htot = 120 + 640 + 24 + 340
    sheet = Image.new("RGB", (Wtot, Htot), PAPER)
    d = ImageDraw.Draw(sheet)
    d.text((16, 24), "ALMA PICKS  +  RISHA", font=font("blk", 56), fill=INK)
    d.text((20, 88), "rendered from the actual STL files  -  iddoperez.ai",
           font=font("bd", 23), fill=MUTE)
    sheet.paste(panels[0], (0, 120))
    sheet.paste(panels[1], (636, 120))
    sheet.paste(panels[2], (0, 120 + 640 + 24))
    p = os.path.join(OUT, "alma-picks-render.png")
    sheet.save(p)
    print("render:", p, sheet.size)
