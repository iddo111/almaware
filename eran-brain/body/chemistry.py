"""chemistry.py — the neuromodulator VECTOR. Every plasticity knob lives here.

DA  = dopamine   : smoothed learning-progress delta (prediction error falling
                   faster than expected -> the world is teachable -> learn more)
ACh = attention  : who is talking; scales eta directly
NE  = norepinephrine : surprise spike -> temporary high plasticity (reset)
5HT = serotonin  : patience; persistence on hard units, damps unit-switching
OXT = oxytocin   : rises on parent taps, multiplies parent payout, decays in
                   isolation — the child learns most in the parent's presence

eta_eff = ETA0 * ach * (1 + da) * (1 + ne)   — the darwish-midi math, extended.
All state is one dict, journaled every beat to state/metrics.jsonl by the life
loop. Embodies: mood channels gate learning rate (ALMA-LIVING-NEURON engine 2).
"""
import genome


class Chemistry:
    def __init__(self, state=None):
        self.da = genome.DA0
        self.ach = genome.ACH0
        self.ne = genome.NE0
        self.sht = genome.SHT0
        self.oxt = genome.OXT0
        self._fast = 0.5          # fast EMA of surprise (1 - cosine sim)
        self._slow = 0.5          # slow EMA — the expectation
        self.frozen = False       # --ablate chemistry: everything at baseline
        if state:
            self.__dict__.update(state)

    # ----------------------------------------------------------- persistence
    def to_state(self):
        return {"da": self.da, "ach": self.ach, "ne": self.ne,
                "sht": self.sht, "oxt": self.oxt,
                "_fast": self._fast, "_slow": self._slow}

    def snapshot(self):
        return {k: round(float(v), 4) for k, v in
                [("da", self.da), ("ach", self.ach), ("ne", self.ne),
                 ("sht", self.sht), ("oxt", self.oxt)]}

    # -------------------------------------------------------------- dynamics
    def observe(self, surprise):
        """Called on every heard utterance with surprise = 1 - cosine sim."""
        if self.frozen:
            return
        self._fast += (surprise - self._fast) / genome.PROG_TAU_FAST
        self._slow += (surprise - self._slow) / genome.PROG_TAU_SLOW
        progress = self._slow - self._fast          # error falling = positive
        self.da = min(genome.DA_MAX, max(0.0, genome.DA_GAIN * progress))
        if surprise > self._slow + genome.NE_JUMP:  # a real jolt
            self.ne = min(genome.NE_MAX, self.ne + 1.0)

    def progress(self):
        """The learning-progress signal the drives eat from."""
        return max(0.0, self._slow - self._fast)

    def parent_touch(self):
        """A tap arrived — oxytocin rises; the child feels the parent."""
        if self.frozen:
            return
        self.oxt = min(genome.OXT_MAX, self.oxt + genome.OXT_TOUCH)

    def valence(self, v):
        """Pleasure (+) / pain (-) moves serotonin — the mood remembers."""
        if self.frozen:
            return
        self.sht = min(1.0, max(0.0, self.sht + 0.1 * v))

    def decay(self):
        """Every beat: moods relax toward baseline; oxytocin fades in isolation."""
        if self.frozen:
            return
        self.ne *= genome.NE_DECAY
        self.sht += genome.SHT_TAU * (genome.SHT0 - self.sht)
        self.oxt = genome.OXT0 + (self.oxt - genome.OXT0) * genome.OXT_DECAY

    # ------------------------------------------------- the gate on plasticity
    def plasticity(self):
        """The multiplier the brain applies to ETA0."""
        if self.frozen:
            return 1.0
        return self.ach * (1.0 + self.da) * (1.0 + self.ne)

    def patience(self):
        """5HT in [0,1]; the school reads it to damp unit-switching."""
        return self.sht
