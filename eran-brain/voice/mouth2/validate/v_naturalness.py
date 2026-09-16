# -*- coding: utf-8 -*-
"""v_naturalness.py -- the first naturalness set: ah, ba, ma, abba.

Gesture-space renders with tasteful defaults, f0 ~280 Hz with a falling
contour, written to validate/naturalness/NN_unit.wav + spectrogram PNGs.

NO QUALITY CLAIM IS MADE HERE. These files exist for Iddo's ear; the
plan's rule stands -- no milestone from a number, and none from this
script either. The script only proves the files exist, are non-silent,
and are deterministic.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import measure as M
import mouth2

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "naturalness")


def units():
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

    return [("01_ah", ah), ("02_ba", ba), ("03_ma", ma), ("04_abba", abba)]


def main():
    os.makedirs(OUT, exist_ok=True)
    print("NATURALNESS set (no quality claim -- for Iddo's ear)")
    ok = True
    for name, g in units():
        y = mouth2.say_gesture(g, seed=0)
        y2 = mouth2.say_gesture(g, seed=0)
        det = np.array_equal(y, y2)
        alive = y is not None and M.rms(y) > 0.01
        M.save_wav(os.path.join(OUT, name + ".wav"), y)
        M.spectrogram_png(os.path.join(OUT, name + ".png"), y,
                          title=name + " (mouth2, seed 0)")
        print("  %s: %.2f s, rms %.3f, deterministic %s -> %s"
              % (name, y.size / 16000.0, M.rms(y), det,
                 "written" if (alive and det) else "PROBLEM"))
        ok &= alive and det
    print("  -> %s (existence + determinism only; the ear that matters "
          "is Iddo's)" % ("PASS" if ok else "FAIL"))
    return {"gate": "naturalness", "pass": bool(ok)}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["pass"] else 1)
