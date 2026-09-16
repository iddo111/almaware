# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

HOW MANY MILLIMETRES IS ONE PIXEL OF IDDO'S FOOTAGE?

A texture is worthless without a physical size. A brick photographed at an unknown
distance is not a brick, it is a pattern. So before a single material is harvested,
every source patch gets a MEASURED mm-per-pixel, and it is measured the way a
machinist measures: against a rule that is IN THE SHOT.

Iddo filmed a 150 mm steel rule lying on his polished desk (frames/f0008.jpg).
`scene.json`'s own calibration used that rule's 1 cm..13 cm graduations and got
403.0376 mm per model unit at 0.49 mm RMS. This file does NOT reuse that number —
it measures the graduations again, straight off the pixels, so texture scale
inherits no error from the 3D reconstruction.

THE METHOD, and the two things that had to be got right
--------------------------------------------------------
1. **Autocorrelation, not a spectral peak.** The graduations are a comb: a short
   tick every 1 mm, a longer one every 5, the longest every 10. A single FFT peak
   picks whichever harmonic is strongest — measured here, that is the 5 mm tick,
   at exactly 5x the truth, and it looked perfectly convincing. The FIRST peak of
   the autocorrelation is the fundamental by construction, and it cannot be a
   harmonic of anything.

2. **The band has to sit on the ENGRAVING.** Down the middle of the rule are the
   printed digits, which are not periodic; the ticks live at the edges. So the
   estimator scans perpendicular offsets and keeps the one whose autocorrelation
   peak is strongest. Measured on f0008: offsets -30..-15 px and +30 px give a
   6.00 px peak at correlation 0.72-0.83, and offsets through the digits give
   noise at the 2.5 px sampling limit.

WHAT THE MEASUREMENT FOUND
--------------------------
The pitch is 5.96 px/mm and it is CONSTANT to 0.3% over the 700 px of rule that is
in shot (six of eight windows: 5.949, 5.953, 5.964, 5.966, 5.969, 5.965). I had
expected perspective foreshortening to make it vary by 20% along the rule and
built a windowed estimator for that reason; the measurement says the rule lies
close enough to fronto-parallel that it does not. The windowing stayed anyway,
because it is what PROVED the constancy and it is what catches the two windows
that lock onto the wrong tooth of the comb (11.02 = the 2 mm tick, 2.93 = half).

So: **one pixel of f0008 is 0.1677 mm on the desk surface** (5.963 px/mm), and a
512 px patch is 85.9 mm of real desk.

CROSS-CHECK (independent of everything above): the printed digits "3" and "15" on
f0008 sit at x = 15 px and x = 715 px, i.e. 120.0 mm over 700 px = 5.83 px/mm.
The autocorrelation says 6.00. They agree to 2.9%, which is the uncertainty this
calibration is reported with.

Numpy + PIL only.
"""
from __future__ import annotations

# TZ-8 (2026-09-06): FIRST, BEFORE NUMPY. Caps the BLAS/OpenMP thread pools (they
# size themselves once, at numpy import) and drops this process's priority. The
# materials track had NO nice, no priority class and no thread cap anywhere while
# every other TZELEM entry point has set BELOW_NORMAL since the 2026-09-03 KESHEV
# starvation — and it was run on eran1, the box that serves ERAN's live microphone.
import courtesy                                             # noqa: E402,F401

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOM3D = r"D:\CLAUDE\_deliverables\room3d"

SAMPLES_PER_PX = 4.0          # profile oversampling; the pitch is ~6 px
MIN_PITCH_PX = 3.0            # below this the graduations are not resolved
MAX_PITCH_PX = 20.0


# ------------------------------------------------------------------ the rule

def rule_mask(rgb: np.ndarray, vmin: float = 140.0, smax: float = 0.22) -> np.ndarray:
    """Bright AND unsaturated: that is steel, and it is not the wood around it."""
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    return (mx > vmin) & (sat < smax)


def rule_axis(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """PCA of the mask. Returns (centre_xy, unit_dir, t_lo, t_hi) in pixels."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 200:
        raise ValueError("no rule found in this crop")
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    c = pts.mean(axis=0)
    _u, _s, vt = np.linalg.svd(pts - c, full_matrices=False)
    d = vt[0] / np.linalg.norm(vt[0])
    t = (pts - c) @ d
    return c, d, float(np.percentile(t, 1.0)), float(np.percentile(t, 99.0))


