"""segmenter tests — the blip law, the hang-exclusion law, forced close."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.gates import GATE_RMS  # noqa: E402
from app.segmenter import Segmenter  # noqa: E402

SPEECH = GATE_RMS + 0.02
SILENCE = 0.001


def run(seg, frames):
    out = []
    for ms, rms in frames:
        r = seg.feed(ms, rms)
        if r is not None:
            out.append(r)
    return out


class SegmenterTests(unittest.TestCase):
    def test_silence_never_opens(self):
        seg = Segmenter()
        self.assertEqual(run(seg, [(100, SILENCE)] * 50), [])
        self.assertFalse(seg.open)

    def test_blip_below_min_yields_none(self):
        """100 ms of speech + long silence → the close is a None (tonight's
        4D lesson pinned on my own module too)."""
        seg = Segmenter(min_ms=280, hang_ms=420)
        out = run(seg, [(100, SPEECH)] + [(100, SILENCE)] * 6)
        self.assertEqual(out, [])
        self.assertFalse(seg.open)

    def test_hang_excluded_from_segment_end(self):
        """800 ms speech, then hang silence: the segment ends at 800, not at
        800+hang — the silence we waited through is not his voice."""
        seg = Segmenter(min_ms=280, hang_ms=420)
        out = run(seg, [(200, SPEECH)] * 4 + [(140, SILENCE)] * 3 + [(100, SILENCE)])
        self.assertEqual(len(out), 1)
        s = out[0]
        self.assertEqual((s.start_ms, s.end_ms, s.forced), (0, 800, False))

    def test_monologue_force_closes(self):
        seg = Segmenter(max_ms=15000)
        frames = [(500, SPEECH)] * 40          # 20 s of speech
        out = run(seg, frames)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].forced)
        self.assertLessEqual(out[0].dur_ms, 15000)

    def test_reopens_after_close(self):
        seg = Segmenter(min_ms=280, hang_ms=420)
        run(seg, [(200, SPEECH)] * 3 + [(500, SILENCE)])
        out = run(seg, [(200, SPEECH)] * 3 + [(500, SILENCE)])
        self.assertEqual(len(out), 1, "the segmenter must live again")

    def test_mid_speech_pause_shorter_than_hang_stays_open(self):
        """A 200 ms breath inside a sentence must not split the sentence."""
        seg = Segmenter(min_ms=280, hang_ms=420)
        out = run(seg, [(200, SPEECH)] * 2 + [(200, SILENCE)] +
                       [(200, SPEECH)] * 2 + [(500, SILENCE)])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].end_ms, 1000, "the pause is inside the segment")


if __name__ == "__main__":
    unittest.main()
