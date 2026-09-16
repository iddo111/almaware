# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE WORKSHOP, PLANTED AND PAINTED WITH EVERY KNOB EXPOSED.

`D:\\CLAUDE\\oneroom\\paint.py` hard-codes RADIUS, VOXEL, MAX_STROKES and the
resolution, and it is the file that produced the picture Iddo rejected. This module
is the same planter with those four turned into arguments, plus the new occlusion
path, so the sweep can ask what each one is actually worth in Laplacian variance
and what it costs in seconds and megabytes.

Nothing in `oneroom/paint.py`, `oneroom/room.py`, `tzelem/stage.py`,
`tzelem/anatomy.py` or `tzelem/canvas.py` is modified by importing this.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
          "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(v, "4")

TZ = r"D:\CLAUDE\eran-brain\holobrain\tzelem"
ONEROOM = r"D:\CLAUDE\oneroom"
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (TZ, ONEROOM, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import canvas                                            # noqa: E402
import occlusion                                         # noqa: E402
import room                                              # noqa: E402
from anatomy import Strokes                              # noqa: E402
from stage import Camera                                 # noqa: E402

PLANT_W, PLANT_H, PLANT_FOV = 512, 384, 76.0
SEED = 17
YAWS = [0.0, 40.0, -40.0, 82.0, -82.0, 132.0, -132.0, 180.0]
EXTRA = [(0.0, -46.0), (180.0, -46.0), (0.0, 34.0), (180.0, 30.0), (-90.0, -40.0)]

# WHERE THE LIGHT ACTUALLY IS. Both are read off room.build() geometry, not guessed.
WINDOW_POS = np.array([-2.90, 1.60, -0.925])            # the window in the west wall
TUBE_POS = [np.array([0.0, 2.60, -1.99]), np.array([0.0, 2.60, 0.71])]

# the shell and the fixtures: a shadow ray must not be stopped by the wall the
# light is cut into, or by the lamp itself. Everything else in the room blocks.
NON_BLOCKING = {"wall_north", "wall_south", "wall_west", "wall_east", "ceiling",
                "window", "sill", "lintel", "mullion", "tube", "tube_body"}


def _dir(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    y, p = np.radians(yaw_deg), np.radians(pitch_deg)
    cp = np.cos(p)
    return np.array([-np.sin(y) * cp, np.sin(p), -np.cos(y) * cp])


def plant_cameras() -> list[Camera]:
    cams = []
    for t in (0.0, 0.5, 1.0):
        eye = room.RAIL_A + (room.RAIL_B - room.RAIL_A) * t
        for yaw in YAWS:
            d = _dir(yaw, -10.0)
            cams.append(Camera(eye=eye, target=eye + d * 3.0, width=PLANT_W,
                               height=PLANT_H, fov_deg=PLANT_FOV))
        for yaw, pitch in EXTRA:
            d = _dir(yaw, pitch)
            cams.append(Camera(eye=eye, target=eye + d * 3.0, width=PLANT_W,
                               height=PLANT_H, fov_deg=PLANT_FOV))
    return cams


def _voxel_key(pt: np.ndarray, nrm: np.ndarray, voxel: float) -> np.ndarray:
    ijk = np.floor(pt / voxel).astype(np.int64) + 4096
    axis = np.argmax(np.abs(nrm), axis=1)
    sign = (nrm[np.arange(len(nrm)), axis] >= 0).astype(np.int64)
    face = axis * 2 + sign
    return (((ijk[:, 0] * 8192 + ijk[:, 1]) * 8192 + ijk[:, 2]) * 6) + face


def anchors(voxel: float, max_strokes: int, verbose: bool = True) -> dict:
    """Plant the room's surfaces ONCE: point, normal, box index. No colour yet.

    Colour is deliberately not computed here - the occlusion pass has to run on
    the DEDUPED set (a fortieth of the candidates), and a stroke's colour depends
    on it, so anything that touched colour before the dedupe would be thrown away.
    """
    st = room.RoomStage(room.BOXES)
    P, N, B = [], [], []
    cams = plant_cameras()
    t0 = time.time()
    for k, cam in enumerate(cams):
        g = st.gbuffer(cam)
        m = g["mask"] & (np.abs(np.einsum("hwk,hwk->hw", g["normal"],
                                          cam.rays())) >= 0.14)
        if not m.any():
            continue
        pt, nr, bx = g["point"][m], g["normal"][m], g["box"][m]
        _, idx = np.unique(_voxel_key(pt, nr, voxel), return_index=True)
        P.append(pt[idx]); N.append(nr[idx]); B.append(bx[idx])
        if verbose and (k + 1) % 8 == 0:
            print(f"    planted {k+1}/{len(cams)} cams, "
                  f"{sum(len(a) for a in P):,} candidates, "
                  f"{time.time()-t0:.0f}s", flush=True)
    pt = np.concatenate(P); nr = np.concatenate(N); bx = np.concatenate(B)
    _, idx = np.unique(_voxel_key(pt, nr, voxel), return_index=True)
    if len(idx) > max_strokes:
        idx = idx[np.random.default_rng(3).permutation(len(idx))[:max_strokes]]
        idx.sort()
    pt, nr, bx = pt[idx], nr[idx], bx[idx]
    pt = pt + nr * 0.0015
    if verbose:
        print(f"    {len(pt):,} anchors at voxel {voxel} in {time.time()-t0:.0f}s",
              flush=True)
    return {"point": pt, "normal": nr, "box": bx, "stage": st,
            "plant_seconds": time.time() - t0}


def occlude_anchors(st, pt, nr, ao_rays: int = 12, ao_reach: float = 0.55,
                    shadow_samples: int = 4, verbose: bool = True) -> dict:
    """Contact shadow (per light state) + ambient occlusion at every anchor."""
    blockers = np.array([b["kind"] not in NON_BLOCKING for b in room.BOXES])
    t0 = time.time()
    ao = occlusion.ambient_occlusion(st, pt, nr, n_rays=ao_rays, reach=ao_reach) \
        if ao_rays else np.ones(len(pt))
    t_ao = time.time() - t0

    t0 = time.time()
    dark = occlusion.shadow_point(st, pt, nr, WINDOW_POS, blockers=blockers,
                                  softness=0.34, samples=shadow_samples)
    lit = np.zeros(len(pt))
    for lp in TUBE_POS:
        lit = np.maximum(lit, occlusion.shadow_point(
            st, pt, nr, lp, blockers=blockers, softness=0.55,
            samples=max(2, shadow_samples - 1)))
    t_sh = time.time() - t0
    if verbose:
        print(f"    AO {ao_rays} rays {t_ao:.0f}s (mean {ao.mean():.3f}) | "
              f"shadow {t_sh:.0f}s (dark lit-frac {dark.mean():.3f}, "
              f"lit {lit.mean():.3f})", flush=True)
    return {"ao": ao, "sun_dark": dark, "sun_lit": lit,
            "seconds": t_ao + t_sh}


def colours(st, pt, nr, bx, state: str, occ: dict | None,
            ao_strength: float = 0.80, shadow_strength: float = 0.70,
            texture_strength: float = 0.30, expose: bool = True,
            gain: float = 1.0) -> np.ndarray:
    """What a painter standing in this room would SEE at every anchor.

    Line for line `room.RoomStage.paint_rgb`, evaluated at points instead of at
    pixels, and then multiplied by the occlusion. The emissive boxes are painted
    flat LAST, exactly as `paint_rgb` does, so a lit tube is still the light and
    not a shadowed surface.
    """
    s = room.STATES[state]
    ld = np.asarray(s["light_dir"], dtype=np.float64)
    ld = ld / np.linalg.norm(ld)
    amb = float(s["ambient"])

    alb = np.zeros((len(pt), 3))
    for i, b in enumerate(st.boxes):
        m = bx == i
        if m.any():
            alb[m] = b.albedo
    gnd = bx < 0
    if gnd.any():
        chk = ((np.floor(pt[gnd, 0]) + np.floor(pt[gnd, 2])) % 2 == 0)
        alb[gnd] = np.where(chk[:, None], st.ground_albedo * 1.25,
                            st.ground_albedo * 0.72)

    if occ is not None and texture_strength > 0:
        alb = np.clip(alb * occlusion.texture(pt, nr, texture_strength)[:, None],
                      0.0, 1.0)

    lam = np.clip(-(nr @ ld), 0.0, 1.0)
    lam0 = lam
    if occ is not None and shadow_strength > 0:
        sun = occ["sun_dark"] if state == "dark" else occ["sun_lit"]
        lam = lam * (1.0 - shadow_strength * (1.0 - sun))
    col = alb * (amb + (1.0 - amb) * lam[:, None])
    if occ is not None and ao_strength > 0:
        col = col * (1.0 - ao_strength * (1.0 - occ["ao"]))[:, None]

    # EXPOSURE. Occlusion is a MULTIPLIER: it can only ever take light away, so it
    # darkens the whole picture, and Laplacian variance scales with the SQUARE of
    # contrast. Measured on the first probe: the dark room went 21.7 -> 12.9 with
    # shadow and AO switched on -- it had MORE edges and read LESS sharp, purely
    # because it was dimmer. Every renderer that adds occlusion re-exposes after
    # it; not doing so would be measuring the light meter, not the picture. The
    # mean of the un-occluded solution is restored exactly, so the comparison is
    # between two pictures of the same brightness.
    if occ is not None and expose:
        ref = (alb * (amb + (1.0 - amb) * lam0[:, None])).mean()
        now = col.mean()
        if now > 1e-9:
            col = col * (ref / now)
    col = col * np.asarray(s["tint"]) * s["gain"] * gain

    which = 0 if state == "dark" else 1
    for i, e in enumerate(st.emit):
        if e is None or e[which] is None:
            continue
        m = bx == i
        if m.any():
            col[m] = e[which]
    return np.clip(col, 0.0, 1.0)


def world_tangent(nr: np.ndarray) -> np.ndarray:
    """THE DIRECTION A STROKE LIES IN, decided by the WALL and not by the camera.

    Found by looking at the picture, not by a number, 2026-09-06. With the hard
    compositor switched on, the pegboard grew a visible VORTEX - concentric rings
    of brushstrokes centred on the middle of the frame. The cause is in
    `canvas._tangent_dir`: with no tangent given, a stroke lies along
    `cross(normal, view)`, which on a large flat surface rotates smoothly around
    the view axis and draws a spiral. `anatomy.Strokes` already documents that
    direction as "a legal surface tangent, but an ARBITRARY one" and already
    accepts a real one; nobody had supplied it, and the soft compositor had been
    hiding the consequence by averaging it away.

    A painter does not brush in circles around his own eye. He brushes ALONG the
    thing. So: horizontal along every wall (cross with world up), and along x on
    floors and ceilings. It is a world vector in the surface, so it still turns
    with the wall when the camera moves and coherence is untouched.
    """
    up = np.array([0.0, 1.0, 0.0])
    t = np.cross(nr, up)
    ln = np.linalg.norm(t, axis=1, keepdims=True)
    flat = ln[:, 0] < 1e-6                       # floor or ceiling
    t = np.where(ln > 1e-6, t / np.maximum(ln, 1e-9), np.array([1.0, 0.0, 0.0]))
    t[flat] = np.array([1.0, 0.0, 0.0])
    return t


def paint(pt, nr, rgb, radius: float, width: int, height: int, state: str,
          t: float = 0.30, jitter: float = 0.22, seed: int = SEED,
          edge: float | None = None, soft: bool = True,
          elong: float | None = None, kwargs_tangent: bool = False,
          supersample: int = 1) -> tuple[np.ndarray, float, float]:
    """Render with tzelem/canvas.py itself. Returns (image, seconds, coverage).

    `soft=False` takes the HARD path that has been in canvas.py since it was
    written and that nothing had ever measured: pass 1's ownership only, one
    stroke per pixel, no alpha, no averaging. Measured 2026-09-06 on this room,
    at 100% coverage both ways: dark 9.1 -> 42.0, lit 124 -> 465. That is where
    the blur was.

    `supersample` renders at N x the requested size and Lanczos-downsamples, which
    is the standard cure for the one thing the hard path gives up - a stroke's
    silhouette lands on whole pixels, so its rim is a staircase. It costs N^2 in
    time and it is honest antialiasing, not sharpening.
    """
    n = len(pt)
    rr = np.random.default_rng(seed + 1)
    rad = radius * (1.0 + rr.uniform(-jitter, jitter, n))
    el = None if elong is None else np.full(n, float(elong))
    tan = world_tangent(nr) if kwargs_tangent else None
    strokes = Strokes(point=pt, normal=nr, rgb=rgb, radius=rad, elong=el,
                      tangent=tan)
    ss = max(1, int(supersample))
    cam = room.rail_camera(t, width * ss, height * ss)
    t0 = time.time()
    if soft:
        kw = {"edge": edge} if edge is not None else {}
        img, _z, hit = canvas.render(None, cam, strokes, style="painterly",
                                     seed=seed,
                                     background=room.STATES[state]["sky"],
                                     return_zbuf=True, **kw)
        cov = float(hit.mean())
    else:
        from palette import Palette
        owner, _z, _fp = canvas.ownership(cam, strokes, style="painterly",
                                          seed=seed)
        img = Palette.of(strokes).lookup(owner, room.STATES[state]["sky"])
        cov = float((owner >= 0).mean())
    if ss > 1:
        from PIL import Image as _I
        a = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        img = np.asarray(_I.fromarray(a).resize((width, height), _I.LANCZOS),
                         dtype=np.float64) / 255.0
    return img, time.time() - t0, cov
