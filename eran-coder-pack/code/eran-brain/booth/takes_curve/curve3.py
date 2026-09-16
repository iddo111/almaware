"""curve3.py -- (1) PAIRED knee test, (2) the real cost of a take in seconds.

(1) The 1-SD knee rule the brief specifies uses the ACROSS-DRAW sd, and in
design D most of that sd is not measurement noise about N -- it is which block
got held out. Some blocks are simply harder. Since every N is scored on the
SAME 30 draws, the paired difference (acc at N=90 minus acc at N) removes that
nuisance entirely and is the sensitive test. Reported alongside the 1-SD rule,
never instead of it.

(2) HOW LONG A TAKE ACTUALLY COSTS HIM. Not a guess: the wav durations are on
disk and so are the file mtimes, which are the times the booth wrote each clip.
Median gap between consecutive takes of the same unit = the real seconds per
take, his own pace, including his breath and his pauses.
"""
import glob
import json
import os
import sys
import wave

import numpy as np

CACHE = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\8aa52163-564a-4846-8f48-cd46afaf48f4\scratchpad\t06_cochlea.npz"
STAGED = r"D:\CLAUDE\eran-brain\booth\staged\t06"
OUT = r"D:\CLAUDE\eran-brain\booth\TAKES-CURVE.json"
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
BLOCK, N_BLOCKS, SEEDS = 10, 10, 3
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


def score(tr_takes, te_takes):
    tr_r = np.concatenate([idx[u][tr_takes[u]] for u in DEEP])
    te_r = np.concatenate([idx[u][te_takes[u]] for u in DEEP])
    Xtr, ytr, Xte, yte = X[tr_r], unit[tr_r], X[te_r], unit[te_r]
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    dd = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    return float(np.mean(ytr[np.argmin(dd, axis=1)] == yte))


# ---- rebuild design D spread, keeping every per-draw score --------------
per_draw = {N: [] for N in D_GRID}
for N in D_GRID:
    for b in range(N_BLOCKS):
        test_t = np.arange(b * BLOCK, (b + 1) * BLOCK)
        pool = np.setdiff1d(np.arange(100), test_t)
        for s in range(SEEDS):
            rng = np.random.RandomState(7000 + b * 97 + s)
            tr = {u: rng.permutation(pool)[:N] for u in DEEP}
            per_draw[N].append(score(tr, {u: test_t for u in DEEP}))
P = {N: np.array(v) * 100 for N, v in per_draw.items()}
REF = D_GRID[-1]

print("=" * 82)
print("PAIRED TEST vs the asymptote (N=%d), design D spread, %d matched draws"
      % (REF, N_BLOCKS * SEEDS))
print("Same held-out blocks at every N, so the block-difficulty variance cancels.")
print("CHANCE = %.2f%%   (6 units)" % CHANCE)
print("=" * 82)
print("%4s | %8s | %14s | %8s | %s"
      % ("N", "acc", "deficit vs N=90", "95% CI", "significant?"))
paired = {}
knee_paired = None
for N in D_GRID:
    diff = P[REF] - P[N]
    m = float(diff.mean())
    sem = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    lo, hi = m - 1.96 * sem, m + 1.96 * sem
    sig = lo > 0
    paired[str(N)] = {"N": N, "acc_pct": float(P[N].mean()),
                      "deficit_vs_N90_pct": m, "sem_pct": sem,
                      "ci95_lo": lo, "ci95_hi": hi, "significant": bool(sig)}
    if not sig and knee_paired is None:
        knee_paired = N
    print("%4d | %7.2f%% | %+8.2f points | [%+5.2f,%+5.2f] | %s"
          % (N, P[N].mean(), m, lo, hi, "YES still behind" if sig else "no -- caught up"))
print()
print("  PAIRED KNEE = smallest N whose deficit vs N=90 is not statistically")
print("  distinguishable from zero (95%%):  N = %s" % knee_paired)

# also: smallest N within 1 PAIRED sd (the brief's rule, paired form)
knee_1sd_paired = None
for N in D_GRID:
    diff = P[REF] - P[N]
    if diff.mean() <= diff.std(ddof=1):
        knee_1sd_paired = N
        break
print("  Brief's 1-SD rule in PAIRED form (deficit <= 1 paired sd): N = %s"
      % knee_1sd_paired)

