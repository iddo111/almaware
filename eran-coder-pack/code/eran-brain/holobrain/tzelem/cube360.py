# -*- coding: utf-8 -*-
"""TZELEM / צלם -- A 360 PLATE FOR VR GLASSES: six cube faces -> one equirectangular.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

WHAT THIS IS FOR, and why it is not a print job.
------------------------------------------------
Print cares about DPI. A headset cares about PIXELS PER DEGREE. For an equirect,
PPD at the equator is exactly WIDTH / 360 -- 4096 wide = 11.4, 8192 = 22.8,
12288 = 34.1. The target here is an HTC Vive gen-1 at 1080x1200 per eye, about
11 PPD, so 8192x4096 clears it 2x and anything beyond that is pixels the glass
cannot show.

A 360 image is NOT a photograph with a wide lens. Six 90-degree pinhole views tile
the sphere exactly, and a pinhole camera is all TZELEM (or Godot) has. So:

    Godot  ->  six .tzg G-buffers, ONE eye, exactly 90.0 deg, square, per-face up
    here   ->  plant world-anchored strokes from all six
    here   ->  canvas.render(soft=False) -- the HARD ownership path -- per face
    here   ->  resample the six into one equirect, bilinear, seamless
    here   ->  MEASURE: coverage, seam, PPD, lapvar on a cut rectilinear view

THE SEAM IS THE FAILURE MODE, and it is beaten in three places at once:
  1. ONE ORIGIN and exactly 90.0 deg, enforced in tzelem_cube360.gd.
  2. ONE STROKE SET. Every face is rendered from the strokes planted by ALL SIX
     faces (restricted to a widened frustum for speed, not for correctness -- see
     `_visible_subset`). A stroke straddling a cube edge is therefore drawn on
     both sides of it from the same world anchor, with the same colour. The seam
     is killed by construction, not by blurring it away afterwards.
  3. SEAMLESS SAMPLING. The equirect resampler never clamps at a face border; each
     face is padded with a one-pixel ring fetched from its NEIGHBOURS along the
     true ray direction, so bilinear taps at the edge read real neighbour pixels.
     The difference between that ring and the face's own edge line IS the seam
     number reported below -- it is a measurement of disagreement, not a fix.

STEREO -- SAID PLAINLY. Real panoramic stereo is omni-directional stereo: every
COLUMN rendered from a different eye position around a circle of radius IPD/2.
Nothing in TZELEM or in the Godot scripts does that. Offsetting the whole camera
by an IPD instead gives correct depth ahead and INVERTED depth behind, which hurts
in a headset. So this file makes MONO plates only and says so.

Numpy + PIL only.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import canvas                                    # noqa: E402
import gbuffer                                   # noqa: E402
from anatomy import Strokes                      # noqa: E402
from palette import Palette                      # noqa: E402
from stage import Camera                         # noqa: E402

FACE_ORDER = ("px", "nx", "py", "ny", "pz", "nz")


# ------------------------------------------------------------------ loading

def load_faces(folder: str) -> dict:
    """Load the six .tzg faces. Refuses anything that is not one cube.

    Every check here has a way it has actually gone wrong in a cubemap: faces from
    two eyes (a panorama of nothing), a face at 62 deg because someone reused the
    beauty camera, a rectangular face (where Godot's vertical fov stops being the
    horizontal one).
    """
    out = {}
    for name in FACE_ORDER:
        g, cam = gbuffer.load(os.path.join(folder, f"face_{name}"))
        out[name] = {"g": g, "cam": cam}
    eyes = np.array([out[n]["cam"].eye for n in FACE_ORDER])
    if not np.allclose(eyes, eyes[0], atol=1e-9):
        raise ValueError("the six faces do not share one eye -- they tile nothing:\n"
                         + repr(eyes))
    for n in FACE_ORDER:
        c = out[n]["cam"]
        if abs(c.fov_deg - 90.0) > 1e-9:
            raise ValueError(f"face {n} is {c.fov_deg} deg, not exactly 90.0")
        if c.width != c.height:
            raise ValueError(f"face {n} is {c.width}x{c.height}; a cube face must be "
                             "SQUARE or Godot's vertical fov is not the horizontal one")
    return out


def face_basis(faces: dict) -> dict:
    """(f, r, u) per face, taken from the camera itself -- never re-derived.

    This is the one thing that must not be re-invented. `stage.Camera.basis()` is
    what `Camera.rays()` and `Camera.project()` use, and it is provably the same
    basis Godot's `look_at` built (the derivation is in tzelem_cube360.gd). Reading
    it back off the camera means the resampler and the renderer cannot drift apart.
    """
    return {n: faces[n]["cam"].basis() for n in FACE_ORDER}


# ------------------------------------------------------- direction <-> face

def dirs_to_face_uv(d: np.ndarray, basis: dict):
    """World unit directions -> (face index, gx, gy) with gx,gy in [-1,1].

    The face is the one whose forward axis the direction leans on most, which for
    an axis-aligned 90-degree cube is exactly the face that contains it.
    """
    t = np.stack([d @ basis[n][0] for n in FACE_ORDER], axis=-1)     # (..., 6)
    k = np.argmax(t, axis=-1)
    fwd = np.stack([basis[n][0] for n in FACE_ORDER])
    rgt = np.stack([basis[n][1] for n in FACE_ORDER])
    upv = np.stack([basis[n][2] for n in FACE_ORDER])
    tk = np.einsum("...i,...i->...", d, fwd[k])
    gx = np.einsum("...i,...i->...", d, rgt[k]) / tk
    gy = np.einsum("...i,...i->...", d, upv[k]) / tk
    return k, gx, gy


def equirect_dirs(width: int, height: int, yaw0: float = 0.0) -> np.ndarray:
    """The world direction of every equirect pixel. (H, W, 3), unit.

    CONVENTION, stated so the file is not a mystery in a month:
      column i  ->  longitude  lam = (i+0.5)/W*2pi - pi          (left -pi, right +pi)
      row    j  ->  latitude   phi = pi/2 - (j+0.5)/H*pi         (top +pi/2, bottom -pi/2)
      direction  d = ( sin(lam+yaw0)cos(phi), sin(phi), -cos(lam+yaw0)cos(phi) )

    That is the ordinary spherical-panorama layout every 360 viewer expects (the
    horizontal centre of the image is what the viewer opens looking at, and moving
    right in the image turns right in the world). `yaw0` rotates the whole plate
    about the world Y axis so the centre column can be aimed somewhere meaningful --
    here, at the pose the shot list already stands a person at.
    """
    lam = (np.arange(width) + 0.5) / width * 2.0 * np.pi - np.pi + yaw0
    phi = np.pi * 0.5 - (np.arange(height) + 0.5) / height * np.pi
    cl, sl = np.cos(lam)[None, :], np.sin(lam)[None, :]
    cp, sp = np.cos(phi)[:, None], np.sin(phi)[:, None]
    d = np.empty((height, width, 3), dtype=np.float64)
    d[..., 0] = sl * cp
    d[..., 1] = np.broadcast_to(sp, (height, width))
    d[..., 2] = -cl * cp
    return d


def yaw_of(direction) -> float:
    """The azimuth of a world direction under the convention above."""
    d = np.asarray(direction, dtype=np.float64)
    return float(np.arctan2(d[0], -d[2]))


# --------------------------------------------------------- seamless padding

def _bilinear(img: np.ndarray, px: np.ndarray, py: np.ndarray,
              wrap_x: bool = False) -> np.ndarray:
    """Bilinear sample of an (H,W,C) image at pixel-centre coordinates.

    `wrap_x` is for sampling an EQUIRECT, whose left and right edges are the same
    meridian. Without it a view cut across longitude 180 gets a one-pixel stripe
    down its middle from the clamp -- an artefact of the cutting tool that looks
    exactly like a defect in the plate.
    """
    h, w = img.shape[:2]
    x0 = np.floor(px).astype(np.int64)
    y0 = np.floor(py).astype(np.int64)
    fx = (px - x0)[..., None]
    fy = (py - y0)[..., None]
    if wrap_x:
        x0c = np.mod(x0, w)
        x1c = np.mod(x0 + 1, w)
    else:
        x0c = np.clip(x0, 0, w - 1)
        x1c = np.clip(x0 + 1, 0, w - 1)
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y0 + 1, 0, h - 1)
    a = img[y0c, x0c]
    b = img[y0c, x1c]
    c = img[y1c, x0c]
    e = img[y1c, x1c]
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy)
            + c * (1 - fx) * fy + e * fx * fy)


def pad_faces(imgs: dict, basis: dict) -> tuple[dict, dict]:
    """Grow every face by one pixel, filling the ring FROM ITS NEIGHBOURS.

    Returns (padded, seam) where padded[n] is (N+2, N+2, 3) and seam[n] holds the
    four measured mean-absolute differences between the imported ring and the
    face's own outermost line -- i.e. how far the two independent renders of
    almost-the-same ray disagree.

    Why this matters: a bilinear tap whose footprint crosses a face border needs a
    pixel that does not exist on that face. Clamping invents one by repeating the
    edge, which smears a half-pixel stripe down every cube edge of the panorama and
    is indistinguishable, by eye, from a real seam. This fetches the true pixel
    instead, and reports what it found.
    """
    n = imgs[FACE_ORDER[0]].shape[0]
    padded, seam = {}, {}
    for name in FACE_ORDER:
        f, r, u = basis[name]
        big = np.zeros((n + 2, n + 2, 3), dtype=np.float64)
        big[1:-1, 1:-1] = imgs[name]
        # the ring's own pixel coordinates, in the face's frame, then as directions
        # ring index j = 0..n+1 stands for face pixel -1..n on that axis.
        #   gx = (px + 0.5)/n*2 - 1        gy = 1 - (py + 0.5)/n*2 = -gx(py)
        idx = np.arange(-1, n + 1, dtype=np.float64)
        g = (idx + 0.5) / n * 2.0 - 1.0
        g_out_lo = ((-1) + 0.5) / n * 2.0 - 1.0          # one pixel before 0
        g_out_hi = (n + 0.5) / n * 2.0 - 1.0             # one pixel after n-1
        sides = {
            "top":    (g, np.full(n + 2, -g_out_lo)),
            "bottom": (g, np.full(n + 2, -g_out_hi)),
            "left":   (np.full(n + 2, g_out_lo), -g),
            "right":  (np.full(n + 2, g_out_hi), -g),
        }
        gx = np.concatenate([sides[s][0] for s in ("top", "bottom", "left", "right")])
        gy = np.concatenate([sides[s][1] for s in ("top", "bottom", "left", "right")])
        d = f[None, :] + gx[:, None] * r[None, :] + gy[:, None] * u[None, :]
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        # look the direction up on WHICHEVER face owns it -- never this one
        t = np.stack([d @ basis[m][0] for m in FACE_ORDER], axis=-1)
        t[:, FACE_ORDER.index(name)] = -np.inf
        k = np.argmax(t, axis=-1)
        vals = np.zeros((d.shape[0], 3))
        for j, m in enumerate(FACE_ORDER):
            sel = k == j
            if not sel.any():
                continue
            fm, rm, um = basis[m]
            tk = d[sel] @ fm
            ax = (d[sel] @ rm) / tk
            ay = (d[sel] @ um) / tk
            vals[sel] = _bilinear(imgs[m], (ax + 1.0) * 0.5 * n - 0.5,
                                  (1.0 - ay) * 0.5 * n - 0.5)
        s = n + 2
        top, bot, lef, rig = vals[:s], vals[s:2 * s], vals[2 * s:3 * s], vals[3 * s:]
        big[0, :] = top
        big[-1, :] = bot
        big[:, 0] = lef
        big[:, -1] = rig
        # THE SEAM, measured: imported ring vs this face's own outermost line.
        own = imgs[name]
        seam[name] = {
            "top": float(np.abs(top[1:-1] - own[0, :]).mean()),
            "bottom": float(np.abs(bot[1:-1] - own[-1, :]).mean()),
            "left": float(np.abs(lef[1:-1] - own[:, 0]).mean()),
            "right": float(np.abs(rig[1:-1] - own[:, -1]).mean()),
            # the honest yardstick: how much do two ADJACENT pixels inside this
            # same face differ, at the same place? A seam is only a seam if it is
            # bigger than the picture's own pixel-to-pixel texture.
            "interior_baseline": float(np.abs(own[0, :] - own[1, :]).mean()
                                       + np.abs(own[-1, :] - own[-2, :]).mean()
                                       + np.abs(own[:, 0] - own[:, 1]).mean()
                                       + np.abs(own[:, -1] - own[:, -2]).mean()) / 4.0,
        }
        padded[name] = big
    return padded, seam


# ------------------------------------------------------------- the equirect

def to_equirect(imgs: dict, basis: dict, width: int, height: int,
                yaw0: float = 0.0, chunk: int = 256):
    """Resample six square faces into one equirectangular plate. Bilinear, seamless."""
    n = imgs[FACE_ORDER[0]].shape[0]
    padded, seam = pad_faces(imgs, basis)
    out = np.zeros((height, width, 3), dtype=np.float32)
    for y0 in range(0, height, chunk):
        y1 = min(y0 + chunk, height)
        # the same formula as equirect_dirs(), one horizontal band at a time so an
        # 8192x4096 plate never materialises six full-size dot products at once
        lam = (np.arange(width) + 0.5) / width * 2.0 * np.pi - np.pi + yaw0
        phi = np.pi * 0.5 - (np.arange(y0, y1) + 0.5) / height * np.pi
        cl, sl = np.cos(lam)[None, :], np.sin(lam)[None, :]
        cp, sp = np.cos(phi)[:, None], np.sin(phi)[:, None]
        d = np.empty((y1 - y0, width, 3))
        d[..., 0] = sl * cp
        d[..., 1] = np.broadcast_to(sp, (y1 - y0, width))
        d[..., 2] = -cl * cp
        k, gx, gy = dirs_to_face_uv(d, basis)
        # +1 shifts into the padded image, where the border ring is real neighbour
        px = (gx + 1.0) * 0.5 * n - 0.5 + 1.0
        py = (1.0 - gy) * 0.5 * n - 0.5 + 1.0
        for j, m in enumerate(FACE_ORDER):
            sel = k == j
            if not sel.any():
                continue
            out[y0:y1][sel] = _bilinear(padded[m], px[sel], py[sel]).astype(np.float32)
    return out, seam


# ------------------------------------------------------- a rectilinear view

def cut_view(equi: np.ndarray, look_dir, fov_deg: float, size: int,
             yaw0: float = 0.0, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    """Cut a normal pinhole view out of the plate -- what the headset actually shows.

    The ruler is NEVER run on the equirect itself. An equirect stretches the poles
    by 1/cos(latitude), so it flatters or punishes an image for a projection
    artefact rather than for its sharpness. A headset displays a rectilinear view;
    that is what gets measured.
    """
    f = np.asarray(look_dir, dtype=np.float64)
    f /= np.linalg.norm(f)
    r = np.cross(f, np.asarray(up, dtype=np.float64))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    half = np.tan(np.radians(fov_deg) * 0.5)
    g = (np.arange(size) + 0.5) / size * 2.0 - 1.0
    gx, gy = np.meshgrid(g, -g)
    d = (f[None, None, :] + (gx * half)[..., None] * r[None, None, :]
         + (gy * half)[..., None] * u[None, None, :])
    d /= np.linalg.norm(d, axis=2, keepdims=True)
    h, w = equi.shape[:2]
    lam = np.arctan2(d[..., 0], -d[..., 2]) - yaw0
    lam = (lam + np.pi) % (2.0 * np.pi) - np.pi
    phi = np.arcsin(np.clip(d[..., 1], -1.0, 1.0))
    px = (lam + np.pi) / (2.0 * np.pi) * w - 0.5
    py = (np.pi * 0.5 - phi) / np.pi * h - 0.5
    px = np.mod(px, w)                      # longitude wraps; latitude does not
    return _bilinear(equi.astype(np.float64), px, py, wrap_x=True)


# ------------------------------------------------------------------ writing

def save_png(path: str, img: np.ndarray) -> str:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    a = (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    Image.fromarray(a).save(path)
    return path


def save_jpg(path: str, img: np.ndarray, quality: int = 95) -> str:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    a = (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    Image.fromarray(a).save(path, quality=quality, subsampling=0)
    return path
