# -*- coding: utf-8 -*-
"""THE DECISIVE TEST, on the real output.

Score the 136 clips Iddo actually judged with the FULL v4 chooser and the FULL
v5 chooser -- the same code paths the search minimises, gate and identity term
included, not just the headline feature -- and ask which one agrees with him.

Reads wav bytes. Plays nothing. Touches no running process."""
import collections, json, os, sys, wave
import numpy as np
sys.path.insert(0, os.path.expanduser("~/throat-ruler"))
sys.path.insert(0, os.path.expanduser("~/throat-search-v4"))
sys.path.insert(0, os.path.expanduser("~/ear-v3"))
from f1traj import f1_traj_hz
import targets_v3 as T
import gates_v3
from ear3 import features as EF

HERE = os.path.expanduser("~/throat-ruler")
MAN = json.load(open(os.path.join(HERE, "judged-manifest.json")))
BAND = json.load(open(os.path.join(HERE, "human-band.json")))
STATS = T.load_all()
IDENTITY_LAMBDA, MARGIN_TARGET, W_F1, W_FENCE = 3.0, 0.2029, 1.0, 3.0


def load(p):
    with wave.open(p) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0


def identity(v, wd, unit):
    if unit != "ba":
        return 0.0
    others = [u for u in STATS if u != unit and u in T.UNITS]
    rival = min(T.wdist(v, STATS[u]) for u in others)
    return IDENTITY_LAMBDA * max(0.0, MARGIN_TARGET - (rival - wd))


out = []
for m in MAN:
    u = m["unit"]
    if u not in STATS or u not in BAND or not BAND[u].get("usable"):
        continue                                  # ga/na/pa/ta: no target exists
    y = load(os.path.join(HERE, m["arc"]))
    v, aux = EF.features_with_aux(y)
    wd = float(T.wdist(v, STATS[u]))
    gate = float(gates_v3.penalty(u, gates_v3.gate_stats(aux, y)))
    idp = float(identity(v, wd, u))
    cap = float(BAND[u]["p90"])
    t = f1_traj_hz(y)
    f1c = 1.0 if t != t else 1.0 - min(float(t), cap) / cap
    bar = 1.3 * float(STATS[u]["real_wdist_mean"])
    wf = max(0.0, wd - bar) / bar
    out.append(dict(m, wdist=wd, gate=gate, identity=idp, f1_cost=f1c,
                    w_fence=wf, f1_traj=(None if t != t else float(t)),
                    v4_cost=wd + gate + idp,
                    v5_cost=W_F1 * f1c + W_FENCE * wf + gate + idp))
json.dump(out, open(os.path.join(HERE, "decide.json"), "w"), indent=1)
print("scored", len(out), "clips through the REAL scorer code paths")


def strat_auc(rows, key, sign=-1.0):
    S = collections.defaultdict(list)
    for d in rows:
        S[(d["source"], d["unit"])].append((sign * float(d[key]), float(d["y"])))
    conc = ties = tot = 0
    for arr in S.values():
        for i in range(len(arr)):
            for j in range(i + 1, len(arr)):
                (a, ya), (b, yb) = arr[i], arr[j]
                if ya == yb:
                    continue
                tot += 1
                hi, lo = (a, b) if ya > yb else (b, a)
                if hi > lo:
                    conc += 1
                elif hi == lo:
                    ties += 1
    return (conc + 0.5 * ties) / tot if tot else float("nan"), tot


print()
for k, lab in [("v4_cost", "v4 chooser  wd + gate + identity      (MINIMISED)"),
               ("v5_cost", "v5 chooser  f1 + 3*fence + gate + id  (MINIMISED)")]:
    a, n = strat_auc(out, k)
    print("  %-46s AUC %.4f  n_pairs %d" % (lab, a, n))

rng = np.random.default_rng(20260901)
ys = np.array([d["y"] for d in out])
null = []
for _ in range(2000):
    p = rng.permutation(len(out))
    sh = [dict(d, y=float(ys[p[i]])) for i, d in enumerate(out)]
    null.append(strat_auc(sh, "v5_cost")[0])
null = np.array(null)
obs = strat_auc(out, "v5_cost")[0]
print("  %-46s     %.4f +- %.4f  95%% [%.3f, %.3f]"
      % ("FLOOR (2000 shuffles of his labels)", null.mean(), null.std(),
         np.percentile(null, 2.5), np.percentile(null, 97.5)))
print("  permutation p (v5 chooser)                          %.5f"
      % max(float((null >= obs).mean()), 1 / 2000))

print()
print("  per (source,unit) cell:")
S = collections.defaultdict(list)
for d in out:
    S[(d["source"], d["unit"])].append(d)
for k in sorted(S):
    if len(S[k]) < 4:
        continue
    a4, n4 = strat_auc(S[k], "v4_cost")
    a5, _ = strat_auc(S[k], "v5_cost")
    print("    %-22s %-4s n=%2d  v4 %.3f   v5 %.3f   (pairs %d)"
          % (k[0], k[1], len(S[k]), a4, a5, n4))
