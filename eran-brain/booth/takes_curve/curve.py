"""curve.py -- HOW MANY TAKES PER SYLLABLE ACTUALLY BUY ANYTHING?

Measured on Iddo's own 600 wavs (6 units x 100 takes, talker t06, 2026-08-23),
through ERAN's OWN frozen cochlea (body/ears.py, 24 bands x 8 slices = 192 d),
with the project's own probe (1-NN, z-scored by TRAIN statistics, squared
euclidean -- corpus-syllables/verify.py lines 154-158).

THREE DESIGNS, because the literal request is not measurable as stated:
  A  spec-literal   train = N random takes/unit, test = ALL remaining takes.
                    N=100 is IMPOSSIBLE: training on all 100 takes leaves no
                    take to test on. N=99 (leave-one-take-out) is the closest
                    thing that exists, and its test set is 6 clips, so its
                    across-draw SD is dominated by binomial noise on 6 trials.
  B  fixed test pool (PRIMARY, and the one the knee is read off)
                    30 takes/unit are held out per draw (180 test clips, the
                    SAME size at every N, so the SDs are comparable), train is
                    N drawn from the other 70.
  C  temporal block train = the FIRST N takes he recorded, test = his LAST 30.
                    Same session, but the train takes are no longer temporally
                    interleaved with the test takes. This is the within-session
                    shadow of the session-leak scar.

TWO METRICS, because the z-score is itself N-dependent:
  zs   verify.py exactly: z-score by train mu/sd. At N=1 that sd is estimated
       from 6 vectors and is mostly noise -- which would depress low-N scores
       for a reason that has nothing to do with phonetics.
  cos  plain squared euclidean on the raw L2-normalized cochlea vectors
       (monotone in cosine). No fitted statistic, so nothing about the probe
       changes with N. The honest low-N reading.
"""
import datetime
import json
import os
import sys

import numpy as np

CACHE = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\8aa52163-564a-4846-8f48-cd46afaf48f4\scratchpad\t06_cochlea.npz"
OUT = r"D:\CLAUDE\eran-brain\booth\TAKES-CURVE.json"
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
DRAWS = 30
N_GRID = [1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 70, 90, 99]
TEST_POOL = 30                      # design B / C held-out takes per unit

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

d = np.load(CACHE, allow_pickle=True)
X, unit, take = d["X"], d["unit"].astype(str), d["take"].astype(int)
DIM = int(d["dim"])

# ---- index the deep units: idx[u][k] = row of take k of unit u -------------
idx = {}
for u in DEEP:
    rows = np.where(unit == u)[0]
    order = rows[np.argsort(take[rows])]
    assert len(order) == 100 and list(take[order]) == list(range(100)), u
    idx[u] = order
CHANCE = 100.0 / len(DEEP)


def nn_parts(Xtr, ytr, Xte, yte, metric):
    """1-NN, the project's probe. metric 'zs' = verify.py's train z-score."""
    if metric == "zs":
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    else:
        A, B = Xtr, Xte
    dd = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    return dd, ytr[np.argmin(dd, axis=1)], yte


def score(Xtr, ytr, Xte, yte, metric):
    _, pred, yte = nn_parts(Xtr, ytr, Xte, yte, metric)
    return float(np.mean(pred == yte))


def build(train_takes, test_takes):
    tr_r = np.concatenate([idx[u][train_takes[u]] for u in DEEP])
    te_r = np.concatenate([idx[u][test_takes[u]] for u in DEEP])
    return X[tr_r], unit[tr_r], X[te_r], unit[te_r]


results = {"design_A": {}, "design_B": {}, "design_C": {}}

# ============================== DESIGN A ===================================
print("=" * 80)
print("DESIGN A -- spec-literal: train = N random takes/unit, test = the rest")
print("            %d random draws per N.  CHANCE = %.2f%%  (6 units)"
      % (DRAWS, CHANCE))
print("=" * 80)
print("%4s %8s %7s | %8s %6s | %9s %6s | chance"
      % ("N", "n_train", "n_test", "zs mean", "zs sd", "cos mean", "cos sd"))
