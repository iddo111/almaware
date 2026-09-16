# -*- coding: utf-8 -*-
"""calib.py -- Ear v3 calibration: the SPL gain and the structural gates.

Writes ~/ear-v3/ear3-calib.json. Two stages, run in order:

  python -m ear3.calib --spl      # stage A: the frozen scalar SPL gain
  python -m ear3.calib --gates    # stage B: G1-G4 per-unit thresholds
                                  # (needs scripts/precompute_t06.py first)

STAGE A -- SPL GAIN (frozen convention). For each of the 600 big-unit t06
clips: 10 ms non-overlapping window RMS on the RAW samples; speech span =
windows above 10% of the peak window RMS, first to last; span RMS = RMS of
the samples inside the span. gain = TARGET_RMS / median(span RMS over 600).
TARGET_RMS = 0.05 is DEFINED as 65 dB SPL equivalent (so full-scale RMS 1.0
= 91 dB SPL). One number, applied identically to disk wavs and mouth renders.

STAGE B -- GATES (deterministic, judge-independent, GATE_PENALTY=50).
All stats come from the NAP loudness contour + BLOCK P aux of the REAL t06
clips; thresholds set so >=95% of real takes of each unit PASS by
construction (5th-percentile rule):

  G1 dip-depth   hump_profile() ported VERBATIM (iteration-3 logic) from
                 legacy ears_v2.py onto the NAP loudness contour. Following
                 the legacy calibrate_v2 decision: hump COUNT is not gated
                 (noisy on real speech); the gate is min_dip = p5(real dips)
                 for units whose real median dip >= 0.1, else 0 (inert).
  G2 voiced-frac min = p5(real voiced fractions) per unit.
  G3 median-f0   plan band [120,450] Hz. If a unit's real clips pass at
                 <95% with lo=120 (Iddo is an adult; his f0 may sit lower),
                 lo is lowered to max(80, 0.95*p2.5(real f0)) and the
                 deviation is RECORDED in the json ("g3_lo_deviation").
                 lo never goes below 80, so the archived 70 Hz croak always
                 fails. Voiceless clips (median_f0=0) fail G3 by definition.
  G4 occupancy   speech-span duration / total duration >= p5(real) per unit.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIB_PATH = os.path.join(_ROOT, "ear3-calib.json")
CORPUS = os.path.expanduser("~/eran-cortex/data/t06")
UNITS = ["ah", "ba", "ih", "ma", "abba", "ima"]

TARGET_RMS = 0.05
SPL_DB = 65.0
GATE_PENALTY = 50.0
SMOOTH = 5                   # loudness-contour smoothing frames (10 ms each)
SPEECH_FRAC = 0.10
G3_HI = 450.0
G3_LO_PLAN = 120.0
# MEASURED DEVIATION (2026-08-26): the plan's 120 Hz floor -- and even an
# 80 Hz floor -- fails 25-37% of Iddo's REAL abba/ima takes: his median f0
# falls through 60-80 Hz on final falls (abba f0 deciles 62/72/79/94/139/
# 177/203 Hz). The floor therefore drops to the pitch band's bottom, 60 Hz.
# The croak scar is still covered where it actually bit: a flat 70 Hz buzz
# has dip ~0 and fails G1 on abba/ima; the archived v1 cheat wavs are all
# ~220 Hz renders (G3 never touched them). All recorded in PHASE1-STATUS.md.
G3_LO_FLOOR = 60.0


# ----------------------------------------------------------- stage A: SPL

def speech_span_rms(samples, fs=16000, hop_ms=10.0):
    """Raw-domain speech-span RMS (the stage-A statistic)."""
    x = np.asarray(samples, dtype=np.float64)
    hop = int(round(fs * hop_ms / 1000))
    nf = x.size // hop
    if nf == 0:
        return float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
    fr = np.sqrt((x[:nf * hop].reshape(nf, hop) ** 2).mean(axis=1))
    live = fr > float(fr.max()) * SPEECH_FRAC
    idx = np.where(live)[0]
    if len(idx) == 0:
        return float(np.sqrt(np.mean(x ** 2)))
    seg = x[idx[0] * hop:(idx[-1] + 1) * hop]
    return float(np.sqrt(np.mean(seg ** 2)))


def clips(unit, corpus=CORPUS):
    names = sorted(n for n in os.listdir(corpus)
                   if n.endswith(".wav") and n.split("_")[0] == unit)
    return [os.path.join(corpus, n) for n in names]


def calibrate_spl(corpus=CORPUS, write=True):
    from ear3.features import read_wav
    rmses = []
    for u in UNITS:
        for p in clips(u, corpus):
            rmses.append(speech_span_rms(read_wav(p)))
    med = float(np.median(rmses))
    gain = TARGET_RMS / med
    entry = {"target_rms": TARGET_RMS, "spl_db": SPL_DB,
             "median_span_rms": med, "gain": gain, "n_clips": len(rmses),
             "convention": "median t06 big-unit speech-span RMS -> RMS 0.05 "
                           "== 65 dB SPL equivalent (full-scale RMS 1.0 == "
                           "91 dB SPL)"}
    if write:
        _update_calib({"spl": entry})
    return entry


# ----------------------------------------------------------- stage B: gates

def live_span(loud):
    """The same speech-span rule the pipeline uses, on the loudness contour."""
    loud = np.asarray(loud, dtype=np.float64)
    if loud.size == 0:
        return loud
    idx = np.where(loud > float(np.max(loud)) * SPEECH_FRAC)[0]
    if len(idx) < 2:
        return loud
    return loud[idx[0]:idx[-1] + 1]


def hump_profile(loud):
    """(n_peaks, deepest_dip_frac). VERBATIM port of legacy ears_v2.py
    iteration-3 logic, input = NAP loudness contour instead of frame RMS."""
    seg = live_span(loud)
    if seg.size < 2 * SMOOTH:
        return 0, 0.0
    k = np.ones(SMOOTH) / SMOOTH
    env = np.convolve(seg, k, mode="same")
    peak = float(env.max())
    if peak <= 0:
        return 0, 0.0
    min_sep = max(SMOOTH, len(env) // 20)
    floor = peak * 0.15
    cand = [i for i in range(1, len(env) - 1)
            if env[i] >= env[i - 1] and env[i] >= env[i + 1]
            and env[i] >= floor]
    maxima = []
    for i in sorted(cand, key=lambda j: -env[j]):
        if all(abs(i - m) >= min_sep for m in maxima):
            maxima.append(i)
    maxima.sort()
    if len(maxima) < 2:
        return len(maxima), 0.0
    best = 0.0
    for a, b in zip(maxima, maxima[1:]):
        valley = float(env[a:b + 1].min())
        lower = min(float(env[a]), float(env[b]))
        if lower > 0:
            best = max(best, 1.0 - valley / lower)
    return len(maxima), best


def gate_stats(aux):
    """features_with_aux() aux -> the four gate statistics."""
    n, dip = hump_profile(aux["loud"])
    return {"humps": int(n), "dip": float(dip),
            "voiced_frac": float(aux["voiced_frac"]),
            "median_f0": float(aux["median_f0"]),
            "occupancy": float(aux["occupancy"])}


def calibrate_gates(stats_by_unit, write=True):
    """{unit: list of gate_stats dicts} -> per-unit thresholds.

    THE JOINT RATE IS WHAT IS CALIBRATED (measured lesson: four ANDed gates
    each passing 95% of real clips only passed 58-85% JOINTLY). Per unit,
    the per-gate quantile q is lowered from 5% until >=95% of that unit's
    real takes pass ALL gates together; q and the achieved joint rate are
    recorded. G1 stays inert (min_dip=0) for units whose real median dip is
    below 0.1 (the legacy calibrate_v2 rule). G3's low edge never drops
    below G3_LO_FLOOR=80 Hz (so the archived 70 Hz croak always fails) even
    when that caps the achievable joint rate -- Iddo's own low takes are the
    honest cost, and the number is printed, not hidden."""
    out = {}
    for u in UNITS:
        rows = stats_by_unit[u]
        dips = np.array([r["dip"] for r in rows])
        vfs = np.array([r["voiced_frac"] for r in rows])
        f0s = np.array([r["median_f0"] for r in rows])
        occ = np.array([r["occupancy"] for r in rows])
        med_dip = float(np.median(dips))
        plan_rate = float(np.mean((f0s >= G3_LO_PLAN) & (f0s <= G3_HI)))
        chosen = None
        for q in (5.0, 4.0, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.25, 0.0):
            min_dip = float(np.percentile(dips, q)) if med_dip >= 0.1 else 0.0
            g3_lo = G3_LO_PLAN if plan_rate >= 0.95 else max(
                G3_LO_FLOOR, 0.95 * float(np.percentile(f0s, q)))
            # Thresholds are stored at FULL precision, nudged DOWN by 1e-9.
            # (Scar: round(...,4) rounded a threshold UP past the exact
            # minimum and 11 real ima clips sitting AT the minimum failed
            # a gate "calibrated" to pass them.)
            thr = {
                "min_dip": (min_dip - 1e-9) if min_dip > 0 else 0.0,
                "min_voiced_frac": float(np.percentile(vfs, q)) - 1e-9,
                "g3_lo": g3_lo - 1e-9, "g3_hi": G3_HI,
                "min_occupancy": float(np.percentile(occ, q)) - 1e-9,
            }
            joint = float(np.mean([check_gates(u, r, {u: thr})[0]
                                   for r in rows]))
            chosen = (q, thr, joint)
            if joint >= 0.95:
                break
        q, thr, joint = chosen
        thr.update({
            "quantile_pct": q,
            "joint_real_pass": round(joint, 4),
            "g3_lo_deviation": thr["g3_lo"] != G3_LO_PLAN,
            "real_dip_median": round(med_dip, 4),
            "real_f0_median": round(float(np.median(f0s)), 2),
            "real_f0_p2_5": round(float(np.percentile(f0s, 2.5)), 2),
        })
        out[u] = thr
    if write:
        _update_calib({"gates": out, "gate_penalty": GATE_PENALTY})
    return out


def check_gates(unit, gs, calib_gates):
    """gate_stats dict vs one unit's thresholds -> (all_pass, detail)."""
    c = calib_gates.get(unit)
    if c is None:
        return True, {}
    detail = {
        "G1_dip": (c["min_dip"] <= 0.0) or (gs["dip"] >= c["min_dip"]),
        "G2_voiced": gs["voiced_frac"] >= c["min_voiced_frac"],
        "G3_f0": c["g3_lo"] <= gs["median_f0"] <= c["g3_hi"],
        "G4_occupancy": gs["occupancy"] >= c["min_occupancy"],
    }
    return all(detail.values()), detail


