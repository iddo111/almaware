"""Play/Pause and the level bar — Iddo, 2026-08-15.

  "Keshev should have proper play pause button."
  "and also should have the soundbar"

PAUSE IS A TYPING PAUSE, NOT A CAPTURE PAUSE. The mic stays open, segments
keep spooling, decodes keep happening — only the last step, putting text into
his window, is withheld. Closing the device on every button tap would re-enter
the open/silent-reopen hazard that cost 127 silent-reopens and forty minutes of
his dictation that same day. Paused speech is PARKED, never dropped (scar 35).

THE LEVEL is the RMS the silence watch already computes each callback, so a
moving bar and a silent-reopen can never tell him two different stories. None
and 0.0 are different answers and stay different all the way to the pixels:
None is "no stream", 0.0 is "a stream delivering digital silence" — which is
scar 25 itself, the failure that had the mic open and deaf for hours.
"""
from __future__ import annotations

import unittest

import numpy as np

from client.capture import SilentOpenWatch


class TestLevelIsPublished(unittest.TestCase):

    def test_none_before_any_audio(self):
        """Never 0.0 before the first callback — that would draw a confident
        'silent' when nothing has been heard yet."""
        w = SilentOpenWatch(rate=16000)
        self.assertIsNone(w.last_level)

    def test_speech_level_is_published(self):
        w = SilentOpenWatch(rate=16000)
        loud = (np.random.default_rng(7).normal(0, 0.05, 1600)
                .astype(np.float32))
        w.feed(loud)
        self.assertIsNotNone(w.last_level)
        self.assertGreater(w.last_level, 0.01)

    def test_digital_silence_publishes_zero_not_none(self):
        """A stream delivering dead air must read 0.0, distinguishable from
        'no stream at all'."""
        w = SilentOpenWatch(rate=16000)
        w.feed(np.zeros(1600, dtype=np.float32))
        self.assertEqual(w.last_level, 0.0)
        self.assertIsNotNone(w.last_level)

    def test_level_tracks_the_latest_chunk(self):
        w = SilentOpenWatch(rate=16000)
        w.feed(np.full(1600, 0.2, dtype=np.float32))
        loud = w.last_level
        w.feed(np.zeros(1600, dtype=np.float32))
        self.assertLess(w.last_level, loud)

    def test_empty_chunk_does_not_lie(self):
        """An empty callback must not overwrite the last real reading with 0."""
        w = SilentOpenWatch(rate=16000)
        w.feed(np.full(1600, 0.2, dtype=np.float32))
        before = w.last_level
        w.feed(np.array([], dtype=np.float32))
        self.assertEqual(w.last_level, before)

    def test_publishing_did_not_break_the_silence_trigger(self):
        """The whole point of this class still works: a full window of
        silence still asks for a re-resolve."""
        w = SilentOpenWatch(rate=16000, window_s=0.2)
        fired = any(w.feed(np.zeros(1600, dtype=np.float32)) for _ in range(4))
        self.assertTrue(fired)


class TestPauseIsTypingOnly(unittest.TestCase):
    """Uses the real assembly, so a pause that is not wired fails here."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from tests.test_app import AppHarness
        self.tmp = Path(tempfile.mkdtemp())
        self.h = AppHarness(self.tmp)
        self.addCleanup(self.h.app.shutdown)
        self.app = self.h.app

    def test_starts_unpaused(self):
        self.assertFalse(self.app.is_paused())

    def test_pause_then_resume(self):
        self.app.pause()
        self.assertTrue(self.app.is_paused())
        self.app.resume()
        self.assertFalse(self.app.is_paused())

    def test_pause_is_idempotent(self):
        self.app.pause()
        self.app.pause()
        self.assertTrue(self.app.is_paused())

    def test_paused_types_nothing(self):
        self.app.pause()
        self.assertFalse(self.app.router.type_fn("שלום"))
        self.assertEqual(self.h.typed(), [])

    def test_paused_text_is_PARKED_never_dropped(self):
        """scar 35: divert, never drop. His words survive a pause."""
        self.app.pause()
        self.app.router.type_fn("this must not vanish")
        parked = (self.tmp / "state" / "parked.txt").read_text(encoding="utf-8")
        self.assertIn("this must not vanish", parked)
        self.assertIn("paused", parked)

    def test_resume_types_again(self):
        self.app.pause()
        self.app.resume()
        self.assertTrue(self.app.router.type_fn("back on"))
        self.assertIn("back on", self.h.typed())

    def test_pause_does_not_close_the_device(self):
        """A capture pause would re-enter the open/silent-reopen hazard on
        every button tap. The stream must be untouched."""
        before = self.app.capture, self.app.stream, self.app.device
        self.app.pause()
        self.assertEqual((self.app.capture, self.app.stream, self.app.device),
                         before)

    def test_tray_pause_is_wired_not_a_stub(self):
        """The tray said 'pause is not wired yet' until today. Prove it now
        performs the real action rather than announcing a shrug."""
        self.app.tray.update()
        self.app.tray.toggle_pause()
        self.assertTrue(self.app.is_paused())
        self.app.tray.update()
        self.app.tray.toggle_pause()
        self.assertFalse(self.app.is_paused())


class TestInputLevelSeam(unittest.TestCase):

    def setUp(self):
        import tempfile
        from pathlib import Path
        from tests.test_app import AppHarness
        self.tmp = Path(tempfile.mkdtemp())
        self.h = AppHarness(self.tmp)
        self.addCleanup(self.h.app.shutdown)

    def test_no_capture_reads_none_not_zero(self):
        self.h.app.capture = None
        self.assertIsNone(self.h.app.input_level())


if __name__ == "__main__":
    unittest.main()
