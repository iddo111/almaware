# -*- coding: utf-8 -*-
"""TZELEM paints the six cube faces, then they become ONE 360 plate for VR glasses.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

THE FIVE DECISIONS IN THIS FILE, each one stated with what it costs.

1. THE HARD COMPOSITOR PATH, canvas.render(soft=False) in all but name.
   Settled 2026-09-06 in sharpen/README-FINDINGS.md: the blur was never the brush,
   it was pass 2 of the soft path averaging every stroke that covers a pixel, so
   MORE paint made the picture BLURRIER (340k strokes 9.1 lapvar, 40k 79.2). The
   hard path -- pure nearest-wins ownership, one stroke owns one pixel -- took the
   workshop 124 -> 465 lit at 100% coverage and 3x faster. This file calls
   `canvas.ownership` and `Palette.lookup` directly rather than `render(soft=False)`
   only so the ownership map is available for the COVERAGE number; the two are the
   same three lines of canvas.py.

2. ONE STROKE SET FOR ALL SIX FACES, and every stroke's SHAPE frozen in the world.
   This is what kills the seam. A stroke is planted once, in the world, from
   whichever face saw it, and every face that can see it draws it. But
   `canvas.footprint(style="painterly")` draws its elongation and its angle jitter
   from `default_rng(seed)` indexed by POSITION IN THE ARRAY -- so the same stroke
   in two different per-face subsets would get two different shapes, and the cube
   edges would crawl. So the shape is baked in the world instead: a per-stroke
   `elong`, and an angle jitter applied as a ROTATION OF THE TANGENT ABOUT THE
   SURFACE NORMAL. Both are pure functions of the stroke, so `style="round"` plus
   those two arrays reproduces the painterly look and is subset-invariant. It is
   also more correct: a world rotation turns with the wall, a screen-space jitter
   does not.

3. THE BRUSH IS SCALED TO THE FACE RESOLUTION, per stroke, through its DEPTH.
   `canvas._pixel_radius` is `radius_world * focal / depth`, and focal is N/2 for a
   90-degree face. A single world radius therefore paints a 41-pixel blob at 0.5 m
   and a sub-pixel speck at 100 m -- and this scene runs 0.56 m to 108 m. So each
   stroke gets `radius_world = TARGET_PX * depth / focal`: every mark is the same
   size ON THE CANVAS, which is what a painter does and what
   README-FINDINGS calls for ("to be sharp at 4K the room needs more anchors, not a
   smaller brush"). The strokes stay world-anchored -- only their world size is
   chosen per stroke, from the one origin this plate is made at.

4. THE SKY IS PAINTED, not left as background.
   Godot's depth pass marks sky as a miss, so no stroke would be planted there and
   the +Y face would come back 75% flat background -- which the coverage gate would
   then fail for a reason that has nothing to do with holes. But the BEAUTY pass
   holds the real rendered sky colour at those pixels. So sky pixels get strokes on
   a dome at SKY_DIST metres, carrying that colour. From a plate made at ONE fixed
   point this is exact: the sky is at infinity and a dome reproduces precisely what
   this eye receives. Nearest-wins means a sky stroke can never occlude geometry.
   Coverage is reported BOTH ways -- with the dome and on surface pixels only.

5. MONO. No omni-directional stereo exists anywhere in TZELEM or the Godot scripts,
   and a whole-camera IPD offset would give correct depth ahead and INVERTED depth
   behind. That is painful in a headset, so it is not done.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "sharpen"))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import canvas                                    # noqa: E402
import cube360 as C                              # noqa: E402
import gbuffer                                   # noqa: E402
from anatomy import Strokes                      # noqa: E402
from palette import Palette                      # noqa: E402

BACKGROUND = canvas.BACKGROUND
SKY_DIST = 250.0          # metres; the dome the sky's own rendered colour sits on
ELONG_MIN, ELONG_MAX = canvas.ELONG_MIN, canvas.ELONG_MAX
JITTER_DEG = canvas.JITTER_DEG
FRUSTUM_MARGIN = 1.08     # |gx|,|gy| kept per face. A stroke is TARGET_PX wide and
                          # at most 4x that long, so a centre beyond ~1.01 cannot
                          # touch the face at all; 1.08 is slack, not approximation.


def _unit(v, fallback):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    bad = n[..., 0] < 1e-9
    out = np.divide(v, np.where(n > 1e-9, n, 1.0))
    out[bad] = fallback
    return out


def plant_face(g, cam, frac: float, target_px: float, seed: int, sky: bool = True):
    """Plant world-anchored strokes on everything ONE face can see, sky included."""
    n = cam.width
    focal = 0.5 * cam.height / np.tan(np.radians(cam.fov_deg) * 0.5)
    rays = cam.rays()
    mask = g["mask"]
    rng = np.random.default_rng(seed)

    take = rng.random(mask.shape) < frac
    surf = np.nonzero(take & mask)
    pts, nrm, rgb, dep, ray = [], [], [], [], []
    if surf[0].size:
        ys, xs = surf
        pts.append(g["point"][ys, xs])
        nrm.append(_unit(g["normal"][ys, xs], np.array([0.0, 1.0, 0.0])))
        rgb.append(g["albedo"][ys, xs])
        dep.append(g["depth"][ys, xs])
        ray.append(rays[ys, xs])
    if sky:
        sk = np.nonzero(take & ~mask)
        if sk[0].size:
            ys, xs = sk
            d = rays[ys, xs]
            pts.append(cam.eye + d * SKY_DIST)
            nrm.append(-d)                     # the dome faces the eye
            rgb.append(g["albedo"][ys, xs])    # the BEAUTY pass: the real sky colour
            dep.append(np.full(ys.size, SKY_DIST))
            ray.append(d)
    if not pts:
        raise ValueError("this face planted nothing at all")

    point = np.concatenate(pts).astype(np.float64)
    normal = np.concatenate(nrm).astype(np.float64)
    colour = np.concatenate(rgb).astype(np.float64)
    depth = np.concatenate(dep).astype(np.float64)
    view = np.concatenate(ray).astype(np.float64)

    # THE BRUSH, scaled per stroke so every mark is TARGET_PX wide on this canvas.
    radius = target_px * depth / focal

    # THE TANGENT, in the world. cross(normal, view) is the direction canvas.py
    # would have chosen by default; taking it here lets the jitter be baked in as a
    # world rotation about the normal, which is subset-invariant AND turns with the
    # wall. Two fallbacks for the degenerate cases (a surface seen exactly edge-on,
    # and the sky dome, whose normal IS -view).
    tan = np.cross(normal, view)
    bad = np.linalg.norm(tan, axis=1) < 1e-6
    if bad.any():
        alt = np.cross(normal[bad], np.array([0.0, 1.0, 0.0]))
        worse = np.linalg.norm(alt, axis=1) < 1e-6
        if worse.any():
            alt[worse] = np.cross(normal[bad][worse], np.array([1.0, 0.0, 0.0]))
        tan[bad] = alt
    tan = _unit(tan, np.array([1.0, 0.0, 0.0]))
    return {"point": point, "normal": normal, "rgb": colour, "radius": radius,
            "tangent": tan, "depth": depth, "is_sky": depth >= SKY_DIST - 1e-6}


def bake_shape(parts: dict, seed: int) -> dict:
    """Elongation and angle jitter, ONCE, over the whole set. See decision 2."""
    n = parts["point"].shape[0]
    rng = np.random.default_rng(seed)
    elong = rng.uniform(ELONG_MIN, ELONG_MAX, n)
    ang = np.radians(rng.uniform(-JITTER_DEG, JITTER_DEG, n))
    t, nn = parts["tangent"], parts["normal"]
    c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
    rot = t * c + np.cross(nn, t) * s          # Rodrigues, with n.t == 0
    parts["tangent"] = _unit(rot, np.array([1.0, 0.0, 0.0]))
    parts["elong"] = elong
    return parts


def subset_for(parts: dict, cam, margin: float = FRUSTUM_MARGIN):
    """Only the strokes whose splat can land on THIS face. Exact, not approximate."""
    f, r, u = cam.basis()
    v = parts["point"] - cam.eye
    t = v @ f
    ok = t > 1e-9
    gx = np.full(t.shape, np.inf)
    gy = np.full(t.shape, np.inf)
    np.divide(v @ r, t, out=gx, where=ok)
    np.divide(v @ u, t, out=gy, where=ok)
    sel = ok & (np.abs(gx) <= margin) & (np.abs(gy) <= margin)
    idx = np.nonzero(sel)[0]
    s = Strokes(point=parts["point"][idx], normal=parts["normal"][idx],
                rgb=parts["rgb"][idx], radius=parts["radius"][idx],
                tangent=parts["tangent"][idx], elong=parts["elong"][idx],
                asked=int(idx.size))
    return s, idx


def paint_face(parts: dict, cam):
    """THE HARD PATH. Returns (image, coverage_map). No blending, no sort."""
    s, _ = subset_for(parts, cam)
    owner, _z, _fp = canvas.ownership(cam, s, style="round", need_owner=True)
    img = Palette.of(s).lookup(owner, BACKGROUND)
    return img, (owner >= 0), len(s)


# ------------------------------------------------------------------- driver

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--faces", required=True, help="folder of face_*.tzg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="plate")
    ap.add_argument("--frac", type=float, default=0.50,
                    help="fraction of each face's pixels that gets an anchor")
    ap.add_argument("--target-px", type=float, default=1.4,
                    help="half-width of every stroke ON THE CANVAS, in pixels")
    ap.add_argument("--equi-width", type=int, default=8192)
    ap.add_argument("--seed", type=int, default=1933)
    ap.add_argument("--look", default=None,
                    help="x,y,z world point the plate's centre column aims at")
    ap.add_argument("--cut-fov", type=float, default=90.0)
    ap.add_argument("--raw", action="store_true",
                    help="also stitch the unpainted Godot buffers, for comparison")
    a = ap.parse_args()

    t_all = time.time()
    os.makedirs(a.out, exist_ok=True)
    # MEMORY. Six 2048x2048 G-buffers held at once is depth+point+normal+albedo+mask
    # = ~337 MB each, 2.0 GB, and the stroke set is another 1.5 GB on top. So each
    # face is loaded, planted from, and thrown away, keeping only its camera and its
    # surface mask (4 MB) -- the mask is needed later to report coverage over the
    # pixels that HAVE a surface, separately from the sky dome.
    cams, masks = {}, {}
    for name in C.FACE_ORDER:
        _g, _cam = gbuffer.load(os.path.join(a.faces, f"face_{name}"))
        cams[name] = _cam
        masks[name] = _g["mask"]
    eyes = np.array([cams[m].eye for m in C.FACE_ORDER])
    if not np.allclose(eyes, eyes[0], atol=1e-9):
        raise ValueError("the six faces do not share one eye -- they tile nothing")
    for name in C.FACE_ORDER:
        c = cams[name]
        if abs(c.fov_deg - 90.0) > 1e-9:
            raise ValueError(f"face {name} is {c.fov_deg} deg, not exactly 90.0")
        if c.width != c.height:
            raise ValueError(f"face {name} is {c.width}x{c.height}, not square")
    faces = {m: {"cam": cams[m]} for m in C.FACE_ORDER}
    basis = C.face_basis(faces)
    n = cams["px"].width
    eye = cams["px"].eye
    print(f"[paint] six faces {n}x{n} at 90.0 deg, eye={eye}", flush=True)

    yaw0 = 0.0
    look_dir = None
    if a.look:
        p = np.array([float(v) for v in a.look.split(",")])
        look_dir = p - eye
        yaw0 = C.yaw_of(look_dir)
        print(f"[paint] centre column aimed at {p} -> yaw0 = "
              f"{np.degrees(yaw0):.3f} deg", flush=True)

    # ---- plant ---------------------------------------------------------
    t0 = time.time()
    chunks = []
    per_face = {}
    for i, name in enumerate(C.FACE_ORDER):
        g, _c = gbuffer.load(os.path.join(a.faces, f"face_{name}"))
        pf = plant_face(g, cams[name], a.frac, a.target_px, a.seed + 101 * i)
        del g
        per_face[name] = pf["point"].shape[0]
        chunks.append(pf)
        print(f"[plant] {name}: {pf['point'].shape[0]:,} strokes "
              f"({int(pf['is_sky'].sum()):,} of them sky)", flush=True)
    parts = {k: np.concatenate([c[k] for c in chunks]) for k in
             ("point", "normal", "rgb", "radius", "tangent", "depth", "is_sky")}
    del chunks
    parts = bake_shape(parts, a.seed)
    # float32 halves 1.5 GB of stroke arrays. It cannot move a stroke by a pixel:
    # a float32 metre holds ~1e-7 m of precision over this 200 m scene, and the
    # projection promotes to float64 the moment it subtracts the eye.
    for k in ("point", "normal", "rgb", "radius", "tangent", "elong"):
        parts[k] = parts[k].astype(np.float32)
    total = parts["point"].shape[0]
    print(f"[plant] {total:,} strokes in {time.time()-t0:.1f}s "
          f"({total/(6*n*n):.3f} anchors per face pixel)", flush=True)

    # ---- paint ---------------------------------------------------------
    imgs, cov = {}, {}
    surf_cov = {}
    for name in C.FACE_ORDER:
        t0 = time.time()
        cam = cams[name]
        img, hit, used = paint_face(parts, cam)
        imgs[name] = img
        m = masks[name]
        cov[name] = float(hit.mean())
        surf_cov[name] = float(hit[m].mean()) if m.any() else float("nan")
        print(f"[paint] {name}: {used:,} strokes in frustum, coverage "
              f"{cov[name]*100:.3f}% (surface-only {surf_cov[name]*100:.3f}%), "
              f"{time.time()-t0:.1f}s", flush=True)
        C.save_png(os.path.join(a.out, f"face_{name}.png"), img)

    cov_min = min(cov.values())

    # ---- stitch --------------------------------------------------------
    t0 = time.time()
    w = a.equi_width
    h = w // 2
    equi, seam = C.to_equirect(imgs, basis, w, h, yaw0=yaw0, chunk=64)
    print(f"[stitch] {w}x{h} in {time.time()-t0:.1f}s", flush=True)
    plate = os.path.join(a.out, f"{a.name}-equirect-{w}x{h}.png")
    C.save_png(plate, equi)
    C.save_jpg(os.path.join(a.out, f"{a.name}-equirect-{w}x{h}.jpg"), equi, 95)

    sides = [seam[f][s] for f in C.FACE_ORDER
             for s in ("top", "bottom", "left", "right")]
    base = [seam[f]["interior_baseline"] for f in C.FACE_ORDER]
    print(f"[seam] painted plate: mean |diff| {np.mean(sides):.5f}  "
          f"max {np.max(sides):.5f}  interior adjacent-pixel baseline "
          f"{np.mean(base):.5f}  ratio {np.mean(sides)/np.mean(base):.2f}x",
          flush=True)

    # ---- the cut view, and the ruler -----------------------------------
    import sharpness
    if look_dir is None:
        look_dir = np.array([1.0, 0.0, 0.0])
    cut_n = w // 4
    view = C.cut_view(equi, look_dir, a.cut_fov, cut_n, yaw0=yaw0)
    cut = os.path.join(a.out, f"{a.name}-view-{a.cut_fov:.0f}deg-{cut_n}px.png")
    C.save_png(cut, view)
    lap = sharpness.lapvar_array(view)
    lap_equi = sharpness.lapvar_array(equi)
    print(f"[ruler] lapvar on the CUT RECTILINEAR VIEW ({a.cut_fov:.0f} deg, "
          f"{cut_n}x{cut_n}) = {lap:.1f}   [on the equirect itself, which is NOT "
          f"the number to use: {lap_equi:.1f}]", flush=True)

    ppd = w / 360.0
    report = {
        "name": a.name, "eye": [float(v) for v in eye],
        "face_px": int(n), "faces": list(C.FACE_ORDER),
        "fov_per_face_deg": 90.0,
        "equirect": [int(w), int(h)], "ppd_equator": float(ppd),
        "yaw0_deg": float(np.degrees(yaw0)),
        "strokes_total": int(total), "strokes_per_face": per_face,
        "anchors_per_face_pixel": float(total / (6 * n * n)),
        "target_px": a.target_px, "frac": a.frac, "seed": a.seed,
        "compositor": "HARD (canvas.ownership + Palette.lookup; soft=False)",
        "coverage": cov, "coverage_min": cov_min,
        "coverage_surface_only": surf_cov,
        "seam": seam,
        "seam_mean_abs_diff": float(np.mean(sides)),
        "seam_max_abs_diff": float(np.max(sides)),
        "seam_interior_baseline": float(np.mean(base)),
        "lapvar_cut_view": float(lap), "lapvar_equirect_do_not_use": float(lap_equi),
        "cut_fov_deg": a.cut_fov, "cut_px": int(cut_n),
        "stereo": "MONO -- no ODS anywhere in TZELEM; a fixed IPD offset would "
                  "invert depth behind the viewer, so it was not done",
        "seconds": round(time.time() - t_all, 1),
    }
    with open(os.path.join(a.out, f"{a.name}-report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, indent=1)

    if a.raw:
        del imgs, parts
        raw = {}
        for m in C.FACE_ORDER:
            g, _c = gbuffer.load(os.path.join(a.faces, f"face_{m}"))
            raw[m] = g["albedo"].astype(np.float32)
            del g
        req, _s = C.to_equirect(raw, basis, w, h, yaw0=yaw0, chunk=64)
        C.save_jpg(os.path.join(a.out, f"{a.name}-RAW-godot-{w}x{h}.jpg"), req, 95)
        rv = C.cut_view(req, look_dir, a.cut_fov, cut_n, yaw0=yaw0)
        C.save_png(os.path.join(a.out, f"{a.name}-RAW-view.png"), rv)
        print(f"[raw] lapvar on the same cut of the UNPAINTED Godot plate: "
              f"{sharpness.lapvar_array(rv):.1f}", flush=True)

    print(f"[done] {time.time()-t_all:.1f}s  ->  {plate}", flush=True)
    print(f"[gate] coverage min {cov_min*100:.3f}%  "
          f"({'PASS' if cov_min >= 0.99 else 'REJECT'} at the 99% floor)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
