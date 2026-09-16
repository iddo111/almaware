# -*- coding: utf-8 -*-
"""test_cheat.py -- the archived v1 cheat wavs are PERMANENT negative tests.

Every best-v1cheat.wav under ~/throat-search-v1-20260826/run/*/ goes through
features + wdist vs its arm's unit (from the run dir name, falling back to
abba) + the gates.

CRITERION (stated, not hidden): a cheat is CAUGHT if it fails gates OR its
wdist exceeds 1.3x the unit's real-clip MEAN -- the Phase-3 campaign's own
success rule (a winning render must come ≤1.3x the real-clip bar), so
"caught" = "could never be declared a win". The distance vs the absolute
worst real take is also printed: one cheat (abba-0, measured 2026-08-26)
sits 0.08 INSIDE the single worst real clip while being farther than the
other 99 -- the max-bar framing alone would call that a slip, and the
number is printed so nobody has to take the criterion on faith."""
import glob
import os

import _common
from ear3 import calib as C
from ear3 import features as F
from ear3 import judge as J

ARCHIVE = os.path.expanduser("~/throat-search-v1-20260826")


def unit_for(path):
    d = os.path.basename(os.path.dirname(path)).lower()
    for u in J.UNITS:
        if u in d.split("-"):
            return u
    return "abba"


def main():
    cache = J.load_cache()
    gates = C.load_calib()["gates"]
    wavs = sorted(glob.glob(os.path.join(ARCHIVE, "run", "*",
                                         "best-v1cheat.wav")))
    if not wavs:
        raise SystemExit(f"no best-v1cheat.wav under {ARCHIVE}/run/*/")
    all_caught = True
    for p in wavs:
        u = unit_for(p)
        v, aux = F.features_with_aux(F.read_wav(p))
        gs = C.gate_stats(aux)
        d = J.wdist(v, cache[u])
        s = cache[u]
        ok, detail = C.check_gates(u, gs, gates)
        bar = 1.3 * s["real_wdist_mean"]
        outside = d > s["real_wdist_max"]
        caught = (d > bar) or not ok
        all_caught &= caught
        arm = os.path.basename(os.path.dirname(p))
        print(f"{arm} (judged vs {u}):")
        print(f"  wdist {d:.2f} = {d / s['real_wdist_mean']:.2f}x real mean "
              f"{s['real_wdist_mean']:.2f} (win needs <=1.3x = {bar:.2f}); "
              f"beyond worst real take ({s['real_wdist_max']:.2f}): "
              f"{outside}")
        print(f"  stats humps={gs['humps']} dip={gs['dip']:.3f} "
              f"voiced={gs['voiced_frac']:.3f} f0={gs['median_f0']:.1f} "
              f"occ={gs['occupancy']:.3f}")
        print(f"  gates {detail} -> {'PASS' if ok else 'FAIL'}")
        print(f"  -> {'CAUGHT' if caught else 'NOT CAUGHT'}")
    print(f"VERDICT: {'ALL CAUGHT' if all_caught else 'AT LEAST ONE CHEAT SLIPS THROUGH -- recorded honestly'}")
    if not all_caught:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
