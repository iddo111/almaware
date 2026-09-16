"""TZELEM / צלם — GATE 2: the same painting, at any resolution.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

THE CLAIM GATE 2 EXISTS TO TEST
-------------------------------
An upscaler makes a bigger FILE. A resolution-free organ makes a bigger PAINTING:
the same strokes, in the same places, with crisp edges, because a stroke's size is
in the WORLD and the canvas only decides how many pixels a world unit covers.

So the test is not "does 8K look nice". It is:

  (a) OWNERSHIP AGREEMENT — render at 480x270 and at 3840x2160, take the majority
      stroke of every 8x8 block of the 4K ownership map, and demand it names the
      same stroke the native 480p frame does, for >= 95% of pixels. If the organ
      were resolution-DEPENDENT the two would disagree at every edge.
  (b) FIDELITY DOES NOT DECAY — MSE against the shaded truth at 4K must not be
      worse than at 480p by more than 10%. A painting that only works small is a
      painting that was hiding behind its own pixels.

Numpy only. No torch on the PC.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import canvas                       # noqa: E402
from anatomy import scatter         # noqa: E402
from palette import Palette         # noqa: E402
from stage import Stage, orbit      # noqa: E402

# PC courtesy (2026-09-03 scar: renders starved the KESHEV mic): run below normal priority.
try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass


BASE_W, BASE_H = 480, 270


# ------------------------------------------------------------------ helpers

def plant(stage, n: int = 1800, seed: int = 7, step: float = 0.0,
          size: float = 0.020, w: int = BASE_W, h: int = BASE_H):
    """Plant the strokes ONCE, on a 480p view. Every resolution re-sees these."""
    return scatter(stage, orbit(step, w, h), n=n, seed=seed, size=size)


def block_mode(a: np.ndarray, k: int) -> np.ndarray:
    """Majority value of every k x k block. The ownership map's 'block average'.

    Averaging stroke INDICES would be meaningless (index 3 and index 5 do not
    average to index 4), so the honest downsample of an ownership map is the
    majority vote.
    """
    h, w = a.shape
    b = a[:h - h % k, :w - w % k]
    hh, ww = b.shape[0] // k, b.shape[1] // k
    blocks = (b.reshape(hh, k, ww, k).transpose(0, 2, 1, 3)
              .reshape(hh * ww, k * k))
    srt = np.sort(blocks, axis=1)
    kk = k * k
    idx = np.arange(kk)
    start_mark = np.ones_like(srt, dtype=bool)
    start_mark[:, 1:] = srt[:, 1:] != srt[:, :-1]
    start = np.maximum.accumulate(np.where(start_mark, idx, 0), axis=1)
    end_mark = np.ones_like(srt, dtype=bool)
    end_mark[:, :-1] = srt[:, :-1] != srt[:, 1:]
    end = np.minimum.accumulate(np.where(end_mark, idx, kk - 1)[:, ::-1],
                                axis=1)[:, ::-1]
    run = end - start + 1
    pick = np.argmax(run, axis=1)
    return srt[np.arange(srt.shape[0]), pick].reshape(hh, ww)


def block_mean(img: np.ndarray, k: int) -> np.ndarray:
    """Honest box downsample of a colour image."""
    h, w = img.shape[:2]
    b = img[:h - h % k, :w - w % k]
    hh, ww = b.shape[0] // k, b.shape[1] // k
    return b.reshape(hh, k, ww, k, 3).mean(axis=(1, 3))


def _mse(a, b) -> float:
    return float(((a - b) ** 2).mean())


# ------------------------------------------------------------- the measurement

PASS_OWNERSHIP = 0.95      # hand-picked 2026-09-01; see `spread()` below (TZ-16)
PASS_FIDELITY = 1.10       # hand-picked 2026-09-01


def spread(n_strokes: int = 1800, factor: int = 8, seeds=(7, 11, 13),
           angles=(0.0, 4.0, 8.0), style: str = "painterly",
           verbose: bool = True) -> dict:
    """THE SAME MEASUREMENT, MANY TIMES -- so the pass bars can state a distance.

    REVISION 2026-09-06 (TZ-16). `resolution_free` measures ONE seed at ONE camera
    pose, and its two bars (0.95 and 1.10) are bare constants, so nothing anywhere
    could say whether the stored 0.98831 agreement was one sigma from failing or ten.
    Gate 1 has had `ruler.sweep` reporting mean/std/min/max over five frames since the
    day it was written; this is gate 2's. Run it and the bar becomes demonstrated
    rather than chosen.

    DELIBERATELY not run by `__main__`: at factor 8 every sample is a 4K render, so
    the caller pays knowingly. `factor=2` over a few seeds already shows the spread.
    """
    runs = []
    for a in angles:
        for sd in seeds:
            runs.append(resolution_free(n_strokes=n_strokes, factor=factor, seed=sd,
                                        style=style, verbose=False, start_deg=a))

    def agg(key):
        v = np.array([r[key] for r in runs], dtype=float)
        return {"mean": float(v.mean()), "std": float(v.std()),
                "min": float(v.min()), "max": float(v.max()), "n": int(v.size)}

    own, fid = agg("ownership_agreement"), agg("fidelity_ratio")
    out = {"samples": len(runs), "seeds": list(seeds), "angles": list(angles),
           "factor": factor, "ownership_agreement": own, "fidelity_ratio": fid,
           "bars": {"ownership": PASS_OWNERSHIP, "fidelity": PASS_FIDELITY},
           "sigmas_from_bar": {
               "ownership": ((own["mean"] - PASS_OWNERSHIP) / own["std"]
                             if own["std"] > 0 else float("inf")),
               "fidelity": ((PASS_FIDELITY - fid["mean"]) / fid["std"]
                            if fid["std"] > 0 else float("inf"))},
           "painter": canvas.source_hashes(),
           "per_run": runs}
    if verbose:
        print(f"  ownership {own['mean']:.5f} +- {own['std']:.5f} over {own['n']} "
              f"samples  ({out['sigmas_from_bar']['ownership']:.1f} sigma above "
              f"the {PASS_OWNERSHIP} bar)")
        print(f"  fidelity ratio {fid['mean']:.5f} +- {fid['std']:.5f}  "
              f"({out['sigmas_from_bar']['fidelity']:.1f} sigma below "
              f"the {PASS_FIDELITY} bar)")
    return out


def resolution_free(n_strokes: int = 1800, factor: int = 8, seed: int = 7,
                    style: str = "painterly", verbose: bool = True,
                    start_deg: float = 0.0) -> dict:
    """Render the SAME strokes small and large; report the two gate-2 numbers."""
    stage = Stage()
    strokes = plant(stage, n=n_strokes, seed=seed)
    small = orbit(start_deg, BASE_W, BASE_H)
    big = orbit(start_deg, BASE_W * factor, BASE_H * factor)

    # REVISION 2026-09-06 (TZ-12): this used to call canvas.ownership and then
    # canvas.render, and render calls ownership again internally -- so the splat loop
    # over every stroke's bounding box ran TWICE per resolution for one answer
    # (measured at 480x360: ownership 1.42 s against a 2.47 s render, ~37% of the
    # pair; 5-6 s of every gate 2 run at 4K). render now hands back the map it
    # already built. The numbers are identical; only the clock moves.
    t0 = time.time()
    img_s, own_s = canvas.render(stage, small, strokes, style=style,
                                 return_owner=True)
    t_small = time.time() - t0

    t0 = time.time()
    img_b, own_b = canvas.render(stage, big, strokes, style=style,
                                 return_owner=True)
    t_big = time.time() - t0

    own_b_down = block_mode(own_b, factor)
    agree = float((own_b_down == own_s).mean())

    truth_s = stage.shade(stage.gbuffer(small))
    truth_b = stage.shade(stage.gbuffer(big))
    fid_s = _mse(img_s, truth_s)
    fid_b = _mse(img_b, truth_b)

    out = {
        "strokes": int(len(strokes)),
        "small": [BASE_W, BASE_H], "big": [BASE_W * factor, BASE_H * factor],
        "style": style,
        "ownership_agreement": agree,
        "fidelity_small": fid_s,
        "fidelity_big": fid_b,
        "fidelity_ratio": fid_b / max(fid_s, 1e-12),
        "seconds_small": t_small, "seconds_big": t_big,
        "start_deg": start_deg, "seed": seed,
        "pass_ownership": agree >= PASS_OWNERSHIP,
        "pass_fidelity": fid_b <= fid_s * PASS_FIDELITY,
        # TZ-4: WHICH PAINTER produced these numbers.
        "painter": canvas.source_hashes(),
        # TZ-16: ONE seed at ONE pose. `spread()` is what turns these bars into a
        # measured distance; until someone runs it the margin is unknown.
        "samples": 1,
    }
    if verbose:
        print(f"  strokes {out['strokes']}  style {style}")
        print(f"  ownership agreement 480p vs 4K-majority : {agree * 100:.2f}%"
              f"   ({'PASS' if out['pass_ownership'] else 'FAIL'} >= "
              f"{PASS_OWNERSHIP * 100:.0f}%, ONE sample -- run spread() for a margin)")
        print(f"  fidelity MSE  480p {fid_s:.5f}   4K {fid_b:.5f}"
              f"   ratio {out['fidelity_ratio']:.3f}"
              f"   ({'PASS' if out['pass_fidelity'] else 'FAIL'} <= 1.10)")
        print(f"  wall clock    480p {t_small:.2f}s   4K {t_big:.2f}s")
    return out


# ------------------------------------------------------------------- timings

RESOLUTIONS = [("480p", 480, 270), ("1080p", 1920, 1080),
               ("4K", 3840, 2160), ("8K", 7680, 4320)]


def _rss_mb(peak: bool = True) -> float:
    """Resident set of THIS process in MB. `peak` = peak_wset, else the current rss.

    A silent 0 MB is a broken window, so this raises rather than guesses: the first
    hand-rolled ctypes version returned 0 for every resolution and would have put a
    column of zeros in the plan.
    """
    import psutil
    mi = psutil.Process().memory_info()
    return (mi.peak_wset if peak else mi.rss) / 1e6


def bench(n_strokes: int = 1800, seed: int = 7, style: str = "painterly",
          which=None) -> list[dict]:
    """Wall clock and peak resident memory per resolution, on this PC, measured.

    Deliberately NOT under tracemalloc: tracing every allocation cost 3x at 480p
    and turned the small end of the table into a measurement of the profiler.
    """
    stage = Stage()
    strokes = plant(stage, n=n_strokes, seed=seed)
    rows = []
    for name, w, h in (which or RESOLUTIONS):
        cam = orbit(0.0, w, h)
        # TZ-13 (2026-09-06): `peak_wset` is the peak over the WHOLE process lifetime
        # and is monotone, so each row silently carried every earlier row's peak --
        # visible in the stored gate2.json, where the 4K row's rss_before_mb is
        # exactly the 1080p row's peak_rss_mb. The table only read correctly because
        # the loop happens to run smallest-first; bench(which=[('8K',..),('480p',..)])
        # reported 2 GB for 480p. A row's OWN cost is the delta over its own start.
        before = _rss_mb(peak=False)
        process_peak_before = _rss_mb()
        t0 = time.time()
        img = canvas.render(stage, cam, strokes, style=style)
        dt = time.time() - t0
        peak = _rss_mb()
        rows.append({"name": name, "w": w, "h": h, "seconds": dt,
                     "mpix": w * h / 1e6,
                     "row_peak_rss_mb": max(peak - before, 0.0),
                     "process_peak_rss_mb": peak,
                     "process_peak_before_mb": process_peak_before,
                     "rss_before_mb": before,
                     "px_per_s": w * h / max(dt, 1e-9)})
        print(f"  {name:>6}  {w}x{h:<5}  {dt:7.2f} s   "
              f"{w * h / 1e6:6.2f} Mpx   this row {max(peak - before, 0.0):7.1f} MB "
              f"(process peak {peak:7.1f} MB)   "
              f"{w * h / max(dt, 1e-9) / 1e6:6.2f} Mpx/s")
        del img
    return rows


if __name__ == "__main__":
    import json

    print("TZELEM gate 2 — resolution-free")
    r = resolution_free()
    print("\ntimings")
    rows = bench()
    with open(os.path.join(_HERE, "out", "gate2.json"), "w", encoding="utf-8") as f:
        json.dump({"resolution_free": r, "timings": rows}, f,
                  indent=2, ensure_ascii=False)
    print("\nwrote out/gate2.json")
