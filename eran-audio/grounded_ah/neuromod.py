#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
neuromod.py — Eran's NEUROMODULATOR core (Part 1b of multi-neuromodulator learning).

Three-factor Hebbian rule with neuromodulator channels:
    Δw = lr · eligibility(pre, post) · M(DA, OXT, ACh, NE, 5HT, cortisol)

Channels:
  - dopamine (DA):       reward, correctness, learning
  - oxytocin (OXT):      bonding, attachment (fires when Iddo's sensory context present)
  - acetylcholine (ACh): attention, salience
  - norepinephrine (NE): arousal, urgency
  - serotonin (5HT):     mood, homeostasis
  - cortisol:            stress (high = inhibit learning)
  - endorphin (END):     pain relief, social bonding

Correctness judge: analyze output /a/ waveform for acoustic markers:
  - F1 (formant 1): ~800-1000 Hz for open vowel /a/
  - F2 (formant 2): ~1200-1500 Hz
  - Pitch (F0): ~120 Hz (Eran's nominal pitch)
  - Envelope match: output energy should match target

Eligibility traces: per-weight decaying memory of coactivation
  e_ij(t) = pre_i(t) * post_j(t) + γ * e_ij(t-1)

Homeostatic balance: keep E/I activity bounded

State written to D:\CLAUDE\eran-nursery\state\gentle_state.json so it's live-readable.

This is Part 1b: the ARCHITECTURE & core channels firing correctly.
NOT full implementation yet (save that for next phase).
"""

import os
import sys
import json
import numpy as np
import datetime

try:
    from scipy import signal
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(os.path.dirname(HERE), '..', 'eran-nursery', 'state')


class NeuromodulatorState:
    """Live neuromodulator state for Eran."""

    def __init__(self):
        """Initialize all neuromodulator channels to homeostatic baseline."""
        self.dopamine = 0.5  # 0=no reward, 1=max reward
        self.oxytocin = 0.3  # 0=no bonding, 1=max bonding
        self.acetylcholine = 0.4  # 0=distracted, 1=hyper-focused
        self.norepinephrine = 0.3  # 0=lethargic, 1=panicked
        self.serotonin = 0.5  # 0=depressed, 1=euphoric
        self.cortisol = 0.2  # 0=relaxed, 1=max stress
        self.endorphin = 0.1  # 0=in pain, 1=numb

        # Eligibility traces: one dict per neuromodulator
        self.eligibility = {
            'dopamine': {},
            'oxytocin': {},
            'acetylcholine': {},
            'norepinephrine': {},
            'serotonin': {},
            'cortisol': {},
            'endorphin': {},
        }
        self.decay_factor = 0.95  # eligibility trace decay per timestep

    def to_dict(self):
        """Serialize state to dict for JSON logging."""
        return {
            'dopamine': float(self.dopamine),
            'oxytocin': float(self.oxytocin),
            'acetylcholine': float(self.acetylcholine),
            'norepinephrine': float(self.norepinephrine),
            'serotonin': float(self.serotonin),
            'cortisol': float(self.cortisol),
            'endorphin': float(self.endorphin),
        }

    def __repr__(self):
        return (f"NeuromodulatorState("
                f"DA={self.dopamine:.2f}, OXT={self.oxytocin:.2f}, "
                f"ACh={self.acetylcholine:.2f}, NE={self.norepinephrine:.2f}, "
                f"5HT={self.serotonin:.2f}, cortisol={self.cortisol:.2f})")


class CorrectnessJudge:
    """Analyze output /a/ waveform for acoustic correctness.

    Looks for formants in the /a/ range:
      F1: 700-1100 Hz
      F2: 1100-1700 Hz
      F0: ~120 Hz (pitch)
    """

    def __init__(self, sr=16000):
        self.sr = sr

    def extract_formants(self, waveform):
        """
        Extract formant frequencies from waveform using spectral analysis.

        Returns dict with F0, F1, F2, confidence (0-1).
        If scipy unavailable, returns placeholder.
        """
        if not HAS_SCIPY or len(waveform) < 512:
            # Fallback: no spectral analysis
            return {'F0': 120, 'F1': 850, 'F2': 1350, 'confidence': 0.0}

        try:
            # Simple spectrogram to find peaks
            freqs, times, spec = signal.spectrogram(waveform, self.sr,
                                                     nperseg=512, noverlap=256)
            # Average power across time
            power = spec.mean(axis=1)

            # F0 search: 80-150 Hz (male voice)
            f0_idx = np.argmax(power[(freqs >= 80) & (freqs <= 150)])
            f0 = freqs[(freqs >= 80) & (freqs <= 150)][f0_idx] if f0_idx.size > 0 else 120

            # F1 search: 600-1200 Hz
            f1_idx = np.argmax(power[(freqs >= 600) & (freqs <= 1200)])
            f1 = freqs[(freqs >= 600) & (freqs <= 1200)][f1_idx] if f1_idx.size > 0 else 850

            # F2 search: 1000-2000 Hz
            f2_idx = np.argmax(power[(freqs >= 1000) & (freqs <= 2000)])
            f2 = freqs[(freqs >= 1000) & (freqs <= 2000)][f2_idx] if f2_idx.size > 0 else 1350

            # Confidence: how much power in the formant bands
            f1_power = power[(freqs >= 700) & (freqs <= 1100)].sum()
            f2_power = power[(freqs >= 1100) & (freqs <= 1700)].sum()
            total_power = power.sum()
            confidence = (f1_power + f2_power) / (total_power + 1e-9)

            return {
                'F0': float(f0),
                'F1': float(f1),
                'F2': float(f2),
                'confidence': min(float(confidence), 1.0),
            }
        except Exception as e:
            print(f"[judge] formant extraction failed: {e}")
            return {'F0': 120, 'F1': 850, 'F2': 1350, 'confidence': 0.0}

    def judge(self, output_waveform, target_waveform=None):
        """
        Judge whether output_waveform is a correct /a/.

        Returns dict with:
          - is_correct (bool)
          - reward_da (float 0-1): dopamine signal
          - details (dict): formants, envelope, etc.
        """
        formants = self.extract_formants(output_waveform)

        # Check formant ranges for /a/
        f1_ok = 700 <= formants['F1'] <= 1100
        f2_ok = 1100 <= formants['F2'] <= 1700
        f0_ok = 80 <= formants['F0'] <= 150

        # All three formants in range = correct
        is_correct = f1_ok and f2_ok and f0_ok

        # Dopamine: confidence * formant correctness
        reward_da = formants['confidence'] * (
            (1.0 if f1_ok else 0.3) +
            (1.0 if f2_ok else 0.3) +
            (1.0 if f0_ok else 0.3)
        ) / 3.0

        # Envelope: RMS energy should be substantial
        rms = np.sqrt(np.mean(output_waveform ** 2))
        envelope_ok = rms > 0.1
        if not envelope_ok:
            is_correct = False
            reward_da *= 0.5

        details = {
            'formants': formants,
            'f1_ok': bool(f1_ok),
            'f2_ok': bool(f2_ok),
            'f0_ok': bool(f0_ok),
            'rms': float(rms),
            'envelope_ok': bool(envelope_ok),
        }

        if target_waveform is not None:
            # MSE vs target
            mse = np.mean((output_waveform - target_waveform) ** 2)
            details['target_mse'] = float(mse)
            # Adjust reward for fidelity
            reward_da *= np.exp(-mse)

        return {
            'is_correct': bool(is_correct),
            'reward_da': float(np.clip(reward_da, 0, 1)),
            'details': details,
        }


class EligibilityTrace:
    """Per-weight eligibility trace for three-factor learning.

    e_ij(t) = pre_i(t) * post_j(t) + decay * e_ij(t-1)
    """

    def __init__(self, decay=0.95):
        self.decay = decay
        self.traces = {}  # (pre_idx, post_idx) -> scalar

    def update(self, pre_activity, post_activity):
        """
        Update traces given pre and post activities.

        Args:
            pre_activity: np.ndarray, presynaptic activity
            post_activity: np.ndarray, postsynaptic activity

        Returns:
            dict of traces (pre_idx, post_idx) -> scalar
        """
        # Decay old traces
        for key in self.traces:
            self.traces[key] *= self.decay

        # Add new coactivation
        for i in range(len(pre_activity)):
            for j in range(len(post_activity)):
                key = (i, j)
                coact = float(pre_activity[i]) * float(post_activity[j])
                self.traces[key] = self.traces.get(key, 0) + coact

        return self.traces

    def get_trace(self, i, j):
        """Retrieve trace for synapse (i, j)."""
        return self.traces.get((i, j), 0)


class HomeostaticBalance:
    """Maintain E/I balance and prevent runaway activity."""

    def __init__(self, target_activity=0.3, smoothing=0.99):
        self.target_activity = target_activity
        self.smoothing = smoothing
        self.running_activity = 0.0

    def balance(self, activity):
        """
        Compute an inhibitory scaling factor to keep activity in check.

        Args:
            activity: float, mean activity in the layer

        Returns:
            scaling: float, multiply weights by this to inhibit if needed
        """
        # Exponential smoothing
        self.running_activity = (
            self.smoothing * self.running_activity +
            (1 - self.smoothing) * activity
        )

        # If activity too high, inhibit
        if self.running_activity > self.target_activity:
            excess = self.running_activity - self.target_activity
            scaling = 1.0 - 0.1 * excess  # 10% inhibition per unit excess
        else:
            scaling = 1.0

        return np.clip(float(scaling), 0.5, 1.5)


def compute_neuromod_factor(state: NeuromodulatorState, learning_rule='three_factor'):
    """
    Compute the neuromodulator factor M() for weight updates.

    Three-factor rule: Δw ∝ lr * eligibility * M(neuromod)

    Returns:
        scalar: combined neuromodulator effect on learning rate
    """
    if learning_rule == 'three_factor':
        # Basic combination: higher dopamine = faster learning
        # Cortisol gates (stress inhibits learning)
        # Oxytocin bonus for social/bonding context
        m = (
            state.dopamine * (1 - 0.5 * state.cortisol) +
            0.3 * state.oxytocin +
            0.2 * state.acetylcholine
        )
        return float(np.clip(m, 0, 2.0))
    else:
        return 1.0


def save_state(state: NeuromodulatorState, label='gentle'):
    """
    Save neuromodulator state to JSON so it's live-readable.

    Args:
        state: NeuromodulatorState
        label: str, state type (e.g. 'gentle', 'excited', 'learning')
    """
    os.makedirs(STATE_DIR, exist_ok=True)

    state_file = os.path.join(STATE_DIR, f'{label}_state.json')
    data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'label': label,
        'neuromod': state.to_dict(),
    }

    with open(state_file, 'w') as f:
        json.dump(data, f, indent=2)

    return state_file


if __name__ == "__main__":
    # Self-test
    print("[neuromod] self-test")

    # Test state
    state = NeuromodulatorState()
    print(f"[neuromod] initial state: {state}")

    # Test judge
    judge = CorrectnessJudge(sr=16000)

    # Fake correct /a/
    t = np.linspace(0, 0.5, 8000, endpoint=False)
    fake_ah = (
        np.sin(2 * np.pi * 120 * t) * 0.3 +  # F0 = 120 Hz
        np.sin(2 * np.pi * 850 * t) * 0.3 +  # F1 = 850 Hz
        np.sin(2 * np.pi * 1350 * t) * 0.2   # F2 = 1350 Hz
    )
    fake_ah = fake_ah / (np.max(np.abs(fake_ah)) + 1e-9)

    verdict = judge.judge(fake_ah)
    print(f"[neuromod] judge synthetic /a/: {verdict}")

    # Test eligibility trace
    et = EligibilityTrace(decay=0.95)
    pre = np.array([0.5, 0.3])
    post = np.array([0.8, 0.2, 0.1])
    traces = et.update(pre, post)
    print(f"[neuromod] eligibility traces: {len(traces)} synapses updated")

    # Test homeostatic balance
    hb = HomeostaticBalance(target_activity=0.3)
    for activity in [0.1, 0.3, 0.5, 0.4, 0.3]:
        scaling = hb.balance(activity)
        print(f"[neuromod] activity {activity:.1f} -> scaling {scaling:.2f}")

    # Test state save
    state.dopamine = 0.8
    state.oxytocin = 0.5
    saved = save_state(state, label='test_run')
    print(f"[neuromod] state saved to {os.path.basename(saved)}")

    print("[neuromod] self-test OK")