for N in N_GRID:
    if N >= 100:
        continue
    zs, co = [], []
    for s in range(DRAWS):
        rng = np.random.RandomState(1000 + s)
        trt = {u: rng.permutation(100)[:N] for u in DEEP}
        tet = {u: np.setdiff1d(np.arange(100), trt[u]) for u in DEEP}
        Xtr, ytr, Xte, yte = build(trt, tet)
        zs.append(score(Xtr, ytr, Xte, yte, "zs"))
        co.append(score(Xtr, ytr, Xte, yte, "cos"))
    r = {"N": N, "n_train": N * 6, "n_test": (100 - N) * 6,
         "zs_mean": float(np.mean(zs) * 100), "zs_sd": float(np.std(zs) * 100),
         "cos_mean": float(np.mean(co) * 100), "cos_sd": float(np.std(co) * 100),
         "draws": DRAWS}
    results["design_A"][str(N)] = r
    print("%4d %8d %7d | %7.2f%% %5.2f | %8.2f%% %5.2f | %.2f%%"
          % (N, N * 6, (100 - N) * 6, r["zs_mean"], r["zs_sd"],
             r["cos_mean"], r["cos_sd"], CHANCE))
print("%4s %8d %7d |  NOT MEASURABLE: training on all 100 takes leaves no take"
      " to test on." % ("100", 600, 0))

# ============================== DESIGN B ===================================
print()
print("=" * 80)
print("DESIGN B -- PRIMARY. Fixed test pool: %d held-out takes/unit (%d clips)"
      % (TEST_POOL, TEST_POOL * 6))
print("            train = N drawn from the other %d.  %d draws.  CHANCE = %.2f%%"
      % (100 - TEST_POOL, DRAWS, CHANCE))
print("=" * 80)
print("%4s %8s %7s | %8s %6s | %9s %6s | %6s | chance"
      % ("N", "n_train", "n_test", "zs mean", "zs sd", "cos mean", "cos sd", "shuf"))
B_GRID = [n for n in N_GRID if n <= 100 - TEST_POOL]
for N in B_GRID:
    zs, co, sh = [], [], []
    for s in range(DRAWS):
        rng = np.random.RandomState(2000 + s)
        perm = {u: rng.permutation(100) for u in DEEP}
        tet = {u: perm[u][:TEST_POOL] for u in DEEP}
        pool = {u: perm[u][TEST_POOL:] for u in DEEP}
        trt = {u: pool[u][:N] for u in DEEP}
        Xtr, ytr, Xte, yte = build(trt, tet)
        zs.append(score(Xtr, ytr, Xte, yte, "zs"))
        co.append(score(Xtr, ytr, Xte, yte, "cos"))
        sh.append(score(Xtr, rng.permutation(ytr), Xte, yte, "zs"))
    r = {"N": N, "n_train": N * 6, "n_test": TEST_POOL * 6,
         "zs_mean": float(np.mean(zs) * 100), "zs_sd": float(np.std(zs) * 100),
         "cos_mean": float(np.mean(co) * 100), "cos_sd": float(np.std(co) * 100),
         "shuffled_zs_mean": float(np.mean(sh) * 100),
         "shuffled_zs_sd": float(np.std(sh) * 100), "draws": DRAWS}
    results["design_B"][str(N)] = r
    print("%4d %8d %7d | %7.2f%% %5.2f | %8.2f%% %5.2f | %5.1f%% | %.2f%%"
          % (N, N * 6, TEST_POOL * 6, r["zs_mean"], r["zs_sd"],
             r["cos_mean"], r["cos_sd"], r["shuffled_zs_mean"], CHANCE))

# ============================== DESIGN C ===================================
print()
print("=" * 80)
print("DESIGN C -- temporal block: train = his FIRST N takes, test = his LAST %d."
      % TEST_POOL)
print("            Deterministic (no draws).  CHANCE = %.2f%%" % CHANCE)
print("=" * 80)
print("%4s %8s %7s | %7s | %7s | chance" % ("N", "n_train", "n_test", "zs", "cos"))
for N in B_GRID:
    trt = {u: np.arange(N) for u in DEEP}
    tet = {u: np.arange(100 - TEST_POOL, 100) for u in DEEP}
    Xtr, ytr, Xte, yte = build(trt, tet)
    a_zs = score(Xtr, ytr, Xte, yte, "zs")
    a_co = score(Xtr, ytr, Xte, yte, "cos")
    results["design_C"][str(N)] = {"N": N, "n_train": N * 6,
                                   "n_test": TEST_POOL * 6,
                                   "zs": a_zs * 100, "cos": a_co * 100}
    print("%4d %8d %7d | %6.2f%% | %6.2f%% | %.2f%%"
          % (N, N * 6, TEST_POOL * 6, a_zs * 100, a_co * 100, CHANCE))


