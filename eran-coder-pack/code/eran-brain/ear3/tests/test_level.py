# -*- coding: utf-8 -*-
"""test_level.py -- level honesty (plan acceptance item 7).

(a) SAME clip at 0 dB and -6 dB (samples x 0.5): the vectors must DIFFER
    meaningfully -- level is information, the v3 ear must not be level-blind
    the way the frozen 192 is. Reported per block, in the judge's own units
    (the ah unit's block-balanced w): which blocks move, which moves most.
    Expectation stated up front: the LEGACY block moves ~0 BY DESIGN (its
    per-frame spectrum normalization cancels a scalar gain -- that is the
    documented old blindness, kept frozen under the growth law); the LEVEL
    block should be the top mover among the new blocks.

(b) ROBUSTNESS: the whole 600-clip corpus perturbed by -3 dB (x 10^(-3/20)),
    full recompute through the cochlea, then the SAME LOO + LNO protocol as
    test_loo.py. Accuracy must stay within 3 points of the clean number
    UNDER THE SAME PROTOCOL. Note on the bar: the plan quotes 0.757, which
    is the clean LNO six-way; the clean LOO six-way is 0.695. Comparing a
    perturbed LOO to a clean LNO would cross protocols, so BOTH pairs are
    checked, each against its own clean twin: |LOO_p - LOO_c| <= 0.03 and
    |LNO_p - LNO_c| <= 0.03. All four numbers printed.
    Also printed (informational, no bar): perturbed clips judged against
    the CLEAN full-corpus stats -- the cross-level transfer number.

Writes results/level.json for scripts/assemble_accept.py.
"""
import json
import os
import time

import numpy as np

import _common
from ear3 import features as F
from ear3 import judge as J

CLIP = "ah_t06_1.wav"
DB6 = 0.5                      # the task's convention: -6 dB = samples x 0.5
DB3 = 10.0 ** (-3.0 / 20.0)    # -3 dB = x 0.70795
TOL = 0.03
RESULTS = os.path.join(_common.ROOT, "results", "level.json")


def block_moves(v0, v1, w):
    """Per-block movement in judge units (w is already block-balanced)."""
    out = {}
    for name, lo, hi in F.block_ranges():
        z = (v0[lo:hi] - v1[lo:hi]) / w[lo:hi]
        out[name] = float(np.sqrt(np.sum(z ** 2)))
    return out


def loo_lno(X, idx, units):
    """Same math as test_loo.py: (loo_six, loo_bin, lno_six, lno_bin)."""
    P = {u: X[idx[u]] for u in units}
    full = {u: (P[u].mean(axis=0), J.spread_floor(P[u].std(axis=0)))
            for u in units}
    n_ok = n_tot = bin_ok = bin_tot = 0
    lno_ok = lno_bok = lno_btot = 0
    for u in units:
        n = P[u].shape[0]
        S = P[u].sum(axis=0)
        Q = (P[u] ** 2).sum(axis=0)
        for i in range(n):
            v = P[u][i]
            m = (S - v) / (n - 1)
            var = np.maximum((Q - v ** 2) / (n - 1) - m ** 2, 0.0)
            w_loo = J.spread_floor(np.sqrt(var))
            dists = {}
            for cu in units:
                mm, ww = (m, w_loo) if cu == u else full[cu]
                dists[cu] = float(np.sqrt(np.sum(((v - mm) / ww) ** 2)))
            n_ok += min(dists, key=dists.get) == u
            n_tot += 1
            if u in ("ah", "abba"):
                bin_ok += min(("ah", "abba"), key=dists.get) == u
                bin_tot += 1
            d = {cu: float(np.sqrt(np.sum(
                ((v - full[cu][0]) / full[cu][1]) ** 2))) for cu in units}
            lno_ok += min(d, key=d.get) == u
            if u in ("ah", "abba"):
                lno_bok += min(("ah", "abba"), key=d.get) == u
                lno_btot += 1
    return (n_ok / n_tot, bin_ok / bin_tot,
            lno_ok / n_tot, lno_bok / lno_btot)


