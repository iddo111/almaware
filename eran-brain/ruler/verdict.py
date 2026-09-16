# -*- coding: utf-8 -*-
"""verdict.py -- the significance, and the one test that decides it.

> BROKEN WINDOWS LAW: if it is not working, fix it IMMEDIATELY. Test the REAL output.

Three things left to settle honestly:

  A. Is the leave-one-take-out gain of the new ruler real, or 33 clips of luck?
     McNemar on the paired per-clip decisions, plus a take-level bootstrap.

  B. Is any AUC against Iddo's ear distinguishable from a coin? Hanley-McNeil
     standard errors on 33 yes vs 48 no. If the interval covers 0.5, say so.

  C. THE DECIDING TEST. The claim behind a centroid/whitened ruler is that it
     measures the SYLLABLE and not the recording. There is exactly one way to
     test that with the data on this machine: fit the ruler on one human corpus
     and use it on the OTHER one. A ruler that is really about /ba/ transfers.
     A ruler that is about the recording does not. Floor 33.3% on the three
     shared units, and the plain centroid's own 33.3% is the number to beat.
"""
from __future__ import annotations

import json
import os

import numpy as np

from ruler import fit_nn_clip, fit_centroid, fit_wccn_score, fit_diag_perclass

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")


def mcnemar(a_ok, b_ok):
    """Exact binomial two-sided p on the discordant pairs."""
    from math import comb
    b = int(((~a_ok) & b_ok).sum())        # a wrong, b right
    c = int((a_ok & (~b_ok)).sum())        # a right, b wrong
    n = b + c
    if n == 0:
        return b, c, 1.0
    k = min(b, c)
    p = 2.0 * sum(comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return b, c, min(1.0, p)


def hanley(auc, n1, n2):
    q1 = auc / (2 - auc)
    q2 = 2 * auc * auc / (1 + auc)
    v = (auc * (1 - auc) + (n1 - 1) * (q1 - auc ** 2)
         + (n2 - 1) * (q2 - auc ** 2)) / (n1 * n2)
    return float(np.sqrt(max(v, 0)))


def main():
    out = {}
    d = np.load(os.path.join(HERE, "..", "holobrain", "ear-human.npz"),
                allow_pickle=True)
    X = d["V"].astype(np.float64)
    y = d["y"].astype(np.int64)
    t = d["t"].astype(np.int64)
    syl = [str(s) for s in d["syllables"]]
    C, T = len(syl), int(t.max()) + 1

    # ------------------------------------------------------------------- A
    print("A. IS THE LEAVE-ONE-TAKE-OUT GAIN REAL?")
    preds = {}
    order = []
    for name, f in (("OLD nearest clip", fit_nn_clip),
                    ("ear3 per-class spread", fit_diag_perclass),
                    ("NEW centroid", fit_centroid),
                    ("NEW WCCN lam=0.50",
                     lambda a, b, c: fit_wccn_score(a, b, c, 0.50))):
        P, Y, TK = [], [], []
        for k in range(T):
            tr, te = t != k, t == k
            P.append(f(X[tr], y[tr], C)(X[te]).argmin(1))
            Y.append(y[te])
            TK.append(t[te])
        preds[name] = (np.concatenate(P) == np.concatenate(Y))
        order.append(name)
        takes = np.concatenate(TK)
    for name in order:
        print("   %-24s %5.2f%%" % (name, 100 * preds[name].mean()))
    base = preds["OLD nearest clip"]
    print("\n   against the OLD ruler, McNemar on 396 paired decisions:")
    for name in order[1:]:
        b, c, p = mcnemar(base, preds[name])
        print("     %-24s +%5.2f pts   fixed %3d  broke %3d   p = %.2g"
              % (name, 100 * (preds[name].mean() - base.mean()), b, c, p))
        out.setdefault("mcnemar", {})[name] = {
            "delta_pts": round(100 * (preds[name].mean() - base.mean()), 2),
            "fixed": b, "broke": c, "p": p}
    # take-level bootstrap: the 6 takes are the independent units, not the clips
    rng = np.random.default_rng(1933)
    ds = []
    w = preds["NEW WCCN lam=0.50"]
    for _ in range(20000):
        ks = rng.integers(0, T, T)
        m = np.concatenate([np.where(takes == k)[0] for k in ks])
        ds.append(w[m].mean() - base[m].mean())
    ds = np.array(ds)
    lo, hi = np.percentile(ds, [2.5, 97.5])
    print("   take-level bootstrap of WCCN - OLD: %+.2f pts, 95%% CI [%+.2f, %+.2f]"
          % (100 * ds.mean(), 100 * lo, 100 * hi))
    out["bootstrap_wccn_minus_old_pts"] = [round(100 * ds.mean(), 2),
                                           round(100 * lo, 2), round(100 * hi, 2)]

    # ------------------------------------------------------------------- B
    print("\nB. IS ANY RULER DISTINGUISHABLE FROM A COIN ON IDDO'S EAR?")
    a1 = json.load(open(os.path.join(HERE, "agree-measured.json"), encoding="utf-8"))
    a2 = json.load(open(os.path.join(HERE, "target-measured.json"), encoding="utf-8"))
    print("   Hanley-McNeil SE on 33 yes vs 48 no; a 95%% band of +-%.3f."
          % (1.96 * hanley(0.5, 33, 48)))
    print("   %-42s %6s   %s" % ("ruler (target it was scored against)", "AUC",
                                 "95% CI"))
    combos = [("%s  [vs 22-syl reference]" % k, v["auc_1v3"])
              for k, v in a1["test1"].items()]
    combos += [("%s  [vs t06, the real target]" % k, v)
               for k, v in a2["auc_vs_t06"].items()]
    for name, A in combos:
        se = hanley(A, 33, 48)
        lo_, hi_ = A - 1.96 * se, A + 1.96 * se
        flag = "" if lo_ > 0.5 or hi_ < 0.5 else "   <- covers 0.500, a coin"
        print("   %-42s %6.3f   [%.3f, %.3f]%s" % (name, A, lo_, hi_, flag))
        out.setdefault("auc_ci", {})[name] = [round(A, 3), round(lo_, 3),
                                              round(hi_, 3)]

    # ------------------------------------------------------------------- C
    print("\nC. THE DECIDING TEST -- DOES THE RULER SURVIVE A CORPUS CHANGE?")
    z = np.load(os.path.join(D, "ruler-t06.npz"), allow_pickle=True)
    V6 = z["V"].astype(np.float64)
    u6 = np.array([str(s).split("_")[0] for s in z["names"]])
    SH = ["ah", "ba", "ma"]
    yR = np.array([syl[i] for i in y])
    selR, sel6 = np.isin(yR, SH), np.isin(u6, SH)
    XR, yRs = X[selR], yR[selR]
    X6, y6s = V6[sel6], u6[sel6]
    print("   fit on one corpus, judged on the other, 3 units, floor 33.3%%")
    print("   %-26s %14s %14s %12s" % ("ruler", "ref -> t06", "t06 -> ref",
                                       "self (ref)"))
    for name, fit in (("nearest single clip", fit_nn_clip),
                      ("ear3 per-class spread", fit_diag_perclass),
                      ("centroid", fit_centroid),
                      ("WCCN lam=0.50",
                       lambda a, b, c: fit_wccn_score(a, b, c, 0.50))):
        iR = np.array([SH.index(u) for u in yRs])
        i6 = np.array([SH.index(u) for u in y6s])
        r2t = float((fit(XR, iR, 3)(X6).argmin(1) == i6).mean())
        t2r = float((fit(X6, i6, 3)(XR).argmin(1) == iR).mean())
        # self, honest: leave-one-take-out inside the reference set
        acc = []
        tR = t[selR]
        for k in range(T):
            tr, te = tR != k, tR == k
            acc.append(float((fit(XR[tr], iR[tr], 3)(XR[te]).argmin(1)
                              == iR[te]).mean()))
        print("   %-26s %13.1f%% %13.1f%% %11.1f%%"
              % (name, 100 * r2t, 100 * t2r, 100 * np.mean(acc)))
        out.setdefault("cross_corpus", {})[name] = {
            "ref_to_t06_pct": round(100 * r2t, 2),
            "t06_to_ref_pct": round(100 * t2r, 2),
            "ref_self_loto_pct": round(100 * float(np.mean(acc)), 2)}
    print("   floor 33.3%. Anything at the floor is not measuring the syllable.")

    with open(os.path.join(HERE, "verdict.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("\nwrote verdict.json")


if __name__ == "__main__":
    main()
