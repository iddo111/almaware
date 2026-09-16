"""alma-mic / vad.py — voice activity detection.

ALMAWARE-pure: our OWN VAD, zero library. Energy-based with an adaptive noise floor,
a warmup (learn the room before deciding), an absolute floor, and hangover smoothing.
Single responsibility: stream of mono float32 frames -> complete speech segments.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

SAMPLE_RATE = 16_000


@dataclass
class VADConfig:
    onset_factor: float = 3.0    # speech when RMS > noise_floor * this
    offset_factor: float = 1.8   # back to silence below noise_floor * this
    abs_min_rms: float = 0.003   # AND speech must clear this absolute floor (kills false onsets)
    hangover_ms: int = 300       # stay "speech" this long after dipping
    min_speech_ms: int = 250     # discard blips shorter than this
    warmup_ms: int = 150         # learn the room's noise floor before allowing onset
    floor_adapt: float = 0.1     # EMA rate for the noise floor (while silent)


class VAD:
    """Streaming VAD. Feed frames; get a finished speech segment when one ends."""

    def __init__(self, cfg: VADConfig | None = None, block_ms: int = 30):
        self.cfg = cfg or VADConfig()
        self.block_ms = block_ms
        self._floor = 0.0
        self._seeded = False
        self._warmup_left = self.cfg.warmup_ms
        self._in_speech = False
        self._hang = 0
        self._buf: list[np.ndarray] = []
        self._speech_ms = 0

    @property
    def in_speech(self) -> bool:
        """True while a speech segment is in progress (for live UI state)."""
        return self._in_speech

    @staticmethod
    def _rms(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame * frame)) + 1e-12)

    def push(self, frame: np.ndarray):
        """Feed one frame. Returns a completed speech segment (ndarray) when one ends, else None."""
        rms = self._rms(frame)
        cfg = self.cfg
        if not self._seeded:
            self._floor = rms          # start the floor at the real ambient level
            self._seeded = True

        if not self._in_speech:
            self._floor = (1 - cfg.floor_adapt) * self._floor + cfg.floor_adapt * rms
            if self._warmup_left > 0:   # learn the room first, no onset yet
                self._warmup_left -= self.block_ms
                return None
            if rms > self._floor * cfg.onset_factor and rms > cfg.abs_min_rms:
                self._in_speech = True
                self._buf = [frame.copy()]
                self._speech_ms = self.block_ms
                self._hang = cfg.hangover_ms
            return None

        # in speech
        self._buf.append(frame.copy())
        self._speech_ms += self.block_ms
        if rms > self._floor * cfg.offset_factor and rms > cfg.abs_min_rms * 0.5:
            self._hang = cfg.hangover_ms
        else:
            self._hang -= self.block_ms
            if self._hang <= 0:
                seg = np.concatenate(self._buf)
                self._in_speech = False
                self._buf = []
                return seg if self._speech_ms >= cfg.min_speech_ms else None
        return None
