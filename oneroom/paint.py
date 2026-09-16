# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

PLANT THE ROOM ONCE, IN THE WORLD — and hand the same strokes to two consumers.

    D:\\CLAUDE\\oneroom\\web\\strokes.bin   the browser paints these live, every frame
    D:\\CLAUDE\\oneroom\\web\\*.jpg         the same strokes, painted here by canvas.py

Both read ONE array. That matters more than it sounds: if the browser drew something
of its own invention there would be no honest way to say "this is TZELEM running in
a game". Every number in `strokes.bin` was produced by `room.RoomStage.gbuffer` on
this PC, and the .jpg beside it is `tzelem/canvas.py` — untouched — painting exactly
those numbers. The GPU is a second body for the same organ, not a second organ.

WHAT IS DIFFERENT FROM `anatomy.scatter`, said plainly
-----------------------------------------------------
`scatter` picks random pixels of ONE camera and gives every stroke a radius
proportional to its depth — constant ANGULAR size, which is exactly right for a
still and exactly wrong for a room you walk into: a stroke planted on the far wall
from the doorway becomes a 30 cm blob when you are standing under it.

So the planter here differs in two ways and only two:
  * it plants from a RING of cameras (three positions on the player's rail, eleven
    directions each) so the surfaces behind and above the player exist too, and
  * the radius is a constant in the WORLD (2.6 cm), like real paint on a real wall.
    Uniform surface density x constant world radius = the same coverage fraction at
    every distance, so the picture does not thin out with depth either.

Everything else is `anatomy.Strokes` and `canvas.render` untouched, and the GATE
(gate.py) deliberately does NOT use this planter — it uses stock `scatter`, so the
number it reports is comparable to the boulevard's.

Numpy only, BELOW_NORMAL. Nothing on the fleet.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_TZELEM = r"D:\CLAUDE\eran-brain\holobrain\tzelem"
for p in (_TZELEM, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

sys.stdout.reconfigure(encoding="utf-8")
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
          "NUMEXPR_NUM_THREADS"):
    os.environ[v] = "4"

import room                                        # noqa: E402
from stage import Camera                           # noqa: E402

WEB = os.path.join(HERE, "web")
PLANT_W, PLANT_H = 512, 384
PLANT_FOV = 76.0
VOXEL = 0.0165             # world grid the planter dedupes on
RADIUS = 0.021             # a brushstroke is 2.1 cm of paint on a real surface
RADIUS_JITTER = 0.22
SEED = 17                  # the SAME seed canvas.py's painterly style draws with
MAX_STROKES = 340_000

# three places on the rail, eleven directions each: everything a player on this
# rail can turn and look at gets planted, including the floor and the ceiling.
YAWS = [0.0, 40.0, -40.0, 82.0, -82.0, 132.0, -132.0, 180.0]
EXTRA = [(0.0, -46.0), (180.0, -46.0), (0.0, 34.0), (180.0, 30.0), (-90.0, -40.0)]


