# -*- coding: utf-8 -*-
"""v_determinism.py -- same seed twice -> bit-identical. All three doors.

Also proves the streams are seed-pure across PROCESSES (two fresh
python subprocesses hash the same bytes) and that a different seed
actually changes the waveform.
"""
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import geometry
import mouth2

_SUB = """
import sys, hashlib, numpy as np
sys.path.insert(0, r'%s')
import mouth2, geometry
L, a44 = geometry.child_area(60, vowel='a')
y = mouth2.say(geometry.resample_areas(a44, 34), seconds=0.3, seed=7)
ka = mouth2.vowel_knots('a')
g = {'keyframes': [mouth2.keyframe(ka), mouth2.keyframe(ka, c_pos=0.97, c_area=0.0, voicing=0.3), mouth2.keyframe(ka)],
     'durations': [0.12, 0.06, 0.12], 'f0_knots': [300, 280, 250],
     'tenseness_knots': [0.6, 0.6, 0.6]}
yg = mouth2.say_gesture(g, seed=7)
print(hashlib.sha256(y.tobytes()).hexdigest(), hashlib.sha256(yg.tobytes()).hexdigest())
"""


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    L, a44 = geometry.child_area(60, vowel="a")
    a34 = geometry.resample_areas(a44, 34)

    print("DETERMINISM gate")
    ok = True

    y1 = mouth2.say(a34, seconds=0.3, seed=7)
    y2 = mouth2.say(a34, seconds=0.3, seed=7)
    y3 = mouth2.say(a34, seconds=0.3, seed=8)
    t1 = np.array_equal(y1, y2) and not np.array_equal(y1, y3)
    print("  say: same seed identical, different seed differs -> %s"
          % ("PASS" if t1 else "FAIL"))
    ok &= t1

    kf = [(a34, 0.12), (np.clip(a34 * 0.2, 0.001, 4.0), 0.06), (a34, 0.12)]
    s1 = mouth2.say_sequence(kf, seed=7)
    s2 = mouth2.say_sequence(kf, seed=7)
    t2 = np.array_equal(s1, s2)
    print("  say_sequence: bit-identical -> %s" % ("PASS" if t2 else "FAIL"))
    ok &= t2

    ka = mouth2.vowel_knots("a")
    g = {"keyframes": [mouth2.keyframe(ka),
                       mouth2.keyframe(ka, c_pos=0.97, c_area=0.0, voicing=0.3),
                       mouth2.keyframe(ka)],
         "durations": [0.12, 0.06, 0.12], "f0_knots": [300, 280, 250],
         "tenseness_knots": [0.6, 0.6, 0.6]}
    g1 = mouth2.say_gesture(g, seed=7)
    g2 = mouth2.say_gesture(g, seed=7)
    g3 = mouth2.say_gesture(g, seed=9)
    t3 = np.array_equal(g1, g2) and not np.array_equal(g1, g3)
    print("  say_gesture: same seed identical, different seed differs -> %s"
          % ("PASS" if t3 else "FAIL"))
    ok &= t3

    code = _SUB % root
    h = []
    for _ in range(2):
        out = subprocess.run([sys.executable, "-c", code], cwd=root,
                             capture_output=True, text=True)
        h.append(out.stdout.strip())
    t4 = bool(h[0]) and h[0] == h[1]
    print("  cross-process: two fresh interpreters, same sha256 -> %s"
          % ("PASS" if t4 else "FAIL"))
    print("    %s" % h[0][:64])
    ok &= t4

    print("  -> %s" % ("PASS" if ok else "FAIL"))
    return {"gate": "determinism", "pass": bool(ok)}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["pass"] else 1)
