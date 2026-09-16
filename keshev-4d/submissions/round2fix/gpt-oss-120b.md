```python
# app/gates.py
from __future__ import annotations

GATE_RMS = 0.008  # RMS threshold for speech detection


def energy_ok(rms: float, gate: float = GATE_RMS) -> bool:
    """Return True if the RMS value is above the gate threshold."""
    return rms >= gate


class Segmenter:
    """
    Detect speech segments from a stream of RMS values.

    Parameters
    ----------
    min_ms : int
        Minimum length of a speech segment to be considered valid.
    max_ms : int
        Maximum length of a speech segment before a forced close.
    hang_ms : int
        Length of silence required to close a segment (hang time).
    """

    def __init__(self, *, min_ms: int = 280, max_ms: int = 15000, hang_ms: int = 420):
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.hang_ms = hang_ms

        self._reset_state()
        self._clock = 0  # internal time in ms when now_ms is omitted

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def feed(self, frame_ms: int, rms: float, now_ms: int | None = None) -> tuple[int, int, bool] | None:
        """
        Process a single frame.

        Returns
        -------
        (start_ms, end_ms, forced) or None
            * start_ms – when the segment opened
            * end_ms   – last speech frame (hang excluded)
            * forced   – True if the segment was closed by max_ms limit
        """
        # Resolve current timestamp
        if now_ms is None:
            now_ms = self._clock + frame_ms
        self._clock = now_ms

        # -----------------------------------------------------------------
        # Not currently open – look for opening condition
        # -----------------------------------------------------------------
        if not self._open:
            if energy_ok(rms):
                self._open = True
                self._start_ms = now_ms
                self._last_speech_ms = now_ms
            return None

        # -----------------------------------------------------------------
        # Segment is open – update last speech time if energy is OK
        # -----------------------------------------------------------------
        if energy_ok(rms):
            self._last_speech_ms = now_ms

        # -----------------------------------------------------------------
        # Forced close check (max_ms)
        # -----------------------------------------------------------------
        if now_ms - self._start_ms >= self.max_ms:
            segment = (self._start_ms, self._last_speech_ms, True)
            self._reset_state()
            return segment

        # -----------------------------------------------------------------
        # Hang silence check – close if silence exceeds hang_ms
        # -----------------------------------------------------------------
        if now_ms - self._last_speech_ms >= self.hang_ms:
            span = self._last_speech_ms - self._start_ms
            if span < self.min_ms:
                # Drop – call journal.event exactly once
                try:
                    import app.journal as journal
                except Exception:
                    # If the journal module is missing, we silently ignore
                    # (the spec guarantees its presence in production)
                    pass
                else:
                    journal.event(
                        "segment_dropped",
                        start=self._start_ms,
                        end=self._last_speech_ms,
                        span=span,
                    )
                self._reset_state()
                return None
            else:
                segment = (self._start_ms, self._last_speech_ms, False)
                self._reset_state()
                return segment

        # No state change – continue waiting
        return None

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _reset_state(self) -> None:
        """Reset all segment‑tracking attributes."""
        self._open = False
        self._start_ms = 0
        self._last_speech_ms = 0

    def _reset_state(self) -> None:
        """Reset all segment‑tracking attributes."""
        self._open = False
        self._start_ms = 0
        self._last_speech_ms = 0
```

```python
# tests/test_gates.py
import unittest
import sys
import types

# --------------------------------------------------------------------- #
# Stub out the journal module so we can verify calls without side effects
# --------------------------------------------------------------------- #
journal_stub = types.SimpleNamespace()
journal_stub.calls = []

def _event(*args, **kwargs):
    journal_stub.calls.append((args, kwargs))

journal_stub.event = _event
sys.modules["app.journal"] = journal_stub

# Import the module under test
from app.gates import Segmenter, energy_ok, GATE_RMS


class TestEnergyOk(unittest.TestCase):
    def test_below_gate(self):
        self.assertFalse(energy_ok(GATE_RMS - 0.001))

    def test_at_gate(self):
        self.assertTrue(energy_ok(GATE_RMS))

    def test_above_gate(self):
        self.assertTrue(energy_ok(GATE_RMS + 0.005))


class TestSegmenter(unittest.TestCase):
    def setUp(self):
        # Reset journal call log before each test
        journal_stub.calls.clear()
        self.seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)

    def _feed_sequence(self, rms_values, frame_ms=10, start_time=0):
        """Utility to feed a list of RMS values, advancing time."""
        t = start_time
        for rms in rms_values:
            self.seg.feed(frame_ms, rms, now_ms=t)
            t += frame_ms
        return t

    def test_blip_dropped_and_journal_called(self):
        # Create a short speech blip (200 ms) – shorter than min_ms (280 ms)
        # RMS above gate for 20 frames of 10 ms each = 200 ms
        rms_seq = [0.02] * 20 + [0.001] * 50  # follow with silence
        self._feed_sequence(rms_seq)
        # After enough silence, the segment should close and be dropped
        result = self.seg.feed(10, 0.001, now_ms=2000)  # force a hang check
        self.assertIsNone(result)
        self.assertEqual(len(journal_stub.calls), 1)
        args, kwargs = journal_stub.calls[0]
        self.assertEqual(args, ("segment_dropped",))
        self.assertIn("start", kwargs)
        self.assertIn("end", kwargs)
        self.assertIn("span", kwargs)
        self.assertLess(kwargs["span"], self.seg.min_ms)

    def test_speech_with_hang_excludes_hang_from_end(self):
        # Speech lasting 500 ms (>= min_ms) then silence > hang_ms
        rms_seq = [0.02] * 50 + [0.001] * 100
        self._feed_sequence(rms_seq)
        # Provide a timestamp far enough after last speech to trigger hang
        result = self.seg.feed(10, 0.001, now_ms=2000)
        self.assertIsNotNone(result)
        start, end, forced = result
        self.assertFalse(forced)
        self.assertEqual(start, 0)  # opened at first frame (t=0)
        self.assertEqual(end, 490)  # last speech frame at 49*10 = 490 ms
        self.assertEqual(len(journal_stub.calls), 0)

    def test_force_close_at_max_duration(self):
        # Continuous speech longer than max_ms (15 s)
        rms_seq = [0.02] * (self.seg.max_ms // 10 + 5)  # a few frames beyond max
        self._feed_sequence(rms_seq)
        # The forced close should happen exactly when max_ms is exceeded
        result = self.seg.feed(10, 0.02, now_ms=self.seg.max_ms + 10)
        self.assertIsNotNone(result)
        start, end, forced = result
        self.assertTrue(forced)
        self.assertEqual(start, 0)
        # end should be the last speech frame before the forced close
        self.assertEqual(end, self.seg.max_ms)
        self.assertEqual(len(journal_stub.calls), 0)

    def test_never_opens_on_silence(self):
        rms_seq = [0.001] * 200  # all below gate
        for i, rms in enumerate(rms_seq):
            result = self.seg.feed(10, rms, now_ms=i * 10)
            self.assertIsNone(result)
        self.assertEqual(len(journal_stub.calls), 0)


if __name__ == "__main__":
    unittest.main()
```