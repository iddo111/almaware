# -*- coding: utf-8 -*-
"""test_speed.py -- median per-call cost of full features() on a 0.5 s clip.

Run PINNED:  taskset -c 0 env OMP_NUM_THREADS=1 python tests/test_speed.py
Budget: <= ~50 ms workable, > 70 ms triggers the named contingencies
(NAP 2:1 decimation before SAI -- ALREADY TAKEN, see pitch.py -- then C++).
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import time  # noqa: E402

import numpy as np  # noqa: E402

import _common  # noqa: E402
from ear3 import features as F  # noqa: E402


def main():
    x = F.read_wav(os.path.join(_common.CORPUS, "ah_t06_1.wav"))[:8000]
    assert x.size == 8000
    # warmup: JIT compile + caches
    for _ in range(3):
        F.features_with_aux(x)
    per, tim = [], []
    for _ in range(30):
        t0 = time.perf_counter()
        _, aux = F.features_with_aux(x)
        per.append((time.perf_counter() - t0) * 1e3)
        tim.append(aux["timing"])
    per.sort()
    med = per[len(per) // 2]
    parts = {k: float(np.median([t[k] for t in tim])) for k in tim[0]}
    print(f"features() on 0.5 s clip, single pinned core:")
    print(f"  median {med:.1f} ms   min {per[0]:.1f}   max {per[-1]:.1f}")
    print("  breakdown (median ms): "
          + "  ".join(f"{k}={v:.1f}" for k, v in parts.items()))
    verdict = ("PASS (<=50ms)" if med <= 50 else
               "WORKABLE-BUT-OVER-50" if med <= 70 else
               "OVER-70 -> contingency ladder")
    print(f"  budget verdict: {verdict}")


if __name__ == "__main__":
    main()
