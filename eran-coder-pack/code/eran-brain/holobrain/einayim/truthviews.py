"""EINAYIM / עֵינַיִם — THE GROUND-TRUTH VIEWS.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-03: "yesterday with the Quest I scanned the room and it modelled
everything in 3D. Let's make something that with 2 cameras or more can model
EVERYTHING easily."

Before we point a photo model at a real object we point it at a world we OWN, so
the ruler cannot lie. TZELEM's stage already renders a scene with exact depth and
exact camera. This file turns that into what a photogrammetry model expects —
plain RGB images plus a pinhole K and a world->camera [R|t] — and keeps the truth
next to it on disk.

TWO HONEST ADMISSIONS, up front:

1. The stage is Lambert-flat by design ("a rich scene would hide a weak organ").
   A flat box has NO features, and a feed-forward multi-view model has nothing to
   latch onto — we would be measuring the absence of texture, not the model. So
   this file adds a PROCEDURAL triplanar texture (value-noise fbm + checker) on
   top of the stage's own albedo. That is allowed and it is stated here: it is
   still our geometry, our light, our camera. Only the paint is new.

2. We do NOT modify anything under tzelem/. stage.py and meshstage.py are imported
   read-only and subclassed. Another agent is editing that folder tonight.

Numpy + Pillow only. No torch on the PC (D:\\CLAUDE\\CLAUDE.md).
"""
from __future__ import annotations

