# -*- coding: utf-8 -*-
"""Head-to-head on the REAL OUTPUT: measure each run's best.wav directly.
Not "the service is active" -- the actual wav each chooser produced.
Reads wav bytes. Plays nothing."""
import glob, json, os, sys, wave
import numpy as np
sys.path.insert(0, os.path.expanduser("~/throat-ruler"))
sys.path.insert(0, os.path.expanduser("~/throat-search-v4"))
sys.path.insert(0, os.path.expanduser("~/ear-v3"))
from f1traj import f1_traj_hz
import targets_v3 as T
from ear3 import features as EF

RUN = os.path.expanduser("~/throat-search-v4/run")
BAND = json.load(open(os.path.expanduser("~/throat-ruler/human-band.json")))
stats = T.load_all()


def load(p):
    with wave.open(p) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0


print("%-24s %8s %9s %9s %8s %9s %7s" %
      ("run", "evals", "f1_traj", "f1_reach", "wdist", "fence_bar", "gate"))
for d in sorted(sys.argv[1:]):
    p = os.path.join(RUN, d, "best.wav")
    j = os.path.join(RUN, d, "best.json")
    if not os.path.exists(p):
        print("%-24s  (no best.wav yet)" % d); continue
    y = load(p)
    b = json.load(open(j)) if os.path.exists(j) else {}
    unit = b.get("unit", "ba")
    cap = float(BAND[unit]["p90"])
    t = f1_traj_hz(y)
    reach = 0.0 if t != t else 1.0 - (1.0 - min(t, cap) / cap)
    wd = float(T.wdist(EF.features(y), stats[unit]))
    bar = 1.3 * float(stats[unit]["real_wdist_mean"])
    print("%-24s %8s %9.1f %9.4f %8.3f %9.3f %7s" %
          (d, b.get("evals", "?"), (t if t == t else float("nan")), reach,
           wd, bar, b.get("gate_pass")))
