#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fleurs_transfer_probe.py -- does the FLEURS-cut food survive contact with Iddo's mouth?

THE NUMBER THIS EXISTS TO BEAT.
    On 2026-08-23 `corpus-syllables/human_transfer_probe.py` measured the synthetic
    corpus against Iddo's own voice and got **6.1 % top-1, against 4.5 % chance and a
    4.2 % shuffled-label control**. Six synthetic talkers and 396 clips taught this
    feature space nothing that survived a real mouth. That verdict is what condemned
    the corpus.

    This script asks the same question of the new food -- 7,388 CV syllables cut out
    of FLEURS he_il (9.47 h, 1,502 real human speakers, CC-BY-4.0) by cut_syllables.py.

METHOD IS DELIBERATELY BORROWED, NOT INVENTED. `voiced_profile` below is copied
    byte-for-byte from `corpus-syllables/verify.py` (14 dims per frame -> loudest 60 %
    of frames -> mean+std -> 28 dims) and the classifier is the same 1-NN. A new
    feature stack would produce a number that cannot be compared to 6.1 %, which
    would defeat the whole point.

CANONICAL CLASSES ON BOTH SIDES. Modern Hebrew merges ta/tha (both /t/) and ka/qa
    (both /k/). Nothing can separate those from audio, so both sides of the probe are
    mapped to canonical classes before scoring. Scoring them apart would manufacture
    errors that are facts of the language, not faults of the food.

CONTROLS, because a bare accuracy means nothing:
    chance                 1/n_classes
    shuffled-label         same pipeline, answer key shuffled -- catches leakage
                           through clip length, loudness or file order
    his own voice -> his own voice, where n allows -- the ceiling for this probe

Reads only. Plays nothing. Writes nothing on eran1.
"""
from __future__ import annotations
import os, sys, glob, wave, json
import numpy as np

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

FLEURS_DIR = os.path.expanduser("~/eran-food-human")
IDDO_DIR   = os.path.expanduser("~/iddo-t06")

# ERAN unit name -> canonical class (the merges are real Hebrew, see docstring)
UNIT2CLASS = {
    "ba":"B", "va":"V", "ga":"G", "da":"D", "ha":"H", "za":"Z", "kha":"X",
    "ta":"T", "tha":"T", "ya":"Y", "ka":"K", "qa":"K", "la":"L", "ma":"M",
    "na":"N", "sa":"S", "pa":"P", "tsa":"TS", "ra":"R", "sha":"SH",
}
# 'aa'/'ah' are bare vowels and 'ih'/'abba'/'ima' are not CV+/a/, so they have no
# counterpart in the cut food and are excluded rather than fudged.


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
        band = [np.log(sp[edges[b]:edges[b + 1]].sum() + 1e-10) for b in range(bands)]
        feats.append([energy, zcr] + band)
    return np.array(feats) if feats else np.zeros((1, 2 + bands))


def voiced_profile(x):
    f = frame_features(x)
    if f.shape[0] == 0:
        return np.zeros(28)
    keep = max(1, int(round(0.6 * f.shape[0])))
    idx = np.argsort(f[:, 0])[-keep:]          # loudest 60 % of frames
    v = f[idx]
    return np.concatenate([v.mean(axis=0), v.std(axis=0)])


def nn_accuracy(Xtr, ytr, Xte, yte):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    d = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    nn = np.argmin(d, axis=1)
    top1 = float(np.mean(ytr[nn] == yte))
    top5 = float(np.mean([yte[i] in ytr[np.argsort(d[i])[:5]] for i in range(len(yte))]))
    return top1, top5


def load_fleurs(per_class):
    X, y = [], []
    for cls in sorted(os.listdir(FLEURS_DIR)):
        d = os.path.join(FLEURS_DIR, cls)
        if not os.path.isdir(d) or cls not in set(UNIT2CLASS.values()):
            continue
        files = sorted(glob.glob(os.path.join(d, "*.wav")))[:per_class]
        for p in files:
            X.append(voiced_profile(read_wav(p))); y.append(cls)
    return np.array(X), np.array(y)


def load_iddo():
    """t06 == Iddo's own booth recordings. His real mouth, the thing to survive."""
    X, y, names = [], [], []
    for p in sorted(glob.glob(os.path.join(IDDO_DIR, "*_t06_*.wav"))):
        unit = os.path.basename(p).split("_t06_")[0]
        cls = UNIT2CLASS.get(unit)
        if cls is None:
            continue
        X.append(voiced_profile(read_wav(p))); y.append(cls); names.append(unit)
    return np.array(X), np.array(y), names


def main():
    per_class = int(os.environ.get("PER_CLASS", "150"))
    Xf, yf = load_fleurs(per_class)
    Xi, yi, units = load_iddo()
    classes = sorted(set(yf) & set(yi))
    keep_f = np.isin(yf, classes); keep_i = np.isin(yi, classes)
    Xf, yf, Xi, yi = Xf[keep_f], yf[keep_f], Xi[keep_i], yi[keep_i]

    print(f"FLEURS-cut food : {len(Xf)} clips, {len(set(yf))} classes "
          f"({per_class}/class cap)")
    print(f"Iddo t06 (real) : {len(Xi)} clips, {len(set(yi))} classes")
    print(f"classes         : {' '.join(classes)}")
    chance = 1.0 / len(classes)
    print(f"chance          : {chance*100:.1f}%\n")

    top1, top5 = nn_accuracy(Xf, yf, Xi, yi)
    print(f"  FLEURS-CUT (1502 human mouths) -> IDDO : top1 {top1*100:5.1f}%   "
          f"top5 {top5*100:5.1f}%")

    rng = np.random.default_rng(0)
    sh = [nn_accuracy(Xf, rng.permutation(yf), Xi, yi)[0] for _ in range(5)]
    print(f"  shuffled-label control                 : top1 {np.mean(sh)*100:5.1f}% "
          f"(sd {np.std(sh)*100:.1f})")
    print(f"  chance                                 : top1 {chance*100:5.1f}%")
    print("\n  ---- the number this had to beat ----")
    print("  SYNTHETIC (TTS) -> IDDO, measured 2026-08-23 : top1   6.1%  "
          "(chance 4.5%, shuffled 4.2%)")

    print("\n  per-class recall on Iddo's clips:")
    mu, sd = Xf.mean(0), Xf.std(0) + 1e-9
    A, B = (Xf - mu) / sd, (Xi - mu) / sd
    d = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    pred = yf[np.argmin(d, axis=1)]
    for c in classes:
        m = yi == c
        if m.sum():
            print(f"    {c:3s} n={int(m.sum()):3d}  correct {int((pred[m]==c).sum()):3d}"
                  f"   heard as: {', '.join(sorted(set(pred[m])))}")


if __name__ == "__main__":
    main()