def main():
    z = _common.load_t06()
    names, idx = _common.by_unit(z)
    units = J.UNITS
    cache = J.load_cache()
    w_ah = np.asarray(cache["ah"]["w"], dtype=np.float64)

    # ---------------- (a) same clip, 0 dB vs -6 dB
    x = F.read_wav(os.path.join(_common.CORPUS, CLIP))
    v0 = F.features(x)
    v6 = F.features(x * np.float32(DB6))
    raw_l2 = float(np.linalg.norm(v0 - v6))
    moves = block_moves(v0, v6, w_ah)
    total_wd = float(np.sqrt(sum(m ** 2 for m in moves.values())))
    order = sorted(moves, key=moves.get, reverse=True)
    real_mean = cache["ah"]["real_wdist_mean"]
    print(f"(a) {CLIP} at 0 dB vs -6 dB (x{DB6}):")
    print(f"  raw L2 (unweighted): {raw_l2:.4f}")
    print(f"  judge-units distance (ah w): {total_wd:.3f} "
          f"(= {total_wd / real_mean:.2f}x the ah real-clip mean wdist "
          f"{real_mean:.2f})")
    print("  per-block movement (judge units, block-balanced w):")
    for nm in order:
        note = ("  <- level-blind BY DESIGN (growth law)"
                if nm == "legacy192" else "")
        print(f"    {nm:12s} {moves[nm]:8.3f}{note}")
    new_blocks = [nm for nm in order if nm != "legacy192"]
    top_new = new_blocks[0]
    ok_differ = total_wd > 0.5
    ok_level_top = top_new == "level"
    print(f"  top mover among NEW blocks: {top_new} "
          f"-> {'level, as designed' if ok_level_top else 'NOT level -- recorded honestly'}")

    # ---------------- (b) -3 dB corpus, full recompute, LOO+LNO
    print(f"(b) recomputing all {len(names)} clips at -3 dB "
          f"(x{DB3:.5f}) through the full ear...", flush=True)
    t0 = time.perf_counter()
    Xp = np.empty_like(z["X"])
    for i, nm in enumerate(names):
        xi = F.read_wav(os.path.join(_common.CORPUS, nm))
        Xp[i] = F.features(xi * np.float32(DB3))
    wall = time.perf_counter() - t0
    print(f"  done in {wall:.0f}s ({wall / len(names) * 1e3:.0f} ms/clip, "
          f"unpinned)")

    loo_c, bin_c, lno_c, lnob_c = loo_lno(z["X"], idx, units)
    loo_p, bin_p, lno_p, lnob_p = loo_lno(Xp, idx, units)
    print("  protocol            clean    -3dB     |delta|")
    print(f"  LOO six-way         {loo_c:.3f}    {loo_p:.3f}    "
          f"{abs(loo_p - loo_c):.3f}")
    print(f"  LOO binary          {bin_c:.3f}    {bin_p:.3f}    "
          f"{abs(bin_p - bin_c):.3f}")
    print(f"  LNO six-way         {lno_c:.3f}    {lno_p:.3f}    "
          f"{abs(lno_p - lno_c):.3f}   (0.757 = the plan-quoted clean number)")
    print(f"  LNO binary          {lnob_c:.3f}    {lnob_p:.3f}    "
          f"{abs(lnob_p - lnob_c):.3f}")

    # informational: perturbed clips vs CLEAN stats (cross-level transfer)
    P = {u: z["X"][idx[u]] for u in units}
    full = {u: (P[u].mean(axis=0), J.spread_floor(P[u].std(axis=0)))
            for u in units}
    x_ok = 0
    for u in units:
        for i in idx[u]:
            d = {cu: float(np.sqrt(np.sum(
                ((Xp[i] - full[cu][0]) / full[cu][1]) ** 2)))
                for cu in units}
            x_ok += min(d, key=d.get) == u
    cross = x_ok / len(names)
    print(f"  informational: -3dB clips vs CLEAN targets (LNO): {cross:.3f} "
          f"(no bar -- level IS information, a shift SHOULD cost something)")

    ok_loo = abs(loo_p - loo_c) <= TOL
    ok_lno = abs(lno_p - lno_c) <= TOL
    print(f"ASSERT (a) vectors differ meaningfully "
          f"({total_wd:.2f} judge units > 0.5): "
          f"{'PASS' if ok_differ else 'FAIL'}")
    print(f"ASSERT (a) level = top new-block mover: "
          f"{'PASS' if ok_level_top else 'FAIL'}")
    print(f"ASSERT (b) |LOO_p - LOO_c| <= {TOL}: "
          f"{'PASS' if ok_loo else 'FAIL'}")
    print(f"ASSERT (b) |LNO_p - LNO_c| <= {TOL}: "
          f"{'PASS' if ok_lno else 'FAIL'}")

    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump({
            "clip": CLIP, "raw_l2_minus6db": raw_l2,
            "judge_units_dist_minus6db": total_wd,
            "vs_ah_real_mean": total_wd / real_mean,
            "block_moves": moves, "top_new_block": top_new,
            "loo_clean": loo_c, "loo_pert": loo_p,
            "bin_clean": bin_c, "bin_pert": bin_p,
            "lno_clean": lno_c, "lno_pert": lno_p,
            "lno_bin_clean": lnob_c, "lno_bin_pert": lnob_p,
            "cross_level_lno": cross, "tol": TOL,
            "pass": bool(ok_differ and ok_level_top and ok_loo and ok_lno),
        }, f, indent=1)
    print(f"wrote {RESULTS}")
    if not (ok_differ and ok_level_top and ok_loo and ok_lno):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