# ============================== THE KNEE ===================================
def knee(table, key_mean, key_sd, grid):
    ref = table[str(grid[-1])]
    thr = ref[key_mean] - ref[key_sd]
    for N in grid:
        if table[str(N)][key_mean] >= thr:
            return N, thr, ref[key_mean], ref[key_sd]
    return grid[-1], thr, ref[key_mean], ref[key_sd]


print()
print("=" * 80)
print("THE KNEE -- smallest N whose MEAN is within 1 SD of the asymptote mean")
print("=" * 80)
knees = {}
for design, table, grid, km, ks in (
        ("A spec-literal  zs (ref N=99)", results["design_A"],
         [n for n in N_GRID if n < 100], "zs_mean", "zs_sd"),
        ("A spec-literal  cos(ref N=99)", results["design_A"],
         [n for n in N_GRID if n < 100], "cos_mean", "cos_sd"),
        ("B fixed pool    zs (ref N=70)", results["design_B"], B_GRID,
         "zs_mean", "zs_sd"),
        ("B fixed pool    cos(ref N=70)", results["design_B"], B_GRID,
         "cos_mean", "cos_sd")):
    k, thr, rm, rs = knee(table, km, ks, grid)
    knees[design] = {"knee_N": k, "threshold_pct": thr, "ref_mean_pct": rm,
                     "ref_sd_pct": rs, "knee_mean_pct": table[str(k)][km],
                     "knee_sd_pct": table[str(k)][ks]}
    print("  %-32s ref %5.2f%% +/- %4.2f  ->  threshold %5.2f%%  ->  KNEE N = %d"
          "  (mean %.2f%%)" % (design, rm, rs, thr, k, table[str(k)][km]))

# --- marginal gain per extra take, design B / zs ---------------------------
print()
print("MARGINAL GAIN, design B (zs): accuracy points bought by each step in N")
prev_n, prev_m = None, None
marg = {}
for N in B_GRID:
    m = results["design_B"][str(N)]["zs_mean"]
    if prev_n is not None:
        per = (m - prev_m) / (N - prev_n)
        marg["%d->%d" % (prev_n, N)] = {"delta_points": m - prev_m,
                                        "points_per_extra_take": per}
        print("  %3d -> %3d takes : %+6.2f points total, %+7.3f points per extra take"
              % (prev_n, N, m - prev_m, per))
    prev_n, prev_m = N, m
results["marginal_gain_B_zs"] = marg
results["knees"] = knees

# --- per-unit accuracy at the knee (design B, zs) --------------------------
KN = knees["B fixed pool    zs (ref N=70)"]["knee_N"]
print()
print("PER-UNIT accuracy at the knee (N=%d, design B, zs, %d draws)" % (KN, DRAWS))
per_unit = {u: [] for u in DEEP}
conf = np.zeros((6, 6))
for s in range(DRAWS):
    rng = np.random.RandomState(2000 + s)
    perm = {u: rng.permutation(100) for u in DEEP}
    tet = {u: perm[u][:TEST_POOL] for u in DEEP}
    trt = {u: perm[u][TEST_POOL:][:KN] for u in DEEP}
    Xtr, ytr, Xte, yte = build(trt, tet)
    _, pred, yte = nn_parts(Xtr, ytr, Xte, yte, "zs")
    for u in DEEP:
        m = yte == u
        per_unit[u].append(float(np.mean(pred[m] == u)))
    for i, u in enumerate(DEEP):
        for j, v in enumerate(DEEP):
            conf[i, j] += np.sum((yte == u) & (pred == v))
conf = conf / conf.sum(axis=1, keepdims=True) * 100
results["per_unit_at_knee"] = {u: {"mean_pct": float(np.mean(v) * 100),
                                   "sd_pct": float(np.std(v) * 100)}
                               for u, v in per_unit.items()}
for u in DEEP:
    print("  %5s : %5.1f%%  (sd %4.1f)"
          % (u, np.mean(per_unit[u]) * 100, np.std(per_unit[u]) * 100))
print()
print("  confusion, rows = true, cols = predicted (%):")
print("        " + "".join("%7s" % v for v in DEEP))
for i, u in enumerate(DEEP):
    print("  %5s " % u + "".join("%7.1f" % conf[i, j] for j in range(6)))
results["confusion_at_knee_pct"] = {u: {v: float(conf[i, j])
                                        for j, v in enumerate(DEEP)}
                                    for i, u in enumerate(DEEP)}

