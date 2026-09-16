```python
# app/gates.py
import os
import sys
from typing import Optional, Tuple

# Ensure module path is available
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from journal import event

class Segmenter:
    def __init__(self, min_ms: int, max_ms: int, hang_ms: int, gate: float, SPEECH: float, SILENCE: float):
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.hang_ms = hang_ms
        self.gate = gate
        self.SPEECH = SPEECH
        self.SILENCE = SILENCE
        self.reset()

    def reset(self):
        self._start_ms: Optional[int] = None
        self._last_speech_end_ms: Optional[int] = None
        self._silence_run_ms: int = 0
        self._open: bool = False

    def feed(self, duration_ms: int, level: float) -> Optional[Tuple[int, int, bool]]:
        """
        Feed a frame of audio.
        Returns (start_ms, end_ms, forced) on segment closure, or None.
        forced=True means max_ms triggered the close.
        """
        if not self._open:
            # Only open on speech
            if level >= self.SPEECH:
                self._start_ms = 0 if self._start_ms is None else self._start_ms
                self._open = True
                self._last_speech_end_ms = duration_ms
                self._silence_run_ms = 0
                event("SEGMENT_OPEN", start_ms=0)
            return None

        # We are open
        t = self._start_ms + duration_ms  # current end time of this frame

        if level >= self.SPEECH:
            self._last_speech_end_ms = t
            self._silence_run_ms = 0
            return None

        # Silence frame
        self._silence_run_ms += duration_ms

        # Check forced close (max_ms)
        if t - self._start_ms >= self.max_ms:
            forced = True
            end_ms = t
            self._open = False
            self._start_ms = None
            self._last_speech_end_ms = None
            self._silence_run_ms = 0
            event("SEGMENT_CLOSE", reason="MAX_MS", start_ms=self._start_ms, end_ms=end_ms, forced=forced)
            return (self._start_ms, end_ms, forced)

        # Check hang_ms: silence_run >= hang_ms triggers immediate close
        if self._silence_run_ms >= self.hang_ms:
            end_ms = self._last_speech_end_ms
            # Enforce min_ms: if segment too short, drop it
            if end_ms - self._start_ms < self.min_ms:
                self._open = False
                self._start_ms = None
                self._last_speech_end_ms = None
                self._silence_run_ms = 0
                event("SEGMENT_DROP", reason="MIN_MS", start_ms=self._start_ms, end_ms=end_ms)
                return None
            forced = False
            self._open = False
            self._start_ms = None
            self._last_speech_end_ms = None
            self._silence_run_ms = 0
            event("SEGMENT_CLOSE", reason="HANG_MS", start_ms=self._start_ms, end_ms=end_ms, forced=forced)
            return (self._start_ms, end_ms, forced)

        return None


# For compatibility with journal
class Journal:
    def event(self, name: str, **kwargs):
        # In real app, this writes to log; here, just a stub
        pass

journal = Journal()
```