def line_profile(g: np.ndarray, c: np.ndarray, d: np.ndarray, t: np.ndarray,
                 offset: float) -> np.ndarray:
    """One scan line parallel to the rule axis, `offset` px to its side."""
    p = np.array([-d[1], d[0]])
    x = c[0] + d[0] * t + p[0] * offset
    y = c[1] + d[1] * t + p[1] * offset
    xi = np.clip(np.rint(x), 0, g.shape[1] - 1).astype(np.int64)
    yi = np.clip(np.rint(y), 0, g.shape[0] - 1).astype(np.int64)
    return g[yi, xi]


# ------------------------------------------------------- the pitch, from lag 0 up

def autocorr(x: np.ndarray) -> np.ndarray:
    x = x - x.mean()
    s = x.std()
    if s < 1e-9:
        return np.zeros_like(x)
    x = x / s
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    return np.fft.irfft(np.abs(f) ** 2, 2 * n)[:n] / n


def first_peak(prof: np.ndarray, step_px: float) -> tuple[float, float]:
    """(pitch in px, correlation) of the FIRST autocorrelation peak past the floor.

    The fundamental, by construction: a comb of period p has its first
    autocorrelation maximum at p, whatever the relative height of its harmonics.
    """
    a = autocorr(prof)
    lag = np.arange(len(a)) * step_px
    sel = (lag >= MIN_PITCH_PX) & (lag <= MAX_PITCH_PX)
    if not sel.any():
        return 0.0, 0.0
    idx = np.nonzero(sel)[0]
    k = idx[int(np.argmax(a[idx]))]
    # parabolic refinement between neighbouring lags
    if 0 < k < len(a) - 1:
        y0, y1, y2 = a[k - 1], a[k], a[k + 1]
        dk = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-30)
        dk = float(np.clip(dk, -1.0, 1.0))
    else:
        dk = 0.0
    return float((k + dk) * step_px), float(a[k])


def best_offset(g, c, d, t, offsets) -> tuple[float, float, float]:
    """Which side-offset actually sits on the engraving. (offset, pitch, corr)."""
    best = (0.0, 0.0, -1.0)
    for o in offsets:
        pr = line_profile(g, c, d, t, o)
        p, r = first_peak(pr, float(t[1] - t[0]))
        if r > best[2] and p > 0:
            best = (float(o), p, r)
    return best


def windowed(g, c, d, t_lo, t_hi, offsets, win_px=280.0, stride_px=70.0) -> list[dict]:
    """px/mm as a function of position along the rule. Perspective is measured."""
    out = []
    t0 = t_lo
    while t0 + win_px <= t_hi + 1e-9:
        t = np.linspace(t0, t0 + win_px, int(win_px * SAMPLES_PER_PX))
        o, p, r = best_offset(g, c, d, t, offsets)
        out.append({"t_centre": t0 + win_px * 0.5, "offset_px": o,
                    "px_per_mm": p, "corr": r})
        t0 += stride_px
    return out


