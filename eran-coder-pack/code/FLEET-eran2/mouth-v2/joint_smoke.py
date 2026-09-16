# -*- coding: utf-8 -*-
"""joint_smoke.py -- first end-to-end NEW-MOUTH -> NEW-EAR number (eran2).

Renders the 4 naturalness gestures (exact params from
validate/v_naturalness.py) with the C backend, pushes each through Ear
v3 (ear3.features) and the wdist judge against all 6 units, and prints
the nearest-unit table (the embarrassment check) + per-render ms
breakdown (mouth C + ear).

NO search, NO training -- just the loop cost + sanity. These are
hand-authored gestures, not searched winners; the table is information,
not a milestone (no milestone from a number -- the plan's law).

Run on eran2:
    cd ~/mouth-v2 && ~/ear-v3/venv/bin/python joint_smoke.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.expanduser("~/ear-v3"))

import numpy as np

import mouth2


def units():
    """EXACT gesture params of validate/v_naturalness.py units()."""
    ka = mouth2.vowel_knots("a")
    seal = dict(c_pos=0.97, c_area=0.0)

    ah = {"keyframes": [mouth2.keyframe(ka, tenseness=0.55),
                        mouth2.keyframe(ka),
                        mouth2.keyframe(ka, tenseness=0.5)],
          "durations": [0.15, 0.25, 0.15],
          "f0_knots": [295.0, 282.0, 248.0],
          "tenseness_knots": [0.55, 0.6, 0.5]}

    ba = {"keyframes": [mouth2.keyframe(ka, voicing=0.25, **seal),
                        mouth2.keyframe(ka, voicing=0.25),
                        mouth2.keyframe(ka),
                        mouth2.keyframe(ka, tenseness=0.5)],
          "durations": [0.10, 0.004, 0.024, 0.35],
          "f0_knots": [300.0, 280.0, 245.0],
          "tenseness_knots": [0.6, 0.6, 0.5]}

    ma = {"keyframes": [mouth2.keyframe(ka, velum=0.5, **seal),
                        mouth2.keyframe(ka, velum=0.15),
                        mouth2.keyframe(ka),
                        mouth2.keyframe(ka, tenseness=0.5)],
          "durations": [0.16, 0.05, 0.20, 0.15],
          "f0_knots": [290.0, 280.0, 245.0],
          "tenseness_knots": [0.55, 0.6, 0.5]}

    abba = {"keyframes": [mouth2.keyframe(ka),
                          mouth2.keyframe(ka, voicing=0.25, **seal),
                          mouth2.keyframe(ka, voicing=0.25),
                          mouth2.keyframe(ka),
                          mouth2.keyframe(ka, tenseness=0.5)],
            "durations": [0.20, 0.12, 0.004, 0.024, 0.32],
            "f0_knots": [300.0, 285.0, 245.0],
            "tenseness_knots": [0.6, 0.6, 0.5]}

    return [("ah", ah), ("ba", ba), ("ma", ma), ("abba", abba)]


def main():
    from ear3 import features as F
    from ear3 import judge as J
    stats = J.load_cache()

    print("JOINT SMOKE: mouth2 C backend -> Ear v3, eran2")
    print("(hand-authored gestures; information, not a milestone)")
    # warm-up: load the C lib and JIT EVERY render's cochlea shape bucket
    # (first call on a new 1000-sample bucket pays ~1 s of JAX JIT;
    # measured 2026-08-26: cold ba/abba buckets read 1028/1045 ms of
    # "ear" that was really compilation. A search loop renders a fixed
    # duration, so the steady-state number is the honest loop cost; the
    # cold number is reported here in the header instead.)
    t0 = time.perf_counter()
    for name, g in units():
        F.features(mouth2.say_gesture(g, seed=0, backend="c"))
    warm_s = time.perf_counter() - t0
    print("(bucket warm-up incl. JIT, all 4 renders once: %.1f s)" % warm_s)

    rows = []
    for name, g in units():
        t0 = time.perf_counter()
        y = mouth2.say_gesture(g, seed=0, backend="c")
        t1 = time.perf_counter()
        vec = F.features(y)
        t2 = time.perf_counter()
        table = J.nearest_table(vec, stats)
        mouth_ms = (t1 - t0) * 1000.0
        ear_ms = (t2 - t1) * 1000.0
        rows.append((name, y.size / 16000.0, mouth_ms, ear_ms, table))

    print("%-6s %6s | %8s %8s %8s | nearest units (wdist)"
          % ("render", "dur_s", "mouth_ms", "ear_ms", "total"))
    for name, dur, m_ms, e_ms, table in rows:
        near = "  ".join("%s %.2f" % (r["unit"], r["wdist"])
                         for r in table[:3])
        hit = table[0]["unit"] == name
        print("%-6s %6.2f | %8.1f %8.1f %8.1f | %s%s"
              % (name, dur, m_ms, e_ms, m_ms + e_ms, near,
                 "" if hit else "   <-- nearest is NOT %s" % name))
    print()
    for name, dur, m_ms, e_ms, table in rows:
        print("%s full table: %s" % (
            name, "  ".join("%s %.2f" % (r["unit"], r["wdist"])
                            for r in table)))


if __name__ == "__main__":
    main()
