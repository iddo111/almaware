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
