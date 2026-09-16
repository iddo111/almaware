"""A6 -- DOES THE TAKE REQUIREMENT GROW WITH THE NUMBER OF CLASSES?

Only 3 takes exist for 19 of the 25 units, so the widest problem this data can
pose is K=25 at N<=2. Measure the gain from 1 take to 2 takes at every K.
If that gain grows with K, then 220 classes need MORE takes than 6 classes do
and the flat 'N takes for everything' recommendation is wrong.

Reported three ways, because raw points are not comparable across K (chance
moves): raw points, error REDUCTION (what a classifier actually buys), and
the above-chance ratio.
"""
import json, numpy as np
from probe import load, nn1
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(23)
first3 = {}
for u in sorted(set(unit)):
    r = np.where(unit == u)[0]; first3[u] = r[np.argsort(take[r])][:3]
ALL = sorted(first3)

def run(us, N):
    """train N of the 3 takes, test the remaining 3-N. Average over all splits."""
    accs = []
    for rep in range(3 if N == 1 else 3):
        tr, te = [], []
        for u in us:
            p = rng.permutation(3)
            tr.append(first3[u][p[:N]]); te.append(first3[u][p[N:]])
        tr, te = np.concatenate(tr), np.concatenate(te)
        accs.append(nn1(X[tr], unit[tr], X[te], unit[te])[1])
    return float(np.mean(accs))

print("   K  chance   N=1     N=2    gain(pts)  err 1->2  err reduction  ratio1  ratio2")
rows = []
for K in [2, 3, 4, 6, 8, 10, 12, 15, 20, 25]:
    a1, a2 = [], []
    reps = 400 if K < 25 else 60
    for _ in range(reps):
        us = list(rng.choice(ALL, K, replace=False)) if K < 25 else ALL
        a1.append(run(us, 1)); a2.append(run(us, 2))
    m1, m2 = 100*np.mean(a1), 100*np.mean(a2); ch = 100.0/K
    e1, e2 = 100-m1, 100-m2
    rows.append(dict(K=K, n1=m1, n2=m2, gain=m2-m1, err_red=100*(e1-e2)/e1,
                     r1=(m1-ch)/(100-ch), r2=(m2-ch)/(100-ch)))
    print(f"  {K:3d}  {ch:5.2f}%  {m1:6.2f}  {m2:6.2f}   {m2-m1:+6.2f}    "
          f"{e1:5.2f}->{e2:5.2f}   {100*(e1-e2)/e1:6.2f}%      "
          f"{(m1-ch)/(100-ch):.3f}  {(m2-ch)/(100-ch):.3f}")
json.dump(rows, open("a6.json","w"), indent=1)

K = np.array([r["K"] for r in rows]); G = np.array([r["gain"] for r in rows])
E = np.array([r["err_red"] for r in rows])
print(f"\n  r(log2 K, raw gain pts)       = {np.corrcoef(np.log2(K), G)[0,1]:+.3f}")
print(f"  r(log2 K, %% error reduction) = {np.corrcoef(np.log2(K), E)[0,1]:+.3f}")

print("\n=== how far does K=25 sit below K=6 at the SAME N? (3 takes, leave-one-take-out) ===")
def loto(rows_):
    ok = []
    for i in rows_:
        tr = np.array([j for j in rows_ if j != i])
        ok.append(nn1(X[tr], unit[tr], X[[i]], unit[[i]])[0][0] == unit[i])
    return 100*float(np.mean(ok))
pts = []
for K in [2,3,4,6,8,10,12,15,20,25]:
    a = []
    reps = 200 if K < 25 else 1
    for _ in range(reps):
        us = list(rng.choice(ALL, K, replace=False)) if K < 25 else ALL
        a.append(loto(list(np.concatenate([first3[u] for u in us]))))
    pts.append((K, float(np.mean(a))))
lk = np.log2([p[0] for p in pts]); ac = np.array([p[1] for p in pts])
b, a0 = np.polyfit(lk, ac, 1)
print(f"  linear fit acc = {a0:.2f} {b:+.2f} * log2(K)     R^2 = {np.corrcoef(lk,ac)[0,1]**2:.4f}")
print(f"  -> {b:+.2f} points per DOUBLING of the class count.")
for K in [6, 25, 140, 220]:
    print(f"     K={K:4d}  fit says {a0 + b*np.log2(K):6.2f}%   (chance {100/K:5.2f}%)"
          + ("   MEASURED" if K in (6,25) else "   EXTRAPOLATED -- outside the data"))
