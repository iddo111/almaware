# -*- coding: utf-8 -*-
"""build_targets.py -- turn the precomputed t06 vectors into the Ear-v3
targets cache (targets-cache/ear3-t06.json) with spec_hash guard."""
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from ear3 import features as F                      # noqa: E402
from ear3 import judge as J                         # noqa: E402


def main():
    z = np.load(os.path.join(_ROOT, "targets-cache", "t06-feats.npz"),
                allow_pickle=False)
    if str(z["spec_hash"]) != F.spec_hash():
        raise SystemExit("t06-feats.npz spec_hash mismatch -- rerun "
                         "scripts/precompute_t06.py first")
    names = [str(n) for n in z["names"]]
    X = z["X"]
    by_unit = {}
    for i, nm in enumerate(names):
        by_unit.setdefault(nm.split("_")[0], []).append(X[i])
    d = J.build_cache({u: np.stack(v) for u, v in by_unit.items()})
    for u in J.UNITS:
        s = d["units"][u]
        print(f"{u:5s} n={s['n_clips']}  real wdist mean {s['real_wdist_mean']:.2f}"
              f"  min {s['real_wdist_min']:.2f}  max {s['real_wdist_max']:.2f}")
    print(f"cache written, spec {d['spec_hash'][:12]}")


if __name__ == "__main__":
    main()
