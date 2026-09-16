"""delta_over_ear.py — the adversarial reviewer's OWN falsifier, run verbatim.

Same day, same deployed ears.py, same fixed 132-item heldout:
  A) ear-only nearest-centroid (22 labelled centroids from train)   <- the control
  B) ear-only 1-NN over all 396 labelled train vectors              <- the control
  C) the prototype memory grown UNSUPERVISED over the FULL diet, 3 seeds
     (same brain.py, same chemistry-at-baseline rule the tournament uses)
  D) reported organism number (read from results/ERANB-001.json)

C is the number that separates "the Hebbian layer destroys information"
from "the curriculum has only exposed 3 of 22 units".
"""
import json
import os
import random
import sys

import numpy as np

ROOT = os.path.expanduser("~/eran-brain")
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "proof"))

import genome                                   # noqa: E402
from ears import Ears                           # noqa: E402
from brain import Brain                         # noqa: E402
from chemistry import Chemistry                 # noqa: E402
import measure                                  # noqa: E402

ears = Ears(exam=True)
print(f"[cfg] repr={ears.repr} n_bands={ears.n_bands} pooling={ears.pooling} dim={ears.dim}")

train = measure.wavs_in(genome.FOOD_TRAIN)
held = measure.wavs_in(genome.HELDOUT_VAULT)
print(f"[cfg] train={len(train)} heldout={len(held)}")

TX = np.stack([ears.utterance(p) for p in train])
TY = [measure.label_of(p) for p in train]
HX = np.stack([ears.utterance(p) for p in held])
HY = [measure.label_of(p) for p in held]
classes = sorted(set(TY))
print(f"[cfg] classes={len(classes)}")

# ---------------------------------------------------- A) nearest-centroid
cent, cnames = [], []
for c in classes:
    v = TX[[i for i, y in enumerate(TY) if y == c]].mean(axis=0)
    n = np.linalg.norm(v)
    cent.append(v / n if n > 0 else v)
    cnames.append(c)
cent = np.stack(cent)
pred = [cnames[int(np.argmax(cent @ x))] for x in HX]
nc = sum(1 for t, y in zip(HY, pred) if t == y) / len(HY)
print(f"[A] ear-only nearest-centroid  = {nc:.4%}")

# ------------------------------------------------------------- B) 1-NN
pred = [TY[int(np.argmax(TX @ x))] for x in HX]
nn1 = sum(1 for t, y in zip(HY, pred) if t == y) / len(HY)
print(f"[B] ear-only 1-NN              = {nn1:.4%}")

# ------------------- C) prototype memory, unsupervised, full diet, 3 seeds
seeds = []
for seed in (1, 2, 3):
    rng = random.Random(seed)
    order = list(range(len(train)))
    rng.shuffle(order)
    chem = Chemistry()
    chem.frozen = True
    b = Brain(ears.dim)
    for beat, i in enumerate(order):
        b.hear(TX[i], chem, beat=beat)
    # majority-vote prototype -> class, exactly as the examiner does
    votes = {}
    for i in range(len(train)):
        idx, _, _ = b.nearest(TX[i])
        if idx is None:
            continue
        votes.setdefault(idx, {})
        votes[idx][TY[i]] = votes[idx].get(TY[i], 0) + 1
    plab = {i: max(v.items(), key=lambda kv: kv[1])[0] for i, v in votes.items()}
    ok = 0
    for x, t in zip(HX, HY):
        idx, _, _ = b.nearest(x)
        if idx is not None and plab.get(idx) == t:
            ok += 1
    acc = ok / len(HY)
    seeds.append((acc, len(b.protos)))
    print(f"[C] brain, full diet, seed {seed} = {acc:.4%}  ({len(b.protos)} protos)")

cacc = [a for a, _ in seeds]
print(f"[C] mean = {np.mean(cacc):.4%}  min = {min(cacc):.4%}  max = {max(cacc):.4%}")

# --------------------------------------------------------- D) the organism
live = None
rp = os.path.join(ROOT, "results", "ERANB-001.json")
if os.path.exists(rp):
    with open(rp) as f:
        r = json.load(f)
    live = r["heldout_top1"]
    print(f"[D] live organism (curriculum unit 3/22) = {live:.4%} "
          f"({r['prototypes']} protos, beat {r['beats']})")

print()
print("======================= DELTA OVER EAR =======================")
print(f"chance                         = { 1/22:.4%}")
print(f"printed baseline raw+loudest60 = {genome.BASELINES['raw_features_loudest60']:.4%}  <- CLAIMED")
print(f"same-day ear control (centroid)= {nc:.4%}")
print(f"same-day ear control (1-NN)    = {nn1:.4%}")
print(f"brain over full diet (3 seeds) = {np.mean(cacc):.4%}")
print(f"  delta_over_ear vs centroid   = {np.mean(cacc)-nc:+.4%}")
print(f"  delta_over_ear vs 1-NN       = {np.mean(cacc)-nn1:+.4%}")
if live is not None:
    print(f"live organism (3/22 units)     = {live:.4%}")
    print(f"  delta_over_ear vs centroid   = {live-nc:+.4%}")
