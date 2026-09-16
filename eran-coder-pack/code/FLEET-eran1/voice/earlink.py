# -*- coding: utf-8 -*-
"""earlink.py -- the one place that opens ERAN's OWN ear and Iddo's real voice.

WHY THIS EXISTS AT ALL. The first learning event in this project's history, on
2026-08-23 20:29, was measured in eran2's 28-float `gist` -- a space in which
the organism's 62 prototypes DO NOT LIVE. The living brain on eran1 is 192-d
(EAR_SLICES 8 x N_BANDS 24) and every prototype it owns is a vector in that
space. So the 15.05 -> 7.66 result, real as it was, was about a different animal
than the child. Everything downstream of this file scores in the organism's own
frozen cochlea instead, via body/ears.py -- the same ear, the same code path,
the same pool(), that scored 79.55% on the sealed 22-class heldout.

WHY THE CORPUS IS WHERE IT IS. Iddo's real voice lives in ~/eran-voice-corpus/,
OUTSIDE ~/eran-brain/ and deliberately so:

  * food/train is what the LIVING organism eats every beat. Copying anything in
    there changes the child's diet, silently, while he is awake. Not without
    Iddo's word.
  * and it would not even work: measure.is_dev() computes int(digits) % 6 == 0,
    so talker t06 -- Iddo -- is DEV. His voice dropped into food/train would be
    eaten exactly zero times, with no error and no warning.

The 396 clips in food/train are 100% synthetic (six torch seeds of one TTS
model, not six people), and on 2026-08-23 that corpus was measured to transfer
to a real human mouth AT CHANCE: 6.1% against a 4.5% floor. Only human mouths
move ERAN. This module reads the 657 real clips of ONE human mouth -- Iddo's --
and nothing else.

THE HELDOUT IS NEVER OPENED HERE. Ears() is constructed with exam=False, which
makes body/ears.py refuse any path containing 'heldout' at read time. Nothing in
this file ever passes exam=True, and nothing that imports it may either.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(ROOT, "body"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import genome                                    # noqa: E402
from ears import Ears, read_wav, write_wav       # noqa: E402

CORPUS = os.path.expanduser(os.environ.get(
    "ERAN_HUMAN_CORPUS", "~/eran-voice-corpus/t06"))


def open_ear():
    """THE organism's ear -- genome defaults, no crown override, exam=False.

    Not a rebuilt or reconstructed ear: the same construction the life loop uses,
    so a distance printed here means the same thing a distance inside the child
    means.
    """
    ears = Ears()
    if ears.repr != "cochlea" or ears.dim != genome.EAR_SLICES * ears.n_bands:
        raise RuntimeError(
            "this is not the frozen cochlea: repr=%r dim=%d" % (ears.repr, ears.dim))
    return ears


def clips(unit, corpus=None, limit=None):
    """Every real recording of one unit, sorted. Raises if the unit is absent."""
    d = corpus or CORPUS
    if not os.path.isdir(d):
        raise FileNotFoundError("no human corpus at %s" % d)
    names = sorted(n for n in os.listdir(d)
                   if n.endswith(".wav") and n.split("_")[0] == unit)
    if not names:
        raise FileNotFoundError(
            "no clips for unit %r in %s (have: %s)"
            % (unit, d, ",".join(sorted({n.split("_")[0] for n in os.listdir(d)
                                         if n.endswith(".wav")}))))
    if limit:
        names = names[:limit]
    return [os.path.join(d, n) for n in names]


def percepts(ears, paths):
    """(n, dim) -- what the organism's own cochlea makes of each real recording."""
    return np.stack([ears.utterance(p) for p in paths])


def target_for(ears, unit, corpus=None, limit=None):
    """The centre of Iddo's cloud for one unit, in ERAN's ear. L2-normalised.

    Returns (target, stats) where stats carries the honest scale of the thing:
    how far a REAL clip of this unit sits from this centroid, and how wide the
    cloud is. A synthetic distance means nothing without those two numbers next
    to it -- 0.34 is only impressive because a real recording averages 0.38.
    """
    paths = clips(unit, corpus, limit)
    P = percepts(ears, paths)
    t = P.mean(axis=0)
    n = float(np.linalg.norm(t))
    t = t / n if n > 0 else t
    d_real = np.linalg.norm(P - t[None, :], axis=1)
    # within-class spread: mean pairwise distance between two real recordings
    G = P @ P.T
    d2 = np.maximum(0.0, np.diag(G)[:, None] + np.diag(G)[None, :] - 2 * G)
    iu = np.triu_indices(len(P), k=1)
    stats = {
        "unit": unit,
        "n_clips": len(paths),
        "real_to_centroid_mean": float(d_real.mean()),
        "real_to_centroid_min": float(d_real.min()),
        "real_to_centroid_max": float(d_real.max()),
        "within_class_spread": float(np.sqrt(d2[iu]).mean()) if len(P) > 1 else 0.0,
        "corpus": corpus or CORPUS,
    }
    return t.astype(np.float64), stats


def distance(vec, target):
    """L2 between two L2-normalised percepts. The whole objective, in one line."""
    return float(np.linalg.norm(np.asarray(vec, dtype=np.float64) - target))


def units(corpus=None):
    d = corpus or CORPUS
    return sorted({n.split("_")[0] for n in os.listdir(d) if n.endswith(".wav")})
