# -*- coding: utf-8 -*-
"""Formant measurement on ant exemplars.

Two questions:
  1. the headline -- find each ant's MOST VOWEL-LIKE exemplar
     (periodicity x low-band-energy ratio) and measure F1/F2 by LPC.
  2. the vowel space -- the top N most-periodic exemplars, placed on an F1/F2
     chart against the five Hebrew vowel regions.

CALIBRATION (this is why the estimator is defined the way it is).
The brief's BEFORE values are ant-a 660/1064, ant-b 392/1948, ant-c 348/1332,
ant-d 660/1064. Running the selection rule below on state/ant-*/current.json
picks units 8/40/49/12 and their two lowest LPC poles are

    ant-a  659.6 (bw  42)  1064.3 (bw 447)
    ant-b  392.4 (bw  17)  1948.2 (bw 595)
    ant-c  348.3 (bw  94)  1332.4 (bw  43)
    ant-d  659.6 (bw  42)  1064.3 (bw 447)

i.e. all four BEFORE values reproduce exactly, with NO bandwidth gate. A
bandwidth gate would have thrown away ant-a's 1064 Hz pole and ant-b's 1948 Hz
pole and produced different, non-comparable numbers. So `PRIMARY` = two lowest
poles in 200-5000 Hz, no bandwidth gate. `bw<400` is kept alongside as a
robustness column, not as the headline.

levinson() is imported unchanged from the corpus-side scanner so the ant
numbers and the corpus numbers come out of one implementation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus-big" / "human" / "scripts"))
from formants import levinson  # noqa: E402

SR = 16000
ORDER = 12

# /a/ acceptance window used by the original diagnosis.
A_F1 = (650.0, 850.0)
A_F2 = (1000.0, 1400.0)

# Hebrew five-vowel regions. Centres are standard adult-male Modern Hebrew
# values; boxes are deliberately wide because a 25 ms exemplar gives one noisy
# LPC estimate, not a careful average over many tokens.
VOWELS = {
    "a": {"f1": (600, 900), "f2": (1000, 1500), "centre": (700, 1250)},
    "e": {"f1": (400, 620), "f2": (1700, 2300), "centre": (490, 1980)},
    "i": {"f1": (230, 420), "f2": (2000, 2900), "centre": (300, 2350)},
    "o": {"f1": (400, 620), "f2": (700, 1150), "centre": (510, 900)},
    "u": {"f1": (230, 420), "f2": (600, 1150), "centre": (330, 850)},
}


def lpc_poles(frame: np.ndarray, order: int = ORDER):
    """All positive-frequency LPC poles as (freq_hz, bandwidth_hz), f-sorted."""
    x = frame - frame.mean()
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])      # pre-emphasis
    x = x * np.hamming(len(x))
    r = np.correlate(x, x, "full")[len(x) - 1:len(x) + order]
    if r[0] <= 1e-12:
        return None
    a = levinson(r / r[0], order)
    if a is None:
        return None
    try:
        rts = np.roots(a)
    except Exception:
        return None
    rts = rts[np.imag(rts) > 0]
    if len(rts) == 0:
        return None
    f = np.angle(rts) * SR / (2 * np.pi)
    bw = -0.5 * (SR / (2 * np.pi)) * np.log(np.abs(rts) + 1e-12)
    o = np.argsort(f)
    return f[o], bw[o]


def formants_primary(frame):
    """BEFORE-compatible: two lowest poles in 200-5000 Hz, no bandwidth gate."""
    p = lpc_poles(frame)
    if p is None:
        return None
    f, _ = p
    f = f[(f > 200) & (f < 5000)]
    return f[:3] if len(f) >= 2 else None


def formants_bwgated(frame, max_bw=400.0):
    """Robustness variant: same, but only poles narrower than max_bw."""
    p = lpc_poles(frame)
    if p is None:
        return None
    f, bw = p
    keep = (f > 200) & (f < 5000) & (bw < max_bw)
    f = f[keep]
    return f[:3] if len(f) >= 2 else None


def periodicity(frame: np.ndarray) -> float:
    """Peak normalised autocorrelation over the 62-400 Hz F0 band."""
    d = frame - frame.mean()
    d0 = float(np.dot(d, d))
    if d0 < 1e-12:
        return 0.0
    ac = np.correlate(d, d, "full")[len(d) - 1:]
    lo, hi = 40, min(len(ac), 258)          # 400 Hz .. 62 Hz
    if hi <= lo:
        return 0.0
    return float(ac[lo:hi].max() / d0)


def low_band_ratio(frame: np.ndarray, cutoff_hz: float = 1000.0) -> float:
    """Share of spectral power below `cutoff_hz`. Vowels are bottom-heavy."""
    x = (frame - frame.mean()) * np.hanning(len(frame))
    power = np.abs(np.fft.rfft(x)) ** 2
    total = float(power.sum())
    if total <= 0:
        return 0.0
    freqs = np.fft.rfftfreq(len(frame), 1.0 / SR)
    return float(power[freqs < cutoff_hz].sum() / total)


def _fmt(f):
    if f is None:
        return (None, None, None)
    return (float(f[0]), float(f[1]),
            float(f[2]) if len(f) >= 3 else None)


def score_exemplars(exemplars: np.ndarray) -> list[dict]:
    """exemplars: (units, frame_samples) int16-valued array."""
    x = np.asarray(exemplars, dtype=np.float64) / 32768.0
    rows = []
    for unit in range(len(x)):
        frame = x[unit]
        per = periodicity(frame)
        low = low_band_ratio(frame)
        f1, f2, f3 = _fmt(formants_primary(frame))
        g1, g2, _ = _fmt(formants_bwgated(frame))
        rows.append({
            "unit": unit,
            "periodicity": per,
            "low_band_ratio": low,
            "vowel_score": per * low,
            "rms": float(np.sqrt(np.mean(frame ** 2))),
            "f1": f1, "f2": f2, "f3": f3,
            "f1_bwgated": g1, "f2_bwgated": g2,
        })
    return rows


def is_a(f1, f2) -> bool:
    return (f1 is not None and f2 is not None
            and A_F1[0] <= f1 <= A_F1[1] and A_F2[0] <= f2 <= A_F2[1])


def classify_vowel(f1, f2):
    """Nearest Hebrew vowel region; returns (label, landed_inside_a_box)."""
    if f1 is None or f2 is None:
        return None, False
    inside = [v for v, s in VOWELS.items()
              if s["f1"][0] <= f1 <= s["f1"][1] and s["f2"][0] <= f2 <= s["f2"][1]]
    def d(v):
        c1, c2 = VOWELS[v]["centre"]
        return np.log(f1 / c1) ** 2 + np.log(f2 / c2) ** 2
    if inside:
        return min(inside, key=d), True
    return min(VOWELS, key=d), False


def analyse_checkpoint(path: Path, top_n: int = 12) -> dict:
    ck = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = score_exemplars(np.asarray(ck["exemplars_pcm16"]))
    best = max(rows, key=lambda r: r["vowel_score"])
    by_period = sorted(rows, key=lambda r: -r["periodicity"])[:top_n]
    space = []
    for r in by_period:
        v, inside = classify_vowel(r["f1"], r["f2"])
        space.append({**r, "vowel": v, "inside_box": inside})
    v_best, inside_best = classify_vowel(best["f1"], best["f2"])

    # The headline rule takes ONE argmax out of 256 candidates, so at 256 units
    # it is close to arbitrary among the many frames that score high. This is
    # the fairer question the headline is a proxy for: of the units that are
    # clearly voiced, is there one that lands on /a/, and how close is the best?
    voiced = [r for r in rows if r["periodicity"] > 0.45 and r["f1"] and r["f2"]]
    a_best = None
    if voiced:
        c1, c2 = 750.0, 1200.0          # centre of the /a/ acceptance window
        a_best = min(voiced, key=lambda r: np.log(r["f1"] / c1) ** 2
                     + np.log(r["f2"] / c2) ** 2)
        a_best = {**a_best, "is_a": is_a(a_best["f1"], a_best["f2"])}

    return {
        "checkpoint": str(path),
        "ant": ck.get("ant"),
        "seed": ck.get("seed"),
        "units": ck.get("units"),
        "colony": Path(path).parent.parent.name,
        "headline": {
            "unit": best["unit"],
            "f1": best["f1"], "f2": best["f2"], "f3": best["f3"],
            "f1_bwgated": best["f1_bwgated"], "f2_bwgated": best["f2_bwgated"],
            "periodicity": best["periodicity"],
            "low_band_ratio": best["low_band_ratio"],
            "vowel_score": best["vowel_score"],
            "is_a": is_a(best["f1"], best["f2"]),
            "nearest_vowel": v_best,
            "inside_box": inside_best,
        },
        "best_a_candidate": a_best,
        "vowel_space_top_periodic": space,
        "regions_covered_inside_box": sorted({s["vowel"] for s in space if s["inside_box"]}),
        "regions_nearest": sorted({s["vowel"] for s in space if s["vowel"]}),
        # Coverage over the WHOLE codebook, not just its 12 most periodic units:
        # of the units that are clearly voiced, how many land in each vowel box.
        "voiced_unit_count": len(voiced),
        "vowel_box_counts": {
            v: sum(1 for r in voiced if classify_vowel(r["f1"], r["f2"]) == (v, True))
            for v in VOWELS},
        "a_capable_units": sum(1 for r in rows if is_a(r["f1"], r["f2"])),
        "a_capable_units_periodic": sum(
            1 for r in rows if is_a(r["f1"], r["f2"]) and r["periodicity"] > 0.45),
        "total_units": len(rows),
        "all_units": rows,
    }


def main() -> None:
    out = {str(Path(t)): analyse_checkpoint(Path(t)) for t in sys.argv[1:]}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
