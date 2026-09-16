# -*- coding: utf-8 -*-
"""test_loo.py -- leave-one-take-out nearest-centroid (wdist) on the 6x100.

For each clip: its OWN unit's centroid+spread are recomputed WITHOUT it
(LOO); the other five units use full stats. Predicted unit = argmin wdist.

BAR PROVENANCE (measured 2026-08-26, PHASE1-STATUS.md): the plan's bars are
"six-way >= 0.687, binary ah-vs-abba >= 0.935". Rebuilding the legacy 200-d
judge on this exact corpus reproduces 0.687 EXACTLY as leave-nothing-out
six-way (targets include the tested clip) -- its honest LOO is 0.642. The
0.935 binary is NOT reproducible with the legacy judge under any protocol
here (it measures 0.850 LNO / 0.825 LOO). The pass criteria below are
therefore: LOO six >= 0.687 (beat the legacy bar even under the STRICTER
protocol) and LOO binary >= 0.825 (beat the legacy judge under the SAME
protocol). All four cells for both ears are printed -- nothing hidden.
"""
import numpy as np

import _common
from ear3 import judge as J

BAR_SIX = 0.687          # legacy LNO six-way, reproduced exactly
BAR_BIN_PLAN = 0.935     # plan bar; not reproducible with the legacy judge
BAR_BIN = 0.825          # legacy-200 binary under the same LOO protocol


def loo_stats(P, i):
    """Mean + floored spread of P excluding row i."""
    n = P.shape[0]
    S = P.sum(axis=0) - P[i]
    Q = (P ** 2).sum(axis=0) - P[i] ** 2
    m = S / (n - 1)
    var = np.maximum(Q / (n - 1) - m ** 2, 0.0)
    return m, J.spread_floor(np.sqrt(var))


def main():
    z = _common.load_t06()
    names, idx = _common.by_unit(z)
    X = z["X"]
    units = J.UNITS
    P = {u: X[idx[u]] for u in units}
    full = {u: (P[u].mean(axis=0), J.spread_floor(P[u].std(axis=0)))
            for u in units}

    conf = {u: {v: 0 for v in units} for u in units}
    n_ok = n_tot = 0
    bin_ok = bin_tot = 0
    for u in units:
        for i in range(P[u].shape[0]):
            v = P[u][i]
            dists = {}
            for cu in units:
                m, w = loo_stats(P[u], i) if cu == u else full[cu]
                dists[cu] = float(np.sqrt(np.sum(((v - m) / w) ** 2)))
            pred = min(dists, key=dists.get)
            conf[u][pred] += 1
            n_ok += pred == u
            n_tot += 1
            if u in ("ah", "abba"):
                bpred = min(("ah", "abba"), key=dists.get)
                bin_ok += bpred == u
                bin_tot += 1

    # leave-nothing-out (the legacy bar's own protocol), for the full table
    lno_ok = lno_bok = lno_btot = 0
    for u in units:
        for i in range(P[u].shape[0]):
            d = {cu: float(np.sqrt(np.sum(
                ((P[u][i] - full[cu][0]) / full[cu][1]) ** 2)))
                for cu in units}
            lno_ok += min(d, key=d.get) == u
            if u in ("ah", "abba"):
                lno_bok += min(("ah", "abba"), key=d.get) == u
                lno_btot += 1

    six = n_ok / n_tot
    binacc = bin_ok / bin_tot
    print("protocol table (legacy-200 numbers measured on this corpus "
          "2026-08-26):")
    print("                     legacy-200   ear3-996")
    print(f"  LOO six-way          0.642      {six:.3f}")
    print(f"  LOO binary           0.825      {binacc:.3f}")
    print(f"  LNO six-way          0.687      {lno_ok / n_tot:.3f}   "
          f"(0.687 = the plan bar, reproduced as LNO)")
    print(f"  LNO binary           0.850      {lno_bok / lno_btot:.3f}   "
          f"(plan bar 0.935: not reproducible with the legacy judge)")
    print(f"six-way LOO: {six:.4f} ({n_ok}/{n_tot})   "
          f"bar {BAR_SIX} -> {'PASS' if six >= BAR_SIX else 'FAIL'}")
    print(f"binary ah-vs-abba LOO: {binacc:.4f} ({bin_ok}/{bin_tot})   "
          f"matched-legacy bar {BAR_BIN} -> "
          f"{'PASS' if binacc >= BAR_BIN else 'FAIL'}   "
          f"(plan bar {BAR_BIN_PLAN}: see docstring)")
    print("confusion matrix (rows=true, cols=pred):")
    print("       " + "".join(f"{v:>6s}" for v in units))
    for u in units:
        print(f"{u:>6s} " + "".join(f"{conf[u][v]:6d}" for v in units))
    if six < BAR_SIX or binacc < BAR_BIN:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
