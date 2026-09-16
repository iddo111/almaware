"""A7 -- does the KNEE of the take-curve move as the class count grows?

Only K=2..6 is measurable (only 6 units have >3 takes), and I say so. Within
that range: for every K, the full take-curve under the HONEST design
(train = takes 0-32, test = takes 67-99: separated in time), and the N at
which the curve reaches 95% / 99% of its own N=33 value.
"""
import json, itertools, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
rng = np.random.default_rng(31)
EARLY, LATE = np.arange(0, 33), np.arange(67, 100)
NG = [1, 2, 3, 5, 8, 10, 15, 20, 25, 33]

def curve(us, draws=120):
    out = []
    for N in NG:
        a = []
        for _ in range(draws):
            tr = np.concatenate([idx[u][rng.choice(EARLY, N, replace=False)] for u in us])
            te = np.concatenate([idx[u][LATE] for u in us])
            a.append(nn1(X[tr], unit[tr], X[te], unit[te])[1])
        out.append(100*float(np.mean(a)))
    return out

print("HONEST design (train early third, test late third). chance = 100/K.")
hdr = "  K  " + "".join(f"N={n:<5d}" for n in NG) + "  95%@N  99%@N"
print(hdr)
res = {}
for K in [2, 3, 4, 5, 6]:
    combos = list(itertools.combinations(DEEP, K))
    if len(combos) > 10: combos = [tuple(rng.choice(DEEP, K, replace=False)) for _ in range(10)]
    cs = np.array([curve(list(c), draws=60) for c in combos]).mean(0)
    asym = cs[-1]
    k95 = next(NG[i] for i in range(len(NG)) if cs[i] >= 0.95*asym)
    k99 = next(NG[i] for i in range(len(NG)) if cs[i] >= 0.99*asym)
    res[K] = dict(curve=list(cs), k95=k95, k99=k99, chance=100/K)
    print(f"  {K}  " + "".join(f"{v:<7.2f}" for v in cs) + f"  {k95:<6d} {k99:<6d}")
print("\n  same, expressed as fraction of the K's own N=33 asymptote:")
for K in res:
    cs = np.array(res[K]["curve"]); print(f"  K={K}  " + "".join(f"{v/cs[-1]:<7.3f}" for v in cs))
json.dump(res, open("a7.json","w"), indent=1)
print("\n  NOTE: K=7..220 is NOT MEASURABLE from this data -- 19 of the 25 units")
print("        have 3 takes. No file in booth/ contains a take-curve above K=6.")
