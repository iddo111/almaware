# -*- coding: utf-8 -*-
"""v_parity.py -- the C-twin parity gate (SANITY0 pattern).

A battery of 14 renders spanning all three APIs (say, say_sequence,
say_gesture; vowels, seal/burst stops, velum nasals, multi-keyframe
gestures, extreme fence values). Each is rendered with backend="ref"
(the pure-numpy truth) and backend="c" (voc_eran.c via fastcore) and the
float32 outputs are compared sample by sample.

GATE: max |diff| < 1e-6 across the whole battery (double math inside,
float32 out, peak 0.7). The honest number is printed either way.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import geometry
import mouth2

GATE = 1e-6


def battery():
    L, a_a = geometry.child_area(60, vowel="a")
    _, a_i = geometry.child_area(60, vowel="i")
    _, a_u = geometry.child_area(60, vowel="u")
    a34 = lambda a: geometry.resample_areas(a, 34)
    ka = mouth2.vowel_knots("a")
    ki = mouth2.vowel_knots("i")
    seal = dict(c_pos=0.97, c_area=0.0)

    cases = []
    # --- say: vowels, band edges, fence-breaking areas
    cases.append(("say_a_260", lambda be: mouth2.say(
        a34(a_a), f0=260.0, seconds=0.5, seed=0, backend=be)))
    cases.append(("say_i_300", lambda be: mouth2.say(
        a34(a_i), f0=300.0, seconds=0.5, seed=1, backend=be)))
    cases.append(("say_u_220", lambda be: mouth2.say(
        a34(a_u), f0=220.0, seconds=0.5, seed=2, backend=be)))
    cases.append(("say_neutral_f0max", lambda be: mouth2.say(
        a34(geometry.child_area(60)[1]), f0=999.0,   # fence -> 500
        seconds=0.5, seed=3, backend=be)))
    extreme = np.concatenate([np.full(17, 0.001), np.full(17, 50.0)])
    cases.append(("say_extreme_fences", lambda be: mouth2.say(
        extreme, f0=100.0,                            # fence -> 200
        seconds=0.5, seed=4, backend=be)))

    # --- say_sequence: mouth34 contract, incl. sub-fence closure (stop)
    closed = a34(a_a).copy()
    closed[-4:] = 0.02                                # closed_lips-style seal
    cases.append(("seq_a_closed_a", lambda be: mouth2.say_sequence(
        [(a34(a_a), 0.18), (closed, 0.10), (a34(a_a), 0.22)],
        f0=260.0, seed=5, backend=be)))
    cases.append(("seq_a_i_u", lambda be: mouth2.say_sequence(
        [(a34(a_a), 0.17), (a34(a_i), 0.17), (a34(a_u), 0.16)],
        f0=280.0, seed=6, backend=be)))

    # --- say_gesture: the 4 naturalness units (exact validate/ params)
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
    for name, g in (("gest_ah", ah), ("gest_ba", ba),
                    ("gest_ma", ma), ("gest_abba", abba)):
        cases.append((name, lambda be, g=g: mouth2.say_gesture(
            g, seed=0, backend=be)))

    # --- 3-keyframe aba (the mouth2 __main__ smoke gesture)
    aba3 = {"keyframes": [mouth2.keyframe(ka),
                          mouth2.keyframe(ka, c_pos=0.97, c_area=0.0,
                                          voicing=0.35),
                          mouth2.keyframe(ka)],
            "durations": [0.20, 0.09, 0.25],
            "f0_knots": [300, 285, 250],
            "tenseness_knots": [0.6, 0.6, 0.55]}
    cases.append(("gest_aba3", lambda be: mouth2.say_gesture(
        aba3, seed=7, backend=be)))

    # --- extreme fences in gesture space (everything clipped)
    wild = {"keyframes": [
        np.array([-10, 10, -10, 10, -10, 10, -10, 10,   # log2 areas clipped
                  0.0, 5.0, 2.0, 0.01, 0.0]),           # c_pos/c_area/velum/
        np.array([10, -10, 10, -10, 10, -10, 10, -10,   # tenseness/voicing
                  1.5, -1.0, -0.5, 0.99, 1.0])],
        "durations": [0.25, 0.25],
        "f0_knots": [50.0, 800.0, 100.0],               # fence -> [200,500]
        "tenseness_knots": [0.01, 0.99, 0.5]}
    cases.append(("gest_wild_fences", lambda be: mouth2.say_gesture(
        wild, seed=8, backend=be)))

    # --- nasal-vented seal: velum wide open, lips sealed (no burst path)
    mvent = {"keyframes": [mouth2.keyframe(ka, velum=0.8, **seal),
                           mouth2.keyframe(ka, velum=0.8, **seal),
                           mouth2.keyframe(ka)],
             "durations": [0.15, 0.15, 0.20],
             "f0_knots": [280.0, 270.0, 250.0],
             "tenseness_knots": [0.6, 0.6, 0.55]}
    cases.append(("gest_m_vented", lambda be: mouth2.say_gesture(
        mvent, seed=9, backend=be)))
    return cases


def main():
    import fastcore
    if not fastcore.available():
        print("FAIL: voc_eran library not built -- run build.sh first")
        return {"gate": "parity", "pass": False, "reason": "no library"}
    rows = []
    worst = 0.0
    ok = True
    print("C-TWIN PARITY (ref = truth; gate max|diff| < %g)" % GATE)
    print("%-22s %10s %10s %8s %8s" % ("case", "maxdiff", "rms_ref",
                                       "t_ref_s", "t_c_s"))
    for name, fn in battery():
        t0 = time.time(); yr = fn("ref"); t1 = time.time()
        yc = fn("c"); t2 = time.time()
        if yr is None or yc is None:
            same_none = yr is None and yc is None
            print("%-22s %10s (ref None? %s c None? %s)"
                  % (name, "NONE", yr is None, yc is None))
            ok &= same_none
            rows.append({"case": name, "none": True, "agree": same_none})
            continue
        if yr.shape != yc.shape:
            print("%-22s SHAPE MISMATCH %r vs %r" % (name, yr.shape, yc.shape))
            ok = False
            continue
        d = float(np.max(np.abs(yr.astype(np.float64)
                                - yc.astype(np.float64))))
        worst = max(worst, d)
        rms = float(np.sqrt(np.mean(yr.astype(np.float64) ** 2)))
        print("%-22s %10.3e %10.4f %8.2f %8.3f"
              % (name, d, rms, t1 - t0, t2 - t1))
        rows.append({"case": name, "max_diff": d, "rms_ref": rms,
                     "t_ref_s": t1 - t0, "t_c_s": t2 - t1})
        ok &= d < GATE
    print("-" * 64)
    print("worst max|diff| over battery: %.3e -> %s"
          % (worst, "PASS" if ok else "FAIL"))
    res = {"gate": "parity", "pass": bool(ok), "worst_max_diff": worst,
           "gate_value": GATE, "cases": rows}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "parity_results.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["pass"] else 1)
