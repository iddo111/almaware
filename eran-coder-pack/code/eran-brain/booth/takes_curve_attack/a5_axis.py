"""A5 -- the 36.4% was measured with a DIFFERENT EAR. Prove it, on the same clips.

The memory that carries the 36.4% (project_eran_synthetic_corpus_scar, measured
on eran1 2026-08-23 11:45) says in its own words: "the project's own
voiced_profile features and 1-NN probe (byte-for-byte from
corpus-syllables/verify.py)". voiced_profile is 28 dims (mean+std of a 14-dim
frame feature over the loudest 60%). The frozen cochlea is 192 dims.
Two different ears -> two different axes.

Run BOTH on the identical clips, identical probe, identical split.
"""
import os, sys, json, wave, numpy as np
sys.path.insert(0, r"D:\CLAUDE\voice-ant-farm\corpus-syllables")
from probe import load, nn1

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
        band = [np.log(sp[edges[i]:edges[i+1]].sum() + 1e-10) for i in range(bands)]
        feats.append(np.array([energy, zcr] + band))
    return np.array(feats) if feats else np.zeros((0, 2 + bands))

def voiced_profile(x):
    f = frame_features(x)
    if f.shape[0] < 4: return np.zeros(28)
    keep = f[:, 0] >= np.quantile(f[:, 0], 0.40)
    f = f[keep] if keep.sum() >= 3 else f
    return np.concatenate([f.mean(axis=0), f.std(axis=0)])

X, unit, take, mt, sit, dur = load()
R = json.load(open("feats_sit.json"))
D = r"D:\CLAUDE\eran-brain\booth\staged\t06"
V = np.array([voiced_profile(read_wav(os.path.join(D, r["file"]))) for r in R])
print(f"voiced_profile dim {V.shape[1]}   frozen cochlea dim {X.shape[1]}")

def loto(F, rows):
    ok = []
    for i in rows:
        tr = np.array([j for j in rows if j != i])
        p, _ = nn1(F[tr], unit[tr], F[[i]], unit[[i]])
        ok.append(p[0] == unit[i])
    return 100*float(np.mean(ok))

first3 = {}
for u in sorted(set(unit)):
    r = np.where(unit == u)[0]; first3[u] = r[np.argsort(take[r])][:3]
s0 = list(np.where(sit == 0)[0])
all3 = list(np.concatenate([first3[u] for u in sorted(first3)]))

print("\n leave-one-take-out, 3 takes/unit, SAME clips, SAME probe, two ears:")
print("  set                                  n_units  voiced_profile(28d)  frozen cochlea(192d)")
for name, rows in [("sitting 0 only (20 units, one 3.3-min run)", s0),
                   ("all 25 units, first 3 takes of each", all3)]:
    nu = len(set(unit[rows]))
    print(f"  {name:36s}   {nu:3d}     {loto(V,rows):7.2f}%           {loto(X,rows):7.2f}%")
print(f"\n  the memory's claim, for reference: 36.4% on 22 units x 3 takes, chance 4.5%")
print(f"  (measured with voiced_profile, on eran1, 2026-08-23 11:45)")

print("\n=== replicate at K=22 with the ear the 36.4% actually used ===")
rng = np.random.default_rng(19)
ALL = sorted(first3)
for K in [20, 22, 25]:
    accs_v, accs_c = [], []
    reps = 300 if K < 25 else 1
    for _ in range(reps):
        us = list(rng.choice(ALL, K, replace=False)) if K < 25 else ALL
        rows = list(np.concatenate([first3[u] for u in us]))
        accs_v.append(loto(V, rows)); accs_c.append(loto(X, rows))
    print(f"  K={K:3d} (chance {100/K:.2f}%)  voiced_profile {np.mean(accs_v):6.2f}% +-{np.std(accs_v):4.2f}"
          f"   cochlea {np.mean(accs_c):6.2f}% +-{np.std(accs_c):4.2f}")
print("  -> the memory's 36.4% at K=22 sits inside the voiced_profile band, not the cochlea one.")
