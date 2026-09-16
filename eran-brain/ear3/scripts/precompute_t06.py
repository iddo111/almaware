# -*- coding: utf-8 -*-
"""precompute_t06.py -- run the full Ear-v3 pipeline over the 600 big-unit
t06 clips ONCE, cache vectors + gate aux to targets-cache/t06-feats.npz.

Everything downstream (gate calibration, targets cache, LOO test) reads this
file instead of re-running the cochlea. The npz records the spec_hash it was
built under; consumers must check it.

The 19x3 small-unit clips are NOT included: no Phase-1 test uses them.
"""
import os
import sys
import time

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from ear3 import features as F                      # noqa: E402
from ear3 import calib as C                         # noqa: E402

OUT = os.path.join(_ROOT, "targets-cache", "t06-feats.npz")


def main():
    names, vecs, auxes = [], [], []
    t_start = time.perf_counter()
    for u in C.UNITS:
        paths = C.clips(u)
        print(f"{u}: {len(paths)} clips", flush=True)
        for p in paths:
            v, aux = F.features_with_aux(F.read_wav(p))
            names.append(os.path.basename(p))
            vecs.append(v)
            auxes.append(aux)
    wall = time.perf_counter() - t_start
    X = np.stack(vecs)

    maxlen = max(a["loud"].size for a in auxes)
    loud = np.zeros((len(auxes), maxlen))
    loud_len = np.zeros(len(auxes), dtype=np.int64)
    for i, a in enumerate(auxes):
        loud[i, :a["loud"].size] = a["loud"]
        loud_len[i] = a["loud"].size

    gs = [C.gate_stats(a) for a in auxes]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(
        OUT,
        names=np.array(names),
        X=X,
        loud=loud, loud_len=loud_len,
        span_a=np.array([a["span"][0] for a in auxes], dtype=np.int64),
        span_b=np.array([a["span"][1] for a in auxes], dtype=np.int64),
        total_dur=np.array([a["total_dur"] for a in auxes]),
        span_dur=np.array([a["span_dur"] for a in auxes]),
        occupancy=np.array([a["occupancy"] for a in auxes]),
        voiced_frac=np.array([a["voiced_frac"] for a in auxes]),
        median_f0=np.array([a["median_f0"] for a in auxes]),
        f0_slope=np.array([a["f0_slope"] for a in auxes]),
        humps=np.array([g["humps"] for g in gs], dtype=np.int64),
        dip=np.array([g["dip"] for g in gs]),
        spec_hash=np.array(F.spec_hash()),
    )
    per = wall / len(names) * 1e3
    med = {k: float(np.median([a["timing"][k] for a in auxes]))
           for k in auxes[0]["timing"]}
    print(f"wrote {OUT}: X {X.shape}, spec {F.spec_hash()[:12]}")
    print(f"wall {wall:.1f}s = {per:.1f} ms/clip (unpinned, median clip "
          f"{float(np.median([a['total_dur'] for a in auxes])):.2f}s)")
    print("median timing ms per clip: "
          + "  ".join(f"{k}={v:.1f}" for k, v in med.items()))


if __name__ == "__main__":
    main()
