# -*- coding: utf-8 -*-
"""calibrate_v2.py -- measure Iddo's real clips, write ears-v2-calib.json, validate.

Thresholds are MEASURED, never assumed:
  per unit: hump-count range covering >=95% of real clips, and min_dip set at
  the 5th percentile of real dips (only for units whose real clips are
  genuinely two-humped, i.e. abba/ima if the data says so).

Validation (all printed, nothing hidden):
  A. per-unit gate pass-rate on the real clips (must be >=0.95);
  B. the known cheat wav /tmp/L-abba-free-4.wav must FAIL the abba gate;
  C. leave-nothing-out nearest-unit sanity with the gate applied as penalty:
     real clips of each unit, scored against every unit with gate penalty --
     accuracy must be >= the ungated 93.5% baseline's neighbourhood.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import targets                                   # noqa: E402
from ears import read_wav                        # noqa: E402
from ears_v2 import (EarsV2, hump_profile, CALIB_PATH,   # noqa: E402
                     structure_gate, GATE_PENALTY)

UNITS = targets.UNITS
ear = EarsV2.__new__(EarsV2)                      # calib not written yet
from ears_extended import ExtendedEars            # noqa: E402
ExtendedEars.__init__(ear)
ear.calib = {}

# ---- 1. measure real hump statistics per unit --------------------------------
stats = {}
raw = {}
for u in UNITS:
    paths = targets.clips(u)
    rows = []
    for p in paths:
        _, rms = ear.utterance_with_rms(read_wav(p))
        rows.append(hump_profile(rms))
    ns = np.array([r[0] for r in rows]); dips = np.array([r[1] for r in rows])
    raw[u] = rows
    counts = Counter(ns.tolist())
    # smallest hump-count window covering >=95% of clips
    best = None
    for lo in sorted(counts):
        for hi in sorted(counts):
            if hi < lo:
                continue
            cover = np.mean((ns >= lo) & (ns <= hi))
            if cover >= 0.95 and (best is None or hi - lo < best[1] - best[0]):
                best = (lo, hi)
    lo, hi = best if best else (int(ns.min()), int(ns.max()))
    # Iteration 3: gate on DIP DEPTH alone for units whose real clips carry a
    # real median dip (abba, and ima if the data says so). Hump COUNT is not
    # gated at all — the peak detector's count is noisy on real speech, but
    # the deepest-dip statistic separated cleanly (real abba median 0.69,
    # flat-buzz cheat 0.000). Threshold = 5th percentile over ALL the unit's
    # real clips, so >=95% acceptance is by construction.
    lo, hi = 0, 99
    med_dip = float(np.median(dips))
    min_dip = float(np.percentile(dips, 5)) if med_dip >= 0.1 else 0.0
    stats[u] = {"min_humps": lo, "max_humps": hi, "min_dip": round(min_dip, 3),
                "real_hump_counts": dict(counts),
                "real_dip_median": round(float(np.median(dips)), 3)}
    print(f"{u:5s} humps {dict(counts)} -> gate [{lo},{hi}] "
          f"min_dip {stats[u]['min_dip']} (median real dip {stats[u]['real_dip_median']})")

json.dump(stats, open(CALIB_PATH, "w", encoding="utf-8"), indent=1)
print("calib written ->", CALIB_PATH)
ear.calib = stats

# ---- 2. validation -----------------------------------------------------------
print("\nA. gate pass-rate on real clips (need >=0.95):")
ok_all = True
for u in UNITS:
    paths = targets.clips(u)
    passed = 0
    for p in paths:
        _, rms = ear.utterance_with_rms(read_wav(p))
        passed += structure_gate(u, rms, ear.calib)
    rate = passed / len(paths)
    flag = "OK " if rate >= 0.95 else "FAIL"
    ok_all &= rate >= 0.95
    print(f"  {flag} {u:5s} {rate:.3f} ({passed}/{len(paths)})")

print("\nB. the cheat wav vs the abba gate:")
cheat = "/tmp/L-abba-free-4.wav"
if os.path.exists(cheat):
    _, rms = ear.utterance_with_rms(read_wav(cheat))
    n, dip = hump_profile(rms)
    verdict = structure_gate("abba", rms, ear.calib)
    print(f"  cheat humps={n} dip={dip:.3f} -> abba gate pass={verdict} "
          f"({'FAIL = GOOD, cheat blocked' if not verdict else 'BAD: cheat still passes'})")
else:
    print("  cheat wav missing -- copy it to /tmp first")

print("\nC. nearest-unit accuracy, UNGATED CONTROL vs GATED (isolate the gate's cost):")
all_stats = targets.load_all(ear)
c_gated = c_plain = total = 0
for u in UNITS:
    for p in targets.clips(u):
        v, rms = ear.utterance_with_rms(read_wav(p))
        bg = bp = None; sg = sp = None
        for cu in UNITS:
            s0 = targets.wdist(v, all_stats[cu])
            if sp is None or s0 < sp:
                bp, sp = cu, s0
            s1 = s0 + (0.0 if structure_gate(cu, rms, ear.calib) else GATE_PENALTY)
            if sg is None or s1 < sg:
                bg, sg = cu, s1
        c_plain += bp == u; c_gated += bg == u; total += 1
print(f"  ungated control: {c_plain/total:.3f}   gated: {c_gated/total:.3f} ({c_gated}/{total})")
print("\nDONE. A must be all OK, B must be blocked, C must be >= ~0.93.")
