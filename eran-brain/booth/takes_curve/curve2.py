"""curve2.py -- DESIGN D: leave-one-BLOCK-out, and SPREAD vs CLUSTERED takes.

Design B (random split of one sitting) is the optimistic ceiling. Design C
(train on his first N, test on his last 30) lost 13 points -- inside a SINGLE
session. That is the session-leak scar showing up at the scale of minutes, and
it means the number that should decide his recording hours is not B.

DESIGN D is the honest middle and the closest thing to leave-one-SESSION-out
that 100 consecutive takes can support: cut the 100 takes into 10 contiguous
blocks of 10 (each block is ~30-60 s of continuous recording -- a mini-session),
hold out ONE whole block, and train on takes drawn from the other nine. Test
clips are therefore never temporal neighbours of any training clip, but the
training set still spans the whole sitting. 10 blocks x 3 seeds = 30 draws.

And the question that decides how he should SPEND the takes, not just how many:
  SPREAD    the N training takes are drawn from across the whole session
  CLUSTERED the N training takes are N CONSECUTIVE takes -- i.e. he said the
            syllable N times in a row and moved on
Same N, same test blocks, same ear, same probe. If spread beats clustered, then
"10 repeats now" is worth less than "10 repeats scattered", and the recording
plan changes shape, not just size.
"""
import json
import sys

import numpy as np

CACHE = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\8aa52163-564a-4846-8f48-cd46afaf48f4\scratchpad\t06_cochlea.npz"
OUT = r"D:\CLAUDE\eran-brain\booth\TAKES-CURVE.json"
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
BLOCK = 10
N_BLOCKS = 10
SEEDS = 3
D_GRID = [1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 70, 90]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

d = np.load(CACHE, allow_pickle=True)
X, unit, take = d["X"], d["unit"].astype(str), d["take"].astype(int)
idx = {}
for u in DEEP:
    rows = np.where(unit == u)[0]
    idx[u] = rows[np.argsort(take[rows])]
CHANCE = 100.0 / len(DEEP)


def score(tr_takes, te_takes, metric="zs"):
    tr_r = np.concatenate([idx[u][tr_takes[u]] for u in DEEP])
    te_r = np.concatenate([idx[u][te_takes[u]] for u in DEEP])
    Xtr, ytr, Xte, yte = X[tr_r], unit[tr_r], X[te_r], unit[te_r]
    if metric == "zs":
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    else:
        A, B = Xtr, Xte
    dd = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    return float(np.mean(ytr[np.argmin(dd, axis=1)] == yte))


print("=" * 84)
print("DESIGN D -- leave-one-BLOCK-out (10 contiguous takes = one mini-session)")
print("            test = 1 whole block (60 clips); train = N takes from the other 9")
print("            10 blocks x %d seeds = %d draws.  CHANCE = %.2f%%"
      % (SEEDS, N_BLOCKS * SEEDS, CHANCE))
print("=" * 84)
print("%4s %8s %7s | %8s %6s | %9s %6s | %8s %6s | chance"
      % ("N", "n_train", "n_test", "SPREAD", "sd", "CLUSTERED", "sd", "shuffled", "sd"))

design_D = {}
for N in D_GRID:
    sp, cl, sh = [], [], []
    for b in range(N_BLOCKS):
        test_t = np.arange(b * BLOCK, (b + 1) * BLOCK)
        pool = np.setdiff1d(np.arange(100), test_t)          # sorted, 90 long
        for s in range(SEEDS):
            rng = np.random.RandomState(7000 + b * 97 + s)
            # SPREAD: N drawn uniformly from the whole remaining session
            tr_sp = {u: rng.permutation(pool)[:N] for u in DEEP}
            # CLUSTERED: N CONSECUTIVE takes out of the pool (said in a row)
            tr_cl = {}
            for u in DEEP:
                start = rng.randint(0, max(1, len(pool) - N + 1))
                tr_cl[u] = pool[start:start + N]
            te = {u: test_t for u in DEEP}
            sp.append(score(tr_sp, te))
            cl.append(score(tr_cl, te))
            # shuffled-label control on the spread arm
            tr_r = np.concatenate([idx[u][tr_sp[u]] for u in DEEP])
            te_r = np.concatenate([idx[u][te[u]] for u in DEEP])
            Xtr, Xte = X[tr_r], X[te_r]
            mu, sd_ = Xtr.mean(0), Xtr.std(0) + 1e-9
            A, B = (Xtr - mu) / sd_, (Xte - mu) / sd_
            dd = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
            sh.append(float(np.mean(rng.permutation(unit[tr_r])[np.argmin(dd, 1)]
                                    == unit[te_r])))
    design_D[str(N)] = {
        "N": N, "n_train": N * 6, "n_test": BLOCK * 6,
        "spread_mean": float(np.mean(sp) * 100), "spread_sd": float(np.std(sp) * 100),
        "clustered_mean": float(np.mean(cl) * 100), "clustered_sd": float(np.std(cl) * 100),
        "shuffled_mean": float(np.mean(sh) * 100), "shuffled_sd": float(np.std(sh) * 100),
        "draws": N_BLOCKS * SEEDS}
    r = design_D[str(N)]
    print("%4d %8d %7d | %7.2f%% %5.2f | %8.2f%% %5.2f | %7.2f%% %5.2f | %.2f%%"
          % (N, N * 6, BLOCK * 6, r["spread_mean"], r["spread_sd"],
             r["clustered_mean"], r["clustered_sd"],
             r["shuffled_mean"], r["shuffled_sd"], CHANCE))

