"""TZELEM / צלם — THE 8K STILL: a real subject, painted, not upscaled.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

The subject is not a demo scene. It is the two solids this lab actually made:

    KAV's first shape          — the cube ERAN's own modeller emitted (12 faces)
    the larynx fold mould      — the thing that will make ERAN's physical mouth
                                 (85,964 faces, vertex-clustered down to ~2,000)

plus a ground and one light. The point of the picture is the ZOOM CROP: at 8K a
stroke is ~90 pixels across and its edge is still a clean ellipse, because the
stroke was never a pixel — it was a size in the world.

Nothing here is a filter over a small render. The 8K frame is painted from the
strokes directly.

Numpy only. No torch on the PC.
"""
from __future__ import annotations

import os
import struct
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import canvas                                   # noqa: E402
from anatomy import scatter                     # noqa: E402
from meshstage import MeshStage                 # noqa: E402
from stage import Camera                        # noqa: E402

# PC courtesy (2026-09-03 scar: renders starved the KESHEV mic): run below normal priority.
try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass


KAV_STL = os.path.abspath(os.path.join(_HERE, "..", "kav", "KAV-first-shape.stl"))
LARYNX_STL = r"D:\CLAUDE\alma-larynx\silicone-fold-mold.stl"
OUT = os.path.join(_HERE, "out8k")


# ------------------------------------------------------------------ mesh work

def read_stl(path: str) -> np.ndarray:
    """Binary STL -> (F,3,3), read in one shot instead of one struct per face."""
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        raw = np.frombuffer(f.read(n * 50), dtype=np.uint8)
    if raw.size != n * 50:
        raise ValueError(f"{path}: truncated STL")
    rec = raw.reshape(n, 50)[:, :48].copy().view(np.float32).reshape(n, 4, 3)
    return rec[:, 1:, :].astype(np.float64)


def decimate(tris: np.ndarray, target: int = 2000,
             return_converged: bool = False):
    """Vertex clustering: quantise vertices to a grid, keep faces that survive.

    A random subsample of faces would leave a mesh full of holes, and TZELEM would
    faithfully paint the holes. Clustering keeps a closed-ish surface — coarse, but
    the SHAPE is still the mould's shape.
    """
    if len(tris) <= target:
        return (tris, True) if return_converged else tris
    pts = tris.reshape(-1, 3)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    grid = 8
    best = tris
    # TZ-15 (2026-09-06): the bisection can EXHAUST its 30 steps and return whatever
    # `best` last held, off target and silent, and night.py then paints it as if it
    # were the requested budget. The downward step also cannot go below 4
    # (`max(4, int(grid/1.25))` is a no-op at grid 4), so a mesh still too dense at
    # grid 4 spins 30 fruitless iterations. It converges on tonight's subject -- 1346,
    # 1630, 1662 against a target of 1500, all inside the [0.75x, 1.25x] band -- but
    # the feed is Iddo's own STL files and the next mould need not land there.
    converged = False
    for _ in range(30):                       # bisect the grid to hit the target
        q = np.floor((pts - lo) / span * grid).astype(np.int64)
        q = np.clip(q, 0, grid - 1)
        key = (q[:, 0] * grid + q[:, 1]) * grid + q[:, 2]
        uniq, inv = np.unique(key, return_inverse=True)
        centre = np.zeros((len(uniq), 3))
        np.add.at(centre, inv, pts)
        cnt = np.bincount(inv, minlength=len(uniq)).astype(np.float64)
        centre /= cnt[:, None]
        f = inv.reshape(-1, 3)
        keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
        out = centre[f[keep]]
        best = out
        if len(out) > target * 1.25:
            nxt = max(4, int(grid / 1.25))
            if nxt == grid:                  # the floor: coarser is not available
                break
            grid = nxt
        elif len(out) < target * 0.75:
            grid = int(grid * 1.25) + 1
        else:
            converged = True
            break
    if not converged:
        print(f"hero8k.decimate: did NOT hit the budget — {len(best)} faces against a "
              f"target of {target} (grid stopped at {grid})", flush=True)
    return (best, converged) if return_converged else best


def _fit(tris: np.ndarray, height: float, centre_xz=(0.0, 0.0),
         rot_y: float = 0.0) -> np.ndarray:
    """Scale a mesh to a given world height, stand it on y=0, place it."""
    t = tris.copy()
    lo, hi = t.reshape(-1, 3).min(axis=0), t.reshape(-1, 3).max(axis=0)
    s = height / max(hi[1] - lo[1], 1e-9)
    t = (t - (lo + hi) * 0.5) * s
    c, sn = np.cos(rot_y), np.sin(rot_y)
    x, y, z = t[..., 0], t[..., 1], t[..., 2]
    t = np.stack([x * c + z * sn, y, -x * sn + z * c], axis=-1)
    t[..., 1] -= t[..., 1].min()
    t[..., 0] += centre_xz[0]
    t[..., 2] += centre_xz[1]
    return t


