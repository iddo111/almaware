# -*- coding: utf-8 -*-
"""ears_v2.py -- Ear v2: the frozen cochlea + a STRUCTURAL GATE the search cannot trade away.

WHY v1 FAILED IDDO'S EAR (measured, 2026-08-25 08:36). The v1 objective made
structure worth 13.9% of class separation, so CMA-ES optimized the 192 timbre
dims toward the abba centroid and simply PAID the small contour penalty for
having no closure at all. The winning wav (abba-free-4, wdist 8.13, nearest
unit "abba" in v1) is 0.6 s of silence then ONE flat buzz -- Iddo's verdict:
"מה זה החרא הזה". A weighted dim can be traded; a GATE cannot.

WHAT v2 ADDS -- nothing learned, everything measurable:
  1. hump_profile(rms): trims to the live speech span (the same
     EAR_SPEECH_FRAC rule the cochlea uses), smooths the envelope, and counts
     ENERGY HUMPS separated by a real dip. Real "abba" = 2 humps with a deep
     dip (the /b/). Silence-then-buzz = 1 hump, no dip.
  2. structure_gate(unit, rms, calib): pass/fail against thresholds MEASURED
     from Iddo's own t06 clips (calibrate_v2.py writes ears-v2-calib.json).
     Nothing here is assumed: the required hump count and minimum dip depth
     per unit come from the real recordings, set to accept >=95% of them.
  3. score(unit, ...): v1's weighted distance, PLUS a fixed GATE_PENALTY when
     the gate fails. The penalty is larger than the whole useful score range,
     so no amount of timbre polish can buy back a missing closure.

The frozen 192 dims remain bit-identical to body/ears.py. This is a SEARCH
JUDGE, not an organ (genome EAR_FROZEN is Iddo's word alone). Sacred Audio:
hears samples, never plays them.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import genome                                     # noqa: E402
from ears_extended import ExtendedEars            # noqa: E402

CALIB_PATH = os.path.join(_HERE, "ears-v2-calib.json")
GATE_PENALTY = 50.0        # >> any real wdist (real clips live around 9-19)
SMOOTH = 5                 # envelope smoothing window (frames)


def live_span(rms):
    """The same speech-span rule the frozen cochlea pools over."""
    rms = np.asarray(rms, dtype=np.float64)
    if rms.size == 0:
        return rms
    idx = np.where(rms > float(np.max(rms)) * genome.EAR_SPEECH_FRAC)[0]
    if len(idx) < 2:
        return rms
    return rms[idx[0]:idx[-1] + 1]


def hump_profile(rms):
    """(n_peaks, deepest_dip_frac) via direct peak-valley prominence.

    Iteration 3 (2026-08-25). Run-above-threshold hump counting failed twice
    on real speech: a VOICED /b/ keeps energy flowing through the closure, so
    the envelope dips without crossing any fixed threshold and the two
    syllables merged into one run (34/100 real abba clips at 0.25×peak).
    So no thresholded runs at all: find local MAXIMA of the smoothed envelope
    (min separation, min height 0.15×peak), then the deepest valley between
    any ADJACENT pair. dip = 1 - valley/lower_peak. A flat buzz has no
    interior valley -> dip 0; any real mid-word closure -> dip > 0, however
    shallow. Monotone and unfakeable without actually articulating.
    """
    seg = live_span(rms)
    if seg.size < 2 * SMOOTH:
        return 0, 0.0
    k = np.ones(SMOOTH) / SMOOTH
    env = np.convolve(seg, k, mode="same")
    peak = float(env.max())
    if peak <= 0:
        return 0, 0.0
    min_sep = max(SMOOTH, len(env) // 20)
    floor = peak * 0.15
    # local maxima with separation and height
    cand = [i for i in range(1, len(env) - 1)
            if env[i] >= env[i - 1] and env[i] >= env[i + 1] and env[i] >= floor]
    maxima = []
    for i in sorted(cand, key=lambda j: -env[j]):
        if all(abs(i - m) >= min_sep for m in maxima):
            maxima.append(i)
    maxima.sort()
    if len(maxima) < 2:
        return len(maxima), 0.0
    best = 0.0
    for a, b in zip(maxima, maxima[1:]):
        valley = float(env[a:b + 1].min())
        lower = min(float(env[a]), float(env[b]))
        if lower > 0:
            best = max(best, 1.0 - valley / lower)
    return len(maxima), best


def load_calib(path=CALIB_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def structure_gate(unit, rms, calib):
    """True iff the utterance has the unit's measured energy structure."""
    c = calib.get(unit)
    if c is None:
        return True                      # unknown unit: gate is inert, not a wall
    n, dip = hump_profile(rms)
    if not (c["min_humps"] <= n <= c["max_humps"]):
        return False
    if c["min_dip"] > 0 and dip < c["min_dip"]:
        return False
    return True


class EarsV2(ExtendedEars):
    """ExtendedEars + the structural gate. Same 200-d percept vector."""

    def __init__(self, calib_path=CALIB_PATH):
        super().__init__()
        self.calib = load_calib(calib_path) if os.path.exists(calib_path) else {}

    def utterance_with_rms(self, samples):
        feats, rms = self.frozen._frames_from_samples(
            np.asarray(samples, dtype=np.float32))
        from ears_extended import energy_contour
        v = self.frozen.pool(feats, rms)
        return np.concatenate([v, energy_contour(rms)]), np.asarray(rms)

    def gated_penalty(self, unit, rms):
        """0.0 when the structure is right; GATE_PENALTY when it is not."""
        return 0.0 if structure_gate(unit, rms, self.calib) else GATE_PENALTY
