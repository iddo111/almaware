# -*- coding: utf-8 -*-
"""The mini-holobrain — Hebbian binding between sound-units and sight-units.

Pure co-occurrence counting with PMI normalisation. No gradients, no torch,
no labels: the matrix only ever sees which sound-units fired while which
sight-unit was visible in the same world moment. Everything it "knows" about
letters it learned the way a cheider child does — the picture kept hanging
there while the sound kept happening.

Fits the farm's honesty rules: the binding can be shuffled, retrained on
random pairings, or fed marginals only, and the exam must collapse to chance
each time — those controls live in run_cheider_exam.py.
"""
from __future__ import annotations

import numpy as np


class Binding:
    """C[s, v] = how often sound-unit s fired while sight-unit v was visible."""

    def __init__(self, n_sound: int, n_sight: int) -> None:
        self.C = np.zeros((n_sound, n_sight), dtype=np.float64)
        self.sound_marginal = np.zeros(n_sound, dtype=np.float64)
        self.sight_marginal = np.zeros(n_sight, dtype=np.float64)
        self.moments = 0
        self.co_moments = 0

    def observe_both(self, sound_units: np.ndarray, sight_unit: int) -> None:
        s = np.unique(np.asarray(sound_units, dtype=np.int64))
        self.C[s, sight_unit] += 1.0
        self.sound_marginal[s] += 1.0
        self.sight_marginal[sight_unit] += 1.0
        self.moments += 1
        self.co_moments += 1

    def observe_sound(self, sound_units: np.ndarray) -> None:
        s = np.unique(np.asarray(sound_units, dtype=np.int64))
        self.sound_marginal[s] += 1.0
        self.moments += 1

    def observe_sight(self, sight_unit: int) -> None:
        self.sight_marginal[sight_unit] += 1.0
        self.moments += 1

    def pmi(self, alpha: float = 0.5) -> np.ndarray:
        """Smoothed pointwise mutual information, (n_sound, n_sight)."""
        n_s, n_v = self.C.shape
        total = self.C.sum() + alpha * n_s * n_v
        joint = (self.C + alpha) / total
        p_s = (self.sound_marginal + alpha * n_v)
        p_s = p_s / p_s.sum()
        p_v = (self.sight_marginal + alpha * n_s)
        p_v = p_v / p_v.sum()
        return np.log(joint / (p_s[:, None] * p_v[None, :]))


def association(pmi: np.ndarray, sound_units: np.ndarray,
                sight_units: np.ndarray) -> float:
    """Mean PMI between a sound-unit set and a sight-unit set."""
    s = np.unique(np.asarray(sound_units, dtype=np.int64))
    v = np.unique(np.asarray(sight_units, dtype=np.int64))
    return float(pmi[np.ix_(s, v)].mean())
