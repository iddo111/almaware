"""A4 -- (a) replicate the project's 36.4% self-consistency number,
        (b) how accuracy falls as the NUMBER OF CLASSES grows.

(a) sitting 0 (09:12:00-09:15:17) is 20 units x 3 takes, ONE unbroken run --
    the same shape as the old '22 units x 3 takes, leave-one-take-out, 36.4%,
    chance 4.5%' measurement. Run it and see.
(b) all 25 units restricted to 3 takes each (deep units use their first 3).
    Random subsets of K units, K = 2..25, leave-one-take-out. The chance line
    moves with K, so report BOTH raw accuracy and accuracy/chance.
"""
import json, numpy as np
from probe import load, nn1
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(5)

# ---------------- (a) replication on sitting 0 ----------------------------
s0 = np.where(sit == 0)[0]
u0 = sorted(set(unit[s0]))
print(f"(a) sitting 0: {len(s0)} clips, {len(u0)} units x 3 takes, one 3.3-min run")
def loto(rows):
    """leave-one-take-out over the given rows"""
    ok = []
    for i in rows:
        tr = np.array([j for j in rows if j != i])
        p, _ = nn1(X[tr], unit[tr], X[[i]], unit[[i]])
        ok.append(p[0] == unit[i])
    return float(np.mean(ok)), ok
acc0, per0 = loto(list(s0))
print(f"    leave-one-take-out 1-NN : {100*acc0:.2f}%   chance {100/len(u0):.2f}%  "
      f"ratio {acc0*len(u0):.2f}x")
print(f"    project's prior claim   : 36.4% on 22 units x 3 takes, chance 4.5%  ratio 8.09x")

# shuffled-label control
sh = []
for _ in range(200):
    perm = rng.permutation(len(s0)); lab = unit[s0][perm]
    ok = []
    for k, i in enumerate(s0):
        m = np.arange(len(s0)) != k
        p, _ = nn1(X[s0[m]], lab[m], X[[i]], np.array([lab[k]]))
        ok.append(p[0] == lab[k])
    sh.append(np.mean(ok))
print(f"    shuffled-label control  : {100*np.mean(sh):.2f}% +-{100*np.std(sh):.2f}")

# ---------------- (b) class-count scaling ---------------------------------
print("\n(b) accuracy vs NUMBER OF CLASSES, 3 takes each, leave-one-take-out")
first3 = {}
for u in sorted(set(unit)):
    r = np.where(unit == u)[0]
    first3[u] = r[np.argsort(take[r])][:3]
ALL = sorted(first3)
print("    K   raw acc   chance    acc/chance   error rate")
rows = []
for K in [2, 3, 4, 6, 8, 10, 12, 15, 20, 25]:
    accs = []
    reps = 200 if K < 25 else 1
    for _ in range(reps):
        us = list(rng.choice(ALL, K, replace=False)) if K < 25 else ALL
        rows_i = np.concatenate([first3[u] for u in us])
        a, _ = loto(list(rows_i)); accs.append(a)
    m = 100*np.mean(accs); ch = 100.0/K
    rows.append(dict(K=K, acc=m, chance=ch, ratio=m/ch))
    print(f"   {K:3d}  {m:6.2f}%  {ch:6.2f}%   {m/ch:7.2f}x     {100-m:6.2f}%")
json.dump(dict(sit0_acc=100*acc0, sit0_units=len(u0), sit0_shuffle=100*float(np.mean(sh)),
               kscale=rows), open("a4.json","w"), indent=1)
