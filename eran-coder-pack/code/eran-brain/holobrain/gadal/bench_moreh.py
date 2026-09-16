"""GADAL on the MOREH lessons: does growing beat picking a size?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE TESTBED, AND WHY THIS ONE
-----------------------------
MOREH's corpus is the smallest place where capacity >> data is already measured:
333 verified lessons over 24 syllables -- but only **22 distinct inputs**, because the
14 ear facts cannot tell cha from kha or ka from qa. So the honest split is
leave-one-FACT-GROUP-out (22 folds), not leave-one-syllable-out: with kha held out and
cha still in training, a pure memoriser scores a free hit for nothing. (MOREH's own
STATUS.md keeps a "real, without twins" column for exactly this reason.)

TWO TARGETS, ON PURPOSE
-----------------------
  --target decisions   the 14 ear facts -> the 7 discrete decisions (21 one-hot columns),
                       least squares to one-hot, decoded by per-head argmax -- the same
                       objective MOREH's own scorers use. Metric: held-out accuracy.
  --target amounts     the 14 ear facts -> the mouth amounts, scored where live.
                       Metric: masked MAE on per-amount z-scores.

They are here for different reasons and neither alone would be honest:

  decisions HAS A METRIC THAT SEPARATES. MOREH's ridge scores 85.6% held out against a
            74.4% majority floor -- an 11-point gap, so a number from this task can tell
            a good model from a bad one. But the decisions are a DETERMINISTIC function
            of the fact-group (measured: no group holds two decision sets), so the
            irreducible floor is exactly 0 and growth condition B carries no information.
  amounts   HAS A REAL FLOOR. Each syllable has ~14 verified variants with identical
            facts and different amounts, so the within-group spread is a measured
            irreducible error and condition B bites. But its aggregate metric barely
            separates (LOGO: const 0.874, ridge 0.886) -- and where a metric cannot tell
            good from bad, no conclusion drawn from it is worth anything.

THE CONTROLS (a growth mechanism that only beats a straw man has proved nothing)
--------------------------------------------------------------------------------
  majority / const  the do-nothing floor everything must clear
  near              nearest fact-group by Hamming -- MOREH's Copy floor
  ridge14           closed-form linear on the SAME 14 inputs the nets get
  ridge49           MOREH's own house model: linear on 14 facts + 35 hand-built
                    place x manner conjunctions. The nets are NOT given those 35
                    columns; a hidden layer has to find that structure itself.
  fixed-w           a fixed-width net at every size, early-stopped on val
  FIXED*            the fixed width CHOSEN BY VAL -- the well-chosen fixed size, the
                    control the whole claim stands or falls against
  FIXED-max         a width nobody sized to the data -- standard practice
  GADAL             starts at width 1, grows only on underfit, prunes, keeps best-val

THE INSTRUMENT IS CHECKED BEFORE IT IS USED
-------------------------------------------
--shuffle re-assigns which fact-group owns which answers. Every marginal and the whole
within-group spread survive; only the input->output map dies, so NO model can generalise.
If our numbers cannot tell that case from the real one they are measuring nothing, and
every conclusion drawn from them is false confidence. Run both, always.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "moreh")))

from grow import Gardener, noise_floor          # noqa: E402
from net import Net                             # noqa: E402

WIDTHS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128)


# ---------------------------------------------------------------------------- the data
def load(target="decisions"):
    """Read MOREH's lessons. READ ONLY -- this file never writes into moreh/."""
    import anatomy as A                                             # moreh.anatomy
    import learn                                                    # moreh.learn
    rows = learn.load_lessons()
    X = np.stack([r["x"] for r in rows])
    syl = np.array([r["syl"] for r in rows])
    keys = [tuple(x) for x in X]
    order = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    g = np.array([order[k] for k in keys])
    E = np.stack([A.ear(r["x"]) for r in rows])                     # MOREH's own 49 features

    if target == "decisions":
        heads, cols = [], 0
        for d in A.DEC_NAMES:
            heads.append((d, cols, cols + len(A.DECISIONS[d])))
            cols += len(A.DECISIONS[d])
        Y = np.zeros((len(rows), cols))
        for i, r in enumerate(rows):
            for d, a, _ in heads:
                Y[i, a + A.DECISIONS[d].index(r["dec"][d])] = 1.0
        M = np.ones_like(Y)
        return dict(X=X, Y=Y, M=M, g=g, syl=syl, E=E, heads=heads, target=target,
                    names=A.DEC_NAMES)
    if target == "amounts":
        Y = np.stack([r["am"] for r in rows])
        M = np.stack([r["live"] for r in rows]).astype(float)
        return dict(X=X, Y=Y, M=M, g=g, syl=syl, E=E, heads=None, target=target,
                    names=A.AMOUNTS)
    raise ValueError(target)


