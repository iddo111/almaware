"""ceiling.py -- the number that actually decides the recording plan.

ERAN stores a syllable as a PROTOTYPE: the centroid of what he has heard. So the
question "how many takes buy anything" has an exact form:

    take N clips of a syllable from ONE sitting, average them, L2 it.
    (a) how close is that to the TRUE centroid of that same sitting?      -> within
    (b) how close is it to the centroid of a DIFFERENT sitting of the
        same syllable by the same mouth?                                  -> cross
    (c) how close are the two sittings' full centroids to each other?     -> CEILING

(a) climbs towards 1.0 as N grows -- that is just averaging out mic noise and
breath. (b) climbs too, but it can never pass (c). The moment the remaining
headroom in (a) falls below the gap in (c), every further take is polishing a
quantity already smaller than the error between one day and the next. That N is
the honest knee, and it does not depend on how many classes are on the board.

Only ah, ma and ih were recorded in more than one sitting on 2026-08-23, so only
they can answer it. Three units, seven ordered sitting-pairs.

Also re-reports P3's usable draw counts, because at large N some sub-sessions
are too small to supply N+10 clips and those draws are silently skipped.
"""
import json
import sys

import numpy as np

CACHE = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\8aa52163-564a-4846-8f48-cd46afaf48f4\scratchpad\t06_cochlea.npz"
STAGED = r"D:\CLAUDE\eran-brain\booth\staged\t06"
OUT = r"D:\CLAUDE\eran-brain\booth\TAKES-CURVE.json"
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import glob
import os

d = np.load(CACHE, allow_pickle=True)
X, unit, take = d["X"], d["unit"].astype(str), d["take"].astype(int)
paths = sorted(glob.glob(os.path.join(STAGED, "*.wav")))
mt = np.array([os.path.getmtime(p) for p in paths])

subs = {}
for u in sorted(set(unit.tolist())):
    m = np.where(unit == u)[0]
    m = m[np.argsort(take[m])]
    sid = np.concatenate([[0], np.cumsum(np.diff(mt[m]) > 60.0)])
    ss = [m[sid == k] for k in range(sid.max() + 1)]
    subs[u] = [s for s in ss if len(s) >= 20]

MULTI = [u for u in ("ah", "ba", "ma", "ima", "ih", "abba") if len(subs[u]) >= 2]
print("units recorded in more than one sitting (>=20 clips each): %s" % MULTI)
for u in MULTI:
    print("   %s : sitting sizes %s" % (u, [len(s) for s in subs[u]]))


def cent(rows):
    v = X[rows].mean(0)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


GRID = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30]
DRAWS = 200
print()
print("=" * 84)
print("PROTOTYPE CONVERGENCE -- cosine of an N-take prototype to two targets")
print("=" * 84)
rows_out = {}
agg = {N: {"within": [], "cross": []} for N in GRID}
ceil_all = []
for u in MULTI:
    ss = subs[u]
    for a in range(len(ss)):
        for b in range(len(ss)):
            if a == b:
                continue
            A, B = ss[a], ss[b]
            CA, CB = cent(A), cent(B)
            ceiling = float(CA @ CB)
            ceil_all.append(ceiling)
            for N in GRID:
                if N > len(A) - 1:
                    continue
                w, c = [], []
                rng = np.random.RandomState(11000 + a * 31 + b)
                for _ in range(DRAWS):
                    pick = rng.choice(len(A), N, replace=False)
                    cn = cent(A[pick])
                    w.append(float(cn @ CA))
                    c.append(float(cn @ CB))
                agg[N]["within"].append(np.mean(w))
                agg[N]["cross"].append(np.mean(c))
            print("  %-5s sitting %d (n=%3d) -> sitting %d (n=%3d) : "
                  "BETWEEN-SITTING CEILING cos = %.4f" % (u, a, len(A), b, len(B), ceiling))

CEIL = float(np.mean(ceil_all))
print()
print("  mean between-sitting ceiling over %d ordered pairs : cos = %.4f"
      % (len(ceil_all), CEIL))
print("  -> the gap a different day costs you                : %.4f" % (1.0 - CEIL))
print()
print("%4s | %14s | %16s | %14s | %s"
      % ("N", "within-sitting", "headroom left", "cross-sitting", "verdict"))
conv = {}
knee_proto = None
for N in GRID:
    if not agg[N]["within"]:
        continue
    w = float(np.mean(agg[N]["within"]))
    c = float(np.mean(agg[N]["cross"]))
    head = 1.0 - w
    conv[str(N)] = {"N": N, "within_cos": w, "cross_cos": c,
                    "headroom_within": head, "ceiling_cos": CEIL,
                    "pct_of_ceiling": c / CEIL * 100}
    beyond = head < (1.0 - CEIL)
    if beyond and knee_proto is None:
        knee_proto = N
    print("%4d | cos %10.4f | %13.4f | cos %10.4f | %s"
          % (N, w, head, c,
             "past the point -- noise now smaller than the day-to-day gap"
             if beyond else "still averaging out real noise"))
print()
print("  PROTOTYPE KNEE = smallest N where the remaining within-sitting error")
print("  (1 - within_cos) is SMALLER than the between-sitting gap (1 - %.4f = %.4f):"
      % (CEIL, 1.0 - CEIL))
print("      N = %s takes" % knee_proto)

# --- 99% / 99.5% of the achievable cross-sitting cosine --------------------
print()
print("  cross-sitting cosine as a fraction of its own ceiling:")
for N in GRID:
    if str(N) in conv:
        print("    N=%2d : %6.2f%% of ceiling" % (N, conv[str(N)]["pct_of_ceiling"]))
hit99 = next((N for N in GRID if str(N) in conv
              and conv[str(N)]["pct_of_ceiling"] >= 99.0), None)
hit995 = next((N for N in GRID if str(N) in conv
               and conv[str(N)]["pct_of_ceiling"] >= 99.5), None)
print("    -> 99.0%% of the achievable cross-sitting match at N = %s takes" % hit99)
print("    -> 99.5%% of the achievable cross-sitting match at N = %s takes" % hit995)

with open(OUT, "r", encoding="utf-8") as f:
    results = json.load(f)
results["prototype_convergence"] = {
    "units_with_multiple_sittings": MULTI,
    "between_sitting_ceiling_cos": CEIL,
    "between_sitting_gap": 1.0 - CEIL,
    "curve": conv,
    "knee_N_prototype": knee_proto,
    "N_for_99pct_of_ceiling": hit99,
    "N_for_99_5pct_of_ceiling": hit995,
    "draws_per_point": DRAWS,
    "note": "N-take prototype from ONE sitting, cosine to (a) that sitting's own "
            "full centroid and (b) a DIFFERENT sitting's full centroid. The knee "
            "is where 1-within_cos drops below 1-ceiling: past it, extra takes "
            "shrink an error already smaller than the day-to-day gap.",
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print()
print("raw numbers -> %s" % OUT)