# ----------------------------------------------------------------- the knee
print()
print("=" * 84)
print("KNEE on DESIGN D (spread) -- smallest N whose mean is within 1 SD of N=90")
print("=" * 84)
ref = design_D[str(D_GRID[-1])]
knees = {}
for arm in ("spread", "clustered"):
    thr = ref[arm + "_mean"] - ref[arm + "_sd"]
    kN = D_GRID[-1]
    for N in D_GRID:
        if design_D[str(N)][arm + "_mean"] >= thr:
            kN = N
            break
    knees["D_" + arm] = {"knee_N": kN, "threshold_pct": thr,
                         "ref_mean_pct": ref[arm + "_mean"],
                         "ref_sd_pct": ref[arm + "_sd"],
                         "knee_mean_pct": design_D[str(kN)][arm + "_mean"]}
    print("  %-10s ref(N=90) %5.2f%% +/- %4.2f -> threshold %5.2f%% -> KNEE N = %d"
          "  (mean %.2f%%)" % (arm, ref[arm + "_mean"], ref[arm + "_sd"], thr, kN,
                               design_D[str(kN)][arm + "_mean"]))

# --------------------------------------------- fraction of achievable gain
print()
print("HOW MUCH OF THE ACHIEVABLE GAIN EACH N BUYS (design D, spread)")
print("  achievable gain = mean(N=90) - chance = %.2f - %.2f = %.2f points"
      % (ref["spread_mean"], CHANCE, ref["spread_mean"] - CHANCE))
span = ref["spread_mean"] - CHANCE
frac = {}
print("%4s | %8s | %10s | %s" % ("N", "acc", "gain kept", "utterances for 220 units"))
for N in D_GRID:
    m = design_D[str(N)]["spread_mean"]
    f = (m - CHANCE) / span * 100
    frac[str(N)] = {"N": N, "acc_pct": m, "gain_kept_pct": f,
                    "utterances_220_units": N * 220}
    print("%4d | %7.2f%% | %9.1f%% | %6d" % (N, m, f, N * 220))

# ------------------------------------------- marginal points per extra take
print()
print("MARGINAL GAIN (design D, spread): points bought per extra take")
prev_n = prev_m = None
marg = {}
for N in D_GRID:
    m = design_D[str(N)]["spread_mean"]
    if prev_n is not None:
        per = (m - prev_m) / (N - prev_n)
        marg["%d->%d" % (prev_n, N)] = {"delta_points": m - prev_m,
                                        "points_per_extra_take": per}
        print("  %3d -> %3d : %+6.2f points, %+7.3f points per extra take"
              % (prev_n, N, m - prev_m, per))
    prev_n, prev_m = N, m

# -------------------------------------------------- spread vs clustered gap
print()
print("SPREAD MINUS CLUSTERED, same N (positive => scattering the takes wins)")
gap = {}
for N in D_GRID:
    g = design_D[str(N)]["spread_mean"] - design_D[str(N)]["clustered_mean"]
    gap[str(N)] = g
    print("  N=%3d : %+6.2f points" % (N, g))

# ---- what N of CLUSTERED takes equals N=10 SPREAD? the exchange rate ------
target = design_D["10"]["spread_mean"]
eq = None
for N in D_GRID:
    if design_D[str(N)]["clustered_mean"] >= target:
        eq = N
        break
print()
if eq is None:
    print("  NO number of clustered takes up to N=90 reaches the accuracy of 10")
    print("  spread takes (%.2f%%). Clustered tops out at %.2f%% at N=90."
          % (target, design_D["90"]["clustered_mean"]))
else:
    print("  %d CLUSTERED takes are needed to match %d SPREAD takes (%.2f%%)."
          % (eq, 10, target))

with open(OUT, "r", encoding="utf-8") as f:
    results = json.load(f)
results["design_D_leave_block_out"] = design_D
results["knees"].update(knees)
results["gain_fraction_D_spread"] = frac
results["marginal_gain_D_spread"] = marg
results["spread_minus_clustered_points"] = gap
results["design_D_note"] = (
    "10 contiguous takes = 1 held-out block, a within-session stand-in for a "
    "held-out SESSION. Test clips are never temporal neighbours of training "
    "clips. SPREAD draws the N training takes from across the whole sitting; "
    "CLUSTERED takes N consecutive takes, i.e. the syllable said N times in a "
    "row. Same N, same test blocks, same ear, same probe.")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print()
print("raw numbers -> %s" % OUT)
