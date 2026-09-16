"""A8 -- WHICH units collide, and do the hard ones want more takes?"""
import json, collections, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(41)
first3 = {}
for u in sorted(set(unit)):
    r = np.where(unit == u)[0]; first3[u] = r[np.argsort(take[r])][:3]
ALL = sorted(first3)

print("=== A. 25-class confusion, 3 takes each, leave-one-take-out (75 decisions) ===")
rows = list(np.concatenate([first3[u] for u in ALL]))
conf = collections.Counter(); wrong = collections.Counter(); tot = collections.Counter()
for i in rows:
    tr = np.array([j for j in rows if j != i])
    p = nn1(X[tr], unit[tr], X[[i]], unit[[i]])[0][0]
    tot[unit[i]] += 1
    if p != unit[i]:
        conf[(unit[i], p)] += 1; wrong[unit[i]] += 1
print("  per-unit recall (3 decisions each):")
line = []
for u in ALL: line.append(f"{u}:{100*(tot[u]-wrong[u])/tot[u]:.0f}%")
print("   " + "  ".join(line))
print("\n  confusions that happened more than once (true -> predicted):")
for (a, b), c in conf.most_common():
    if c > 1: print(f"    {a:5s} -> {b:5s}   {c} of {tot[a]}")
print("  all single confusions:", ", ".join(f"{a}->{b}" for (a,b),c in conf.items() if c==1))

print("\n=== B. nearest-neighbour syllable of every unit's prototype (25 units) ===")
P = {}
for u in ALL:
    p = X[first3[u]].mean(0); P[u] = p/np.linalg.norm(p)
M = np.array([P[u] for u in ALL])
S = M @ M.T; np.fill_diagonal(S, -9)
print("   unit   closest other unit   cos      2nd closest")
pairs = []
for i, u in enumerate(ALL):
    o = np.argsort(-S[i])
    pairs.append((u, ALL[o[0]], S[i, o[0]], ALL[o[1]], S[i, o[1]]))
for u, a, ca, b, cb in sorted(pairs, key=lambda x: -x[2]):
    print(f"   {u:5s}  {a:5s}  {ca:.4f}   {b:5s} {cb:.4f}")

print("\n=== C. do the HARD deep units gain more from extra takes? (honest early->late) ===")
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
EARLY, LATE = np.arange(0,33), np.arange(67,100)
NG = [1,2,3,5,8,10,15,20,33]
rec = {u: [] for u in DEEP}
for N in NG:
    acc = {u: [] for u in DEEP}
    for _ in range(150):
        tr = np.concatenate([idx[u][rng.choice(EARLY,N,replace=False)] for u in DEEP])
        te = np.concatenate([idx[u][LATE] for u in DEEP])
        p, _ = nn1(X[tr], unit[tr], X[te], unit[te])
        for u in DEEP: acc[u].append(np.mean(p[unit[te]==u]==u))
    for u in DEEP: rec[u].append(100*float(np.mean(acc[u])))
print("  unit  " + "".join(f"N={n:<5d}" for n in NG) + "  gain N=3->10  gain N=10->33")
for u in DEEP:
    c = rec[u]
    print(f"  {u:5s} " + "".join(f"{v:<7.1f}" for v in c) +
          f"  {c[NG.index(10)]-c[NG.index(3)]:+7.1f}      {c[-1]-c[NG.index(10)]:+7.1f}")
json.dump(dict(per_unit_curve={u: rec[u] for u in DEEP}, NG=NG,
               conf={f"{a}->{b}": c for (a,b),c in conf.items()}), open("a8.json","w"), indent=1)
