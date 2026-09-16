"""ATTACK 1 -- is the curve measuring phonetics or 'nearly identical repeats'?

Same units, same clips, same probe, same train size, same test size.
Only the TIME RELATIONSHIP between train and test changes.

  T  EARLY->LATE : train = N takes drawn from the FIRST third of the unit's
                   100, test = ALL 33 takes of the LAST third.
  R  RANDOM MIX  : the same 66 clips per unit; 33 held out AT RANDOM, train =
                   N drawn from the other 33. Train and test interleave in time.

If R >> T, the curve is scoring temporal proximity, not the syllable.
"""
import json, numpy as np
from probe import load, nn1, DEEP

X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(20260824)
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
for u in DEEP: assert len(idx[u]) == 100

EARLY = np.arange(0, 33)      # takes 0-32
LATE  = np.arange(67, 100)    # takes 67-99
POOL  = np.concatenate([EARLY, LATE])
NG = [1, 2, 3, 5, 8, 10, 15, 20, 30, 33]
DRAWS = 200
out = {"design": "A1 early->late vs random mix, 6 deep units, chance 16.67%",
       "early_takes": [0, 32], "late_takes": [67, 99], "draws": DRAWS, "rows": []}

for N in NG:
    accT, accR = [], []
    for d_ in range(DRAWS):
        # --- T: train early, test late
        tr = np.concatenate([idx[u][rng.choice(EARLY, N, replace=False)] for u in DEEP])
        te = np.concatenate([idx[u][LATE] for u in DEEP])
        _, a = nn1(X[tr], unit[tr], X[te], unit[te]); accT.append(a)
        # --- R: same pool, random 33 held out, train N from the other 33
        trR, teR = [], []
        for u in DEEP:
            perm = rng.permutation(POOL)
            teR.append(idx[u][perm[:33]])
            trR.append(idx[u][perm[33:][:N]])
        trR, teR = np.concatenate(trR), np.concatenate(teR)
        _, a = nn1(X[trR], unit[trR], X[teR], unit[teR]); accR.append(a)
    r = dict(N=N, T_early_late=100*float(np.mean(accT)), T_sd=100*float(np.std(accT)),
             R_random_mix=100*float(np.mean(accR)), R_sd=100*float(np.std(accR)),
             gap=100*float(np.mean(accR) - np.mean(accT)))
    out["rows"].append(r)
    print(f"N={N:3d}  T early->late {r['T_early_late']:6.2f} +-{r['T_sd']:5.2f}   "
          f"R random mix {r['R_random_mix']:6.2f} +-{r['R_sd']:5.2f}   "
          f"LEAK = {r['gap']:+6.2f} pts")
json.dump(out, open("a1.json", "w"), indent=1)
