# -*- coding: utf-8 -*-
"""arms.py -- what is actually being searched: a trajectory of tube shapes.

A vowel is one posture; "abba" is a MOVEMENT: /a/ -> lips shut -> burst -> /a/.
Each arm maps a flat parameter vector to keyframes for say_sequence.

THE ARMS, chosen so the fleet answers three questions at once:
  ba         34 vowel areas + closure length + vowel length + closure area.
             Stage 1: can a single closure+vowel find Iddo's real /ba/?
  abba       shared vowel + t1/tc/t2 + closure area (39 dims).
             Stage 2: the word itself, with the closure as a structured gesture.
  abba-free  4 free keyframes x 34 areas + 4 durations (140 dims). No gesture
             structure imposed -- can free articulation beat the structured arm?
  control-*  SAME search space, uniform random search, same eval bookkeeping.
             If CMA-ES does not clearly beat this, nothing was learned and the
             heartbeats must say so ([[feedback_clean_experiments]]).

f0 is FENCED at 220 Hz (a baby, bottom of 200-500; the frog scar). Total
utterance durations are bounded >= 0.2 s so the 8-slice ear always has a real
speech span to slice.
"""
from __future__ import annotations

import json
import os

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))

import mouth34                                   # noqa: E402

F0 = 220.0
N = mouth34.N_SECTIONS                            # 34
A_LO, A_HI = mouth34.AREA_MIN, mouth34.AREA_MAX   # 0.15, 4.0


def _ah_areas():
    with open(os.path.join(_HERE, "postures", "ah-best.json")) as f:
        return np.asarray(json.load(f)["areas"], dtype=float)


class Arm:
    def __init__(self, name, unit, lo, hi, to_keyframes, guided=True):
        self.name = name
        self.unit = unit
        self.lo = np.asarray(lo, dtype=float)
        self.hi = np.asarray(hi, dtype=float)
        self.dim = self.lo.size
        self.to_keyframes = to_keyframes
        self.guided = guided

    def clip(self, x):
        return np.clip(x, self.lo, self.hi)

    def x0(self, seed):
        """Even seeds start from the FOUND vowel (stage-1-on-stage-0 stacking);
        odd seeds start random, so the ah-posture prior is tested, not assumed."""
        rng = np.random.default_rng(seed)
        x = rng.uniform(self.lo, self.hi)
        if seed % 2 == 0:
            ah = _ah_areas()
            x[:N] = np.clip(ah + rng.normal(0, 0.15, N), A_LO, A_HI)
            if self.name == "abba-free":
                for k in range(1, 4):
                    if k != 1:                    # keyframe 1 stays random (closure)
                        x[k * N:(k + 1) * N] = np.clip(
                            ah + rng.normal(0, 0.25, N), A_LO, A_HI)
        return x


def _kf_ba(x):
    v = x[:N]
    tc, tv, ca = x[N], x[N + 1], x[N + 2]
    return [(mouth34.closed_lips(v, 4, ca), tc), (v, tv)]


def _kf_abba(x):
    v = x[:N]
    t1, tc, t2, ca = x[N], x[N + 1], x[N + 2], x[N + 3]
    return [(v, t1), (mouth34.closed_lips(v, 4, ca), tc), (v, t2)]


def _kf_free(x):
    kfs = []
    for k in range(4):
        kfs.append((x[k * N:(k + 1) * N], x[4 * N + k]))
    return kfs


def get(name):
    if name in ("ba", "control-ba"):
        lo = [A_LO] * N + [0.03, 0.17, 0.01]
        hi = [A_HI] * N + [0.18, 0.50, 0.10]
        return Arm(name, "ba", lo, hi, _kf_ba, guided=not name.startswith("control"))
    if name in ("abba", "control-abba"):
        lo = [A_LO] * N + [0.10, 0.03, 0.10, 0.01]
        hi = [A_HI] * N + [0.40, 0.18, 0.40, 0.10]
        return Arm(name, "abba", lo, hi, _kf_abba,
                   guided=not name.startswith("control"))
    if name == "abba-free":
        lo = [A_LO] * (4 * N) + [0.05] * 4
        hi = [A_HI] * (4 * N) + [0.35] * 4
        return Arm(name, "abba", lo, hi, _kf_free)
    raise SystemExit("unknown arm %r" % name)


ALL = ("ba", "abba", "abba-free", "control-ba", "control-abba")