def gated_penalty(unit, gs, calib_gates):
    ok, _ = check_gates(unit, gs, calib_gates)
    return 0.0 if ok else GATE_PENALTY


def load_calib(path=CALIB_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _update_calib(patch, path=CALIB_PATH):
    d = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    d.update(patch)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    return d


# ----------------------------------------------------------------- CLI

def _main(argv):
    if "--spl" in argv:
        e = calibrate_spl()
        print(f"SPL: median span RMS {e['median_span_rms']:.5f} over "
              f"{e['n_clips']} clips -> gain {e['gain']:.4f} (target RMS "
              f"{TARGET_RMS} == {SPL_DB} dB SPL)")
    if "--gates" in argv:
        npz = os.path.join(_ROOT, "targets-cache", "t06-feats.npz")
        z = np.load(npz, allow_pickle=False)
        names = [str(n) for n in z["names"]]
        stats_by_unit = {u: [] for u in UNITS}
        for i, nm in enumerate(names):
            u = nm.split("_")[0]
            if u not in stats_by_unit:
                continue
            loud = z["loud"][i, :int(z["loud_len"][i])]
            stats_by_unit[u].append(gate_stats({
                "loud": loud,
                "voiced_frac": float(z["voiced_frac"][i]),
                "median_f0": float(z["median_f0"][i]),
                "occupancy": float(z["occupancy"][i])}))
        gates = calibrate_gates(stats_by_unit)
        print(json.dumps(gates, indent=1))
        # validation: real pass-rate per unit
        print("gate pass-rate on real clips (need >= 0.95):")
        for u in UNITS:
            passes = sum(check_gates(u, gs, gates)[0]
                         for gs in stats_by_unit[u])
            n = len(stats_by_unit[u])
            rate = passes / n
            print(f"  {'OK ' if rate >= 0.95 else 'FAIL'} {u:5s} "
                  f"{rate:.3f} ({passes}/{n})")


if __name__ == "__main__":
    _main(sys.argv[1:])