def shuffle_map(X, g, seed=12345):
    """Known-bad: keep every row, every answer and every within-group spread, and destroy
    ONLY which input owns which answers. Generalisation becomes impossible by construction."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(g.max() + 1)
    reps = {}
    for i, gi in enumerate(g):
        reps.setdefault(int(gi), X[i])
    return np.stack([reps[int(perm[gi])] for gi in g])


def standardise(Y, M, tr):
    """Per-column z-scores from the TRAIN rows only."""
    mu, sd = np.zeros(Y.shape[1]), np.ones(Y.shape[1])
    for j in range(Y.shape[1]):
        m = tr & (M[:, j] > 0)
        if m.sum() >= 2:
            mu[j] = Y[m, j].mean()
            s = Y[m, j].std()
            sd[j] = s if s > 1e-9 else 1.0
        elif m.sum() == 1:
            mu[j] = Y[m, j].mean()
    return (Y - mu) / sd, mu, sd


def certify(Y, M, g, tr, min_groups=3, min_expl=0.5):
    """TRAIN-ONLY: score an amount only if the training data itself says it is a function
    of the input -- live in >= min_groups distinct train groups, and at least min_expl of
    its variance sits BETWEEN groups rather than inside them. Nothing here sees test.
    (Without this, d_pre -- live in exactly 2 groups -- contributes 9.4-sigma z-scores and
    swamps every other amount.)"""
    ok = np.zeros(Y.shape[1], bool)
    for j in range(Y.shape[1]):
        m = tr & (M[:, j] > 0)
        gs = np.unique(g[m])
        if len(gs) < min_groups:
            continue
        y, gy = Y[m, j], g[m]
        tot = y.var()
        if tot <= 1e-12:
            continue
        within = np.mean([((y[gy == u] - y[gy == u].mean()) ** 2).mean()
                          for u in gs if (gy == u).sum() > 1] or [0.0])
        if 1.0 - within / tot >= min_expl:
            ok[j] = True
    return ok


# ---------------------------------------------------------------------------- scoring
def accuracy(P, Y, heads):
    """Per-head argmax, averaged over heads and rows -- the decisions metric."""
    hit = 0
    for _, a, b in heads:
        hit += float((P[:, a:b].argmax(1) == Y[:, a:b].argmax(1)).sum())
    return hit / (len(Y) * len(heads))


def masked_mae(P, Y, M):
    return float((np.abs(P - Y) * M).sum() / max(float(M.sum()), 1.0))


def score(P, Y, M, heads):
    return accuracy(P, Y, heads) if heads else -masked_mae(P, Y, M)   # higher is better


# ---------------------------------------------------------------------------- floors
def majority(Y, tr, heads):
    P = np.zeros_like(Y)
    for _, a, b in heads:
        P[:, a + int(Y[tr, a:b].sum(0).argmax())] = 1.0
    return P


def const_pred(Y):
    return np.zeros_like(Y)                                          # z-scored: 0 is the mean


def nearest(F, Y, M, tr):
    P = np.zeros_like(Y)
    Ftr, Ytr, Mtr = F[tr], Y[tr], M[tr]
    for i in range(len(F)):
        d = np.abs(Ftr - F[i]).sum(1)
        near = d == d.min()
        for j in range(Y.shape[1]):
            m = near & (Mtr[:, j] > 0)
            P[i, j] = np.median(Ytr[m, j]) if m.any() else 0.0
    return P


def ridge_pred(F, Y, M, tr, lam):
    F1 = np.hstack([F, np.ones((len(F), 1))])
    P = np.zeros_like(Y)
    for j in range(Y.shape[1]):
        m = tr & (M[:, j] > 0)
        if m.sum() < 2:
            continue
        A_ = F1[m].T @ F1[m] + lam * np.eye(F1.shape[1])
        A_[-1, -1] -= lam
        P[:, j] = F1 @ np.linalg.solve(A_, F1[m].T @ Y[m, j])
    return P


def ridge_best(F, Y, M, tr, va, heads, lams=(1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0)):
    best = (-math.inf, None, None)
    for lam in lams:
        P = ridge_pred(F, Y, M, tr, lam)
        s = score(P[va], Y[va], M[va], heads)
        if s > best[0]:
            best = (s, lam, P)
    return best[2], best[1]


# ---------------------------------------------------------------------------- fixed size
def fit_fixed(width, Xtr, Ytr, Mtr, Xva, Yva, Mva, seed, lr=0.03, check=25, max_epochs=6000,
              es_patience=12):
    """A fixed-width net trained exactly the way the gardener trains, early-stopped on val.
    This is the CONTROL, so it gets every advantage the grower gets."""
    n = Net(Xtr.shape[1], Ytr.shape[1], widths=(width,), seed=seed, act="relu")
    best = {"val": math.inf, "state": n.state(), "epoch": 0}
    bad, ep = 0, 0
    while ep < max_epochs:
        for _ in range(check):
            n.step(Xtr, Ytr, Mtr, lr=lr)
        ep += check
        va = n.loss(Xva, Yva, Mva)
        if va < best["val"] * (1 - 1e-4):
            best = {"val": va, "state": n.state(), "epoch": ep}
            bad = 0
        else:
            bad += 1
            if bad >= es_patience:
                break
    n.restore(best["state"])
    return n, best, ep


# ---------------------------------------------------------------------------- one fold
def run_fold(D, held, seed, n_val=5, quick=False, keep_log=False):
    X, Y, M, g, E, heads = D["X"], D["Y"], D["M"], D["g"], D["E"], D["heads"]
    groups = np.unique(g)
    rng = np.random.default_rng(1000 * seed + int(held))
    te = g == held
    rest = np.array([u for u in groups if u != held])
    va = np.isin(g, rng.choice(rest, size=min(n_val, len(rest) - 2), replace=False))
    tr = ~te & ~va

    if D["target"] == "amounts":                       # z-score and certify on TRAIN only
        Yz, _, _ = standardise(Y, M, tr)
        Ms = M * certify(Y, M, g, tr)[None, :]
    else:
        Yz, Ms = Y, M

    Xtr, Ytr, Mtr, gtr = X[tr], Yz[tr], Ms[tr], g[tr]
    Xva, Yva, Mva = X[va], Yz[va], Ms[va]
    Xte, Yte, Mte = X[te], Yz[te], Ms[te]
    fl = noise_floor(Ytr, Mtr, gtr)

    out = {"held": int(held), "seed": int(seed), "n_tr": int(tr.sum()), "n_va": int(va.sum()),
           "n_te": int(te.sum()), "n_groups_tr": int(len(np.unique(gtr))),
           "floor": fl["floor"], "floor_usable": bool(fl["usable"])}

    def three(net):
        return {"train": score(net.forward(Xtr), Ytr, Mtr, heads),
                "val": score(net.forward(Xva), Yva, Mva, heads),
                "test": score(net.forward(Xte), Yte, Mte, heads),
                "train_mse": net.loss(Xtr, Ytr, Mtr), "val_mse": net.loss(Xva, Yva, Mva),
                "test_mse": net.loss(Xte, Yte, Mte), "params": net.n_params}

    widths = (1, 4, 16, 64) if quick else WIDTHS
    me = 1500 if quick else 6000
    out["fixed"] = {}
    for w in widths:
        net, best, ep = fit_fixed(w, Xtr, Ytr, Mtr, Xva, Yva, Mva, seed, max_epochs=me)
        out["fixed"][w] = {**three(net), "epochs": ep, "best_epoch": best["epoch"]}

    for key, mode in (("gadal", "zero"), ("gadal_split", "split")):
        gd = Gardener(X.shape[1], Yz.shape[1], seed=seed, max_epochs=me,
                      max_width=max(widths), widen_mode=mode)
        net, best = gd.fit(Xtr, Ytr, Mtr, Xva, Yva, Mva, groups_tr=gtr)
        grows = [r for r in gd.log if r["kind"] == "grow"]
        out[key] = {**three(net), "width": net.widths[-1], "mode": mode,
                    "n_grow": len(grows),
                    "n_prune": sum(1 for r in gd.log if r["kind"] == "prune" and r["accepted"]),
                    "n_prune_refused": sum(1 for r in gd.log
                                           if r["kind"] == "prune" and not r["accepted"]),
                    "max_preserve_delta": max([r["preserve_max_abs_delta"] for r in grows],
                                              default=0.0),
                    "epochs": gd.log[-1]["epoch"],
                    "halt_reason": next((r["reason"] for r in gd.log
                                         if r["kind"] == "halt_growth"), None),
                    "trail": [(r["width_before"][-1], r["width_after"][-1]) for r in grows]}
        if keep_log:
            out[key]["log"] = gd.log

    # ---- the floors, all judged on the same test rows
    P_maj = majority(Yz, tr, heads) if heads else const_pred(Yz)
    out["majority"] = score(P_maj[te], Yte, Mte, heads)
    out["near"] = score(nearest(X, Yz, Ms, tr)[te], Yte, Mte, heads)
    P14, lam14 = ridge_best(X, Yz, Ms, tr, va, heads)
    P49, lam49 = ridge_best(E, Yz, Ms, tr, va, heads)
    out["ridge14"] = score(P14[te], Yte, Mte, heads)
    out["ridge14_train"] = score(P14[tr], Ytr, Mtr, heads)
    out["ridge49"] = score(P49[te], Yte, Mte, heads)
    out["ridge49_train"] = score(P49[tr], Ytr, Mtr, heads)
    out["lam14"], out["lam49"] = lam14, lam49
    return out


# ---------------------------------------------------------------------------- the run
def _be_polite():
    """PC heavy work runs BELOW_NORMAL or it starves Iddo's live microphone
    (feedback_pc_heavy_work_below_normal: renders once caused 78% empty decodes)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),
                                                0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
    except Exception:
        pass