# --- 25-class reference: what the SAME ear does when the board gets wider ---
print()
print("=" * 80)
print("25-CLASS REFERENCE (all 25 units he recorded; the 19 shallow ones have")
print("only 3 takes, so N is capped at 2). NOT a take-curve -- a class-count")
print("sanity check, because the board is 220 units, not 6.")
print("=" * 80)
allu = sorted(set(unit.tolist()))
ch25 = 100.0 / len(allu)
cls25 = {}
for N in (1, 2):
    zs, co = [], []
    for s in range(DRAWS):
        rng = np.random.RandomState(3000 + s)
        tr_r, te_r = [], []
        for u in allu:
            rows = np.where(unit == u)[0]
            rows = rows[np.argsort(take[rows])][:3]      # first 3 takes only
            p = rng.permutation(3)
            tr_r += list(rows[p[:N]])
            te_r += list(rows[p[N:]])
        tr_r, te_r = np.array(tr_r), np.array(te_r)
        zs.append(score(X[tr_r], unit[tr_r], X[te_r], unit[te_r], "zs"))
        co.append(score(X[tr_r], unit[tr_r], X[te_r], unit[te_r], "cos"))
    cls25[str(N)] = {"N": N, "classes": len(allu), "chance_pct": ch25,
                     "zs_mean": float(np.mean(zs) * 100),
                     "zs_sd": float(np.std(zs) * 100),
                     "cos_mean": float(np.mean(co) * 100),
                     "cos_sd": float(np.std(co) * 100)}
    print("  N=%d takes, 25 classes : zs %5.2f%% (sd %4.2f)   cos %5.2f%% (sd %4.2f)"
          "   chance %.2f%%" % (N, np.mean(zs) * 100, np.std(zs) * 100,
                                np.mean(co) * 100, np.std(co) * 100, ch25))
for N in (1, 2):
    zs = []
    for s in range(DRAWS):
        rng = np.random.RandomState(3000 + s)
        tr_r, te_r = [], []
        for u in DEEP:
            rows = idx[u][:3]
            p = rng.permutation(3)
            tr_r += list(rows[p[:N]])
            te_r += list(rows[p[N:]])
        tr_r, te_r = np.array(tr_r), np.array(te_r)
        zs.append(score(X[tr_r], unit[tr_r], X[te_r], unit[te_r], "zs"))
    cls25["deep6_N%d" % N] = {"N": N, "classes": 6, "chance_pct": CHANCE,
                              "zs_mean": float(np.mean(zs) * 100),
                              "zs_sd": float(np.std(zs) * 100)}
    print("  N=%d takes,  6 classes : zs %5.2f%% (sd %4.2f)"
          "                            chance %.2f%%"
          % (N, np.mean(zs) * 100, np.std(zs) * 100, CHANCE))
results["class_count_reference"] = cls25

results["meta"] = {
    "measured_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "data": r"D:\CLAUDE\eran-brain\booth\staged\t06",
    "wavs_total": int(len(unit)), "wavs_used_for_curve": 600,
    "deep_units": DEEP, "takes_per_deep_unit": 100,
    "ear": {"module": r"D:\CLAUDE\eran-brain\body\ears.py", "repr": "cochlea",
            "n_bands": int(d["n_bands"]), "slices": 8, "dim": DIM,
            "frozen": True},
    "probe": "1-NN, squared euclidean; 'zs' = z-scored by TRAIN mu/sd exactly as "
             "corpus-syllables/verify.py; 'cos' = raw L2-normalized cochlea vectors",
    "chance_pct": CHANCE, "n_classes": 6, "draws_per_N": DRAWS,
    "test_pool_per_unit_designs_BC": TEST_POOL,
    "CAVEAT_SESSION_LEAK": "ALL 600 takes are from ONE session (t06, 2026-08-23). "
                           "Per the session-leak scar these numbers are a WITHIN-SESSION "
                           "ceiling and are optimistic for cross-session use. Design C is "
                           "the only within-session shadow of that effect available here.",
    "CAVEAT_N100": "N=100 with a disjoint test set does not exist: 100 takes were "
                   "recorded, so training on all of them leaves nothing to test. "
                   "N=99 (leave-one-take-out) is the asymptote in design A; N=70 in "
                   "design B.",
    "CAVEAT_CLASS_COUNT": "6 classes, not 220. See class_count_reference.",
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print()
print("raw numbers -> %s" % OUT)
