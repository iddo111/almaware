# -*- coding: utf-8 -*-
"""ruler2.py -- the honest version of ruler.py.

> BROKEN WINDOWS LAW: if it is not working, fix it IMMEDIATELY. Test the REAL output.

Three things ruler.py could not claim, fixed here:

1. NESTED CHOICE. ruler.py picked the WCCN shrinkage by looking at the same
   6-fold score it then reported. That is choosing on the test set. Here the
   shrinkage (and the rank, below) is chosen inside each fold, on the 5
   TRAINING takes only, by an inner leave-one-training-take-out. The reported
   number never saw the take it is scored on.

2. A SAFER FIX THAN WHITENING. Full WCCN inverts the within-class covariance,
   which multiplies up the directions the human corpus almost never moves in.
   A HUMAN clip lives inside that corpus; ERAN's synthetic throat does not, and
   an off-manifold candidate can be handed an enormous or an absurdly small
   score by a direction no human ever excited. The bounded alternative measured
   here is NUISANCE PROJECTION: find the top-k within-class directions (the
   speaker/take subspace) and simply DELETE them, keeping the metric a plain
   Euclidean distance in what is left. Nothing is ever amplified.

3. THE QUESTION THAT IS ACTUALLY LIVE. /ba/ against /ma/. Per-syllable recall
   and the ba<->ma confusion are printed for every ruler.

Floors every number can fall through: chance 4.55%, and the old ruler itself.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

from ruler import (fit_nn_clip, fit_mean_clip, fit_centroid, fit_diag_pooled,
                   fit_diag_perclass, fit_wccn_score, within_between)


# ------------------------------------------------------- the nuisance killer
def _within_scatter(Xtr, ytr, C):
    R = np.concatenate([Xtr[ytr == c] - Xtr[ytr == c].mean(0) for c in range(C)])
    return np.cov(R, rowvar=False, bias=True)


def fit_nuisance(Xtr, ytr, C, k=8):
    """Delete the top-k WITHIN-class directions, then nearest centroid.

    Those directions are what two people saying the same syllable differ in.
    k=0 is exactly the plain centroid ruler, so this family contains its own
    floor and cannot win by construction."""
    if k <= 0:
        return fit_centroid(Xtr, ytr, C)
    S = _within_scatter(Xtr, ytr, C)
    ev, U = np.linalg.eigh(S)
    N = U[:, ::-1][:, :k]                       # top-k within-class directions
    P = np.eye(S.shape[0]) - N @ N.T            # project them out
    M = np.stack([Xtr[ytr == c].mean(0) for c in range(C)]) @ P
    return lambda Q: np.linalg.norm((Q @ P)[:, None, :] - M[None, :, :], axis=-1)


# ------------------------------------------------------------ nested choosing
def _inner_pick(Xtr, ytr, ttr, C, family, grid):
    """Choose the knob on the TRAINING takes alone, by leave-one-inner-take-out."""
    takes = sorted(set(ttr.tolist()))
    best, best_acc = grid[0], -1.0
    for g in grid:
        accs = []
        for k in takes:
            itr, ite = ttr != k, ttr == k
            if not ite.any():
                continue
            sc = family(Xtr[itr], ytr[itr], C, g)
            accs.append(float((sc(Xtr[ite]).argmin(1) == ytr[ite]).mean()))
        a = float(np.mean(accs))
        if a > best_acc:
            best, best_acc = g, a
    return best, best_acc


def loto_nested(X, y, t, C, family, grid, n_take):
    accs, picks, per = [], [], {}
    for k in range(n_take):
        tr, te = t != k, t == k
        g, _ = _inner_pick(X[tr], y[tr], t[tr], C, family, grid)
        sc = family(X[tr], y[tr], C, g)
        pred = sc(X[te]).argmin(1)
        a = float((pred == y[te]).mean())
        accs.append(a)
        picks.append(g)
        per["take%d" % k] = {"acc_pct": round(100 * a, 2), "chosen": g}
    return float(np.mean(accs)), float(np.std(accs)), picks, per


def loto_fixed(X, y, t, C, fitter, n_take):
    accs, per, P, Y = [], {}, [], []
    for k in range(n_take):
        tr, te = t != k, t == k
        pred = fitter(X[tr], y[tr], C)(X[te]).argmin(1)
        accs.append(float((pred == y[te]).mean()))
        per["take%d" % k] = round(100 * accs[-1], 2)
        P.append(pred)
        Y.append(y[te])
    return (float(np.mean(accs)), float(np.std(accs)), per,
            np.concatenate(P), np.concatenate(Y))


def loto_nested_preds(X, y, t, C, family, grid, n_take):
    P, Y = [], []
    for k in range(n_take):
        tr, te = t != k, t == k
        g, _ = _inner_pick(X[tr], y[tr], t[tr], C, family, grid)
        P.append(family(X[tr], y[tr], C, g)(X[te]).argmin(1))
        Y.append(y[te])
    return np.concatenate(P), np.concatenate(Y)


def syllable_report(pred, true, syl, want=("ba", "ma", "pa", "ah", "aa")):
    out = {}
    for s in want:
        if s not in syl:
            continue
        c = syl.index(s)
        m = true == c
        if not m.any():
            continue
        out[s] = {"recall_pct": round(100 * float((pred[m] == c).mean()), 1),
                  "n": int(m.sum())}
    if "ba" in syl and "ma" in syl:
        b, mm = syl.index("ba"), syl.index("ma")
        out["ba_called_ma"] = int(((true == b) & (pred == mm)).sum())
        out["ma_called_ba"] = int(((true == mm) & (pred == b)).sum())
    return out


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--npz", default=os.path.join(here, "..", "holobrain",
                                                  "ear-human.npz"))
    ap.add_argument("--out", default=os.path.join(here, "ruler-nested.json"))
    a = ap.parse_args()

    d = np.load(a.npz, allow_pickle=True)
    X = d["V"].astype(np.float64)
    y = d["y"].astype(np.int64)
    t = d["t"].astype(np.int64)
    syl = [str(s) for s in d["syllables"]]
    C, n_take = len(syl), int(t.max()) + 1
    nrm = np.linalg.norm(X, axis=1, keepdims=True)
    X = np.where(nrm > 0, X / nrm, X)

    print("corpus %d clips, %d syllables, %d takes, dim %d, chance %.2f%%\n"
          % (len(X), C, n_take, X.shape[1], 100.0 / C))
    res = {"chance_pct": round(100.0 / C, 2), "fixed": {}, "nested": {}}

    print("A. RULERS WITH NO KNOB  (leave-one-TAKE-out, 22-way)")
    print("%-50s %8s %6s   %s" % ("ruler", "mean", "sd", "ba/ma"))
    FIXED = [("R0 nearest single CLIP  (THE OLD RULER)", fit_nn_clip),
             ("R1 mean distance to clips", fit_mean_clip),
             ("R2 CENTROID of the syllable", fit_centroid),
             ("R3 centroid + pooled diag spread", fit_diag_pooled),
             ("R4 centroid + per-class spread (ear3 today)", fit_diag_perclass)]
    for name, f in FIXED:
        m, s, per, pred, true = loto_fixed(X, y, t, C, f, n_take)
        sr = syllable_report(pred, true, syl)
        res["fixed"][name] = {"loto_mean_pct": round(100 * m, 2),
                              "loto_sd_pct": round(100 * s, 2),
                              "per_take": per, "syllables": sr}
        print("%-50s %7.2f%% %5.2f   ba %3.0f%% ma %3.0f%%  b->m %d m->b %d"
              % (name, 100 * m, 100 * s, sr["ba"]["recall_pct"],
                 sr["ma"]["recall_pct"], sr["ba_called_ma"], sr["ma_called_ba"]))

    print("\nB. RULERS WITH A KNOB, CHOSEN INSIDE THE FOLD  (never on the test take)")
    FAMS = [("R5 WCCN whiten + centroid", fit_wccn_score,
             [0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 0.90, 0.97]),
            ("R6 nuisance projection + centroid", fit_nuisance,
             [0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32])]
    for name, fam, grid in FAMS:
        m, s, picks, per = loto_nested(X, y, t, C, fam, grid, n_take)
        pred, true = loto_nested_preds(X, y, t, C, fam, grid, n_take)
        sr = syllable_report(pred, true, syl)
        res["nested"][name] = {"loto_mean_pct": round(100 * m, 2),
                               "loto_sd_pct": round(100 * s, 2),
                               "chosen_per_fold": picks, "per_take": per,
                               "grid": grid, "syllables": sr}
        print("%-50s %7.2f%% %5.2f   chosen %s" % (name, 100 * m, 100 * s, picks))
        print("%-50s              ba %3.0f%% ma %3.0f%%  b->m %d m->b %d"
              % ("", sr["ba"]["recall_pct"], sr["ma"]["recall_pct"],
                 sr["ba_called_ma"], sr["ma_called_ba"]))

    print("\nC. WITHIN / BETWEEN, and the reconciliation with the 08-30 record")
    Z = X
    D = np.sqrt(np.maximum(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1), 0))
    iu = np.triu_indices(len(Z), 1)
    dd = D[iu]
    ss = (y[:, None] == y[None, :])[iu]
    st = (t[:, None] == t[None, :])[iu]
    rows = {
        "within, same syllable, ALL pairs   (= the recorded 0.575)":
            float(dd[ss].mean()),
        "within, same syllable, DIFFERENT take": float(dd[ss & ~st].mean()),
        "within, same syllable, SAME take": float(dd[ss & st].mean()),
        "between, different syllable, ALL pairs": float(dd[~ss].mean()),
        "between, different syllable, DIFFERENT take": float(dd[~ss & ~st].mean()),
        "between, different syllable, SAME take   (= the recorded 0.881?)":
            float(dd[~ss & st].mean()),
        "between, CENTROID to CENTROID": float(np.mean([
            np.linalg.norm(X[y == i].mean(0) - X[y == j].mean(0))
            for i in range(C) for j in range(C) if i < j])),
    }
    for k, v in rows.items():
        print("   %-58s %7.4f" % (k, v))
    res["within_between_variants_raw"] = rows

    # the same statistic once the nuisance subspace is deleted (descriptive)
    S = _within_scatter(X, y, C)
    ev, U = np.linalg.eigh(S)
    for k in (4, 8, 16):
        N = U[:, ::-1][:, :k]
        P = np.eye(S.shape[0]) - N @ N.T
        wb = within_between(X, y, t, P)
        res["within_between_nuisance_k%d_descriptive" % k] = wb
        print("   nuisance k=%-2d  within(diff take) %.4f  between %.4f  "
              "ratio %.4f  d' %.3f"
              % (k, wb["within_same_syllable_diff_take"],
                 wb["between_diff_syllable"], wb["ratio_within_over_between"],
                 wb["dprime"]))

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("\nwrote %s" % a.out)


if __name__ == "__main__":
    main()
