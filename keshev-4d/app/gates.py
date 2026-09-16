"""gates.py — energy gate + segmenter.

⚕️ TRANSPLANT — BY IDDO'S ORDER, 2026-08-18 12:39 ("כן תן להם את האוזן שלך").
This organ was NOT written by the fleet. The segmenter chair defeated all
four workers — 8 rejections (gpt-oss ×2, glm ×2, qwen ×2, nemotron ×2; the
full record is KINGS-LOG.md). The logic below is keshev-fable's
app/segmenter.py (the solo builder's first-pass module, commit 0152db8),
adapted to this kingdom's law: feed() returns a tuple, not a dataclass.

The law it obeys (tests/test_gates.py, the king's canonical tests):
- a segment ENDS where speech ended — the hang window is not his voice;
- blips shorter than min_ms yield None;
- monologues force-close at max_ms (forced=True);
- silence never opens; a breath shorter than hang_ms never splits a sentence.
"""
from __future__ import annotations

# Measured on 854 live segments (speech median 0.0276, noise p90 0.0060);
# the gate sits in the gap between the populations.
GATE_RMS: float = 0.008


def energy_ok(rms: float, gate: float = GATE_RMS) -> bool:
    """Pre-GPU: don't wake the decoder for the room's hum."""
    return rms >= gate


class Segmenter:
    def __init__(self, min_ms: int = 280, max_ms: int = 15000,
                 hang_ms: int = 420, gate: float = GATE_RMS) -> None:
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.hang_ms = hang_ms
        self.gate = gate
        self._t = 0                  # running clock, fed frame by frame
        self._start: int | None = None
        self._last_speech_end = 0
        self._silence_run = 0

    @property
    def open(self) -> bool:
        return self._start is not None

    def feed(self, frame_ms: int, rms: float):
        """Advance one frame. Returns None or (start_ms, end_ms, forced)."""
        t0 = self._t
        self._t += frame_ms
        speech = energy_ok(rms, self.gate)

        if self._start is None:
            if speech:
                self._start = t0
                self._last_speech_end = self._t
                self._silence_run = 0
            return None

        if speech:
            self._last_speech_end = self._t
            self._silence_run = 0
        else:
            self._silence_run += frame_ms

        # force-close: the decoder's body limit outranks the hang wait
        if self._t - self._start >= self.max_ms:
            return self._close(forced=True)

        if self._silence_run >= self.hang_ms:
            return self._close(forced=False)
        return None

    def _close(self, *, forced: bool):
        start = self._start
        assert start is not None
        # the segment ends at the LAST SPEECH frame — hang excluded
        end = self._last_speech_end if not forced else self._t
        self._start = None
        self._silence_run = 0
        if end - start < self.min_ms:
            return None              # a blip is not speech
        return (start, end, forced)
