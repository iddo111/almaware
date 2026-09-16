# -*- coding: utf-8 -*-
"""test_splice.py -- real ah + 0.25 s silence + real ah, posing as "abba".

Reports, honestly: where the fake lands in wdist to the abba centroid vs the
real-clip bar, and what each gate says. Note the fake DOES contain a deep
dip (total silence between two vowels), so G1 alone may pass it -- the
report says exactly which gate or metric catches it, and whether any does.
"""
import numpy as np

import _common
from ear3 import calib as C
from ear3 import features as F
from ear3 import judge as J


def main():
    cache = J.load_cache()
    gates = C.load_calib()["gates"]
    ah = sorted(C.clips("ah"))[:2]
    x = np.concatenate([F.read_wav(ah[0]),
                        np.zeros(4000, dtype=np.float32),
                        F.read_wav(ah[1])])
    v, aux = F.features_with_aux(x)
    gs = C.gate_stats(aux)
    d = J.wdist(v, cache["abba"])
    s = cache["abba"]
    ok, detail = C.check_gates("abba", gs, gates)
    print(f"fake 'abba' (ah+0.25s silence+ah from {ah[0].rsplit('/', 1)[-1]}"
          f" + {ah[1].rsplit('/', 1)[-1]}):")
    print(f"  wdist to abba centroid: {d:.2f}")
    print(f"  real abba clips: mean {s['real_wdist_mean']:.2f}  "
          f"max {s['real_wdist_max']:.2f}  (the real-clip bar)")
    print(f"  gate stats: humps={gs['humps']} dip={gs['dip']:.3f} "
          f"voiced={gs['voiced_frac']:.3f} f0={gs['median_f0']:.1f} "
          f"occ={gs['occupancy']:.3f}")
    print(f"  abba gates: {detail} -> {'PASS' if ok else 'FAIL'}")
    print("  nearest units: "
          + "  ".join(f"{r['unit']}={r['wdist']}"
                      for r in J.nearest_table(v, cache)))
    outside = d > s["real_wdist_max"]
    caught = outside or not ok
    print(f"  outside real-clip cloud: {outside}   gates catch it: {not ok}")
    print(f"VERDICT: {'CAUGHT' if caught else 'NOT CAUGHT -- the splice passes; recorded honestly'}")
    if not caught:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