def ground(size: float = 9.0) -> np.ndarray:
    """Two triangles. A floor for the solids to stand on and cast the eye along."""
    s = size
    a = np.array([[-s, 0.0, -s], [s, 0.0, -s], [s, 0.0, s]])
    b = np.array([[-s, 0.0, -s], [s, 0.0, s], [-s, 0.0, s]])
    return np.stack([a, b])


def subject(target_faces: int = 2000):
    """KAV's cube + the larynx mould + a ground, as one triangle soup."""
    cube = _fit(read_stl(KAV_STL), 1.30, centre_xz=(-1.25, 0.15), rot_y=0.38)
    mould = decimate(read_stl(LARYNX_STL), target_faces)
    mould = _fit(mould, 1.75, centre_xz=(0.95, -0.25), rot_y=-0.55)
    gnd = ground()
    tris = np.concatenate([gnd, cube, mould])
    alb = np.concatenate([
        np.tile([0.60, 0.58, 0.53], (len(gnd), 1)),        # ground
        np.tile([0.84, 0.36, 0.26], (len(cube), 1)),       # KAV's cube: terracotta
        np.tile([0.36, 0.50, 0.74], (len(mould), 1)),      # the mould: slate blue
    ])
    return tris, alb, {"ground": len(gnd), "cube": len(cube), "mould": len(mould)}


# --------------------------------------------------------------------- camera

def hero_camera(width: int, height: int) -> Camera:
    """One fixed camera — a Sierra quest's camera. Same view at every resolution."""
    return Camera(eye=np.array([2.05, 1.65, 4.35]),
                  target=np.array([-0.10, 0.72, 0.0]),
                  width=width, height=height, fov_deg=42.0)


# ----------------------------------------------------------------------- main

def save(img: np.ndarray, path: str, quality: int = 94) -> str:
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    if path.lower().endswith((".jpg", ".jpeg")):
        im.save(path, quality=quality, subsampling=0)
    else:
        im.save(path)
    return path


def main(n_strokes: int = 2400, plant_w: int = 640, plant_h: int = 360,
         size: float = 0.020, seed: int = 7, faces: int = 2000,
         do_8k: bool = True) -> dict:
    tris, alb, counts = subject(faces)
    print(f"  subject: {len(tris)} triangles  {counts}")
    stage = MeshStage(tris, albedo=(0.60, 0.58, 0.53), face_albedo=alb,
                      light_dir=(-0.45, -1.0, -0.30), ambient=0.30)

    t0 = time.time()
    cam_plant = hero_camera(plant_w, plant_h)
    strokes = scatter(stage, cam_plant, n=n_strokes, seed=seed, size=size)
    print(f"  planted {len(strokes)} strokes from a {plant_w}x{plant_h} view "
          f"in {time.time() - t0:.1f}s")

    made = {}
    for name, w, h in ([("4K", 3840, 2160)] +
                       ([("8K", 7680, 4320)] if do_8k else [])):
        cam = hero_camera(w, h)
        t0 = time.time()
        img = canvas.render(stage, cam, strokes, style="painterly", seed=17)
        dt = time.time() - t0
        p = save(img, os.path.join(OUT, f"TZELEM-gate2-{name}.png"))
        print(f"  {name} painted in {dt:.1f}s -> {p} "
              f"({os.path.getsize(p) / 1e6:.1f} MB)")
        made[name] = {"path": p, "seconds": dt,
                      "mb": os.path.getsize(p) / 1e6, "img": img}

    big = made.get("8K", made["4K"])["img"]
    H, W = big.shape[:2]
    # the proof crop: 1000x1000 straight out of the big frame, no resampling at all
    cy, cx = int(H * 0.47), int(W * 0.42)
    crop = big[cy - 500:cy + 500, cx - 500:cx + 500]
    made["crop"] = {"path": save(crop, os.path.join(
        OUT, "TZELEM-gate2-8K-crop1000.png"))}

    prev = made["4K"]["img"]
    k = prev.shape[1] // 1920
    small = prev[:prev.shape[0] // k * k, :prev.shape[1] // k * k]
    small = small.reshape(small.shape[0] // k, k, small.shape[1] // k, k, 3
                          ).mean(axis=(1, 3))
    made["preview"] = {"path": save(small, os.path.join(
        OUT, "TZELEM-gate2-8K-preview.jpg"))}
    for k2 in ("4K", "8K"):
        made.get(k2, {}).pop("img", None)
    print(f"  crop    -> {made['crop']['path']}")
    print(f"  preview -> {made['preview']['path']}")
    return {"counts": counts, "strokes": int(len(strokes)), "made":
            {k: {kk: vv for kk, vv in v.items() if kk != 'img'}
             for k, v in made.items()}}


if __name__ == "__main__":
    import json
    r = main(do_8k="--no8k" not in sys.argv)
    with open(os.path.join(OUT, "hero.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(json.dumps(r["counts"], indent=1))
