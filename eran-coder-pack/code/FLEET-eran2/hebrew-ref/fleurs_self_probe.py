#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fleurs_self_probe.py -- the fork in the road after the transfer probe failed.

WHAT JUST HAPPENED. fleurs_transfer_probe.py trained on 2,700 FLEURS-cut syllables
and tested on Iddo's 254 booth clips: **top1 3.1 %, chance 5.6 %, shuffled 3.9 %**.
At chance. Worse than the TTS corpus's own 6.1 % (whose chance was 4.5 %).

TWO EXPLANATIONS, AND THEY LEAD OPPOSITE WAYS.
  (a) THE CUTTING IS WRONG. The spans are not syllables, and the food is junk.
      -> stop, throw it away.
  (b) THE CUTTING IS FINE AND THE PROBE CANNOT CROSS DOMAINS. `voiced_profile` is
      28 dims of log-band energy and ZCR -- a TIMBRE descriptor. Across 1,502
      speakers and unknown channels it is dominated by recording condition, not
      phonetics. Note the prior numbers point this way: within-synthetic 59.8 %,
      his-own-voice-to-itself 36.4 %, but EVERY cross-domain number this probe has
      ever produced sits at chance, including the 6.1 % that condemned the TTS
      corpus ("6.1 % sits inside the shuffled-label control's own noise band").
      -> the probe cannot tell good food from bad, and a different test is needed.

THIS SCRIPT DECIDES BETWEEN THEM, and it is a fair test because it holds the
domain fixed and varies only the SPEAKER:

    LEAVE-SPEAKER-OUT within the FLEURS cuts.
    Train on clips from one set of FLEURS speakers, test on clips from speakers
    never seen in training. Same corpus, same channel distribution, same cutter.

  If this is at chance too, the cuts carry no phonetic identity at all -> (a), junk.
  If this is well above chance, the cuts DO carry syllable identity across mouths,
  and the transfer failure is the probe's domain gap -> (b).

A speaker appears on ONE side only, never both -- otherwise the probe would be
scoring "same voice" rather than "same syllable", the exact leak the session-leak
scar was about.

Reads only. Plays nothing.
"""
from __future__ import annotations
import os, sys, glob, wave, re, json
import numpy as np

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

FLEURS_DIR = os.path.expanduser("~/eran-food-human")
CLASSES = ["B","D","G","H","K","L","M","N","P","R","S","SH","T","TS","V","X","Y","Z"]


def read_wav(path):
    with wave.open(path, "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0


def frame_features(audio, frame=400, hop=160, bands=12):
    feats = []
    for start in range(0, max(0, audio.size - frame + 1), hop):
        seg = audio[start:start + frame]
        win = seg * np.hanning(seg.size)
        energy = np.log(np.sum(seg ** 2) + 1e-10)
        zcr = float(np.mean(np.abs(np.diff(np.sign(seg))) > 0))
        sp = np.abs(np.fft.rfft(win)) ** 2
        edges = np.linspace(0, sp.size, bands + 1).astype(int)
        band = [np.log(sp[edges[b]:edges[b + 1]].sum() + 1e-10) for b in range(bands)]
        feats.append([energy, zcr] + band)
    return np.array(feats) if feats else np.zeros((1, 2 + bands))


def voiced_profile(x):
    f = frame_features(x)
    if f.shape[0] == 0: return np.zeros(28)
    keep = max(1, int(round(0.6 * f.shape[0])))
    v = f[np.argsort(f[:, 0])[-keep:]]
    return np.concatenate([v.mean(axis=0), v.std(axis=0)])


def nn_top1(Xtr, ytr, Xte, yte):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    d = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    return float(np.mean(ytr[np.argmin(d, axis=1)] == yte))


def main():
    per_class = int(os.environ.get("PER_CLASS", "200"))
    X, y, spk = [], [], []
    for cls in CLASSES:
        d = os.path.join(FLEURS_DIR, cls)
        if not os.path.isdir(d): continue
        for p in sorted(glob.glob(os.path.join(d, "*.wav")))[:per_class]:
            m = re.search(r"__fleurs-([^_]+)__", os.path.basename(p))
            if not m: continue
            X.append(voiced_profile(read_wav(p))); y.append(cls); spk.append(m.group(1))
    X, y, spk = np.array(X), np.array(y), np.array(spk)
    speakers = np.array(sorted(set(spk)))
    print(f"{len(X)} clips, {len(set(y))} classes, {len(speakers)} distinct speakers")
    chance = 1.0 / len(set(y))
    print(f"chance: {chance*100:.1f}%\n")

    rng = np.random.default_rng(0)
    accs = []
    for fold in range(5):
        held = set(rng.choice(speakers, size=max(1, len(speakers)//5), replace=False))
        te = np.array([s in held for s in spk])
        tr = ~te
        if te.sum() < 20 or len(set(y[tr])) < 2: continue
        a = nn_top1(X[tr], y[tr], X[te], y[te])
        accs.append(a)
        print(f"  fold {fold}: held-out {len(held)} speakers, {int(te.sum())} test clips"
              f"   top1 {a*100:5.1f}%")
    print(f"\n  LEAVE-SPEAKER-OUT within FLEURS cuts : top1 {np.mean(accs)*100:5.1f}% "
          f"(sd {np.std(accs)*100:.1f})")

    ysh = rng.permutation(y)
    sh = []
    for fold in range(3):
        held = set(rng.choice(speakers, size=max(1, len(speakers)//5), replace=False))
        te = np.array([s in held for s in spk]); tr = ~te
        if te.sum() < 20: continue
        sh.append(nn_top1(X[tr], ysh[tr], X[te], ysh[te]))
    print(f"  shuffled-label control               : top1 {np.mean(sh)*100:5.1f}%")
    print(f"  chance                               : top1 {chance*100:5.1f}%")

    print("\n  VERDICT:")
    if np.mean(accs) > chance * 2:
        print("    The cuts DO carry syllable identity across unseen mouths.")
        print("    -> the transfer failure is the 28-dim probe's domain gap, not the food.")
    elif np.mean(accs) > chance * 1.3:
        print("    Weak but above chance. The cuts carry SOME identity; not strong.")
    else:
        print("    At chance even within its own corpus. The cutting is wrong. Stop.")


if __name__ == "__main__":
    main()