def main():
    _be_polite()
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="decisions", choices=("decisions", "amounts"))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    D = load(a.target)
    if a.shuffle:
        # E (MOREH's 49 hand-built ear features) is a function of X and MUST be rebuilt from
        # the shuffled X. The first shuffled run left it holding the true map, and ridge49
        # scored 0.8312 on destroyed data -- identical to its 0.8247 on the real data. That
        # is what a control is for: it caught the harness, not the model.
        import anatomy as A                                          # moreh.anatomy
        D["X"] = shuffle_map(D["X"], D["g"])
        D["E"] = np.stack([A.ear(x) for x in D["X"]])
    groups = np.unique(D["g"])
    print(f"target {a.target}  lessons {len(D['X'])}  distinct inputs {len(groups)}  "
          f"syllables {len(set(D['syl']))}  outputs {D['Y'].shape[1]}"
          + ("   [SHUFFLED: known-bad control]" if a.shuffle else ""))

    folds, t0 = [], time.time()
    for seed in range(a.seeds):
        for held in groups:
            folds.append(run_fold(D, held, seed, quick=a.quick,
                                  keep_log=(seed == 0 and held == groups[0])))
        print(f"  seed {seed} done  {time.time()-t0:.0f}s")

    tag = a.target + ("_shuffled" if a.shuffle else "")
    out = a.out or os.path.join(_HERE, "runs", f"{tag}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"target": a.target, "shuffled": a.shuffle, "seeds": a.seeds,
                   "quick": a.quick, "folds": folds}, f, ensure_ascii=False)
    print("wrote", out)
    report(folds, a.target)


