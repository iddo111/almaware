"""chemistry.py — three legible mood scalars gate all plasticity.

DA  = dopamine  : reward-prediction-error gain. The world went better than
                  expected -> potentiation amplified.
SHT = serotonin : patience. Praise and steady success raise it; pain drops it.
                  Sets sampling temperature and hunger tolerance. Persisted.
ACh = attention : WHO is talking. Fresh food 1.0, the father 1.5, own echo 0.2,
                  on stage 0.0 (performance never rewires, only tags).
"""
import math

import genome


class Chemistry:
    def __init__(self, state=None):
        self.da = genome.DA_BASE
        self.sht = genome.SEROTONIN_BASE
        self.ach = genome.ACH_FEED
        self._exp_surprise = 3.0          # EMA of surprise (bits), the expectation
        if state:
            self.__dict__.update(state)

    # --- persistence ---------------------------------------------------------
    def to_state(self):
        return {"da": self.da, "sht": self.sht, "ach": self.ach,
                "_exp_surprise": self._exp_surprise}

    # --- dynamics ------------------------------------------------------------
    def observe_surprise(self, bits):
        """Called on every digested token. RPE = expected - actual surprise:
        the world confirming better than expected is dopamine."""
        rpe = self._exp_surprise - bits
        a = 1.0 / genome.DA_TAU
        self._exp_surprise += a * (bits - self._exp_surprise)
        self.da += a * 20 * (max(0.0, rpe) - self.da)      # fast up, slow relax
        self.da = min(genome.DA_MAX, max(0.0, self.da))

    def valence(self, v):
        """Pleasure (+) / pain (-) shifts serotonin — the mood remembers."""
        self.sht = min(1.0, max(0.0, self.sht + 0.1 * v))

    def critic_valence(self, v):
        """DW-04: the bird's OWN verdict moves the mood, at a reduced gain.

        Serotonin used to be written only by parent.pay_taps(), and no human has
        ever tapped, so sht was 0.5 in 1,678 of 1,678 samples (stdev 0.0) and the
        sampling temperature was a constant 1.0 for the whole life. A judgement
        the bird makes about itself is weaker evidence than the father's thumb,
        but it is not nothing — CRITIC_VALENCE_GAIN says how much weaker.
        """
        self.valence(genome.CRITIC_VALENCE_GAIN * v)

    def decay_toward_baseline(self):
        self.da += 0.01 * (genome.DA_BASE - self.da)
        self.sht += 0.002 * (genome.SEROTONIN_BASE - self.sht)

    # --- the gate the brain multiplies by ------------------------------------
    def plasticity_gain(self):
        return self.ach * (1.0 + self.da)

    def temperature(self):
        """Low serotonin -> impulsive hot songs; high -> patient, cool."""
        return genome.T0 * (1.35 - 0.7 * self.sht)

    def mode(self, ach):
        self.ach = ach
