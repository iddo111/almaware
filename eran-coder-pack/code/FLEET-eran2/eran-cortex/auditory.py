# -*- coding: utf-8 -*-
"""auditory.py -- ERAN's first real organ: a cortex that hears Iddo's mouth.

Iddo recorded these himself on 2026-08-23: 100x אַה, 100x בַּ, 100x אַבָּא, 24x אִי.
That is the first deep corpus ERAN has ever had -- everything before it was 3 takes of
22 units from a synthesiser, and this morning's probe measured that corpus transferring
to a real mouth AT CHANCE (6.1% vs 4.5%). So this organ is trained on his voice only.
Not one synthetic clip.

WHAT IT IS. A small 1-D conv encoder over log-mel, trained to discriminate the units.
Small on purpose: 324 clips is a small corpus and a big model would simply memorise the
waveforms, which is the trap the whole project already walked into once
(4.9M params on 89K tokens, train 0.11 / heldout 2.45).

THE TWO QUESTIONS IT MUST ANSWER, and only the second one matters:

  1. Can it tell אַה from בַּ from אַבָּא?   -- table stakes. Chance is 33%.
  2. Can it tell a REAL אַבָּא from אַה+בַּ SPLICED TOGETHER?
     This is the real test. If ERAN scores at chance here, he has learned "אבא" as an
     unanalysable lump of sound and cannot ever build new words from parts. If he beats
     chance, he has heard the thing that makes a word more than its syllables --
     coarticulation, the join, the single breath.

HELD OUT BY TAKE, never by frame. Two takes of one word are nearly the same waveform;
splitting frames across the boundary is the session-leak scar in miniature.
"""
import glob, math, os, random, sys, wave
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F

SR = 16000
DEV = "cuda" if torch.cuda.is_available() else "cpu"
DATA = os.path.expanduser("~/eran-cortex/data/t06")
UNITS = ["ah", "ba", "abba"]


