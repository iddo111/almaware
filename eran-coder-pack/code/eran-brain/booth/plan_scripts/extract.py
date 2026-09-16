import os, sys, re, json, wave
import numpy as np
sys.path.insert(0, r"D:\CLAUDE\eran-brain\body")
import genome, ears
E = ears.Ears()
assert E.repr == "cochlea" and E.dim == 192, (E.repr, E.dim)
assert genome.EAR_FROZEN is True
D = r"D:\CLAUDE\eran-brain\booth\staged\t06"
rows = []
for f in sorted(os.listdir(D)):
    if not f.endswith(".wav"): continue
    m = re.match(r"^(.*)_t06_(\d+)\.wav$", f)
    p = os.path.join(D, f)
    v = E.utterance(p)
    with wave.open(p,'rb') as w:
        nf, sr = w.getnframes(), w.getframerate()
    rows.append(dict(file=f, unit=m.group(1), take=int(m.group(2)),
                     mtime=os.path.getmtime(p), dur=nf/sr, vec=v.tolist()))
rows.sort(key=lambda r: r["mtime"])
json.dump(rows, open("feats.json","w"))
print("wrote", len(rows), "dim", len(rows[0]["vec"]), "repr", E.repr, "bands", E.n_bands, "slices", genome.EAR_SLICES, "frozen", genome.EAR_FROZEN)