# ---- how many takes to be within 2 / 5 points of the asymptote ----------
print()
print("PRACTICAL TARGETS (design D spread, paired):")
for tol in (2.0, 5.0, 10.0):
    hit = next((N for N in D_GRID if (P[REF] - P[N]).mean() <= tol), None)
    print("  within %4.1f points of the N=90 asymptote : N = %s takes  (%s utterances"
          " for 220 units)" % (tol, hit, "%d" % (hit * 220) if hit else "n/a"))

# ================= (2) THE REAL COST OF A TAKE ==========================
print()
print("=" * 82)
print("WHAT A TAKE ACTUALLY COSTS -- measured off the files themselves")
print("=" * 82)
rows = []
for p in sorted(glob.glob(os.path.join(STAGED, "*.wav"))):
    n = os.path.basename(p)[:-4].split("_")
    with wave.open(p, "rb") as w:
        dur = w.getnframes() / float(w.getframerate())
    rows.append((n[0], int(n[2]), dur, os.path.getmtime(p)))
deep_rows = [r for r in rows if r[0] in DEEP]
durs = np.array([r[2] for r in deep_rows])
print("  600 deep-unit clips: audio duration median %.3f s  mean %.3f s  "
      "total %.1f s (%.1f min)"
      % (np.median(durs), durs.mean(), durs.sum(), durs.sum() / 60))

# consecutive-take mtime gaps, per unit
gaps = []
for u in DEEP:
    rr = sorted([r for r in deep_rows if r[0] == u], key=lambda r: r[1])
    ts = np.array([r[3] for r in rr])
    g = np.diff(ts)
    gaps.append(g)
allgap = np.concatenate(gaps)
pos = allgap[(allgap > 0) & (allgap < 120)]     # drop the between-unit jumps
print("  consecutive-take mtime gaps (same unit, 0-120 s): n=%d  median %.2f s  "
      "mean %.2f s  p10 %.2f  p90 %.2f"
      % (len(pos), np.median(pos), pos.mean(), np.percentile(pos, 10),
         np.percentile(pos, 90)))
span_all = max(r[3] for r in deep_rows) - min(r[3] for r in deep_rows)
print("  wall-clock span of the whole 600-clip sitting: %.1f s (%.1f min) "
      "-> %.2f s per take end-to-end" % (span_all, span_all / 60, span_all / 600))

SEC = float(np.median(pos))
WALL = span_all / 600.0
print()
print("  TWO cost estimates, both measured, neither invented:")
print("    tight  %.2f s/take  (median gap between consecutive takes)" % SEC)
print("    real   %.2f s/take  (whole sitting wall-clock / 600 clips)" % WALL)

print()
print("=" * 82)
print("THE BILL FOR 220 UNITS")
print("=" * 82)
print("%4s | %10s | %13s | %13s | %s"
      % ("N", "utterances", "at %.1f s/take" % SEC, "at %.1f s/take" % WALL,
         "acc (design D)"))
bill = {}
for N in D_GRID:
    utt = N * 220
    bill[str(N)] = {"N": N, "utterances": utt,
                    "hours_tight": utt * SEC / 3600.0,
                    "hours_wall": utt * WALL / 3600.0,
                    "acc_pct_design_D": float(P[N].mean())}
    print("%4d | %10d | %10.2f h | %10.2f h | %6.2f%%"
          % (N, utt, utt * SEC / 3600.0, utt * WALL / 3600.0, P[N].mean()))

with open(OUT, "r", encoding="utf-8") as f:
    results = json.load(f)
results["paired_test_design_D_spread"] = paired
results["knees"]["D_spread_PAIRED_95CI"] = {"knee_N": knee_paired,
                                            "rule": "smallest N whose paired deficit "
                                                    "vs N=90 has a 95% CI containing 0"}
results["knees"]["D_spread_PAIRED_1sd"] = {"knee_N": knee_1sd_paired,
                                           "rule": "smallest N whose paired deficit vs "
                                                   "N=90 is <= 1 paired sd"}
results["cost"] = {
    "clip_duration_median_s": float(np.median(durs)),
    "clip_duration_mean_s": float(durs.mean()),
    "total_audio_600_clips_s": float(durs.sum()),
    "consecutive_take_gap_median_s": SEC,
    "consecutive_take_gap_mean_s": float(pos.mean()),
    "sitting_wallclock_s": float(span_all),
    "sitting_wallclock_per_take_s": float(WALL),
    "source": "wav headers + file mtimes of the 600 deep-unit clips in staged/t06",
}
results["bill_for_220_units"] = bill
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print()
print("raw numbers -> %s" % OUT)
