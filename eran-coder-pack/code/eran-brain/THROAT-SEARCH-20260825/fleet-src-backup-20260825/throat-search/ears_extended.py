# -*- coding: utf-8 -*-
"""ears_extended.py -- the frozen cochlea, UNTOUCHED, plus an 8-number energy contour.

THE WALL THIS CLIMBS (measured, results/EAR-STOP-PROBE-20260824T024544Z.json on
eran1): body/ears.py line 197 divides every frame's spectrum by its own sum, so
the frozen 192-d cochlea is level-free BY CONSTRUCTION and pure silence spliced
into a vowel barely moves the percept. A stop consonant IS a silence and a
burst, so hill climbing through the frozen ear alone cannot find the B in ABBA:
the objective is nearly flat in exactly the direction the search must move.

THE FIX, and what it is NOT. The frozen 192 dims are computed by the very same
body/ears.py code object, bit-for-bit -- nothing is retrained, nothing is
re-weighted, no frozen dim is touched. This module only APPENDS 8 numbers: a
per-slice log-RMS energy contour, sliced over the same speech span, by the same
8-way split, as the cochlea's own pooling. The contour is mean-removed, so
overall LOUDNESS still does not exist for this ear (the mouth normalises its
peak anyway) -- but the SHAPE of energy over time, the dip-and-burst that makes
a stop a stop, becomes audible.

THIS IS A SEARCH JUDGE, NOT AN ORGAN. The organism's anatomy is frozen and
changing it is Iddo's word alone (genome.py: EAR_FROZEN). Nothing here writes
into eran-brain/, nothing here is importable by the life loop, and the live
services on eran1/eran2 never load this file. It exists so an OFFLINE search
for a stop-consonant gesture has an objective that can see the gesture.

SACRED AUDIO LAW: hears samples, never plays them.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import genome                                    # noqa: E402
from ears import Ears, read_wav                  # noqa: E402

N_CONTOUR = 8          # one energy number per cochlea slice. 192 + 8 = 200.


def open_frozen():
    """THE organism's ear -- genome defaults, exam=False. Same construction the
    life loop uses, so the first 192 dims of an extended percept mean exactly
    what a percept inside the child means."""
    ears = Ears()
    if ears.repr != "cochlea" or ears.dim != genome.EAR_SLICES * ears.n_bands:
        raise RuntimeError("this is not the frozen cochlea: repr=%r dim=%d"
                           % (ears.repr, ears.dim))
    return ears


def energy_contour(rms):
    """8 log-RMS numbers over the SAME speech span the cochlea itself uses.

    Replicates the frozen pool()'s segmentation exactly: frames above
    EAR_SPEECH_FRAC of the peak RMS bound the speech span; the span is split
    8 ways; each slice contributes log(mean RMS). Mean-removed so absolute
    level -- which the mouth's 0.7 peak-normalisation makes meaningless --
    carries nothing, while the CONTOUR (the closure dip, the burst) survives.
    """
    rms = np.asarray(rms, dtype=np.float64)
    if rms.size == 0:
        return np.zeros(N_CONTOUR)
    live = rms > float(np.max(rms)) * genome.EAR_SPEECH_FRAC
    idx = np.where(live)[0]
    if len(idx) < genome.EAR_SLICES:
        idx = np.arange(len(rms))
    seg = rms[idx[0]:idx[-1] + 1]
    if seg.size < N_CONTOUR:                      # degenerate blip: repeat-pad
        seg = np.concatenate([seg, np.full(N_CONTOUR - seg.size, seg[-1])])
    e = np.array([np.log(float(np.mean(p)) + genome.EAR_EPS)
                  for p in np.array_split(seg, N_CONTOUR)])
    return e - e.mean()


class ExtendedEars:
    """192 frozen dims (bit-identical to body/ears.py) + 8 contour dims = 200."""

    def __init__(self):
        self.frozen = open_frozen()
        self.dim = self.frozen.dim + N_CONTOUR    # 200

    def utterance_from_samples(self, samples):
        feats, rms = self.frozen._frames_from_samples(
            np.asarray(samples, dtype=np.float32))
        v = self.frozen.pool(feats, rms)          # THE frozen 192, untouched
        return np.concatenate([v, energy_contour(rms)])

    def utterance(self, path):
        return self.utterance_from_samples(read_wav(path))

    def split(self, vec):
        """(frozen_192, contour_8) view of one extended percept."""
        return vec[:self.frozen.dim], vec[self.frozen.dim:]