def calibrate(path, crop, name, vmin=140.0, smax=0.22,
              offsets=range(-34, 35, 2), min_corr: float = 0.45) -> dict:
    with Image.open(path) as im:
        sub = im.crop(crop)
        rgb = np.asarray(sub.convert("RGB"), dtype=np.float64)
        g = np.asarray(sub.convert("L"), dtype=np.float64)
    m = rule_mask(rgb, vmin, smax)
    c, d, t_lo, t_hi = rule_axis(m)
    win = windowed(g, c, d, t_lo, t_hi, list(offsets))
    # HARMONIC REJECTION, and it is not cosmetic. Measured on f0008: six of eight
    # windows agree to 0.3% at 5.96 px/mm, one locks on 11.02 (the 2 mm tick, where
    # the offset landed off the fine engraving) and one on 2.93 (half). Both have
    # HIGH correlation — a harmonic always does — so `corr` alone cannot catch them.
    # The robust median can: a window more than 20% from it is a lock on the wrong
    # tooth of the comb, and it is dropped rather than averaged in.
    ok = [w for w in win if w["corr"] >= min_corr and w["px_per_mm"] > 0]
    if len(ok) < 2:
        return {"name": name, "verdict": "REFUSED",
                "reason": f"only {len(ok)} windows above corr {min_corr}"}
    med0 = float(np.median([w["px_per_mm"] for w in ok]))
    good = [w for w in ok if abs(w["px_per_mm"] / med0 - 1.0) <= 0.20]
    for w in win:
        w["used"] = bool(w in good)
    if len(good) < 2:
        return {"name": name, "verdict": "REFUSED", "reason": "no consistent pitch"}
    p = np.array([w["px_per_mm"] for w in good])
    return {
        "name": name, "frame": os.path.basename(path), "crop": list(crop),
        "axis_deg": float(np.degrees(np.arctan2(d[1], d[0]))),
        "centre_xy_in_crop": [float(c[0]), float(c[1])],
        "crop_origin_xy": [int(crop[0]), int(crop[1])],
        "t_range_px": [t_lo, t_hi],
        "px_per_mm_median": float(np.median(p)),
        "px_per_mm_min": float(p.min()), "px_per_mm_max": float(p.max()),
        "spread": float(p.max() / p.min()),
        "windows": win, "min_corr": min_corr,
        "n_good_windows": len(good), "n_windows": len(win),
        "verdict": "PASS",
    }


def px_per_mm_at(cal: dict, xy_full_frame) -> float:
    """The LOCAL px/mm at a full-frame pixel, along the rule's own axis.

    Outside the measured span this clamps to the nearest window rather than
    extrapolating — a linear extrapolation of a perspective curve is a guess
    wearing a number's clothes.
    """
    ox, oy = cal["crop_origin_xy"]
    c = np.array(cal["centre_xy_in_crop"])
    a = np.radians(cal["axis_deg"])
    d = np.array([np.cos(a), np.sin(a)])
    q = np.asarray(xy_full_frame, dtype=np.float64) - np.array([ox, oy])
    t = float((q - c) @ d)
    good = [w for w in cal["windows"] if w.get("used")]
    ts = np.array([w["t_centre"] for w in good])
    ps = np.array([w["px_per_mm"] for w in good])
    o = np.argsort(ts)
    return float(np.interp(t, ts[o], ps[o]))        # np.interp clamps at the ends


TARGETS = [
    (os.path.join(ROOM3D, "frames", "f0008.jpg"), (0, 880, 900, 1020),
     "desk_f0008", 140.0, 0.22),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = []
    for path, crop, name, vmin, smax in TARGETS:
        if not os.path.exists(path):
            print(f"  MISSING {path}")
            continue
        try:
            r = calibrate(path, crop, name, vmin, smax)
        except Exception as e:                     # noqa: BLE001
            r = {"name": name, "verdict": "REFUSED", "reason": repr(e)}
        out.append(r)
        if r["verdict"] != "PASS":
            print(f"{name:16s} REFUSED  {r.get('reason')}")
            continue
        print(f"{r['name']:14s} {r['frame']}  px/mm median {r['px_per_mm_median']:6.3f}"
              f"  range {r['px_per_mm_min']:.2f}..{r['px_per_mm_max']:.2f}"
              f"  spread {r['spread']:.2f}x"
              f"  ({r['n_good_windows']}/{r['n_windows']} windows)  {r['verdict']}")
        for w in r["windows"]:
            flag = "*" if w.get("used") else " REJECTED (harmonic)"
            print(f"      t{w['t_centre']:+7.0f}  off{w['offset_px']:+5.0f}"
                  f"  {w['px_per_mm']:6.3f} px/mm  corr {w['corr']:.3f} {flag}")
    with open(os.path.join(HERE, "calibration.json"), "w", encoding="utf-8") as fh:
        json.dump({"measurements": out,
                   "scene_json_mm_per_model_unit": 403.03764472995397,
                   "cross_check_digits_3_to_15": {"span_mm": 120.0, "span_px": 700,
                                                  "px_per_mm": 5.833},
                   "method": "first autocorrelation peak of a scan line on the "
                             "engraving, windowed along the rule's PCA axis so "
                             "perspective is measured and not assumed"},
                  fh, indent=1)
    print("\nwrote calibration.json")


if __name__ == "__main__":
    main()
