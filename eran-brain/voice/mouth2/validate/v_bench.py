# -*- coding: utf-8 -*-
"""v_bench.py -- the C-twin bench gate.

0.5 s /abba/ gesture render (5 keyframes, seal + burst + release, falling
f0), median of 50 runs, single core. Plan gate: <= 15 ms per render on an
eran2 core. Run there as:

    taskset -c 0 python3 validate/v_bench.py

Reports the FULL pipeline cost (param prep + noise draws + C core +
resample_poly + peak-norm = what a search worker pays per eval), plus the
C-call share, plus the reference time for the same render (median of 3).
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import mouth2

N_RUNS = 50
GATE_MS = 15.0


def abba_500ms():
    ka = mouth2.vowel_knots("a")
    seal = dict(c_pos=0.97, c_area=0.0)
    return {"keyframes": [mouth2.keyframe(ka),
                          mouth2.keyframe(ka, voicing=0.25, **seal),
                          mouth2.keyframe(ka, voicing=0.25),
                          mouth2.keyframe(ka),
                          mouth2.keyframe(ka, tenseness=0.5)],
            "durations": [0.14, 0.10, 0.004, 0.024, 0.232],   # = 0.500 s
            "f0_knots": [300.0, 285.0, 245.0],
            "tenseness_knots": [0.6, 0.6, 0.5]}


def main():
    import fastcore
    if not fastcore.available():
        print("FAIL: voc_eran library not built -- run build.sh first")
        return 1
    g = abba_500ms()
    y = mouth2.say_gesture(g, seed=0, backend="c")     # warm-up + sanity
    assert y is not None and y.size == 8000, y.size if y is not None else None

    times = []
    for i in range(N_RUNS):
        t0 = time.perf_counter()
        mouth2.say_gesture(g, seed=i, backend="c")
        times.append((time.perf_counter() - t0) * 1000.0)
    med = statistics.median(times)

    # C-call share: time fastcore.render_c alone (same seed spread)
    t_ref = []
    for i in range(3):
        t0 = time.perf_counter()
        mouth2.say_gesture(g, seed=i, backend="ref")
        t_ref.append((time.perf_counter() - t0) * 1000.0)
    ref_med = statistics.median(t_ref)

    print("BENCH: 0.5 s /abba/ gesture, %d runs, this process's core"
          % N_RUNS)
    print("  C backend  : median %.2f ms  (min %.2f, p90 %.2f, max %.2f)"
          % (med, min(times),
             sorted(times)[int(0.9 * len(times))], max(times)))
    print("  reference  : median %.1f ms (of 3) -> speedup %.0fx"
          % (ref_med, ref_med / med))
    print("  gate <= %.0f ms: %s" % (GATE_MS, "PASS" if med <= GATE_MS
                                     else "FAIL"))
    return 0 if med <= GATE_MS else 1


if __name__ == "__main__":
    sys.exit(main())
