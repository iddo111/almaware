"""extract.py -- ERAN's OWN frozen cochlea over the 657 staged t06 wavs.

Imports body/ears.py, does not reimplement it. Writes one .npz cache so the
curve script never re-reads audio.
"""
import glob, os, sys, json
import numpy as np

BODY = r"D:\CLAUDE\eran-brain\body"
sys.path.insert(0, BODY)
import genome            # noqa: E402
import ears as ears_mod  # noqa: E402

STAGED = r"D:\CLAUDE\eran-brain\booth\staged\t06"
OUT = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\8aa52163-564a-4846-8f48-cd46afaf48f4\scratchpad\t06_cochlea.npz"

# crown_path pointed at a non-existent file so a stray state/crown.json on this
# PC mirror cannot silently change the ear under the measurement.
ear = ears_mod.Ears(exam=False, crown_path=os.path.join(STAGED, "__no_crown__.json"))
print(f"ear repr   : {ear.repr}")
print(f"n_bands    : {ear.n_bands}")
print(f"slices     : {genome.EAR_SLICES}")
print(f"dim        : {ear.dim}")
print(f"pooling    : {ear.pooling} (inert for cochlea)")
print(f"frame/hop  : {ear.frame}/{ear.hop} samples  ({genome.FRAME_MS}/{genome.HOP_MS} ms)")
print(f"EAR_FROZEN : {genome.EAR_FROZEN}")

paths = sorted(glob.glob(os.path.join(STAGED, "*.wav")))
X, unit, take, dur = [], [], [], []
for p in paths:
    name = os.path.basename(p)[:-4]
    parts = name.split("_")
    assert len(parts) == 3, name
    u, talker, k = parts
    assert talker == "t06", name
    v = ear.utterance(p)
    assert v.shape == (ear.dim,), (name, v.shape)
    X.append(v); unit.append(u); take.append(int(k))
    dur.append(os.path.getsize(p))
X = np.asarray(X, dtype=np.float64)
unit = np.asarray(unit); take = np.asarray(take); dur = np.asarray(dur)
print(f"\nvectors    : {X.shape}")
print(f"units      : {len(set(unit.tolist()))}")
print(f"L2 norms   : min {np.linalg.norm(X,axis=1).min():.6f} "
      f"max {np.linalg.norm(X,axis=1).max():.6f}")
np.savez(OUT, X=X, unit=unit, take=take, size=dur, dim=ear.dim,
         n_bands=ear.n_bands, repr_=ear.repr)
print(f"saved      : {OUT}")