def _ci(v):
    """Mean and a 95% interval over folds x seeds. Folds are not independent draws from
    anything, so this is a spread, not a p-value, and it is labelled as one."""
    v = np.asarray(v, float)
    return v.mean(), 1.96 * v.std(ddof=1) / math.sqrt(len(v))


def report(folds, target):
    hi = target == "decisions"
    unit = "accuracy" if hi else "-MAE"
    ws = sorted(folds[0]["fixed"])
    print(f"\n  THE TRAIN/VAL GAP AT EVERY FIXED SIZE ({unit}, mean over "
          f"{len(folds)} fold x seed runs)")
    print(f"  {'width':>6} {'params':>7} {'train':>8} {'val':>8} {'test':>8} "
          f"{'gap tr-va':>10} {'mse tr':>8} {'mse va':>8} {'mse gap%':>9}")
    best_w, best_val = None, -math.inf
    for w in ws:
        tr = np.mean([f["fixed"][w]["train"] for f in folds])
        va = np.mean([f["fixed"][w]["val"] for f in folds])
        te = np.mean([f["fixed"][w]["test"] for f in folds])
        mtr = np.mean([f["fixed"][w]["train_mse"] for f in folds])
        mva = np.mean([f["fixed"][w]["val_mse"] for f in folds])
        print(f"  {w:>6} {folds[0]['fixed'][w]['params']:>7} {tr:>8.4f} {va:>8.4f} {te:>8.4f} "
              f"{tr-va:>10.4f} {mtr:>8.4f} {mva:>8.4f} {100*(mva-mtr)/max(mtr,1e-9):>8.1f}%")
        if va > best_val:
            best_val, best_w = va, w

    # per-run val-chosen width: the honest way a practitioner would pick, fold by fold
    perrun = [max(ws, key=lambda w: f["fixed"][w]["val"]) for f in folds]
    oracle = [max(f["fixed"][w]["test"] for w in ws) for f in folds]
    rows = [("majority/const floor", [f["majority"] for f in folds], ""),
            ("nearest fact-group", [f["near"] for f in folds], ""),
            ("ridge14 (same input)", [f["ridge14"] for f in folds], ""),
            ("ridge49 MOREH house", [f["ridge49"] for f in folds], "hand-built conjunctions"),
            (f"FIXED* val-chosen w={best_w}", [f["fixed"][best_w]["test"] for f in folds],
             "one width for all folds"),
            ("FIXED* per-run val-chosen", [f["fixed"][w]["test"] for f, w in zip(folds, perrun)],
             "width re-picked every fold"),
            (f"FIXED-{ws[-1]} unsized", [f["fixed"][ws[-1]]["test"] for f in folds],
             "standard practice"),
            ("GADAL grown (zero)", [f["gadal"]["test"] for f in folds], ""),
            ("GADAL grown (Net2Net split)", [f["gadal_split"]["test"] for f in folds],
             "the classic copy-and-split"),
            ("[oracle best width by TEST]", oracle, "NOT achievable; an upper bound only")]
    print(f"\n  HELD-OUT ({unit}, +- is a 95% spread over runs, not a p-value)")
    print(f"  {'':<28} {'mean':>8}          {'median':>8}")
    for name, v, note in rows:
        m, c = _ci(v)
        print(f"  {name:<28} {m:>8.4f} +- {c:.4f}   {np.median(v):>8.4f}   {note}")
    if not hi:
        print("  (the median matters here: one fold's certified amounts sit ~7.6 sigma from "
              "the train mean\n   and would otherwise decide the mean on its own)")

    gw = [f["gadal"]["width"] for f in folds]
    dl = max(f["gadal"]["max_preserve_delta"] for f in folds)
    print(f"\n  GADAL grew to width {np.mean(gw):.1f} +- {np.std(gw):.1f} "
          f"(range {min(gw)}-{max(gw)}), "
          f"{np.mean([f['gadal']['n_grow'] for f in folds]):.1f} growth steps, "
          f"{np.mean([f['gadal']['n_prune'] for f in folds]):.2f} prunes kept / "
          f"{np.mean([f['gadal']['n_prune_refused'] for f in folds]):.2f} refused")
    print(f"  worst function-preservation delta over every growth step in the whole run: {dl:.3e}")
    print(f"  train epochs: GADAL {np.mean([f['gadal']['epochs'] for f in folds]):.0f} vs "
          f"the fixed-size sweep {np.mean([sum(f['fixed'][w]['epochs'] for w in ws) for f in folds]):.0f}")
    hr = {}
    for f in folds:
        hr[f["gadal"]["halt_reason"]] = hr.get(f["gadal"]["halt_reason"], 0) + 1
    print(f"  why growth halted: {hr}")
    print(f"  floor used by condition B: {np.mean([f['floor'] for f in folds]):.6f} "
          f"(usable in {sum(f['floor_usable'] for f in folds)}/{len(folds)} runs)")

    # paired comparisons -- the same fold and seed, so the fold noise cancels
    print("\n  PAIRED, per run (the same fold and seed on both sides)")
    for label, other in ((f"FIXED*(w={best_w})", [f["fixed"][best_w]["test"] for f in folds]),
                         ("FIXED* per-run", [f["fixed"][w]["test"] for f, w in zip(folds, perrun)]),
                         (f"FIXED-{ws[-1]}", [f["fixed"][ws[-1]]["test"] for f in folds]),
                         ("ridge49 house", [f["ridge49"] for f in folds]),
                         ("GADAL split", [f["gadal_split"]["test"] for f in folds])):
        d = np.array([f["gadal"]["test"] for f in folds]) - np.array(other)
        m, c = _ci(d)
        print(f"  GADAL - {label:<16} {m:+.4f} +- {c:.4f}   "
              f"win {int((d>1e-9).sum()):>2} / tie {int((np.abs(d)<=1e-9).sum()):>2} / "
              f"loss {int((d<-1e-9).sum()):>2}")


if __name__ == "__main__":
    main()
