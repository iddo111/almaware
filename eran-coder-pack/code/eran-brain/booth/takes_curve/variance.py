"""variance.py -- takes per sitting vs number of sittings, from the variance itself.

Two things the accuracy curves cannot say on their own:

(1) SCALE. A between-sitting cosine of 0.87 means nothing until you know what a
    between-UNIT cosine looks like. If two sittings of /ma/ are as far apart as
    /ma/ is from /ba/, the day is a bigger deal than the syllable.

(2) HOW TO SPLIT THE BUDGET. A prototype built from S sittings x K takes each has
    error  sigma_b^2 / S  +  sigma_w^2 / (S*K)  --  sigma_b^2 between sittings,
    sigma_w^2 within. Measure both and the split stops being a matter of taste.
    sigma_b^2 is estimated with the standard correction for the fact that each
    sitting centroid is itself an average of only n_s clips.

Only ah, ma and ih were recorded in more than one sitting, so sigma_b rests on
3 units and 8 sittings. Stated, not hidden.
"""
import glob
import json
import os
import sys

import numpy as np

CACHE = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\8aa52163-564a-4846-8f48-cd46afaf48f4\scratchpad\t06_cochlea.npz"
STAGED = r"D:\CLAUDE\eran-brain\booth\staged\t06"
OUT = r"D:\CLAUDE\eran-brain\booth\TAKES-CURVE.json"
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

d = np.load(CACHE, allow_pickle=True)
X, unit, take = d["X"], d["unit"].astype(str), d["take"].astype(int)
mt = np.array([os.path.getmtime(p) for p in sorted(glob.glob(os.path.join(STAGED, "*.wav")))])

subs = {}
for u in DEEP:
    m = np.where(unit == u)[0]
    m = m[np.argsort(take[m])]
    sid = np.concatenate([[0], np.cumsum(np.diff(mt[m]) > 60.0)])
    subs[u] = [m[sid == k] for k in range(sid.max() + 1) if (sid == k).sum() >= 20]


def cent(rows):
    v = X[rows].mean(0)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


# ---------------------------------------------------- (1) the scale
print("=" * 80)
print("SCALE -- cosine between full unit centroids (all 100 takes each)")
print("=" * 80)
C = {u: cent(np.where(unit == u)[0]) for u in DEEP}
print("       " + "".join("%8s" % u for u in DEEP))
off = []
for u in DEEP:
    line = "%6s " % u
    for v in DEEP:
        c = float(C[u] @ C[v])
        line += "%8.3f" % c
        if u != v:
            off.append(c)
    print(line)
BETWEEN_UNIT = float(np.mean(off))
print()
print("  mean BETWEEN-UNIT cosine  : %.4f  (n=%d pairs)" % (BETWEEN_UNIT, len(off)))
print("  max  BETWEEN-UNIT cosine  : %.4f  (the two hardest units to tell apart)"
      % max(off))

pairs = []
for u in subs:
    for a in range(len(subs[u])):
        for b in range(a + 1, len(subs[u])):
            pairs.append(float(cent(subs[u][a]) @ cent(subs[u][b])))
BETWEEN_SIT = float(np.mean(pairs))
print("  mean BETWEEN-SITTING cosine, same unit : %.4f  (n=%d pairs, units ah/ma/ih)"
      % (BETWEEN_SIT, len(pairs)))
print("  worst BETWEEN-SITTING cosine, same unit: %.4f" % min(pairs))
print()
print("  -> same syllable, two sittings : %.4f" % BETWEEN_SIT)
print("     two DIFFERENT syllables     : %.4f" % BETWEEN_UNIT)
print("     worst same-syllable pair    : %.4f  vs  hardest different-syllable pair"
      " %.4f" % (min(pairs), max(off)))
if min(pairs) < max(off):
    print("     ** the worst pair of sittings of ONE syllable is FURTHER APART than")
    print("        the closest pair of DIFFERENT syllables. The day outweighs the sound.")

# ------------------------------------------- (2) variance decomposition
print()
print("=" * 80)
print("VARIANCE DECOMPOSITION (192-d, squared euclidean, unnormalized centroids)")
print("=" * 80)
sw, sb, rows_rep = [], [], []
for u in subs:
    if len(subs[u]) < 2:
        continue
    cs = [X[s].mean(0) for s in subs[u]]
    ns = [len(s) for s in subs[u]]
    w = [float(np.mean(((X[s] - c) ** 2).sum(1))) for s, c in zip(subs[u], cs)]
    grand = np.mean(cs, axis=0)
    b_raw = float(np.mean([((c - grand) ** 2).sum() for c in cs]))
    S = len(cs)
    # unbiased-ish: each centroid carries sigma_w^2/n_s of its own noise
    corr = float(np.mean([wi / n for wi, n in zip(w, ns)]))
    b = max(b_raw * S / (S - 1) - corr, 0.0)
    sw.append(float(np.mean(w)))
    sb.append(b)
    rows_rep.append((u, S, ns, float(np.mean(w)), b))
    print("  %-5s %d sittings %s : sigma_w^2 = %.4f   sigma_b^2 = %.4f   ratio b/w = %.3f"
          % (u, S, ns, np.mean(w), b, b / np.mean(w) if np.mean(w) else float("nan")))
