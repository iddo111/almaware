# -*- coding: utf-8 -*-
"""control.py -- is the 98% real, or is the cortex hearing a click and a length?

A crude concatenation of אַה + בַּ differs from a real אַבָּא in three ways at once:
    (1) coarticulation      <- the thing we WANT it to be using
    (2) total duration       <- a confound: splice is ~1.4x longer
    (3) a discontinuity      <- a confound: a step in the waveform is an audible click,
                                and a click is a broadband smear across every mel band

Claiming (1) while (2) and (3) are free is exactly how a measurement lies. So: rebuild the
fake three ways, each one removing one confound, and see what survives.

    FAKE-A  crude concat                      all three cues available   (the 98% run)
    FAKE-B  length-matched to the real word    duration cue removed
    FAKE-C  length-matched + 20 ms crossfade   duration AND click removed  <- THE REAL TEST
"""
import glob, os, random, sys, wave
import numpy as np
import torch
sys.path.insert(0, os.path.expanduser("~/eran-cortex"))
from auditory import read_wav, logmel, train_eval, DATA

def concat(a, b):
    return np.concatenate([a, b])

def concat_len(a, b, target):
    x = np.concatenate([a, b])
    if x.size <= target:
        return x
    # squeeze by dropping from the middle of each half, not by resampling
    # (resampling would shift formants and hand the cortex a NEW cue)
    cut = x.size - target
    ha = a.size - cut // 2
    hb = b.size - (cut - cut // 2)
    return np.concatenate([a[:max(1, ha)], b[:max(1, hb)]])

def concat_xfade(a, b, target, sr=16000, ms=20):
    n = int(sr * ms / 1000)
    n = min(n, a.size // 2, b.size // 2)
    if n < 4:
        return concat_len(a, b, target)
    w = np.linspace(0, 1, n, dtype=np.float32)
    join = a[-n:] * (1 - w) + b[:n] * w
    x = np.concatenate([a[:-n], join, b[n:]])
    return concat_len(x[:x.size // 2], x[x.size // 2:], target)

def run(kind, make, folds=3):
    raw_ah = [read_wav(p) for p in sorted(glob.glob(os.path.join(DATA, "ah_t06_*.wav")))]
    raw_ba = [read_wav(p) for p in sorted(glob.glob(os.path.join(DATA, "ba_t06_*.wav")))]
    real = [read_wav(p) for p in sorted(glob.glob(os.path.join(DATA, "abba_t06_*.wav")))]
    accs, lens_r, lens_f = [], [], []
    for fold in range(folds):
        rng = random.Random(200 + fold)
        fake = [make(rng.choice(raw_ah), rng.choice(raw_ba), real[i].size) for i in range(len(real))]
        lens_r = [r.size / 16000 for r in real]; lens_f = [f.size / 16000 for f in fake]
        idx = list(range(len(real))); rng.shuffle(idx)
        cut = int(len(idx) * 0.25)
        Xtr, ytr, Xte, yte = [], [], [], []
        for j in idx[:cut]:
            Xte += [logmel(real[j]), logmel(fake[j])]; yte += [1, 0]
        for j in idx[cut:]:
            Xtr += [logmel(real[j]), logmel(fake[j])]; ytr += [1, 0]
        a, _ = train_eval(np.array(Xtr), np.array(ytr), np.array(Xte), np.array(yte), 2, seed=fold)
        accs.append(a)
    print(f"  {kind:52s} {np.mean(accs)*100:5.1f}%  (sd {np.std(accs)*100:.1f})   "
          f"real {np.mean(lens_r):.2f}s vs fake {np.mean(lens_f):.2f}s")
    return float(np.mean(accs))

print("REAL אַבָּא vs a fake, chance 50.0%\n")
a = run("FAKE-A  crude concat (all cues free)", lambda x, y, t: concat(x, y))
b = run("FAKE-B  length-matched (duration removed)", concat_len)
c = run("FAKE-C  length-matched + crossfade (click removed)", concat_xfade)

print("\n" + "=" * 74)
print(f"  crude {a*100:.1f}%  ->  length-matched {b*100:.1f}%  ->  +crossfade {c*100:.1f}%")
if c * 100 > 75:
    print("  VERDICT: SURVIVES. With duration and the click both removed, the cortex still")
    print("           separates a real word from its parts. That residue IS coarticulation.")
elif c * 100 > 60:
    print("  VERDICT: PARTLY SURVIVES. Most of the 98% was duration and the click; a real")
    print("           but smaller signal remains.")
else:
    print("  VERDICT: DOES NOT SURVIVE. The 98% was the click and the length. The cortex")
    print("           has NOT heard what makes אבא a word. Do not build on it.")
print("=" * 74)