def _dir(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    """Forward is -z, exactly as the rail and the browser both use."""
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


def _voxel_key(pt: np.ndarray, nrm: np.ndarray) -> np.ndarray:
    """One slot per (cell, facing). Two sides of a thin wall stay two strokes."""
    ijk = np.floor(pt / VOXEL).astype(np.int64) + 4096
    axis = np.argmax(np.abs(nrm), axis=1)
    sign = (nrm[np.arange(len(nrm)), axis] >= 0).astype(np.int64)
    face = axis * 2 + sign
    return (((ijk[:, 0] * 8192 + ijk[:, 1]) * 8192 + ijk[:, 2]) * 6) + face


def plant(verbose: bool = True) -> dict:
    st = room.RoomStage(room.BOXES)
    objs = np.array([b["obj"] for b in room.BOXES], dtype=np.float64)
    hil = np.array([1.0 if b["kind"].startswith("breaker") or b["kind"] == "lever"
                    else 0.0 for b in room.BOXES])

    P, N, D, L, O, H = [], [], [], [], [], []
    cams = plant_cameras()
    t0 = time.time()
    for k, cam in enumerate(cams):
        g = st.gbuffer(cam)
        # A surface seen almost edge-on gives a stroke whose tangent points at the
        # camera: it lands as a dark sliver ON THE WALL BEHIND IT. Real, but it is
        # speckle, not painting, so grazing anchors are not planted from this pose —
        # another pose in the ring sees the same surface face-on and plants it there.
        m = g["mask"] & (np.abs(np.einsum("hwk,hwk->hw", g["normal"],
                                          cam.rays())) >= 0.14)
        if not m.any():
            continue
        dark = st.paint_rgb(g, "dark")[m]
        lit = st.paint_rgb(g, "lit")[m]
        pt, nr, bx = g["point"][m], g["normal"][m], g["box"][m]
        key = _voxel_key(pt, nr)
        _, idx = np.unique(key, return_index=True)
        P.append(pt[idx]); N.append(nr[idx]); D.append(dark[idx]); L.append(lit[idx])
        ok = bx[idx] >= 0
        O.append(np.where(ok, objs[np.clip(bx[idx], 0, None)], 0.0))
        H.append(np.where(ok, hil[np.clip(bx[idx], 0, None)], 0.0))
        if verbose and (k + 1) % 6 == 0:
            print(f"  planted {k + 1}/{len(cams)} cameras, "
                  f"{sum(len(a) for a in P):,} candidates, "
                  f"{time.time() - t0:.0f}s", flush=True)

    pt = np.concatenate(P); nr = np.concatenate(N)
    dark = np.concatenate(D); lit = np.concatenate(L)
    obj = np.concatenate(O); hlt = np.concatenate(H)
    key = _voxel_key(pt, nr)
    _, idx = np.unique(key, return_index=True)
    if len(idx) > MAX_STROKES:                       # deterministic thinning
        idx = idx[np.random.default_rng(3).permutation(len(idx))[:MAX_STROKES]]
        idx.sort()
    pt, nr, dark, lit = pt[idx], nr[idx], dark[idx], lit[idx]
    obj, hlt = obj[idx], hlt[idx]
    n = len(pt)

    # nudge every anchor a hair off its surface: two coplanar boxes (the pegboard
    # against the wall) otherwise fight for the same voxel and speckle.
    pt = pt + nr * 0.0015

    # THE SAME DRAWS canvas.footprint('painterly', seed=17) makes, in the same
    # order, so the browser and canvas.py agree stroke for stroke.
    rng = np.random.default_rng(SEED)
    elong = rng.uniform(2.0, 4.0, n)
    angle = np.radians(rng.uniform(-14.0, 14.0, n))
    rr = np.random.default_rng(SEED + 1)
    radius = RADIUS * (1.0 + rr.uniform(-RADIUS_JITTER, RADIUS_JITTER, n))

    if verbose:
        print(f"{n:,} strokes, {time.time() - t0:.0f}s planting "
              f"({len(cams)} cameras at {PLANT_W}x{PLANT_H})")
    return {"point": pt, "normal": nr, "dark": dark, "lit": lit,
            "radius": radius, "elong": elong, "angle": angle,
            "obj": obj, "hilite": hlt, "cameras": len(cams)}


def export(s: dict) -> str:
    """16 float32 per stroke: point, normal, rgbDark, rgbLit, r, elong, angle, tag."""
    os.makedirs(WEB, exist_ok=True)
    n = len(s["point"])
    a = np.zeros((n, 16), dtype=np.float32)
    a[:, 0:3] = s["point"]; a[:, 3:6] = s["normal"]
    a[:, 6:9] = s["dark"];  a[:, 9:12] = s["lit"]
    a[:, 12] = s["radius"]; a[:, 13] = s["elong"]; a[:, 14] = s["angle"]
    a[:, 15] = s["obj"] + 2.0 * s["hilite"]
    p = os.path.join(WEB, "strokes.bin")
    a.tofile(p)
    print(f"  {p}  {n:,} strokes, {os.path.getsize(p) / 1e6:.1f} MB")
    return p


def write_room_json(s: dict) -> str:
    """The boxes the browser's crosshair rays, plus the rail and the camera."""
    os.makedirs(WEB, exist_ok=True)
    doc = {
        "strokes": int(len(s["point"])),
        "plant_cameras": s["cameras"],
        "radius_m": RADIUS, "voxel_m": VOXEL, "seed": SEED,
        "rail_a": list(room.RAIL_A), "rail_b": list(room.RAIL_B),
        "look": list(room.LOOK), "fov_deg": room.FOV,
        "sky": {k: list(v["sky"]) for k, v in room.STATES.items()},
        "boxes": [{"lo": b["lo"], "hi": b["hi"], "kind": b["kind"]}
                  for b in room.BOXES],
    }
    p = os.path.join(WEB, "room.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print(f"  {p}  {len(doc['boxes'])} boxes")
    return p


def _world_tangent(nr: np.ndarray) -> np.ndarray:
    """Horizontal along every wall; along x on the floor and the ceiling.

    Without a tangent, `canvas._tangent_dir` falls back to `cross(normal, view)`,
    which rotates around the view axis and draws a VISIBLE VORTEX of brushstrokes
    on a large flat surface — you can see it on the pegboard the moment the soft
    compositor stops averaging it away. `anatomy.Strokes` has always accepted a
    real world tangent; nobody had supplied one. This is a world vector lying in
    the surface, so it still turns with the wall when the camera moves and the
    coherence claim is untouched.
    """
    up = np.array([0.0, 1.0, 0.0])
    t = np.cross(nr, up)
    ln = np.linalg.norm(t, axis=1, keepdims=True)
    flat = ln[:, 0] < 1e-6
    t = np.where(ln > 1e-6, t / np.maximum(ln, 1e-9), np.array([1.0, 0.0, 0.0]))
    t[flat] = np.array([1.0, 0.0, 0.0])
    return t


def stills(s: dict, width=1600, height=900, t=0.30, soft: bool = False) -> list[str]:
    """The same strokes, painted by tzelem/canvas.py itself. Nothing is retouched.

    2026-09-06 — WHY `soft=False` IS NOW THE DEFAULT, and it is the whole fix.
    Iddo rejected this picture for being blurred and he was right. Measured on
    this exact camera at 1600x900, Laplacian variance (greyscale, long edge capped
    at 2400 px — the ruler his own rejection was set on):

        soft=True   (what was published)   dark  10.1    lit  124
        soft=False  (this)                 dark  42.0    lit  465

    both at 100.0% COVERAGE, and the hard path is ~3x FASTER because it skips
    pass 2 entirely. `canvas.render(soft=False)` has been in the file since it was
    written; nothing had ever measured it.

    The reason the soft path is soft is not the brush. Pass 2 makes every pixel
    the alpha-weighted MEAN of every stroke covering it, and averaging k samples
    of a surface divides its variance by about k. Proof, on this room: at a FIXED
    brush, ADDING strokes makes the picture BLURRIER — 40k 79.2, 85k 51.1,
    170k 17.6, 340k 9.1. It was drowning in coats of paint. On the hard path the
    order reverses and more strokes are sharper.

    Shrinking the brush instead LOOKS like a 25x win (radius 0.021 -> 0.007 takes
    it 9.1 -> 231.7) and it is a lie: coverage falls 100% -> 73% and the picture
    is holes showing the background. Put the strokes back to close them and the
    softness comes back with them. Do not go down that road.

    `soft=True` is kept so the old picture can be reproduced exactly.
    """
    import canvas
    from anatomy import Strokes
    from PIL import Image
    made = []
    cam = room.rail_camera(t, width, height)
    tan = None if soft else _world_tangent(s["normal"])
    for state in ("dark", "lit"):
        t0 = time.time()
        strokes = Strokes(point=s["point"], normal=s["normal"], rgb=s[state],
                          radius=s["radius"], tangent=tan)
        if soft:
            img = canvas.render(None, cam, strokes, style="painterly", seed=SEED,
                                background=room.STATES[state]["sky"])
        else:
            from palette import Palette
            owner, _z, _fp = canvas.ownership(cam, strokes, style="painterly",
                                              seed=SEED)
            img = Palette.of(strokes).lookup(owner, room.STATES[state]["sky"])
        p = os.path.join(WEB, f"room-{state}.jpg")
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            p, quality=93, subsampling=0)
        print(f"  {p}  {time.time() - t0:.0f}s  "
              f"({'soft' if soft else 'HARD compositor'})")
        made.append(p)
    return made


def main() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        print("priority BELOW_NORMAL, numpy threads 4")
    except Exception as e:
        print(f"could not lower priority: {e}")
    s = plant()
    export(s)
    write_room_json(s)
    stills(s)


if __name__ == "__main__":
    main()