SW, SB = float(np.mean(sw)), float(np.mean(sb))
print()
print("  pooled sigma_w^2 (take to take, same sitting) = %.4f" % SW)
print("  pooled sigma_b^2 (sitting to sitting)         = %.4f" % SB)
print("  sigma_b^2 / sigma_w^2 = %.3f" % (SB / SW))

print()
print("PROTOTYPE ERROR for S sittings x K takes  =  sigma_b^2/S + sigma_w^2/(S*K)")
print("  (lower is better; the number is squared distance in the ear's own space)")
print()
budgets = [4, 6, 8, 10, 12, 16, 20, 30, 40, 60]
print("  total takes | best split (S x K) | error | error if all in ONE sitting")
plan = {}
for T in budgets:
    best, bestv = None, None
    for S in range(1, T + 1):
        if T % S:
            continue
        K = T // S
        v = SB / S + SW / (S * K)
        if bestv is None or v < bestv:
            bestv, best = v, (S, K)
    one = SB / 1 + SW / (1 * T)
    plan[str(T)] = {"total_takes": T, "best_S": best[0], "best_K": best[1],
                    "best_error": bestv, "one_sitting_error": one,
                    "ratio": one / bestv}
    print("  %11d | %6d x %-6d | %.4f | %.4f   (%.1fx worse)"
          % (T, best[0], best[1], bestv, one, one / bestv))

print()
print("DIMINISHING RETURNS OF K INSIDE ONE SITTING")
print("  error = sigma_b^2 + sigma_w^2/K ; sigma_b^2 = %.4f is a FLOOR K cannot move"
      % SB)
print("  %4s | %8s | %s" % ("K", "error", "% of the floor still removable"))
kcurve = {}
for K in (1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 100):
    e = SB + SW / K
    excess = (e - SB) / SB * 100
    kcurve[str(K)] = {"K": K, "error": e, "excess_over_floor_pct": excess}
    print("  %4d | %8.4f | take-noise adds %6.1f%% on top of the sitting floor" % (K, e, excess))
kstar = next(K for K in (1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 100)
             if SW / K <= 0.10 * SB)
kstar2 = next(K for K in (1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 100)
              if SW / K <= 0.05 * SB)
print()
print("  take-noise falls to 10%% of the sitting floor at K = %d takes" % kstar)
print("  take-noise falls to  5%% of the sitting floor at K = %d takes" % kstar2)
print("  past that, another take moves the prototype by less than a twentieth of")
print("  what simply coming back tomorrow moves it.")

with open(OUT, "r", encoding="utf-8") as f:
    results = json.load(f)
results["scale"] = {
    "between_unit_cos_mean": BETWEEN_UNIT,
    "between_unit_cos_max": float(max(off)),
    "between_sitting_cos_mean": BETWEEN_SIT,
    "between_sitting_cos_min": float(min(pairs)),
    "unit_centroid_cos_matrix": {u: {v: float(C[u] @ C[v]) for v in DEEP} for u in DEEP},
}
results["variance_decomposition"] = {
    "sigma_w2_within_sitting": SW,
    "sigma_b2_between_sitting": SB,
    "ratio_b_over_w": SB / SW,
    "per_unit": [{"unit": u, "n_sittings": S, "sizes": ns, "sigma_w2": w, "sigma_b2": b}
                 for u, S, ns, w, b in rows_rep],
    "model": "prototype error = sigma_b2/S + sigma_w2/(S*K) for S sittings x K takes",
    "best_split_by_budget": plan,
    "K_curve_one_sitting": kcurve,
    "K_take_noise_10pct_of_floor": kstar,
    "K_take_noise_5pct_of_floor": kstar2,
    "CAVEAT": "sigma_b2 rests on 3 units (ah, ma, ih) and 8 sittings, all inside "
              "2026-08-23. A real day-to-day sigma_b2 is likely LARGER, which would "
              "push the answer further towards more sittings and fewer takes.",
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print()
print("raw numbers -> %s" % OUT)