import json
import os
import struct
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_TZELEM = os.path.join(os.path.dirname(_HERE), "tzelem")
for _p in (_TZELEM, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from stage import Camera, Stage, default_boxes      # noqa: E402
from meshstage import MeshStage, frame              # noqa: E402

# PC courtesy (2026-09-03 scar: renders starved the KESHEV mic): run below normal priority.
try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass



# ------------------------------------------------------------- procedural paint

def _hash01(ix, iy, iz):
    """A cheap deterministic hash in 0..1. Not cryptography — repeatable noise."""
    h = np.sin(ix * 127.1 + iy * 311.7 + iz * 74.7) * 43758.5453
    return h - np.floor(h)


def _vnoise(p, freq):
    """Trilinearly interpolated value noise at one frequency. p is (...,3)."""
    q = p * freq
    i = np.floor(q)
    f = q - i
    w = f * f * (3.0 - 2.0 * f)
    out = np.zeros(p.shape[:-1])
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                h = _hash01(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz)
                wt = ((w[..., 0] if dx else 1.0 - w[..., 0])
                      * (w[..., 1] if dy else 1.0 - w[..., 1])
                      * (w[..., 2] if dz else 1.0 - w[..., 2]))
                out = out + h * wt
    return out


def paint(base: np.ndarray, p: np.ndarray, scale: float) -> np.ndarray:
    """Give a surface something a photo model can actually see.

    `scale` maps world units onto texture units so a 40 mm mold and a 5 m room get
    the same amount of detail per pixel. Frequencies below are in texture units.
    """
    q = p * scale
    fbm = 0.55 * _vnoise(q, 2.2) + 0.30 * _vnoise(q, 7.0) + 0.15 * _vnoise(q, 19.0)
    chk = (np.floor(q[..., 0] * 3.0) + np.floor(q[..., 1] * 3.0)
           + np.floor(q[..., 2] * 3.0)) % 2.0
    lum = 0.48 + 0.75 * fbm + 0.16 * chk
    tint = np.stack([_vnoise(q + 11.3, 4.5),
                     _vnoise(q + 27.9, 4.5),
                     _vnoise(q + 41.1, 4.5)], axis=-1)
    return np.clip(base * lum[..., None] * (0.70 + 0.62 * tint), 0.0, 1.0)


class TexturedStage(Stage):
    """The box world, repainted. Geometry, depth and camera are untouched."""

    def __init__(self, *a, tex_scale: float = 1.0, **kw):
        super().__init__(*a, **kw)
        self.tex_scale = float(tex_scale)

    def gbuffer(self, cam):
        g = super().gbuffer(cam)
        g["albedo"] = np.where(g["mask"][..., None],
                               paint(g["albedo"], g["point"], self.tex_scale),
                               g["albedo"])
        return g


class TexturedMeshStage(MeshStage):
    """The triangle world, repainted."""

    def __init__(self, *a, tex_scale: float = 1.0, **kw):
        super().__init__(*a, **kw)
        self.tex_scale = float(tex_scale)

    def gbuffer(self, cam):
        g = super().gbuffer(cam)
        g["albedo"] = np.where(g["mask"][..., None],
                               paint(g["albedo"], g["point"], self.tex_scale),
                               g["albedo"])
        return g


# ------------------------------------------------------------------- STL / mesh

def read_stl(path: str) -> np.ndarray:
    """Binary or ASCII STL -> (F,3,3) float64. No trimesh on the PC."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:5] == b"solid" and b"facet" in raw[:2048]:
        verts = []
        for line in raw.decode("utf-8", "replace").splitlines():
            s = line.strip().split()
            if s and s[0] == "vertex":
                verts.append([float(x) for x in s[1:4]])
        return np.asarray(verts, dtype=np.float64).reshape(-1, 3, 3)
    n = struct.unpack("<I", raw[80:84])[0]
    rec = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                             ("a", "<u2")]), count=n, offset=84)
    return rec["v"].astype(np.float64)


def decimate(tris: np.ndarray, target: int, seed: int = 0) -> np.ndarray:
    """Vertex-clustering decimation. Crude but honest: snap vertices to a grid,
    drop the triangles that collapse. Brute-force ray casting is O(rays*faces),
    so an 86k-face mold has to come down before it can be a stage."""
    if len(tris) <= target:
        return tris
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    span = float(np.linalg.norm(hi - lo))
    n = 8
    for _ in range(40):
        cell = span / n
        q = np.round((tris - lo) / cell)
        keep = ~((q[:, 0] == q[:, 1]).all(1) | (q[:, 1] == q[:, 2]).all(1)
                 | (q[:, 0] == q[:, 2]).all(1))
        snapped = lo + q * cell
        # one representative triangle per cluster triple
        key = np.ascontiguousarray(np.sort(q.reshape(len(q), 9), axis=1))
        _, first = np.unique(key, axis=0, return_index=True)
        sel = np.intersect1d(first, np.flatnonzero(keep))
        if len(sel) >= target:
            return snapped[sel][:target] if len(sel) > target * 1.4 else snapped[sel]
        n = int(n * 1.35) + 1
    return snapped[sel]


def ground_quad(centre, half, y=0.0):
    a = np.array([centre[0] - half, y, centre[2] - half])
    b = np.array([centre[0] + half, y, centre[2] - half])
    c = np.array([centre[0] + half, y, centre[2] + half])
    d = np.array([centre[0] - half, y, centre[2] + half])
    return np.array([[a, b, c], [a, c, d]])


# ------------------------------------------------------------------ the camera

def intrinsics(cam: Camera):
    """Pinhole K for a tzelem Camera, in OpenCV pixel convention (x right, y down).

    stage.Camera builds rays as f + gx*tan(fov/2)*aspect*r + gy*tan(fov/2)*u with
    gx,gy in [-1,1]. Substituting into its own project() gives fx = fy = H/(2 tan).
    Square pixels, principal point at the exact image centre. Derived, not guessed.
    """
    half = np.tan(np.radians(cam.fov_deg) * 0.5)
    f = cam.height / (2.0 * half)
    return np.array([[f, 0.0, cam.width / 2.0 - 0.5],
                     [0.0, f, cam.height / 2.0 - 0.5],
                     [0.0, 0.0, 1.0]])


def extrinsics(cam: Camera):
    """World -> camera [R|t], OpenCV convention: x right, y DOWN, z forward."""
    fwd, right, up = cam.basis()
    R = np.stack([right, -up, fwd], axis=0)
    t = -R @ cam.eye
    return R, t


def ring(centre, radius, height, n, span_deg=140.0, start_deg=-70.0,
         width=640, height_px=480, fov=50.0):
    """N cameras on an arc around the subject — a phone walked around an object."""
    cams = []
    for k in range(n):
        a = np.radians(start_deg + (span_deg * k / max(n - 1, 1)))
        eye = np.asarray(centre, float) + np.array(
            [np.sin(a) * radius, height, np.cos(a) * radius])
        cams.append(Camera(eye=eye, target=np.asarray(centre, float),
                           width=width, height=height_px, fov_deg=fov))
    return cams


# ------------------------------------------------------------------- rendering

def write_png(path, img):
    from PIL import Image
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)


def render_set(stage, cams, out_dir, name):
    """RGB + exact depth + exact camera for every view. This is the ruler."""
    os.makedirs(out_dir, exist_ok=True)
    meta = {"scene": name, "views": []}
    for k, cam in enumerate(cams):
        g = stage.gbuffer(cam)
        rgb = stage.shade(g)
        write_png(os.path.join(out_dir, f"view_{k:02d}.png"), rgb)

        fwd, _, _ = cam.basis()
        # depth_ray = distance from the eye (what stage.py stores);
        # depth_z   = distance along the optical axis (what photo models predict)
        d_ray = np.where(g["mask"], g["depth"], 0.0)
        d_z = np.where(g["mask"], (g["point"] - cam.eye) @ fwd, 0.0)
        np.save(os.path.join(out_dir, f"depth_{k:02d}.npy"), d_z.astype(np.float32))
        np.save(os.path.join(out_dir, f"depthray_{k:02d}.npy"), d_ray.astype(np.float32))
        np.save(os.path.join(out_dir, f"point_{k:02d}.npy"),
                np.where(g["mask"][..., None], g["point"], 0.0).astype(np.float32))
        np.save(os.path.join(out_dir, f"mask_{k:02d}.npy"), g["mask"])

        K = intrinsics(cam)
        R, t = extrinsics(cam)
        meta["views"].append({
            "file": f"view_{k:02d}.png",
            "K": K.tolist(), "R": R.tolist(), "t": t.tolist(),
            "eye": cam.eye.tolist(), "target": cam.target.tolist(),
            "up": cam.up.tolist(), "fov_deg": cam.fov_deg,
            "width": cam.width, "height": cam.height,
            "depth_min": float(d_z[g["mask"]].min()) if g["mask"].any() else 0.0,
            "depth_max": float(d_z[g["mask"]].max()) if g["mask"].any() else 0.0,
            "hit_frac": float(g["mask"].mean()),
        })
        print(f"  {name} view {k}: hit {g['mask'].mean()*100:5.1f}%  "
              f"z {d_z[g['mask']].min():.3f}..{d_z[g['mask']].max():.3f}")
    with open(os.path.join(out_dir, "cams.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return meta


# ------------------------------------------------------------------- the scenes

def scene_room(width=640, height=480, n=8):
    """The box world of stage.py, textured. Room scale, metres."""
    st = TexturedStage(default_boxes(), tex_scale=0.85)
    cams = ring(centre=(0.0, 0.75, 0.0), radius=5.2, height=2.35, n=n,
                span_deg=150.0, start_deg=-75.0, width=width, height_px=height)
    return st, cams


def scene_organs(width=640, height=480, n=8):
    """KAV's own first solid next to the larynx mold, on a textured floor.

    Two organs of ERAN's that have never been in the same picture: the shape KAV
    said, and the mold ALMA-LARYNX printed. Both are real files on this disk.
    """
    kav = read_stl(os.path.join(os.path.dirname(_HERE), "kav", "KAV-first-shape.stl"))
    mold = read_stl(r"D:\CLAUDE\alma-larynx\silicone-fold-mold.stl")
    mold = decimate(mold, 1400)

    def fit(t, size, at):
        lo, hi = t.reshape(-1, 3).min(0), t.reshape(-1, 3).max(0)
        s = size / max(float((hi - lo).max()), 1e-9)
        t = (t - (lo + hi) * 0.5) * s
        t[..., 1] -= t[..., 1].min()
        return t + np.asarray(at, float)

    kav = fit(kav, 0.60, (-0.45, 0.0, 0.0))
    mold = fit(mold, 0.75, (0.50, 0.0, 0.0))
    gnd = ground_quad((0.0, 0.0, 0.0), 2.2)

    tris = np.concatenate([kav, mold, gnd], axis=0)
    fa = np.concatenate([
        np.tile([0.86, 0.40, 0.28], (len(kav), 1)),
        np.tile([0.34, 0.55, 0.82], (len(mold), 1)),
        np.tile([0.66, 0.64, 0.58], (len(gnd), 1)),
    ], axis=0)
    st = TexturedMeshStage(tris, face_albedo=fa, albedo=(0.66, 0.64, 0.58),
                           tex_scale=1.9)
    cams = ring(centre=(0.0, 0.30, 0.0), radius=2.15, height=0.95, n=n,
                span_deg=150.0, start_deg=-75.0, width=width, height_px=height)
    print(f"  organs scene: {len(tris)} triangles "
          f"(kav {len(kav)}, mold {len(mold)}, ground {len(gnd)})")
    return st, cams


if __name__ == "__main__":
    W = int(sys.argv[1]) if len(sys.argv) > 1 else 640
    H = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    N = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    root = os.path.join(_HERE, "truth")
    for name, maker in (("room", scene_room), ("organs", scene_organs)):
        print(f"[{name}]")
        st, cams = maker(W, H, N)
        render_set(st, cams, os.path.join(root, name), name)
    print("truth written to", root)
