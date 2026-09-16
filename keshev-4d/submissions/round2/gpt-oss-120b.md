```python
# app/gates.py
"""
Energy gate and segment policy for KESHEV-4D.

Constants:
- GATE_RMS: 0.008  (gate sits between speech median 0.0276 and noise p90 0.0060)
- SPEECH_MEDIAN: 0.0276
- NOISE_P90: 0.0060
"""

from __future__ import annotations
from typing import Optional, Tuple

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
GATE_RMS: float = 0.008  # measured: speech median 0.0276, noise p90 0.0060
SPEECH_MEDIAN: float = 0.0276
NOISE_P90: float = 0.0060

# ----------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------
def energy_ok(rms: float, gate: float = GATE_RMS) -> bool:
    """
    Return True if the RMS energy is at or above the gate threshold.
    """
    return rms >= gate


# ----------------------------------------------------------------------
# Segmenter
# ----------------------------------------------------------------------
class Segmenter:
    """
    Detect speech segments based on RMS energy.

    Parameters
    ----------
    min_ms : int
        Minimum length of a segment to be considered speech.
    max_ms : int
        Maximum length of a segment; after this the segment is forced closed.
    hang_ms : int
        Length of silence (below gate) required to close an open segment.
    """

    def __init__(self, min_ms: int = 280, max_ms: int = 15000, hang_ms: int = 420):
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.hang_ms = hang_ms

        # Runtime state
        self._start_ms: Optional[int] = None          # start timestamp of current segment
        self._last_above_ms: Optional[int] = None     # last timestamp where rms >= gate

    def feed(self, frame_ms: int, rms: float, now_ms: int) -> Optional[Tuple[int, int, bool]]:
        """
        Process a frame of audio.

        Parameters
        ----------
        frame_ms : int
            Duration of the frame in milliseconds.
        rms : float
            RMS energy of the frame.
        now_ms : int
            Timestamp (in ms) at the *end* of the frame.

        Returns
        -------
        None or (start_ms, end_ms, forced)
            When a segment is closed, a tuple is returned.  If the closed
            segment is shorter than ``min_ms`` the method returns ``None``.
        """
        # No segment open yet
        if self._start_ms is None:
            if energy_ok(rms):
                # Open a new segment; the segment starts at the beginning of this frame
                self._start_ms = now_ms - frame_ms
                self._last_above_ms = now_ms
            return None

        # Segment is open – check for forced close first
        elapsed = now_ms - self._start_ms
        if elapsed >= self.max_ms:
            start = self._start_ms
            end = self._start_ms + self.max_ms
            forced = True
            self._reset()
            if (end - start) >= self.min_ms:
                return (start, end, forced)
            return None

        # Update last above‑gate timestamp if energy is sufficient
        if energy_ok(rms):
            self._last_above_ms = now_ms
            return None

        # Energy below gate – see if hang period elapsed
        if self._last_above_ms is not None:
            silence_duration = now_ms - self._last_above_ms
            if silence_duration >= self.hang_ms:
                # Close the segment
                start = self._start_ms
                # End is the moment the hang period completed
                end = self._last_above_ms + self.hang_ms
                forced = False
                self._reset()
                if (end - start) >= self.min_ms:
                    return (start, end, forced)
                return None

        # Still within hang period – keep segment open
        return None

    def _reset(self) -> None:
        """Reset internal state after a segment is closed."""
        self._start_ms = None
        self._last_above_ms = None
```

```python
# tests/test_gates.py
import unittest

from app.gates import Segmenter, energy_ok, GATE_RMS


class TestEnergyGate(unittest.TestCase):
    def test_energy_ok(self):
        self.assertTrue(energy_ok(GATE_RMS))
        self.assertTrue(energy_ok(GATE_RMS + 0.001))
        self.assertFalse(energy_ok(GATE_RMS - 0.001))


class TestSegmenter(unittest.TestCase):
    def setUp(self):
        self.seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)

    def _run_frames(self, frames):
        """
        Helper to feed a list of (frame_ms, rms) tuples.
        Returns the first non‑None result, if any.
        """
        now = 0
        result = None
        for frame_ms, rms in frames:
            now += frame_ms
            out = self.seg.feed(frame_ms, rms, now)
            if out is not None:
                result = out
        return result

    def test_blip_below_min(self):
        # A short above‑gate blip of 100 ms, then silence long enough to close
        frames = [
            (100, GATE_RMS + 0.01),   # speech blip
            (500, 0.0),               # silence > hang_ms
        ]
        result = self._run_frames(frames)
        self.assertIsNone(result, "Blip shorter than min_ms should be discarded")

    def test_speech_hang_closes(self):
        # Speech lasting 800 ms, then silence causing hang close
        frames = [
            (200, GATE_RMS + 0.02),   # speech
            (200, GATE_RMS + 0.02),   # speech
            (200, GATE_RMS + 0.02),   # speech
            (200, GATE_RMS + 0.02),   # speech (total 800 ms)
            (420, 0.0),               # exactly hang_ms silence
        ]
        result = self._run_frames(frames)
        self.assertIsNotNone(result, "Segment should close after hang")
        start, end, forced = result
        self.assertFalse(forced, "Should be a normal close, not forced")
        self.assertGreaterEqual(end - start, 800, "Segment length should include speech")
        self.assertLessEqual(end - start, 800 + 420, "End should be after hang period")

    def test_force_close_at_max(self):
        # Continuous speech for 20 s (20000 ms) – exceeds max_ms (15000 ms)
        frames = []
        # feed 15 frames of 1000 ms each (total 15000 ms)
        for _ in range(15):
            frames.append((1000, GATE_RMS + 0.03))
        # one more frame to push past max_ms
        frames.append((1000, GATE_RMS + 0.03))
        result = self._run_frames(frames)
        self.assertIsNotNone(result, "Forced segment should be emitted")
        start, end, forced = result
        self.assertTrue(forced, "Segment should be forced closed")
        self.assertEqual(end - start, 15000, "Forced segment length must equal max_ms")

    def test_never_opens_on_silence(self):
        frames = [
            (500, 0.0),
            (500, 0.0),
            (500, 0.0),
        ]
        result = self._run_frames(frames)
        self.assertIsNone(result, "Silence should never open a segment")


if __name__ == "__main__":
    unittest.main()
```