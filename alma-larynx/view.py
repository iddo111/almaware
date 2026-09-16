"""alma-figure / view.py — look at the STL before believing anything about it.

Eyes-and-ears law: the mesh statistics said WATERTIGHT, which tells me the topology is
sound and tells me nothing at all about whether the thing looks like Iddo or like a
potato. So: render it, four sides, and actually look.

    python view.py                       # renders iddo-figure.stl -> iddo-figure.png
    python view.py --stl x.stl --out y.png
"""
from __future__ import annotations

import argparse
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PAPER = (252, 251, 246)
INK = (24, 26, 30)
MUTE = (150, 156, 162)
SKIN = (232, 196, 168)


def load_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        raw = np.frombuffer(f.read(n * 50), dtype=np.uint8).reshape(n, 50)
    tri = np.zeros((n, 3, 3), dtype=np.float32)
    for i in range(3):
        tri[:, i, :] = raw[:, 12 + i * 12:24 + i * 12].copy().view(np.float32)
    return tri


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32)


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)


def render(tris, W, H, yaw, pitch=0.0, base=SKIN, light=(0.4, -0.62, 0.68)):
    """Painter's algorithm with a z-buffer, flat shading. Small, honest, no deps."""
    R = rot_x(pitch) @ rot_z(yaw)
    v = tris.reshape(-1, 3) @ R.T
    v = v.reshape(-1, 3, 3)

    mn, mx = v.reshape(-1, 3).min(axis=0), v.reshape(-1, 3).max(axis=0)
    ctr = (mn + mx) / 2.0
    span = max(mx[0] - mn[0], mx[2] - mn[2]) * 1.12
    sc = min(W, H) / span

    px = (v[:, :, 0] - ctr[0]) * sc + W / 2.0
    py = H / 2.0 - (v[:, :, 2] - ctr[2]) * sc          # screen y is down
    depth = v[:, :, 1].mean(axis=1)

    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(ln, 1e-9)
    L = np.array(light, dtype=np.float32)
    L = L / np.linalg.norm(L)
    lam = np.clip(n @ L, 0.0, 1.0)
    shade = 0.30 + 0.70 * lam                          # ambient + diffuse

    img = Image.new("RGB", (W, H), PAPER)
    dr = ImageDraw.Draw(img)
    order = np.argsort(-depth)                         # far to near
    for i in order:
        if n[i, 1] > 0:                                # back-face cull
            continue
        s = float(shade[i])
        col = (int(base[0] * s), int(base[1] * s), int(base[2] * s))
        dr.polygon([(px[i, 0], py[i, 0]), (px[i, 1], py[i, 1]), (px[i, 2], py[i, 2])],
                   fill=col)
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", default="iddo-figure.stl")
    ap.add_argument("--out", default="iddo-figure.png")
    ap.add_argument("--size", type=int, default=520)
    a = ap.parse_args()

    tris = load_stl(a.stl)
    print("loaded %d triangles from %s" % (len(tris), a.stl))

    # The camera sits at -Y looking toward +Y, and the nose points +Y, so yaw=0 shows
    # the BACK. Start at pi so FRONT actually means front.
    views = [("FRONT", np.pi, 0.0), ("3/4", np.pi - 0.75, 0.0),
             ("SIDE", np.pi / 2, 0.0), ("BACK", 0.0, 0.0)]
    S = a.size
    sheet = Image.new("RGB", (S * len(views), S + 46), PAPER)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 20)
    except Exception:
        f = ImageFont.load_default()
    dr = ImageDraw.Draw(sheet)
    for i, (name, yaw, pitch) in enumerate(views):
        im = render(tris, S, S, yaw, pitch)
        sheet.paste(im, (i * S, 0))
        dr.text((i * S + 16, S + 12), name, font=f, fill=INK)
    h = tris.reshape(-1, 3)[:, 2]
    dr.text((S * len(views) - 260, S + 12),
            "height %.0f mm" % (h.max() - h.min()), font=f, fill=MUTE)
    sheet.save(a.out)
    print("wrote %s  (%dx%d)" % (a.out, *sheet.size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
