# sensitivity.py — the mic's tunable ear.
#
# One shared number: `gate`, the RMS floor below which a frame is "quiet".
# Lower gate = MORE sensitive (fainter speech opens a segment). The slider in the
# window writes it; the segmenter reads it live, every frame. A plain float read/
# write is atomic in CPython, so no lock is needed across the audio/UI threads.
#
# AUTO watches the recent RMS floor (the room's own hum) and parks the gate just
# above it — so "sensitive" tracks the room instead of a number picked once.
from __future__ import annotations

import collections

# the manual slider's ends. 0.001 catches a whisper; 0.05 needs a raised voice.
GATE_MIN = 0.001
GATE_MAX = 0.050


class Sensitivity:
    def __init__(self, gate: float, history: int = 300) -> None:
        self.gate = float(gate)              # live, read by the segmenter each frame
        self.auto = False                    # AUTO on = the gate re-tracks the room
        self._rms = collections.deque(maxlen=history)   # ~ last few seconds of RMS

    def observe(self, rms: float) -> None:
        """Every audio frame's RMS, for the meter and for AUTO."""
        self._rms.append(rms)
        if self.auto and len(self._rms) >= 30:
            self.gate = self.recommend()

    def recommend(self) -> float:
        """The room's quiet floor × a margin — the gate AUTO would set right now."""
        if not self._rms:
            return self.gate
        s = sorted(self._rms)
        floor = s[len(s) // 5]               # 20th percentile = the room when silent
        return _clamp(max(GATE_MIN, floor * 1.8))

    def set(self, gate: float) -> None:
        self.auto = False                    # a hand on the slider turns AUTO off
        self.gate = _clamp(gate)

    def level(self) -> float:
        """The most recent RMS, 0..1 — what the colour bar shows."""
        return self._rms[-1] if self._rms else 0.0


def _clamp(g: float) -> float:
    return max(GATE_MIN, min(GATE_MAX, g))
