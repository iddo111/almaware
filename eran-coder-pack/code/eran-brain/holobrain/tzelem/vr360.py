# -*- coding: utf-8 -*-
"""TZELEM 360 -- six cube faces in, one equirectangular VR plate out.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-06: "לא להדפסה למשקפי VR" -- NOT for print, FOR VR GLASSES. That one
correction changes the ruler. Print cares about DPI; VR cares about PIXELS PER DEGREE,
and for an equirectangular plate PPD at the equator is exactly WIDTH / 360. Above the
headset's own PPD more pixels buy NOTHING, so the width is chosen against the
headset, not against a printer.

WHAT THIS FILE DOES, in order:
  1. loads the six .tzg faces written by alma-vr/godot/scripts/tzelem_cube360.gd
  2. plants world-anchored strokes on ALL SIX at once -- see THE SEAM, below
  3. paints each face with canvas.ownership + Palette.lookup, which IS
     canvas.render(soft=False), the HARD compositor path (proved, not asserted:
     `--prove-hard` compares the two outputs pixel for pixel)
  4. resamples the six into one equirect with bilinear spherical sampling
  5. MEASURES: per-face coverage, the 12 cube-edge seams, PPD, and lapvar via
     D:/CLAUDE/sharpen/sharpness.py on a RECTILINEAR CUT, never on the equirect

THE SEAM, and why this design kills it instead of hiding it.
An equirect built from six independently-painted faces has twelve edges where two
different paintings meet, and any disagreement reads as a line down the panorama.
The usual fixes -- feathering, overlap, blending -- all smear the picture to hide the
problem. TZELEM does not need them, because its strokes are anchored in the WORLD and
all six faces share one eye. So: every face's strokes are pooled into ONE array, in
one order, and EVERY face is painted from ALL of them. A stroke that straddles a cube
edge is then the same stroke, with the same world anchor, the same colour and the same
shape, projected by two cameras that agree on that edge by construction.

That last clause is the load-bearing one, and it is why the stroke array must never be
culled per face: canvas.footprint draws its elongation and angle jitter from
`np.random.default_rng(seed)` in stroke order, so a subset would give the SAME world
stroke a DIFFERENT shape on the neighbouring face -- and re-open the seam that pooling
just closed. Speed is not worth that; the loop is left to skip off-canvas strokes.

THE SKY IS PAINTED TOO. `anatomy.scatter` plants only on `mask` (surfaces), which is
right for a room and wrong for a street: outdoors the sky is a third of the sphere and
would come back as canvas.BACKGROUND, one flat colour, which is exactly the "holes
showing background" failure the workshop run was rejected for. So misses are planted
at a far anchor along their own ray, carrying the colour the BEAUTY pass actually
recorded there. `gbuffer.LoadedStage.shade` throws that colour away (it substitutes a
constant for every miss), so this planter reads `g["albedo"]` directly.

MONO, said plainly. Real panoramic stereo needs omni-directional stereo -- a different
eye position per output COLUMN, around a circle of radius IPD/2. Nothing in TZELEM or
in the Godot scripts can do that: every camera in both is a single pinhole. Offsetting
the whole camera instead would give correct depth ahead and INVERTED depth behind,
which hurts in a headset. So this plate has no depth, and says so.

Numpy only. No torch on the PC.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_SHARPEN = r"D:\CLAUDE\sharpen"
if _SHARPEN not in sys.path:
    sys.path.insert(0, _SHARPEN)

import canvas                                    # noqa: E402
import gbuffer                                   # noqa: E402
from anatomy import Strokes                      # noqa: E402
from palette import Palette                      # noqa: E402
from sharpness import lapvar_array               # noqa: E402  THE ONE RULER
from stage import Camera                         # noqa: E402

FACE_ORDER = ["px", "nx", "py", "ny", "pz", "nz"]
SKY_R = 300.0          # world metres. Any far anchor does; the PIXEL radius of a
                       # stroke is size*focal and does not depend on it.


# --------------------------------------------------------------------- loading

def load_faces(folder: str):
    """The six faces, in a fixed order, with every cubemap precondition CHECKED.

    A 360 plate is only a 360 plate if the six views really do tile the sphere. Three
    things make that true and each is verified here rather than assumed: one eye, a
    square face, exactly 90.0 degrees. The check is cheap and the failure is silent.
    """
    faces = []
    for name in FACE_ORDER:
        stem = os.path.join(folder, "face_" + name)
        if not os.path.exists(stem + ".tzg"):
            raise FileNotFoundError(stem + ".tzg")
        g, cam = gbuffer.load(stem)
        meta = json.load(open(stem + ".json", encoding="utf-8"))
        faces.append({"name": name, "g": g, "cam": cam, "meta": meta})

    eye0 = faces[0]["cam"].eye
    for f in faces:
        c = f["cam"]
        if not np.array_equal(c.eye, eye0):
            raise ValueError(f"face {f['name']} has eye {c.eye}, face px has {eye0}. "
                             "Six views from six points do not tile a sphere.")
        if c.width != c.height:
            raise ValueError(f"face {f['name']} is {c.width}x{c.height}, not square. "
                             "Godot's fov is VERTICAL under KEEP_HEIGHT, so a "
                             "non-square face does not have a 90 degree horizontal "
                             "FOV and the faces do not meet.")
        if abs(c.fov_deg - 90.0) > 1e-9:
            raise ValueError(f"face {f['name']} fov is {c.fov_deg}, not exactly 90.0")
    return faces


def face_bases(faces):
    """(6,3) forward, right, up. The bases the pixels were actually rendered with."""
    F = np.stack([f["cam"].basis()[0] for f in faces])
    R = np.stack([f["cam"].basis()[1] for f in faces])
    U = np.stack([f["cam"].basis()[2] for f in faces])
    return F, R, U


# -------------------------------------------------------------------- planting

def plant(face, n: int, seed: int, size: float):
    """Strokes for ONE face -- surfaces AND sky, both anchored in the world.

    Returns the six arrays a `Strokes` is made of. The caller pools them.
    """
    g, cam = face["g"], face["cam"]
    h, w = cam.height, cam.width
    rays = cam.rays()
    mask = g["mask"]

    total = h * w
    if n >= total:
        pick = np.arange(total)
    else:
        rng = np.random.default_rng(seed)
        pick = rng.choice(total, size=n, replace=False)
    ys, xs = np.divmod(pick, w)

    hit = mask[ys, xs]
    depth = np.where(hit, g["depth"][ys, xs], SKY_R)
    d = rays[ys, xs]                                   # unit ray per picked pixel
    point = cam.eye + d * depth[:, None]
    # A miss has no surface, so it gets the only normal that is defensible: facing
    # the eye. Its tangent then has to be given explicitly (see below).
    normal = np.where(hit[:, None], g["normal"][ys, xs], -d)
    # NOT LoadedStage.shade(): that replaces every miss with one constant and the sky
    # is the thing being planted here. g["albedo"] is the BEAUTY pass, i.e. what the
    # eye received, which is what a stroke must carry.
    rgb = g["albedo"][ys, xs]

    # cross(normal, view) is canvas's own default tangent and is reproduced exactly
    # for surfaces. For a sky stroke it is cross(-d, d) == 0, and canvas would fall
    # back to the world +X axis for EVERY one of them -- a combed sky, all strokes
    # parallel. So sky strokes get a deterministic random direction perpendicular
    # to the ray instead.
    tangent = np.cross(normal, d)
    bad = np.linalg.norm(tangent, axis=1) < 1e-6
    if bad.any():
        rng2 = np.random.default_rng(seed + 991)
        t = rng2.normal(size=(int(bad.sum()), 3))
        dv = d[bad]
        t -= dv * (t * dv).sum(axis=1, keepdims=True)
        tangent[bad] = t
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-12)

    return (point, normal, rgb, size * depth, tangent,
            int(hit.sum()), int(len(pick)))


# --------------------------------------------------------------------- painting

def paint_face(cam, strokes, seed: int, prove_hard: bool = False):
    """One face, on the HARD ownership path. Returns (image float64, coverage).

    canvas.render(..., soft=False) is literally `pal.lookup(ownership(...)[0], bg)`.
    Calling the two halves separately is the same picture and hands back the
    ownership map, which is the only honest source for coverage -- comparing the
    image against a background colour would count a stroke that happens to be that
    colour as a hole. `--prove-hard` asserts the two are pixel-identical.
    """
    owner, _z, _fp = canvas.ownership(cam, strokes, style="painterly", seed=seed)
    img = Palette.of(strokes).lookup(owner, canvas.BACKGROUND)
    cov = float((owner >= 0).mean())
    if prove_hard:
        ref = canvas.render(None, cam, strokes, style="painterly", seed=seed,
                            soft=False)
        if not np.array_equal(ref, img):
            raise AssertionError("ownership+lookup differs from render(soft=False) "
                                 "-- this is NOT the hard path")
        del ref
    # float32 from here on: six 2048x2048x3 faces in float64 is 604 MB held at once,
    # on the machine that is also running Iddo's live microphone.
    return img.astype(np.float32), cov


# ------------------------------------------------------------------- resampling

def _bilinear(img: np.ndarray, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Bilinear sample, edges CLAMPED. img (H,W,3) float32."""
    h, w = img.shape[:2]
    x = np.clip(px, 0.0, w - 1.0)
    y = np.clip(py, 0.0, h - 1.0)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0).astype(np.float32)[..., None]
    fy = (y - y0).astype(np.float32)[..., None]
    top = img[y0, x0] * (1.0 - fx) + img[y0, x1] * fx
    bot = img[y1, x0] * (1.0 - fx) + img[y1, x1] * fx
    return top * (1.0 - fy) + bot * fy


