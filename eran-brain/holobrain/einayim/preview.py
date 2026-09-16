"""EINAYIM — one picture of what the model actually built. numpy + Pillow only."""
import argparse, numpy as np
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("npz"); ap.add_argument("out_png")
ap.add_argument("--title", default="")
ap.add_argument("--w", type=int, default=460); ap.add_argument("--h", type=int, default=460)
ap.add_argument("--yaws", default="-35,0,35")
ap.add_argument("--pitch", type=float, default=-18.0)
ap.add_argument("--splat", type=int, default=2)
ap.add_argument("--zoom", type=float, default=1.0)
ap.add_argument("--radpct", type=float, default=97.0)
a = ap.parse_args()

P = np.load(a.npz, allow_pickle=True)
PW = P["world_points"]; IMG = P["images"]; M = P["valid_mask"] > 0.5
pts = PW[M].astype(np.float32); col = np.clip(IMG[M], 0, 1)
print("points", len(pts))

# robust centre + radius (ignore the 1% tail so one stray ray cannot set the frame)
lo, hi = np.percentile(pts, 1, axis=0), np.percentile(pts, 99, axis=0)
keep = np.all((pts >= lo - 0.15 * (hi - lo)) & (pts <= hi + 0.15 * (hi - lo)), axis=1)
pts, col = pts[keep], col[keep]
c = np.median(pts, axis=0)
rad = float(np.percentile(np.linalg.norm(pts - c, axis=1), a.radpct))
print("kept", len(pts), "radius %.3f" % rad)


def render(yaw_deg, pitch_deg, W, H):
    y, p = np.radians(yaw_deg), np.radians(pitch_deg)
    # camera orbits the cloud centre, looking at it
    d = 2.6 * rad
    eye = c + d * np.array([np.cos(p) * np.sin(y), np.sin(p), -np.cos(p) * np.cos(y)])
    f = c - eye; f /= np.linalg.norm(f)
    # model world frame is RDF: +Y is DOWN. right = down x forward, image-down = forward x right
    down = np.array([0.0, 1.0, 0.0])
    r = np.cross(down, f); r /= np.linalg.norm(r)
    u = np.cross(f, r)
    R = np.stack([r, u, f])                       # world -> cam rows
    Q = (pts - eye) @ R.T
    z = Q[:, 2]; ok = z > 1e-4
    fl = a.zoom * 0.9 * min(W, H) / (2 * rad) * d / 2.0
    x = fl * Q[ok, 0] / z[ok] + W / 2
    yy = fl * Q[ok, 1] / z[ok] + H / 2
    zz = z[ok]; cc = col[ok]
    ix = np.rint(x).astype(np.int64); iy = np.rint(yy).astype(np.int64)
    img = np.zeros((H, W, 3), np.float32); zb = np.full((H, W), np.inf, np.float32)
    s = a.splat
    order = np.argsort(-zz)                      # far first, near overwrites
    ix, iy, zz, cc = ix[order], iy[order], zz[order], cc[order]
    for dy in range(-s, s + 1):
        for dx in range(-s, s + 1):
            X, Y = ix + dx, iy + dy
            m = (X >= 0) & (X < W) & (Y >= 0) & (Y < H)
            img[Y[m], X[m]] = cc[m]; zb[Y[m], X[m]] = zz[m]
    # gentle depth shading so the geometry reads as geometry
    fin = np.isfinite(zb)
    if fin.any():
        znorm = (zb - np.percentile(zb[fin], 2)) / max(np.ptp(zb[fin]), 1e-6)
        sh = np.clip(1.15 - 0.45 * np.clip(znorm, 0, 1), 0.35, 1.15)[..., None]
        img = np.where(fin[..., None], np.clip(img * sh, 0, 1), 0.07)
    return (img * 255).astype(np.uint8)


yaws = [float(v) for v in a.yaws.split(",")]
tiles = [render(y, a.pitch, a.w, a.h) for y in yaws]

# input strip on top
n = IMG.shape[0]
th = 190
ins = []
for k in range(n):
    im = Image.fromarray((np.clip(IMG[k], 0, 1) * 255).astype(np.uint8))
    im = im.resize((int(im.width * th / im.height), th), Image.Resampling.LANCZOS)
    ins.append(im)
top_w = sum(i.width for i in ins) + 8 * (len(ins) - 1)
bot_w = a.w * len(tiles) + 8 * (len(tiles) - 1)
W = max(top_w, bot_w) + 24
H = th + a.h + 24 + 8 + 34
canvas = Image.new("RGB", (W, H), (14, 14, 18))
d = ImageDraw.Draw(canvas)
d.text((12, 8), a.title or a.npz, fill=(235, 235, 240))
x = (W - top_w) // 2
for im in ins:
    canvas.paste(im, (x, 30)); x += im.width + 8
d.text((12, 30 + th + 4), "INPUT PHOTOS  ^     RECONSTRUCTION, NEW VIEWPOINTS  v", fill=(150, 150, 165))
x = (W - bot_w) // 2
for t in tiles:
    canvas.paste(Image.fromarray(t), (x, 30 + th + 22)); x += a.w + 8
canvas.save(a.out_png)
print("wrote", a.out_png, canvas.size)
