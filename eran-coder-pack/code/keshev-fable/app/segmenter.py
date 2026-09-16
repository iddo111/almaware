"""segmenter.py — where speech starts and ends. Pure, injectable time.

Laws inherited (INSIGHTS §1.6; the blip scar; tonight's 4D round-2 lesson —
gpt-oss counted the hang window into the segment):
- A segment ENDS where speech ended. The hang window (silence we wait
  through before closing) is NOT part of the segment.
- Blips shorter than min_ms are not speech; the close yields None.
- A monologue force-closes at max_ms (forced=True) so the decoder's 30 s
  body limit is never hit; the segmenter reopens immediately after.
- PURE module: no IO, no journal, no clock of its own — the caller feeds
  (frame_ms, rms) and journals SEG on a close.
"""
from __future__ import annotations

from dataclasses import dataclass

from .gates import GATE_RMS, energy_ok


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    forced: bool

    @property
    def dur_ms(self) -> int:
        return self.end_ms - self.start_ms


class Segmenter:
    def __init__(self, min_ms: int = 280, max_ms: int = 15000,
                 hang_ms: int = 420, gate: float = GATE_RMS,
                 sensitivity=None) -> None:
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.hang_ms = hang_ms
        self._gate = gate
        # if a live Sensitivity is wired in, the gate is READ FROM IT every frame,
        # so the slider / AUTO button move the threshold without a restart.
        self.sensitivity = sensitivity
        self._t = 0                  # running clock, fed frame by frame
        self._start: int | None = None
        self._last_speech_end = 0
        self._silence_run = 0

    @property
    def gate(self) -> float:
        return self.sensitivity.gate if self.sensitivity is not None else self._gate

    @gate.setter
    def gate(self, value: float) -> None:
        self._gate = value

    @property
    def open(self) -> bool:
        return self._start is not None

    def feed(self, frame_ms: int, rms: float) -> Segment | None:
        """Advance by one frame. Returns a closed Segment or None."""
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

    def _close(self, *, forced: bool) -> Segment | None:
        start = self._start
        assert start is not None
        # the segment ends at the LAST SPEECH frame — hang excluded
        end = self._last_speech_end if not forced else self._t
        self._start = None
        self._silence_run = 0
        if end - start < self.min_ms:
            return None              # a blip is not speech
        return Segment(start_ms=start, end_ms=end, forced=forced)
