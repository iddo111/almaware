# -*- coding: utf-8 -*-
"""ruler.py -- MEASURE THE RULER THE THROAT IS JUDGED BY.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: "tikken et ha-sargel shel ha-garon: lenaked mul merkaz ha-havara
bimkom merhak le-klip boded." -- score against the syllable's CENTRE, not the
distance to one clip.

THE FINDING THIS ANSWERS. On the frozen legacy192 cochlea, over the 396 human
reference clips (22 syllables x 6 takes x 3), two humans saying the SAME
syllable sit 0.575 apart while two humans saying DIFFERENT syllables sit 0.881
apart. The whole syllable signal is 0.306 and the speaker spread is 1.9x bigger.
A search that minimises distance to a clip climbs the speaker, not the syllable.

WHAT IS MEASURED HERE, and the floor each number can fall through:
  * leave-one-TAKE-out 22-way retrieval. Fit on 5 takes, classify the 6th,
    rotate all 6. Chance 4.55%. The frozen ear's published number is 79.55%.
  * within/between: mean pairwise distance same-syllable-different-take vs
    different-syllable. Lower ratio = more of the metric is the syllable.
  * EVERY fitted quantity (centroid, spread, covariance) is fit on the TRAINING
    takes of that fold only. Leaking the held-out take is how a ruler flatters
    itself.

Run:  python ruler.py --npz ../holobrain/ear-human.npz
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np


# --------------------------------------------------------------- the rulers
# Each ruler is fit on training clips (Xtr, ytr) and then scores a query
# against every class. Smaller = closer. All return (n_q, n_class).

def fit_nn_clip(Xtr, ytr, C):
    """R0 -- THE OLD RULER: distance to a single clip, min over that class."""
    def score(Q):
        D = np.sqrt(np.maximum(((Q[:, None, :] - Xtr[None, :, :]) ** 2).sum(-1), 0))
        return np.stack([D[:, ytr == c].min(1) for c in range(C)], 1)
    return score


def fit_mean_clip(Xtr, ytr, C):
    """R1 -- mean distance to all clips of the class (not the same as R2)."""
    def score(Q):
        D = np.sqrt(np.maximum(((Q[:, None, :] - Xtr[None, :, :]) ** 2).sum(-1), 0))
        return np.stack([D[:, ytr == c].mean(1) for c in range(C)], 1)
    return score


def _centroids(Xtr, ytr, C, renorm=True):
    M = np.stack([Xtr[ytr == c].mean(0) for c in range(C)])
    if renorm:
        n = np.linalg.norm(M, axis=1, keepdims=True)
        M = np.where(n > 0, M / n, M)
    return M


def fit_centroid(Xtr, ytr, C):
    """R2 -- THE NEW RULER, plain: distance to the syllable's centre.
    L2-renormalised centroid: verify.py's and zivug.py's convention."""
    M = _centroids(Xtr, ytr, C)
    return lambda Q: np.linalg.norm(Q[:, None, :] - M[None, :, :], axis=-1)


def fit_diag_pooled(Xtr, ytr, C, floor_rel=0.05):
    """R3 -- centroid + POOLED per-dim within-class spread (diagonal
    Mahalanobis). One w for every class, so distances stay comparable."""
    M = _centroids(Xtr, ytr, C)
    R = np.concatenate([Xtr[ytr == c] - Xtr[ytr == c].mean(0) for c in range(C)])
    s = R.std(0, ddof=0)
    s = np.maximum(s, max(1e-12, floor_rel * float(np.median(s))))
    return lambda Q: np.linalg.norm((Q[:, None, :] - M[None, :, :]) / s[None, None, :],
                                    axis=-1)


def fit_diag_perclass(Xtr, ytr, C, floor_rel=0.05):
    """R4 -- what ear3.judge.wdist ACTUALLY does today: centroid AND spread are
    per class. Each class gets its own denominator, so scores are not
    comparable between classes -- which a 22-way retrieval test can expose."""
    M = np.stack([Xtr[ytr == c].mean(0) for c in range(C)])
    W = []
    for c in range(C):
        s = Xtr[ytr == c].std(0, ddof=0)
        W.append(np.maximum(s, max(1e-12, floor_rel * float(np.median(s)))))
    W = np.stack(W)
    return lambda Q: np.stack(
        [np.linalg.norm((Q - M[c]) / W[c], axis=-1) for c in range(C)], 1)


def fit_wccn(Xtr, ytr, C, lam=0.10):
    """R5 -- THE MANIFOLD RULER: pooled WITHIN-class covariance whitening, then
    the centroid. The within-class covariance IS the speaker/take direction;
    dividing it out is what turns 'imitate this throat' into 'say this
    syllable'. Shrinkage lam mixes toward the identity -- 330 training clips
    cannot estimate a 192x192 covariance on their own."""
    R = np.concatenate([Xtr[ytr == c] - Xtr[ytr == c].mean(0) for c in range(C)])
    S = np.cov(R, rowvar=False, bias=True)
    S = (1 - lam) * S + lam * (np.trace(S) / S.shape[0]) * np.eye(S.shape[0])
    ev, U = np.linalg.eigh(S)
    ev = np.maximum(ev, 1e-10)
    A = U @ np.diag(ev ** -0.5) @ U.T                    # whitening transform
    M = np.stack([Xtr[ytr == c].mean(0) for c in range(C)]) @ A
    return (lambda Q: np.linalg.norm((Q @ A)[:, None, :] - M[None, :, :], axis=-1)), A


def fit_wccn_score(Xtr, ytr, C, lam=0.10):
    return fit_wccn(Xtr, ytr, C, lam)[0]


# ----------------------------------------------------------- within/between
def within_between(X, y, t, A=None):
    """Mean pairwise distance, same syllable / different take, versus different
    syllable. Optionally in a whitened space (A applied first)."""
    Z = X @ A if A is not None else X
    D = np.sqrt(np.maximum(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1), 0))
    iu = np.triu_indices(len(Z), 1)
    d = D[iu]
    same_syl = (y[:, None] == y[None, :])[iu]
    same_take = (t[:, None] == t[None, :])[iu]
    w_xt = d[same_syl & ~same_take]      # same syllable, DIFFERENT take
    w_st = d[same_syl & same_take]       # same syllable, same take
    b = d[~same_syl]
    return {"within_same_syllable_diff_take": float(w_xt.mean()),
            "within_same_syllable_same_take": float(w_st.mean()),
            "between_diff_syllable": float(b.mean()),
            "signal_between_minus_within": float(b.mean() - w_xt.mean()),
            "ratio_within_over_between": float(w_xt.mean() / b.mean()),
            "dprime": float((b.mean() - w_xt.mean())
                            / np.sqrt(0.5 * (b.var() + w_xt.var())))}


# ------------------------------------------------------------------- driver
def loto(X, y, t, fitter, C, n_take):
    """Leave-one-TAKE-out 22-way retrieval. Nothing is fit on the held-out take."""
    accs, per = [], {}
    for k in range(n_take):
        tr, te = t != k, t == k
        sc = fitter(X[tr], y[tr], C)
        pred = sc(X[te]).argmin(1)
        acc = float((pred == y[te]).mean())
        accs.append(acc)
        per["take%d" % k] = round(100 * acc, 2)
    return float(np.mean(accs)), float(np.std(accs)), per


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--npz", default=os.path.join(here, "..", "holobrain",
                                                  "ear-human.npz"))
    ap.add_argument("--lam", type=float, default=0.10)
    ap.add_argument("--lam-sweep", action="store_true")
    ap.add_argument("--out", default=os.path.join(here, "ruler-measured.json"))
    a = ap.parse_args()

    d = np.load(a.npz, allow_pickle=True)
    X = d["V"].astype(np.float64)
    y = d["y"].astype(np.int64)
    t = d["t"].astype(np.int64)
    syl = [str(s) for s in d["syllables"]]
    C, n_take = len(syl), int(t.max()) + 1
    nrm = np.linalg.norm(X, axis=1, keepdims=True)
    X = np.where(nrm > 0, X / nrm, X)             # already unit, kept explicit
    print("corpus: %d clips, %d syllables, %d takes, dim %d   chance %.2f%%"
          % (len(X), C, n_take, X.shape[1], 100.0 / C))

    RULERS = [
        ("R0  nearest single CLIP       (THE OLD RULER)", fit_nn_clip),
        ("R1  mean distance to clips", fit_mean_clip),
        ("R2  CENTROID of the syllable  (the fix, plain)", fit_centroid),
        ("R3  centroid + pooled spread  (diag Mahalanobis)", fit_diag_pooled),
        ("R4  centroid + PER-CLASS spread (ear3.judge today)", fit_diag_perclass),
        ("R5  WCCN whiten + centroid    (the manifold fix)",
         lambda Xt, yt, c: fit_wccn_score(Xt, yt, c, a.lam)),
    ]
    res = {"corpus": os.path.abspath(a.npz), "n_clips": int(len(X)),
           "n_syllables": C, "n_takes": n_take, "dim": int(X.shape[1]),
           "chance_pct": round(100.0 / C, 2), "lam": a.lam, "rulers": {}}

    print("\nLEAVE-ONE-TAKE-OUT 22-WAY RETRIEVAL  (fit on 5 takes, judge the 6th)")
    print("%-52s %8s %7s" % ("ruler", "mean", "sd"))
    for name, f in RULERS:
        m, s, per = loto(X, y, t, f, C, n_take)
        res["rulers"][name] = {"loto_mean_pct": round(100 * m, 2),
                               "loto_sd_pct": round(100 * s, 2), "per_take": per}
        print("%-52s %7.2f%% %6.2f" % (name, 100 * m, 100 * s))

    if a.lam_sweep:
        print("\nWCCN shrinkage sweep (is the dial tuned, or coarse?)")
        res["lam_sweep"] = {}
        for lam in (0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75):
            m, s, _ = loto(X, y, t,
                           lambda Xt, yt, c, L=lam: fit_wccn_score(Xt, yt, c, L),
                           C, n_take)
            res["lam_sweep"]["%.2f" % lam] = round(100 * m, 2)
            print("   lam %.2f -> %6.2f%%  (sd %.2f)" % (lam, 100 * m, 100 * s))

    print("\nWITHIN / BETWEEN  (all 396 clips, pairwise)")
    raw = within_between(X, y, t)
    res["within_between_raw"] = raw
    print("  RAW cochlea space (the ruler as it stands):")
    for k, v in raw.items():
        print("    %-38s %8.4f" % (k, v))

    # This whitening is fit on ALL takes ONLY for the descriptive statistic.
    # Every ACCURACY number above was fold-honest.
    _, A = fit_wccn(X, y, C, a.lam)
    wh = within_between(X, y, t, A)
    res["within_between_wccn_all_takes_descriptive"] = wh
    print("  WCCN-whitened space (descriptive; retrieval above was fold-honest):")
    for k, v in wh.items():
        print("    %-38s %8.4f" % (k, v))

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("\nwrote %s" % a.out)


if __name__ == "__main__":
    main()
