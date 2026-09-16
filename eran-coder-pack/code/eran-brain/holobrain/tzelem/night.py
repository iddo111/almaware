"""TZELEM / צלם — THE NIGHT PAINTING (2026-09-05): colour that came through ALMA.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז״ל.

WHAT THIS MAKES, AND WHY IT IS ONE PICTURE AND NOT TWO
-----------------------------------------------------
Tonight ALMA reached v0.4: a spark may be a CHORD — several numbers on one beat
(`alma/chords.py`). That is the door SPEC.md marked shut in two places since
v0.2, and TZELEM was the organ paying for it: `anatomy.py` said so in its own
docstring, that a stroke's spark could carry only a palette INDEX, never a
colour, so the render organ of a holobrain whose law is *everything inside must
be ALMA* carried a receipt for a colour instead of the colour.

So this script paints the same subject twice, from the same planted strokes:

    the BIG frame   — 8K, numpy, the fast body. What a painting looks like.
    the LOOM frame  — the real ALMA loom, at tile resolution, where every
                      tile's colour is the first CHORD to arrive. No palette
                      is consulted. The language itself painted it.

They are the same picture at two resolutions, and the second one is the proof
of the first. `tests/test_organ.py::test_the_colour_travels_the_cord` is the
executable version of the same sentence: halve a cord's weight and the painted
colour halves, which a lookup table physically cannot do.

THE SUBJECT is not a demo scene, and it is not a scene at all in the game sense.
It is FIVE SOLIDS THIS LAB ACTUALLY MADE, standing on a ground under one light:

    mouth-ah.stl        the vocal tract shaped for /ah/   — 192,164 faces
    mouth-ooh.stl       the vocal tract shaped for /ooh/  — 107,816 faces
    silicone-fold-mold  the mould that makes the folds    —  85,964 faces
    THROAT-MOLD-A-real  the throat mould that got printed —      72 faces
    KAV-first-shape     the cube ERAN's own modeller emitted —   12 faces

They are the two vowels ERAN is being built to say, the mould that will make the
folds that say them, and the first shape his own modeller ever emitted — painted
by his own render organ, in the language he is written in. The big meshes are
vertex-clustered down to ~1,500 faces each (`hero8k.decimate`), which keeps a
closed surface: a random face subsample would leave holes, and TZELEM would
faithfully paint the holes.

NOT A REBUILD OF `_deliverables/tzelem-sderot/pipeline/kav_tzelem_8k.py`, which
paints KAV's grammar solids at 8K and stays the right file for that. This one
exists for the LOOM frame: the same strokes painted twice, once by numpy and once
by the actual ALMA loom carrying chords, which is the only reason the subject and
the camera here are different. If all you want is a big picture of KAV's solids,
use that file.

HONEST, BEFORE ANYONE IS MISLED:
  * The 8K frame is painted by numpy, not by the loom. A Python loom cannot run
    33M knots a frame and saying otherwise would be the overselling this lab has
    a law against. The loom frame is small and REAL; the big frame is the same
    semantics in array form, and `test_numpy_colour_is_pinned_to_the_weave`
    refuses to pass unless the two agree exactly at tile resolution.
  * The shading is unchanged Lambert+ambient. Nothing was prettified, because
    `Stage.shade` is the truth gate 1's fidelity number is measured against, and
    making the picture nicer by changing the ruler would delete the measurement.

PC courtesy: BELOW_NORMAL, because on 2026-09-03 a normal-priority render
starved the live KESHEV microphone into 78% empty decodes.
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

try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    _ps = None

import anatomy                                   # noqa: E402
import canvas                                    # noqa: E402
import hero8k                                    # noqa: E402
from meshstage import MeshStage                  # noqa: E402

OUT = os.path.join(_HERE, "out-night")

# The quality dial, and the reason for each number.
#   size 0.011 (was 0.020): a stroke's radius is ANGULAR, so at 8K the old size
#     was ~113 px across — very fat, and detail could not survive it. Halving it
#     is the whole visible difference between "blurry" and "painted".
#   n 14000 (was 2400): coverage goes as n*r^2, so halving r needs ~4x the
#     strokes just to stay as covered. 14000 is denser than before, not equal.
#   plant 960x540 (was 640x360): a stroke can only be anchored where the planting
#     camera has a pixel, so anchor precision was the other ceiling on detail.
N_STROKES = 14_000
SIZE = 0.011
PLANT_W, PLANT_H = 960, 540
TILES = 56                    # the loom frame: 56x56 = 3136 fringe knots


def _rss_mb() -> float:
    return _ps.Process().memory_info().rss / 1e6 if _ps else float("nan")


def save(img: np.ndarray, path: str, quality: int = 95) -> str:
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    if path.lower().endswith((".jpg", ".jpeg")):
        im.save(path, quality=quality, subsampling=0)
    else:
        im.save(path)
    return path


def block_down(img: np.ndarray, target_w: int) -> np.ndarray:
    """Exact block average to roughly target_w. No resampling filter, no lies."""
    k = max(1, img.shape[1] // target_w)
    h, w = img.shape[0] // k * k, img.shape[1] // k * k
    return img[:h, :w].reshape(h // k, k, w // k, k, 3).mean(axis=(1, 3))


def upscale(img: np.ndarray, k: int) -> np.ndarray:
    """Nearest-neighbour blow-up, so a tile stays a visible square and nobody
    can mistake a smoothing filter for detail the loom did not have."""
    return np.repeat(np.repeat(img, k, axis=0), k, axis=1)


# ------------------------------------------------------------------- the subject

LARYNX = os.path.join("D:", os.sep, "CLAUDE", "alma-larynx")
KAV_STL = os.path.abspath(os.path.join(_HERE, "..", "kav", "KAV-first-shape.stl"))

# name, file, world height, (x, z), rotation about y, albedo
# Heights and places are chosen so nothing occludes another object's silhouette
# entirely — an occlusion the camera cannot see through teaches the eye nothing
# about the shape underneath it.
PIECES = [
    ("mouth_ah",  os.path.join(LARYNX, "mouth-ah.stl"),
     1.60, (-2.55, 0.75), 0.55, (0.86, 0.42, 0.24)),       # warm terracotta
    ("fold_mould", os.path.join(LARYNX, "silicone-fold-mold.stl"),
     1.35, (-1.05, -1.15), -0.35, (0.34, 0.48, 0.74)),     # slate blue
    ("kav_cube",  KAV_STL,
     1.00, (-0.20, 1.55), 0.70, (0.58, 0.28, 0.40)),       # plum, nearest the eye
    ("mouth_ooh", os.path.join(LARYNX, "mouth-ooh.stl"),
     1.75, (1.35, -0.45), -0.95, (0.18, 0.46, 0.45)),      # deep teal
    ("throat_a",  os.path.join(LARYNX, "THROAT-MOLD-A-real.stl"),
     1.05, (2.35, 0.80), 0.85, (0.80, 0.73, 0.54)),        # bone
]

GROUND_ALBEDO = (0.62, 0.60, 0.55)


def subject_night(target_faces: int = 1500):
    """The five solids + a ground, as one triangle soup with per-face colour."""
    gnd = hero8k.ground(11.0)
    tris = [gnd]
    alb = [np.tile(GROUND_ALBEDO, (len(gnd), 1))]
    counts = {"ground": len(gnd)}
    for name, path, height, xz, rot, colour in PIECES:
        raw = hero8k.read_stl(path)
        m = hero8k.decimate(raw, target_faces) if len(raw) > target_faces else raw
        m = hero8k._fit(m, height, centre_xz=xz, rot_y=rot)
        tris.append(m)
        alb.append(np.tile(colour, (len(m), 1)))
        counts[name] = len(m)
    return np.concatenate(tris), np.concatenate(alb), counts


def night_camera(width: int, height: int):
    """One fixed camera — a Sierra quest's camera. The same view at every size.

    Pulled back and raised from `hero8k.hero_camera` because the subject is now
    five objects across ~5 world units instead of two across ~2.5.
    """
    from stage import Camera
    return Camera(eye=np.array([1.55, 2.35, 5.70]),
                  target=np.array([-0.10, 0.80, 0.05]),
                  width=width, height=height, fov_deg=40.0)


def main(do_8k: bool = True) -> dict:
    t_all = time.time()
    os.makedirs(OUT, exist_ok=True)
    rec: dict = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 # TZ-4: which painter made every number below.
                 "painter": canvas.source_hashes(),
                 # TZ-9: what was ASKED for, beside what was planted. `strokes` alone
                 # cannot tell a full painting from one that got 3% of its brush.
                 "strokes_asked": N_STROKES,
                 "strokes": N_STROKES, "size": SIZE,
                 "plant": [PLANT_W, PLANT_H], "tiles": TILES, "made": {}}

    tris, alb, counts = subject_night()
    rec["counts"] = counts
    print(f"subject: {len(tris)} triangles {counts}", flush=True)

    stage = MeshStage(tris, albedo=(0.60, 0.58, 0.53), face_albedo=alb,
                      light_dir=(-0.45, -1.0, -0.30), ambient=0.30)

    t0 = time.time()
    strokes = anatomy.scatter(stage, night_camera(PLANT_W, PLANT_H),
                              n=N_STROKES, seed=7, size=SIZE)
    rec["plant_seconds"] = round(time.time() - t0, 1)
    rec["strokes"] = int(len(strokes))          # TZ-9: what was actually planted
    print(f"planted {len(strokes)} strokes from {PLANT_W}x{PLANT_H} "
          f"in {rec['plant_seconds']}s  (rss {_rss_mb():.0f} MB)", flush=True)

    # ---------------------------------------------------------- the LOOM frame
    # The real ALMA loom. Every tile's colour is the first CHORD to arrive.
    # The SAME framing as the big frames (16:9), so the loom picture is that
    # picture and not a different one. A tile therefore covers a WIDE rectangle
    # of canvas, and the blow-up below is anisotropic to put the aspect back —
    # 32x18 is 16:9 to within half a percent.
    cam_loom = night_camera(1920, 1080)
    t0 = time.time()
    loom_img = anatomy.paint_tiles_weave_colour(strokes, cam_loom, tiles=TILES)
    rec["loom_seconds"] = round(time.time() - t0, 1)
    # the pin: numpy must give the loom's exact picture, or one of them is lying
    numpy_img = anatomy.paint_tiles_numpy_colour(strokes, cam_loom, tiles=TILES)
    rec["loom_pinned_to_numpy"] = bool(np.array_equal(loom_img, numpy_img))
    lit = ~np.all(np.isclose(loom_img, (0.82, 0.87, 0.94)), axis=-1)
    rec["loom_tiles_painted"] = int(lit.sum())
    rec["loom_tiles_total"] = TILES * TILES
    rec["loom_distinct_colours"] = int(len(np.unique(
        loom_img.reshape(-1, 3), axis=0)))
    print(f"LOOM: {rec['loom_tiles_painted']}/{TILES*TILES} tiles painted, "
          f"{rec['loom_distinct_colours']} distinct colours, "
          f"pinned={rec['loom_pinned_to_numpy']}, {rec['loom_seconds']}s",
          flush=True)
    if not rec["loom_pinned_to_numpy"]:
        raise SystemExit("the loom and numpy disagree — refusing to publish")
    big_loom = np.repeat(np.repeat(loom_img, 18, axis=0), 32, axis=1)
    rec["made"]["loom"] = save(big_loom,
                               os.path.join(OUT, "TZELEM-night-LOOM.png"))

    # -------------------------------------------------------------- the frames
    peak = _rss_mb()
    for name, w, h in ([("4K", 3840, 2160)] +
                       ([("8K", 7680, 4320)] if do_8k else [])):
        cam = night_camera(w, h)
        t0 = time.time()
        img = canvas.render(stage, cam, strokes, style="painterly", seed=17,
                            out_dtype=np.float32)
        dt = time.time() - t0
        peak = max(peak, _rss_mb())
        p = save(img, os.path.join(OUT, f"TZELEM-night-{name}.png"))
        rec["made"][name] = {"path": p, "seconds": round(dt, 1),
                             "mb": round(os.path.getsize(p) / 1e6, 2),
                             "rss_mb": round(_rss_mb())}
        print(f"{name} painted in {dt:.1f}s -> {os.path.getsize(p)/1e6:.1f} MB "
              f"(rss {_rss_mb():.0f} MB)", flush=True)

        if name == ("8K" if do_8k else "4K"):
            H, W = img.shape[:2]
            cy, cx = int(H * 0.47), int(W * 0.42)
            rec["made"]["crop"] = save(
                img[cy - 500:cy + 500, cx - 500:cx + 500],
                os.path.join(OUT, "TZELEM-night-CROP1000-1to1.png"))
            rec["made"]["view"] = save(
                block_down(img, 1920),
                os.path.join(OUT, "TZELEM-night-VIEW-1920.jpg"))
        del img

    rec["peak_rss_mb"] = round(peak)
    rec["total_seconds"] = round(time.time() - t_all, 1)
    with open(os.path.join(OUT, "night.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    print(f"peak rss {peak:.0f} MB, total {rec['total_seconds']}s", flush=True)
    return rec


if __name__ == "__main__":
    main(do_8k="--no8k" not in sys.argv)