```python
# tests/test_gates.py
import unittest
import os
import sys

# Ensure module path is available
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gates import Segmenter, journal

class MockJournal:
    def __init__(self):
        self.events = []

    def event(self, name: str, **kwargs):
        self.events.append((name, kwargs))

class TestSegmenter(unittest.TestCase):
    def setUp(self):
        self.mock_journal = MockJournal()
        # Patch journal.event
        self.original_event = journal.event
        journal.event = self.mock_journal.event

    def tearDown(self):
        journal.event = self.original_event

    def test_hang_excluded_exact_tuple(self):
        # min_ms=280, max_ms=15000, hang_ms=420, gate=0.008, SPEECH=0.028, SILENCE=0.001
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420, gate=0.008, SPEECH=0.028, SILENCE=0.001)
        SPEECH = 0.028
        SILENCE = 0.001

        # feed(200,SPEECH) t:0->200 opens at 0, last_speech_end=200, silence=0
        result = seg.feed(200, SPEECH)
        self.assertIsNone(result)
        self.assertEqual(seg._start_ms, 0)
        self.assertEqual(seg._last_speech_end_ms, 200)
        self.assertEqual(seg._silence_run_ms, 0)
        self.assertTrue(seg._open)

        # feed(200,SPEECH) t->400  last_speech_end=400
        result = seg.feed(200, SPEECH)
        self.assertIsNone(result)
        self.assertEqual(seg._last_speech_end_ms, 400)

        # feed(200,SPEECH) t->600  last_speech_end=600
        result = seg.feed(200, SPEECH)
        self.assertIsNone(result)
        self.assertEqual(seg._last_speech_end_ms, 600)

        # feed(200,SPEECH) t->800  last_speech_end=800
        result = seg.feed(200, SPEECH)
        self.assertIsNone(result)
        self.assertEqual(seg._last_speech_end_ms, 800)

        # feed(140,SILENCE) t->940  silence=140  (140 < 420: stay open)
        result = seg.feed(140, SILENCE)
        self.assertIsNone(result)
        self.assertEqual(seg._silence_run_ms, 140)

        # feed(140,SILENCE) t->1080 silence=280  (280 < 420: stay open)
        result = seg.feed(140, SILENCE)
        self.assertIsNone(result)
        self.assertEqual(seg._silence_run_ms, 280)

        # feed(140,SILENCE) t->1220 silence=420  (420 >= 420: CLOSE NOW)
        # -> return (0, 800, False)   # end = last_speech_end, hang EXCLUDED
        result = seg.feed(140, SILENCE)
        self.assertIsNotNone(result)
        start, end, forced = result
        self.assertEqual(start, 0)
        self.assertEqual(end, 800)
        self.assertFalse(forced)

        # feed(100,SILENCE) -> None (closed, nothing open)
        result = seg.feed(100, SILENCE)
        self.assertIsNone(result)

        # Verify journal events
        self.assertEqual(len(self.mock_journal.events), 2)
        self.assertEqual(self.mock_journal.events[0][0], "SEGMENT_OPEN")
        self.assertEqual(self.mock_journal.events[1][0], "SEGMENT_CLOSE")
        self.assertEqual(self.mock_journal.events[1][1]["reason"], "HANG_MS")

    def test_breath(self):
        # 200ms silence then speech again -> one segment 0..1000
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420, gate=0.008, SPEECH=0.028, SILENCE=0.001)
        SPEECH = 0.028
        SILENCE = 0.001

        # 5 frames of speech: 200ms each -> 1000ms total
        for _ in range(5):
            seg.feed(200, SPEECH)

        # 200ms silence (still < hang_ms=420)
        seg.feed(200, SILENCE)
        self.assertTrue(seg._open)

        # More speech
        seg.feed(200, SPEECH)
        self.assertTrue(seg._open)

        # Now close with hang_ms silence
        seg.feed(420, SILENCE)
        result = seg.feed(1, SILENCE)  # 1 extra to exceed 420
        self.assertIsNotNone(result)
        start, end, forced = result
        self.assertEqual(start, 0)
        self.assertEqual(end, 1200)  # last_speech_end after 1000+200=1200
        self.assertFalse(forced)

    def test_min_ms_drop(self):
        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420, gate=0.008, SPEECH=0.028, SILENCE=0.001)
        SPEECH = 0.028
        SILENCE = 0.001

        # Only 200ms of speech
        seg.feed(200, SPEECH)
        # Then 420ms silence -> should close but drop due to min_ms
        seg.feed(420, SILENCE)
        result = seg.feed(1, SILENCE)
        self.assertIsNone(result)

        # Verify journal event
        close_events = [e for e in self.mock_journal.events if e[0] == "SEGMENT_DROP"]
        self.assertEqual(len(close_events), 1)
        self.assertEqual(close_events[0][1]["reason"], "MIN_MS")

    def test_max_ms_force_close(self):
        seg = Segmenter(min_ms=280, max_ms=1000, hang_ms=420, gate=0.008, SPEECH=0.028, SILENCE=0.001)
        SPEECH = 0.028

        # Feed 1000ms of speech (exactly max_ms)
        seg.feed(1000, SPEECH)
        result = seg.feed(1, SILENCE)
        self.assertIsNotNone(result)
        start, end, forced = result
        self.assertEqual(start, 0)
        self.assertEqual(end, 1001)
        self.assertTrue(forced)

        # Verify journal event
        close_events = [e for e in self.mock_journal.events if e[0] == "SEGMENT_CLOSE"]
        self.assertTrue(any(e[1]["reason"] == "MAX_MS" for e in close_events))

if __name__ == '__main__':
    unittest.main()
```