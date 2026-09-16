# -*- coding: utf-8 -*-
"""probe_high_fs.py -- the bat-headroom numerics probe (plan Phase 1 risks).

CPU-only, NO corpus, NO calibration dependency. Purely synthetic: for each
fs in {48000, 192000, 384000} design the PATCHED JAX CARFAC at that rate
(the same Ear3Cochlea wrapper the ear uses, spl_gain=1.0, chirp scaled to
RMS 0.05 = the ear's 65 dB SPL convention) and run a 0.2 s linear chirp
100 Hz -> {20k, 80k, 160k}. Report per fs:

  n_channels, top/bottom CF, design time, first-call time (includes JIT
  compile), steady per-call time (median of 3 warm calls), NaN/Inf counts,
  max |NAP|, and a tail-blowup check (max |NAP| in the last 10% of frames
  vs overall -- a filter going unstable rings hardest at the end).

The literature never measured CARFAC numerics at 192/384 kHz -- a FAILURE
at a rate is a FINDING, not a problem to hide: the exact exception text is
recorded in the json and the probe continues to the next rate. This probe
sets no pass/fail bar for Phase 1 (beyond-human hearing is future headroom
by the growth law); it only records the numbers.

Writes results/high_fs.json for scripts/assemble_accept.py.
Run:  env OMP_NUM_THREADS=1 python tests/probe_high_fs.py   (time is
reported for whatever threading the run had; the env line pins it).
"""
import json
import os
import sys
import time
import traceback

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

RESULTS = os.path.join(ROOT, "results", "high_fs.json")
CASES = ((48000, 20000.0), (192000, 80000.0), (384000, 160000.0))
DUR_S = 0.2
F0_HZ = 100.0
TARGET_RMS = 0.05          # the ear's 65 dB SPL convention
WARM_CALLS = 3


def chirp(fs, f1):
    """0.2 s linear chirp F0_HZ -> f1, float32, RMS = TARGET_RMS."""
    n = int(round(DUR_S * fs))
    t = np.arange(n, dtype=np.float64) / fs
    # linear instantaneous frequency f(t) = f0 + (f1-f0)*t/T; phase = integral
    phase = 2.0 * np.pi * (F0_HZ * t + 0.5 * (f1 - F0_HZ) * t ** 2 / DUR_S)
    x = np.sin(phase)
    x *= TARGET_RMS / np.sqrt(np.mean(x ** 2))
    return x.astype(np.float32)


def probe(fs, f1):
    from ear3.carfac_wrap import Ear3Cochlea
    r = {"fs": fs, "chirp_to_hz": f1, "dur_s": DUR_S,
         "designed": False, "ran": False}
    t0 = time.perf_counter()
    try:
        ear = Ear3Cochlea(fs=fs, spl_gain=1.0)
    except Exception:
        r["error"] = traceback.format_exc().strip().splitlines()[-1]
        r["error_full"] = traceback.format_exc()
        r["design_s"] = time.perf_counter() - t0
        return r
    r["design_s"] = time.perf_counter() - t0   # includes pre-roll JIT
    cfs = np.asarray(ear.channel_cfs, dtype=np.float64)
    r["designed"] = True
    r["n_channels"] = int(cfs.size)
    r["top_cf_hz"] = float(np.max(cfs))
    r["bottom_cf_hz"] = float(np.min(cfs))
    r["nyquist_hz"] = fs / 2.0

    x = chirp(fs, f1)
    try:
        t0 = time.perf_counter()
        nap = ear.nap(x)                      # first call: JIT compile
        r["first_call_s"] = time.perf_counter() - t0
        times = []
        for _ in range(WARM_CALLS):
            t0 = time.perf_counter()
            nap = ear.nap(x)
            times.append(time.perf_counter() - t0)
        r["steady_call_s"] = float(np.median(times))
    except Exception:
        r["error"] = traceback.format_exc().strip().splitlines()[-1]
        r["error_full"] = traceback.format_exc()
        return r
    r["ran"] = True
    r["n_samples"] = int(nap.shape[0])
    r["nan_count"] = int(np.isnan(nap).sum())
    r["inf_count"] = int(np.isinf(nap).sum())
    finite = nap[np.isfinite(nap)]
    r["max_abs_nap"] = float(np.max(np.abs(finite))) if finite.size else None
    tail = nap[int(0.9 * nap.shape[0]):]
    tail_f = tail[np.isfinite(tail)]
    r["max_abs_nap_tail10"] = (float(np.max(np.abs(tail_f)))
                               if tail_f.size else None)
    r["stable"] = bool(r["nan_count"] == 0 and r["inf_count"] == 0
                       and r["max_abs_nap"] is not None
                       and r["max_abs_nap"] < 1e3)
    return r


def main():
    import jax
    rows = []
    for fs, f1 in CASES:
        print(f"fs={fs}: designing + running chirp -> {f1 / 1000:.0f}k ...",
              flush=True)
        r = probe(fs, f1)
        rows.append(r)
        if not r["designed"]:
            print(f"  DESIGN FAILED after {r['design_s']:.1f}s: {r['error']}")
            continue
        print(f"  n_channels {r['n_channels']}   CF "
              f"{r['bottom_cf_hz']:.1f} .. {r['top_cf_hz']:.1f} Hz "
              f"(nyquist {r['nyquist_hz']:.0f})   design {r['design_s']:.1f}s")
        if not r["ran"]:
            print(f"  RUN FAILED: {r['error']}")
            continue
        print(f"  first call {r['first_call_s']:.2f}s (JIT)   steady "
              f"{r['steady_call_s'] * 1e3:.0f} ms/call for {DUR_S}s audio")
        print(f"  NaN {r['nan_count']}  Inf {r['inf_count']}  "
              f"max|NAP| {r['max_abs_nap']:.4f}  "
              f"tail10% {r['max_abs_nap_tail10']:.4f}  "
              f"-> {'STABLE' if r['stable'] else 'UNSTABLE -- recorded'}")

    print("\nfs      ch   topCF(Hz)   maxNAP    steady   stable")
    for r in rows:
        if r["designed"] and r["ran"]:
            print(f"{r['fs']:<7d} {r['n_channels']:<4d} "
                  f"{r['top_cf_hz']:<11.1f} {r['max_abs_nap']:<9.4f} "
                  f"{r['steady_call_s'] * 1e3:<8.0f} {r['stable']}")
        else:
            print(f"{r['fs']:<7d} FAILED: {r.get('error', '?')}")

    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump({"cases": rows, "target_rms": TARGET_RMS,
                   "omp_threads": os.environ.get("OMP_NUM_THREADS"),
                   "jax": jax.__version__,
                   "note": "informational probe -- no Phase-1 bar; "
                           "failures are findings"}, f, indent=1)
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
