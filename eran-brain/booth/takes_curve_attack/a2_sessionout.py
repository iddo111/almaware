"""A2 -- LEAVE-ONE-SITTING-OUT, the only true cross-session test in this data.

Three units were recorded in more than one sitting on 2026-08-23:
  ah  sit0 09:12 (3)   sit1 13:00 (73)  sit2 13:24 (24)
  ih  sit3 13:34 (24)  sit4 14:40 (76)
  ma  sit4 14:43 (34)  sit5 15:24 (24)  sit6 20:07 (42)
A 3-way problem {ah, ih, ma}, chance 33.33%.

  WITHIN : train N and test 12, both from the SAME sitting of each unit.
  ACROSS : train N from one sitting, test 12 from a DIFFERENT sitting.
Everything else identical. The gap is the session penalty, measured.
"""
import json, itertools, numpy as np
from probe import load, nn1
X, unit, take, mt, sit, dur = load()
U = ["ah", "ih", "ma"]
rng = np.random.default_rng(3)
# sittings with enough clips to both train and test
S = {}
for u in U:
    S[u] = {}
    for s in sorted(set(sit[unit == u])):
        r = np.where((unit == u) & (sit == s))[0]
        if len(r) >= 24: S[u][int(s)] = r
    print(f"  {u}: usable sittings {[(k, len(v)) for k, v in S[u].items()]}")
TE_N, DRAWS = 12, 120
print("\n   N  |  WITHIN sitting  |  ACROSS sittings |  session penalty")
rows = []
for N in [1, 2, 3, 5, 8, 10, 12]:
    w, a = [], []
    for _ in range(DRAWS):
        # WITHIN
        tr, te = [], []
        ok = True
        for u in U:
            s = rng.choice(list(S[u]))
            p = rng.permutation(S[u][s])
            if len(p) < N + TE_N: ok = False; break
            tr.append(p[:N]); te.append(p[N:N+TE_N])
        if ok:
            w.append(nn1(X[np.concatenate(tr)], unit[np.concatenate(tr)],
                         X[np.concatenate(te)], unit[np.concatenate(te)])[1])
        # ACROSS
        tr, te = [], []
        for u in U:
            s1, s2 = rng.choice(list(S[u]), 2, replace=False)
            tr.append(rng.permutation(S[u][s1])[:N])
            te.append(rng.permutation(S[u][s2])[:TE_N])
        a.append(nn1(X[np.concatenate(tr)], unit[np.concatenate(tr)],
                     X[np.concatenate(te)], unit[np.concatenate(te)])[1])
    rows.append(dict(N=N, within=100*np.mean(w), across=100*np.mean(a),
                     penalty=100*(np.mean(w)-np.mean(a))))
    print(f"  {N:3d}  |  {100*np.mean(w):6.2f} +-{100*np.std(w):5.2f}  |  "
          f"{100*np.mean(a):6.2f} +-{100*np.std(a):5.2f}  |  {100*(np.mean(w)-np.mean(a)):+6.2f} pts")
json.dump(rows, open("a2.json","w"), indent=1)

print("\n=== does ACROSS keep improving with N? (all sitting pairs, exhaustive) ===")
pairs = [dict(zip(U, c)) for c in itertools.product(*[list(S[u]) for u in U])]
print(f"  {len(pairs)} train-sitting combinations x same for test")
for N in [1, 2, 3, 5, 8, 10, 15, 20]:
    a = []
    for _ in range(300):
        tr, te = [], []
        for u in U:
            s1, s2 = rng.choice(list(S[u]), 2, replace=False)
            if len(S[u][s1]) < N: continue
            tr.append(rng.permutation(S[u][s1])[:N]); te.append(rng.permutation(S[u][s2])[:TE_N])
        if len(tr) < 3: continue
        a.append(nn1(X[np.concatenate(tr)], unit[np.concatenate(tr)],
                     X[np.concatenate(te)], unit[np.concatenate(te)])[1])
    print(f"   N={N:3d}  ACROSS {100*np.mean(a):6.2f} +-{100*np.std(a)/np.sqrt(len(a)):4.2f} (SE, n={len(a)})")