def _catmull(img: np.ndarray, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Catmull-Rom bicubic sample, edges CLAMPED. img (H,W,3) float32.

    WHY THIS EXISTS, with the number. A bilinear tap at half-pixel phase is a two-tap
    box: its response at Nyquist is ZERO, so it deletes exactly the frequencies a
    brushstroke edge lives in. The plate goes through TWO resamples (face -> sphere,
    sphere -> the view the ruler reads), and the cost of that was measured, not
    guessed: painted faces read lapvar 872 / 417 / 277 at their native 2048, and the
    90-degree view cut out of the finished plate read 78. The picture had not changed;
    the sampling had eaten it.

    Catmull-Rom is the interpolating cubic (it passes through the samples, so it
    invents no new geometry) with a much flatter passband. It DOES overshoot slightly
    at a hard step -- and the hard compositor makes nothing but hard steps -- so the
    result is clipped back into range and the plate is LOOKED AT for haloing before
    anything ships. Bilinear stays available and is one flag away.
    """
    h, w = img.shape[:2]
    x = np.clip(px, 0.0, w - 1.0)
    y = np.clip(py, 0.0, h - 1.0)
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    xi = x0.astype(np.int64)
    yi = y0.astype(np.int64)

    def _w(t):
        t2, t3 = t * t, t * t * t
        return (-0.5 * t3 + t2 - 0.5 * t,
                1.5 * t3 - 2.5 * t2 + 1.0,
                -1.5 * t3 + 2.0 * t2 + 0.5 * t,
                0.5 * t3 - 0.5 * t2)

    wx = _w(fx)
    wy = _w(fy)
    out = np.zeros(px.shape + (3,), dtype=np.float32)
    for m in range(4):
        ys = np.clip(yi + m - 1, 0, h - 1)
        row = np.zeros_like(out)
        for n in range(4):
            xs = np.clip(xi + n - 1, 0, w - 1)
            row += img[ys, xs] * wx[n][..., None]
        out += row * wy[m][..., None]
    return out


FILTERS = {"bilinear": _bilinear, "catmullrom": _catmull}


def equirect_dirs(width: int, height: int):
    """Direction for every equirect pixel, in GODOT'S OWN PANORAMA CONVENTION.

    Godot's sky shader maps a direction to a panorama with
        u = atan2(p.x, -p.z) / TAU + 0.5      v = acos(p.y) / PI
    so the image CENTRE is world -Z and u grows towards world +X, which is the
    viewer's right when facing -Z. That is also the photo-sphere / equirect standard
    every 360 viewer expects. This file uses it unchanged and does NOT apply a private
    yaw offset to put a prettier direction in the middle: a plate that disagrees with
    the engine's own sky mapping is a silent geometric lie the moment anyone composites
    it against the real scene. Which world direction lands in the centre is stated in
    the README instead -- in a headset you turn your head.
    """
    u = (np.arange(width) + 0.5) / width          # 0..1
    v = (np.arange(height) + 0.5) / height
    lon = (u - 0.5) * 2.0 * np.pi                 # atan2(x, -z)
    lat_polar = v * np.pi                         # acos(y)
    sin_p = np.sin(lat_polar)[:, None]
    y = np.cos(lat_polar)[:, None] * np.ones((1, width))
    x = sin_p * np.sin(lon)[None, :]
    z = -sin_p * np.cos(lon)[None, :]
    return np.stack([x, y, z], axis=-1)


def to_equirect(faces, images, width: int, height: int, rows: int = 256,
                filt: str = "catmullrom"):
    """The six painted faces -> one equirect, bilinear, no blending, no feathering.

    Every output pixel is taken from exactly ONE face -- whichever face's forward axis
    its direction is closest to, which for six axis-aligned faces is the same as
    'largest |component|'. No averaging near an edge: if the two faces disagree there,
    the seam measurement must be able to SEE it, and blending would hide it.
    """
    F, _R, _U = face_bases(faces)
    cams = [f["cam"] for f in faces]
    out = np.zeros((height, width, 3), dtype=np.uint8)
    imgs = [np.ascontiguousarray(im, dtype=np.float32) for im in images]
    for y0 in range(0, height, rows):
        y1 = min(y0 + rows, height)
        # the same map as equirect_dirs, built one BAND at a time so an 8192x4096
        # plate never holds a whole (H,W,3) float64 direction field (768 MB)
        u = (np.arange(width) + 0.5) / width
        v = (np.arange(y0, y1) + 0.5) / height
        lon = (u - 0.5) * 2.0 * np.pi
        pol = v * np.pi
        sin_p = np.sin(pol)[:, None]
        dy = np.cos(pol)[:, None] * np.ones((1, width))
        dx = sin_p * np.sin(lon)[None, :]
        dz = -sin_p * np.cos(lon)[None, :]
        d = np.stack([dx, dy, dz], axis=-1)
        which = np.argmax(d.reshape(-1, 3) @ F.T, axis=1).reshape(d.shape[:2])
        band = np.zeros((y1 - y0, width, 3), dtype=np.float32)
        for k, cam in enumerate(cams):
            m = which == k
            if not m.any():
                continue
            px, py, zz = cam.project(cam.eye + d[m])
            band[m] = FILTERS[filt](imgs[k], px, py)
        out[y0:y1] = np.clip(band, 0.0, 1.0) * 255.0 + 0.5
    return out


def cut_rectilinear(equi: np.ndarray, forward, up, fov_deg: float, size: int,
                    filt: str = "catmullrom"):
    """A pinhole view cut OUT of the equirect -- what the headset actually shows.

    lapvar on the equirect itself would be meaningless: the projection stretches the
    poles by 1/cos(latitude), so it would punish or flatter the plate for geometry it
    does not have. The ruler belongs on a view, at the headset's FOV.
    """
    f = np.asarray(forward, dtype=np.float64)
    f /= np.linalg.norm(f)
    r = np.cross(f, np.asarray(up, dtype=np.float64))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    half = np.tan(np.radians(fov_deg) * 0.5)
    gx = ((np.arange(size) + 0.5) / size * 2.0 - 1.0) * half
    gy = (1.0 - (np.arange(size) + 0.5) / size * 2.0) * half
    GX, GY = np.meshgrid(gx, gy)
    d = f[None, None, :] + GX[..., None] * r[None, None, :] + GY[..., None] * u[None, None, :]
    d /= np.linalg.norm(d, axis=2, keepdims=True)
    h, w = equi.shape[:2]
    lon = np.arctan2(d[..., 0], -d[..., 2])
    pol = np.arccos(np.clip(d[..., 1], -1.0, 1.0))
    px = (lon / (2.0 * np.pi) + 0.5) * w - 0.5
    py = (pol / np.pi) * h - 0.5
    px = np.mod(px, w)                                  # longitude wraps
    src = np.ascontiguousarray(equi, dtype=np.float32)
    # Longitude WRAPS and latitude CLAMPS -- a panorama has no left or right edge, and
    # sampling one as if it did puts a black line down the back of the sphere.
    xi = np.floor(px).astype(np.int64)
    yy = np.clip(py, 0.0, h - 1.0)
    yi = np.floor(yy).astype(np.int64)
    tx = (px - xi).astype(np.float32)
    ty = (yy - yi).astype(np.float32)
    if filt == "bilinear":
        wx = (1.0 - tx, tx)
        wy = (1.0 - ty, ty)
        rng = (0, 1)
    else:
        def _w(t):
            t2, t3 = t * t, t * t * t
            return (-0.5 * t3 + t2 - 0.5 * t, 1.5 * t3 - 2.5 * t2 + 1.0,
                    -1.5 * t3 + 2.0 * t2 + 0.5 * t, 0.5 * t3 - 0.5 * t2)
        wx, wy = _w(tx), _w(ty)
        rng = (-1, 0, 1, 2)
    out = np.zeros(px.shape + (3,), dtype=np.float32)
    for m, dy in enumerate(rng):
        ys = np.clip(yi + dy, 0, h - 1)
        row = np.zeros_like(out)
        for n, dx in enumerate(rng):
            xs = (xi + dx) % w
            row += src[ys, xs] * wx[n][..., None]
        out += row * wy[m][..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


# -------------------------------------------------------------------- the seams

# the twelve cube edges, as (face A, face B, the two world axes that span the edge)
EDGES = [("px", "py"), ("px", "ny"), ("px", "pz"), ("px", "nz"),
         ("nx", "py"), ("nx", "ny"), ("nx", "pz"), ("nx", "nz"),
         ("py", "pz"), ("py", "nz"), ("ny", "pz"), ("ny", "nz")]

AXIS = {"px": np.array([1.0, 0, 0]), "nx": np.array([-1.0, 0, 0]),
        "py": np.array([0, 1.0, 0]), "ny": np.array([0, -1.0, 0]),
        "pz": np.array([0, 0, 1.0]), "nz": np.array([0, 0, -1.0])}


def seam_report(faces, images, samples: int = 2048):
    """Last column of face A vs first column of face B, AFTER PROJECTION.

    For every direction exactly on a shared cube edge, face A projects it to its own
    outermost column and face B to the opposite one. Sampling both and differencing is
    literally the question asked: do the two paintings agree where they meet?
    Reported in 0..255 units so the number means something to an eye.
    """
    by = {f["name"]: (f["cam"], np.ascontiguousarray(im, dtype=np.float32))
          for f, im in zip(faces, images)}
    t = np.linspace(-1.0, 1.0, samples)
    rows = []
    for a, b in EDGES:
        na, nb = AXIS[a], AXIS[b]
        third = np.cross(na, nb)                    # the axis the edge runs along
        d = na[None, :] + nb[None, :] + t[:, None] * third[None, :]
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        cam_a, im_a = by[a]
        cam_b, im_b = by[b]
        pax, pay, _ = cam_a.project(cam_a.eye + d)
        pbx, pby, _ = cam_b.project(cam_b.eye + d)
        va = _bilinear(im_a, pax, pay)
        vb = _bilinear(im_b, pbx, pby)
        diff = np.abs(va - vb).mean() * 255.0
        rows.append({"edge": f"{a}|{b}", "mean_abs_diff_255": round(float(diff), 4),
                     "max_abs_diff_255": round(float(np.abs(va - vb).max() * 255.0), 3)})
    return rows


# ------------------------------------------------------------------------- main

def main() -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--faces", required=True, help="folder with face_*.tzg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="plate")
    ap.add_argument("--width", type=int, default=8192)
    ap.add_argument("--strokes", type=int, default=90_000, help="per face")
    ap.add_argument("--size", type=float, default=0.006)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--cut-forward", default=None,
                    help="x,y,z world direction for the rectilinear ruler view")
    ap.add_argument("--cut-fov", type=float, default=90.0)
    ap.add_argument("--filter", default="catmullrom",
                    choices=sorted(FILTERS), help="spherical resampler")
    ap.add_argument("--prove-hard", action="store_true")
    ap.add_argument("--no-plate", action="store_true", help="measure faces only")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    faces = load_faces(a.faces)
    n_face = faces[0]["cam"].width
    print(f"[vr360] six faces {n_face}x{n_face}, eye={faces[0]['cam'].eye}, "
          f"fov=90.0 -- cubemap preconditions OK", flush=True)

    # ---- plant on all six, pool into ONE array (see THE SEAM in the docstring)
    P, N, C, R, T = [], [], [], [], []
    per_face = []
    for i, f in enumerate(faces):
        pt, nm, rg, rd, tg, nhit, ntot = plant(f, a.strokes, a.seed * 131 + i, a.size)
        P.append(pt); N.append(nm); C.append(rg); R.append(rd); T.append(tg)
        per_face.append({"face": f["name"], "planted": ntot,
                         "on_surface": nhit, "on_sky": ntot - nhit})
        f["g"] = None                     # 340 MB a face at 2048; let it go
    strokes = Strokes(point=np.concatenate(P), normal=np.concatenate(N),
                      rgb=np.concatenate(C), radius=np.concatenate(R),
                      tangent=np.concatenate(T), asked=a.strokes * 6)
    del P, N, C, R, T
    print(f"[vr360] {len(strokes)} strokes pooled from six faces "
          f"({time.time()-t0:.1f} s)", flush=True)

    # ---- paint every face from ALL strokes
    images, cover = [], []
    for f in faces:
        ts = time.time()
        img, cov = paint_face(f["cam"], strokes, a.seed, prove_hard=a.prove_hard)
        images.append(img)
        cover.append(cov)
        print(f"[vr360] face {f['name']}: coverage {cov*100:.3f}%  "
              f"({time.time()-ts:.1f} s)", flush=True)

    from PIL import Image
    for f, im in zip(faces, images):
        Image.fromarray((np.clip(im, 0, 1) * 255 + 0.5).astype(np.uint8)).save(
            os.path.join(a.out, f"face_{f['name']}_painted.png"))

    seams = seam_report(faces, images)
    result = {
        "name": a.name,
        "eye": [float(v) for v in faces[0]["cam"].eye],
        "face_px": n_face, "fov_deg": 90.0, "resampler": a.filter,
        "strokes_per_face": a.strokes, "strokes_total": int(len(strokes)),
        "stroke_size_world_per_metre": a.size,
        "planted": per_face,
        "coverage_pct": {f["name"]: round(c * 100, 4)
                         for f, c in zip(faces, cover)},
        "coverage_min_pct": round(min(cover) * 100, 4),
        "seams": seams,
        "seam_mean_abs_diff_255": round(
            float(np.mean([s["mean_abs_diff_255"] for s in seams])), 4),
        "seam_worst_edge": max(seams, key=lambda s: s["mean_abs_diff_255"]),
    }

    if not a.no_plate:
        w = a.width
        h = w // 2
        te = time.time()
        equi = to_equirect(faces, images, w, h, filt=a.filter)
        print(f"[vr360] equirect {w}x{h} ({time.time()-te:.1f} s)", flush=True)
        Image.MAX_IMAGE_PIXELS = None
        p_png = os.path.join(a.out, f"{a.name}-equirect-{w}x{h}.png")
        Image.fromarray(equi).save(p_png, optimize=False)
        p_jpg = os.path.join(a.out, f"{a.name}-equirect-{w}x{h}.jpg")
        Image.fromarray(equi).save(p_jpg, quality=94, subsampling=0)
        result["equirect_png"] = p_png
        result["equirect_jpg"] = p_jpg
        result["equirect_px"] = f"{w}x{h}"
        result["ppd_equator"] = round(w / 360.0, 3)

        if a.cut_forward:
            fwd = [float(v) for v in a.cut_forward.split(",")]
            cut = cut_rectilinear(equi, fwd, (0, 1, 0), a.cut_fov, w // 4,
                                  filt=a.filter)
            p_cut = os.path.join(a.out, f"{a.name}-view-{a.cut_fov:.0f}deg.png")
            Image.fromarray(cut).save(p_cut)
            result["cut_view_png"] = p_cut
            result["cut_forward"] = fwd
            result["cut_fov_deg"] = a.cut_fov
            result["cut_px"] = f"{w//4}x{w//4}"
            result["lapvar_rectilinear_view"] = round(lapvar_array(cut), 3)
        result["lapvar_equirect_FOR_REFERENCE_ONLY"] = round(lapvar_array(equi), 3)

    result["seconds"] = round(time.time() - t0, 1)
    result["canvas_fingerprint"] = canvas.source_hashes()
    with open(os.path.join(a.out, f"{a.name}-measured.json"), "w",
              encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in result.items() if k != "seams"},
                     indent=1, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()
