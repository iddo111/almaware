```python
# app/gates.py
"""KESHEV-4D: Speech gate and segmenter — hardened against 4 real failures."""

from __future__ import annotations

import pathlib
import time
from typing import Optional, Tuple

# Hard-coded journal stub — no network, no audio, no registry
class Journal:
    def event(self, event_type: str, **kwargs) -> None:
        # Write to a deterministic log path — no side effects beyond disk
        log_path = pathlib.Path(r"D:\CLAUDE\keshev-4d\logs\gates.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        msg = f"[{timestamp}] {event_type} " + " ".join(f"{k}={v}" for k, v in kwargs.items())
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

journal = Journal()

# Threshold: noise p90 < GATE_RMS < speech median (from real-world calibration)
GATE_RMS: float = 0.012  # empirically validated between 0.0060 and 0.0276


def energy_ok(rms: float) -> bool:
    """Return True if RMS is above the speech/noise threshold."""
    return rms >= GATE_RMS


class Segmenter:
    """Segments speech into utterances, enforcing min/max/hang constraints.

    Rules:
    - Silence never opens a segment.
    - Blips below min_ms yield None (no segment).
    - Hang period after speech ends is allowed before closing.
    - Monologues force-close at max_ms.
    - Every drop/refusal calls journal.event exactly once.
    """

    def __init__(self, min_ms: int = 280, max_ms: int = 15000, hang_ms: int = 420):
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.hang_ms = hang_ms
        self._reset()

    def _reset(self) -> None:
        self._segment_start: Optional[int] = None  # ms since start of stream
        self._segment_end: int = 0
        self._hang_remaining: int = 0
        self._in_speech: bool = False
        self._total_ms: int = 0
        self._forced: bool = False

    def feed(self, ms: int, rms: float) -> Optional[Tuple[int, int, bool]]:
        """Feed a frame: duration (ms), RMS energy.

        Returns (start_ms, end_ms, forced) on segment close, else None.
        """
        # Advance global time
        self._total_ms += ms

        # Guard: silence never opens a segment
        if rms < GATE_RMS:
            # If currently in speech, start hang countdown
            if self._in_speech:
                self._hang_remaining = self.hang_ms
                self._in_speech = False
            # If hang is active, decrement it
            elif self._hang_remaining > 0:
                self._hang_remaining -= ms
                if self._hang_remaining < 0:
                    self._hang_remaining = 0
            # If hang expired and we have an active segment, close it
            if self._hang_remaining == 0 and self._segment_start is not None:
                # Finalize segment only if it meets min_ms
                duration = self._segment_end - self._segment_start
                if duration >= self.min_ms:
                    forced = self._forced
                    start = self._segment_start
                    end = self._segment_end
                    self._reset()
                    journal.event("segment_closed", start=start, end=end, forced=forced)
                    return (start, end, forced)
                else:
                    # Drop: too short — log and reset
                    journal.event("segment_dropped", reason="below_min_ms", duration=duration)
                    self._reset()
            return None

        # RMS >= GATE_RMS → speech detected
        if not self._in_speech:
            # Start new segment if none active
            if self._segment_start is None:
                self._segment_start = self._total_ms - ms
                self._segment_end = self._total_ms
                self._in_speech = True
                self._hang_remaining = 0
                self._forced = False
            else:
                # Resume existing segment
                self._segment_end = self._total_ms
                self._in_speech = True
                self._hang_remaining = 0
                self._forced = False
        else:
            # Continue existing segment
            self._segment_end = self._total_ms

        # Enforce max_ms: force-close if exceeded
        if self._segment_start is not None:
            duration = self._segment_end - self._segment_start
            if duration >= self.max_ms:
                start = self._segment_start
                end = self._segment_end
                self._forced = True
                self._reset()
                journal.event("segment_closed", start=start, end=end, forced=True)
                return (start, end, True)

        return None
```


```python
# tests/test_gates.py
"""KING'S CANONICAL TESTS — gates/segmenter. Workers may not edit this file.

The law: a segment ends where SPEECH ended (hang excluded); blips below
min_ms yield None; monologues force-close at max_ms; silence never opens.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.gates import GATE_RMS, Segmenter, energy_ok  # noqa: E402

SPEECH = GATE_RMS + 0.02
SILENCE = 0.001


def run(seg, frames):
    out = []
    for ms, rms in frames:
        r = seg.feed(ms, rms)
        if r is not None:
            out.append(r)
    return out


class EnergyTests(unittest.TestCase):
    def test_gate_between_the_populations(self):
        self.assertGreater(GATE_RMS, 0.0060)   # noise p90
        self.assertLess(GATE_RMS, 0.0276)      # speech median
        self.assertFalse(energy_ok(0.003))
        self.assertTrue(energy_ok(0.0276))


class SegmenterTests(unittest.TestCase):
    def test_silence_never_opens(self):
        seg = Segmenter()
        self.assertEqual(run(seg, [(100, SILENCE)] * 50), [])

    def test_blip_below_min_yields_none(self):
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)
        out = run(seg, [(100, SPEECH)] + [(100, SILENCE)] * 6)
        self.assertEqual(out, [])

    def test_hang_excluded_exact_tuple(self):
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)
        out = run(seg, [(200, SPEECH)] * 4 + [(140, SILENCE)] * 3 + [(100, SILENCE)])
        self.assertEqual(len(out), 1)
        start, end, forced = out[0]
        self.assertEqual((start, end, forced), (0, 800, False))

    def test_monologue_force_closes(self):
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)
        out = run(seg, [(500, SPEECH)] * 40)
        self.assertEqual(len(out), 1)
        start, end, forced = out[0]
        self.assertTrue(forced)
        self.assertLessEqual(end - start, 15000)

    def test_two_utterances_two_segments(self):
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)
        frames = ([(200, SPEECH)] * 3 + [(500, SILENCE)] +
                  [(200, SPEECH)] * 3 + [(500, SILENCE)])
        out = run(seg, frames)
        self.assertEqual(len(out), 2)

    def test_breath_inside_sentence_does_not_split(self):
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)
        out = run(seg, [(200, SPEECH)] * 2 + [(200, SILENCE)] +
                       [(200, SPEECH)] * 2 + [(500, SILENCE)])
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
```