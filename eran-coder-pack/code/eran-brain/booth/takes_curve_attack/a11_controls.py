"""A11 -- controls on MY honest design, plus the corrected bill."""
import json, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(89)
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
EARLY, LATE = np.arange(0,33), np.arange(67,100)

print("=== shuffled-label control on the honest early->late design (chance 16.67%) ===")
for N in [1,3,10,33]:
    a=[]
    for _ in range(200):
        tr=np.concatenate([idx[u][rng.choice(EARLY,N,replace=False)] for u in DEEP])
        te=np.concatenate([idx[u][LATE] for u in DEEP])
        lab = rng.permutation(unit[tr])
        a.append(nn1(X[tr], lab, X[te], unit[te])[1])
    print(f"  N={N:3d}  shuffled labels {100*np.mean(a):6.2f}% +-{100*np.std(a):4.2f}")

print("\n=== duration control: can clip LENGTH alone do it? (1-NN on duration) ===")
Dv = dur.reshape(-1,1)
for N in [10,33]:
    a=[]
    for _ in range(200):
        tr=np.concatenate([idx[u][rng.choice(EARLY,N,replace=False)] for u in DEEP])
        te=np.concatenate([idx[u][LATE] for u in DEEP])
        a.append(nn1(Dv[tr], unit[tr], Dv[te], unit[te])[1])
    print(f"  N={N:3d}  duration-only {100*np.mean(a):6.2f}%   (chance 16.67%)")

print("\n=== THE CORRECTED CURVE (honest, early->late, 6 units, chance 16.67%) ===")
NG=[1,2,3,4,5,6,8,10,12,15,20,25,33]
rows=[]; prev=None
print("    N   accuracy        marginal pts/take   % of the N=33 asymptote")
for N in NG:
    a=[]
    for _ in range(400):
        tr=np.concatenate([idx[u][rng.choice(EARLY,N,replace=False)] for u in DEEP])
        te=np.concatenate([idx[u][LATE] for u in DEEP])
        a.append(nn1(X[tr],unit[tr],X[te],unit[te])[1])
    m,s=100*np.mean(a),100*np.std(a)
    rows.append(dict(N=N,acc=m,sd=s))
    mg = "" if prev is None else f"{(m-prev[1])/(N-prev[0]):+6.2f}"
    prev=(N,m)
    print(f"  {N:3d}   {m:6.2f} +-{s:4.2f}   {mg:>8s}")
asym=rows[-1]["acc"]
for r in rows: r["frac"]=r["acc"]/asym
print()
for r in rows: print(f"   N={r['N']:3d}  {100*r['frac']:5.1f}% of asymptote")
json.dump(rows, open("a11.json","w"), indent=1)
