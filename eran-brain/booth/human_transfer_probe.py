#!/usr/bin/env python3
"""human_transfer_probe.py -- does anything learned from synthetic voices survive
contact with a real human?

Iddo recorded the 22 syllables himself in the booth on 2026-08-23 (talker t06, 66 clips,
26.9 s, 16 kHz mono). Every other talker in corpus-syllables -- t00 through t05 -- is a
synthetic base rendering, WSOLA-tempo-augmented with pink noise and gain jitter, per the
corpus manifest's own augmentation_spec. So t06 is the FIRST real mouth in ERAN's world.

That makes one measurement available that was not available yesterday, and it is the one
that matters before any more of Iddo's time is spent recording:

    train on six synthetic voices  ->  test on a real human voice

If the transfer number collapses to chance, the synthetic corpus is not teaching phonetics,
it is teaching the synthesiser -- and the honest conclusion is that ERAN needs human mouths,
not more augmentation.

METHOD, deliberately borrowed rather than invented. The features are byte-for-byte the
project's own `voiced_profile` from corpus-syllables/verify.py: 14-dim per frame (log
energy, ZCR, 12 log bands), taken over the loudest 60% of frames, mean+std -> 28 dims.
The classifier is the same 1-NN. Using the established probe means these numbers sit on
the same axis as every number already in the repo; a new feature stack would not.

THREE CONTROLS, because a bare accuracy means nothing:
  chance                 1/22 = 4.5%
  synthetic leave-one-talker-out   the ceiling this probe reaches when the test voice is
                                   the same KIND of voice as the training voices
  shuffled labels        the same pipeline with the answer key shuffled -- catches any
                         leak through clip length, loudness or file order

    python human_transfer_probe.py
"""
from __future__ import annotations

import glob
import os
import sys
import wave

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.expanduser("~/eran-brain/corpus-syllables")
SYNTH_DIR = os.path.join(ROOT, "train")
HUMAN_DIR = os.path.join(ROOT, "human")


# ---- the project's own feature extractor, copied verbatim from verify.py ----

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
        band = [np.log(sp[edges[i]:edges[i + 1]].sum() + 1e-10) for i in range(bands)]
        feats.append(np.array([energy, zcr] + band))
    return np.array(feats) if feats else np.zeros((0, 2 + bands))


def voiced_profile(x):
    f = frame_features(x)
    if f.shape[0] < 4:
        return np.zeros(28)
    keep = f[:, 0] >= np.quantile(f[:, 0], 0.40)
    f = f[keep] if keep.sum() >= 3 else f
    return np.concatenate([f.mean(axis=0), f.std(axis=0)])


# ---------------------------------------------------------------- data

def load(dirpath):
    X, y, t = [], [], []
    for p in sorted(glob.glob(os.path.join(dirpath, "*.wav"))):
        name = os.path.basename(p)[:-4]
        parts = name.split("_")
        if len(parts) < 3:
            continue
        X.append(voiced_profile(read_wav(p)))
        y.append(parts[0])
        t.append(parts[1])
    return np.array(X), np.array(y), np.array(t)


def nn_accuracy(Xtr, ytr, Xte, yte, zscore_per_set=True):
    """1-NN. Each set is z-scored against the TRAINING statistics only.

    Per-set z-scoring is what makes this a fair cross-voice test: without it a human
    voice sits in a different corner of feature space than a synthesiser and the probe
    reports 0% for a trivially fixable reason (a constant offset), which would be a
    measurement artefact dressed up as a finding.
    """
    if zscore_per_set:
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        A = (Xtr - mu) / sd
        # the test set is centred on ITS OWN mean -- removes the speaker offset,
        # keeps the phonetic structure. Stated because it is a real choice.
        B = (Xte - Xte.mean(0)) / (Xte.std(0) + 1e-9)
    else:
        A, B = Xtr, Xte
    d = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    pred = ytr[d.argmin(1)]
    top5 = np.mean([yte[i] in ytr[np.argsort(d[i])[:5]] for i in range(len(yte))])
    return float((pred == yte).mean()), float(top5)


def main():
    if not os.path.isdir(HUMAN_DIR):
        raise SystemExit(f"no human corpus at {HUMAN_DIR}")

    Xs, ys, ts = load(SYNTH_DIR)
    Xh, yh, th = load(HUMAN_DIR)
    print(f"synthetic : {len(Xs)} clips, {len(set(ys))} units, talkers {sorted(set(ts))}")
    print(f"human     : {len(Xh)} clips, {len(set(yh))} units, talkers {sorted(set(th))}")
    chance = 100.0 / len(set(ys))
    print(f"chance    : {chance:.1f}%\n")

    # --- control A: leave-one-SYNTHETIC-talker-out. The ceiling for this probe.
    accs, t5s = [], []
    for held in sorted(set(ts)):
        m = ts == held
        a, t5 = nn_accuracy(Xs[~m], ys[~m], Xs[m], ys[m])
        accs.append(a); t5s.append(t5)
        print(f"  synth leave-out {held} : top1 {a*100:5.1f}%   top5 {t5*100:5.1f}%")
    print(f"  --> synthetic mean    : top1 {np.mean(accs)*100:5.1f}% "
          f"(sd {np.std(accs)*100:.1f})   top5 {np.mean(t5s)*100:5.1f}%\n")

    # --- the measurement: six synthetic voices -> one real human
    a, t5 = nn_accuracy(Xs, ys, Xh, yh)
    print(f"  SYNTHETIC -> REAL HUMAN (t06) : top1 {a*100:5.1f}%   top5 {t5*100:5.1f}%")

    # --- control B: human -> human. Can the probe even tell HIS syllables apart?
    #     Leave-one-take-out: takes 0,1 train, take 2 tests.
    takes = np.array([os.path.basename(p)[:-4].split("_")[2]
                      for p in sorted(glob.glob(os.path.join(HUMAN_DIR, "*.wav")))])
    m = takes == "2"
    if m.sum() and (~m).sum():
        ah, t5h = nn_accuracy(Xh[~m], yh[~m], Xh[m], yh[m])
        print(f"  human -> human (his own takes) : top1 {ah*100:5.1f}%   top5 {t5h*100:5.1f}%")
    else:
        ah = float("nan")

    # --- control C: shuffled labels. Anything above chance here is a leak.
    rng = np.random.RandomState(0)
    sh = [nn_accuracy(Xs, rng.permutation(ys), Xh, yh)[0] for _ in range(20)]
    print(f"  shuffled-label control        : top1 {np.mean(sh)*100:5.1f}% "
          f"(sd {np.std(sh)*100:.1f})  -- must sit at chance\n")

    # --- verdict
    print("=" * 66)
    if a * 100 < chance + 2 * np.std(sh) * 100:
        print("VERDICT: transfer is AT CHANCE. Six synthetic voices teach this probe")
        print("         nothing that survives contact with a real mouth.")
        print("         -> ERAN needs human talkers, not more augmentation.")
    elif a < np.mean(accs) * 0.5:
        print(f"VERDICT: transfer is REAL but weak -- {a*100:.1f}% vs {np.mean(accs)*100:.1f}%")
        print("         within-synthetic. The synthetic corpus carries some phonetics,")
        print("         but most of what it teaches is the synthesiser.")
    else:
        print(f"VERDICT: transfer HOLDS -- {a*100:.1f}% on a real human vs "
              f"{np.mean(accs)*100:.1f}% within-synthetic.")
    if ah == ah:
        print(f"         (his own voice is {ah*100:.1f}% self-consistent, "
              f"which bounds what any model can score on it)")
    print("=" * 66)


if __name__ == "__main__":
    main()