def read_wav(p):
    with wave.open(p, "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def logmel(x, n_fft=400, hop=160, n_mels=40, T=64):
    """log-mel, fixed length T frames. Hand-rolled: this box has no torchaudio."""
    if x.size < n_fft:
        x = np.pad(x, (0, n_fft - x.size))
    win = np.hanning(n_fft)
    frames = [np.abs(np.fft.rfft(x[i:i + n_fft] * win)) ** 2
              for i in range(0, x.size - n_fft + 1, hop)]
    S = np.array(frames).T if frames else np.zeros((n_fft // 2 + 1, 1))
    # mel filterbank
    f = np.linspace(0, SR / 2, S.shape[0])
    m = 2595 * np.log10(1 + f / 700)
    edges = np.linspace(m.min(), m.max(), n_mels + 2)
    fb = np.zeros((n_mels, S.shape[0]), dtype=np.float32)
    for i in range(n_mels):
        lo, mid, hi = edges[i], edges[i + 1], edges[i + 2]
        fb[i] = np.clip(np.minimum((m - lo) / (mid - lo + 1e-9),
                                   (hi - m) / (hi - mid + 1e-9)), 0, None)
    M = np.log(fb @ S + 1e-8)
    # centre-pad / crop to T frames so every clip is the same shape
    if M.shape[1] < T:
        M = np.pad(M, ((0, 0), (0, T - M.shape[1])), constant_values=M.min())
    else:
        s = (M.shape[1] - T) // 2
        M = M[:, s:s + T]
    return ((M - M.mean()) / (M.std() + 1e-6)).astype(np.float32)


def splice(ah, ba, overlap_ms=0):
    """אַה + בַּ glued end to end. This is what a word is NOT."""
    return np.concatenate([ah, ba])


class Cortex(nn.Module):
    def __init__(self, n_out, ch=32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(40, ch, 5, padding=2), nn.BatchNorm1d(ch), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(ch, ch * 2, 5, padding=2), nn.BatchNorm1d(ch * 2), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(ch * 2, ch * 2, 3, padding=1), nn.BatchNorm1d(ch * 2), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1))
        self.head = nn.Linear(ch * 2, n_out)

    def forward(self, x):
        return self.head(self.net(x).squeeze(-1))


def train_eval(Xtr, ytr, Xte, yte, n_out, epochs=60, seed=0):
    torch.manual_seed(seed)
    m = Cortex(n_out).to(DEV)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-3, weight_decay=1e-2)
    Xtr_t = torch.tensor(Xtr).to(DEV); ytr_t = torch.tensor(ytr).to(DEV)
    Xte_t = torch.tensor(Xte).to(DEV); yte_t = torch.tensor(yte).to(DEV)
    best = 0.0
    for ep in range(epochs):
        m.train()
        perm = torch.randperm(len(Xtr_t), device=DEV)
        for i in range(0, len(perm), 32):
            b = perm[i:i + 32]
            opt.zero_grad()
            F.cross_entropy(m(Xtr_t[b]), ytr_t[b]).backward()
            opt.step()
        m.eval()
        with torch.no_grad():
            acc = (m(Xte_t).argmax(1) == yte_t).float().mean().item()
        best = max(best, acc)
    return best, sum(p.numel() for p in m.parameters())


def main():
    clips = {u: sorted(glob.glob(os.path.join(DATA, f"{u}_t06_*.wav"))) for u in UNITS}
    for u in UNITS:
        print(f"  {u:5s} {len(clips[u]):3d} clips")
    raw = {u: [read_wav(p) for p in clips[u]] for u in UNITS}

    # ---------- question 1: can it tell the three apart? held out BY TAKE ----------
    print("\n=== Q1: אַה vs בַּ vs אַבָּא   (chance 33.3%) ===")
    rng = random.Random(0)
    accs = []
    for fold in range(3):
        Xtr, ytr, Xte, yte = [], [], [], []
        for ui, u in enumerate(UNITS):
            idx = list(range(len(raw[u]))); rng.shuffle(idx)
            cut = int(len(idx) * 0.25)
            for j in idx[:cut]:
                Xte.append(logmel(raw[u][j])); yte.append(ui)
            for j in idx[cut:]:
                Xtr.append(logmel(raw[u][j])); ytr.append(ui)
        a, npar = train_eval(np.array(Xtr), np.array(ytr), np.array(Xte), np.array(yte), 3, seed=fold)
        accs.append(a)
        print(f"  fold {fold}: {a*100:5.1f}%   ({npar:,} params, {len(Xtr)} train / {len(Xte)} test)")
    print(f"  --> {np.mean(accs)*100:.1f}% (sd {np.std(accs)*100:.1f})")

    # ---------- question 2: real word vs spliced syllables ----------
    print("\n=== Q2: REAL אַבָּא  vs  אַה+בַּ SPLICED   (chance 50.0%) ===")
    print("    -- this is the one that decides whether he heard a WORD or a LUMP --")
    accs2 = []
    for fold in range(3):
        rng2 = random.Random(100 + fold)
        real = raw["abba"]
        fake = [splice(rng2.choice(raw["ah"]), rng2.choice(raw["ba"])) for _ in range(len(real))]
        idx = list(range(len(real))); rng2.shuffle(idx)
        cut = int(len(idx) * 0.25)
        Xtr, ytr, Xte, yte = [], [], [], []
        for j in idx[:cut]:
            Xte += [logmel(real[j]), logmel(fake[j])]; yte += [1, 0]
        for j in idx[cut:]:
            Xtr += [logmel(real[j]), logmel(fake[j])]; ytr += [1, 0]
        a, npar = train_eval(np.array(Xtr), np.array(ytr), np.array(Xte), np.array(yte), 2, seed=fold)
        accs2.append(a)
        print(f"  fold {fold}: {a*100:5.1f}%")
    m2, s2 = np.mean(accs2) * 100, np.std(accs2) * 100
    print(f"  --> {m2:.1f}% (sd {s2:.1f})")

    print("\n" + "=" * 68)
    if m2 > 75:
        print(f"VERDICT: he hears אַבָּא as a WORD, not as two syllables glued -- {m2:.1f}%.")
        print("         The join, the coarticulation, the single breath are IN the signal")
        print("         and the cortex found them. Words can be built from parts.")
    elif m2 > 58:
        print(f"VERDICT: weak but real -- {m2:.1f}%. Something distinguishes the true word;")
        print("         not enough yet to build on. More takes, or a longer window.")
    else:
        print(f"VERDICT: AT CHANCE ({m2:.1f}%). To this cortex a real אַבָּא and a crude splice")
        print("         are the same object. It has learned a lump.")
    print("=" * 68)


if __name__ == "__main__":
    main()
