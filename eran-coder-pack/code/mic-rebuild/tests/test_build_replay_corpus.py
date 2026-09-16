"""Replay-corpus import — the 2-5s utterances Gate 17 and Gate 18 replay.

PHASE2-DESIGN.md section 2 says the corpus WAVs "are collected/imported from
the [long-form] corpus in later milestones"; section 9 Gate 18 names the
Café-Claude recordings as the owner-positive source. This is that import.

Two things are worth pinning, and they are the two ways an imported corpus
can quietly lie:

  the CUT     the utterances must be cut by the PRODUCTION segmenter, not by
              a second energy heuristic written for the importer. If the
              importer cuts differently from the program, the corpus is not
              made of things KESHEV would ever have segmented, and every gate
              replayed through it measures a fiction.
  the BAND    only clips inside the design's 2-5s band are emitted, at
              exactly 16k mono s16 — the rate the injection seam demands
              (keshevctl sits BELOW the resampler).

No microphone, no speakers, no network: synthetic PCM only.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import build_replay_corpus as brc  # noqa: E402


def speechlike(seconds: float, rate: int = 48000, seed: int = 0) -> np.ndarray:
    """Loud broadband-ish burst: passes an energy gate and a VAD better than
    a pure tone does."""
    rng = np.random.default_rng(seed)
    n = int(seconds * rate)
    t = np.arange(n) / rate
    carrier = 0.5 * np.sin(2 * np.pi * 180.0 * t)
    carrier += 0.3 * np.sin(2 * np.pi * 420.0 * t)
    carrier += 0.15 * rng.standard_normal(n)
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 4.0 * t)
    return (carrier * envelope).astype(np.float32)


def write_source(path: Path, blocks: list[np.ndarray], rate: int = 48000,
                 channels: int = 2) -> None:
    mono = np.concatenate(blocks).astype(np.float32)
    pcm = np.clip(mono, -1.0, 1.0)
    i16 = (pcm * 32767.0).astype("<i2")
    if channels == 2:
        i16 = np.repeat(i16, 2)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(i16.tobytes())


class Downmix(unittest.TestCase):
    def test_48k_stereo_becomes_16k_mono_float32(self):
        src = speechlike(1.5)
        stereo = np.repeat(src, 2)
        out = brc.to_mono_16k(stereo, rate=48000, channels=2)
        self.assertEqual(out.dtype, np.float32)
        self.assertAlmostEqual(len(out) / 16000.0, 1.5, places=1)

    def test_a_rate_the_production_resampler_cannot_take_is_refused(self):
        with self.assertRaises(ValueError):
            brc.to_mono_16k(np.zeros(100, dtype=np.float32), rate=0, channels=1)


class Slicing(unittest.TestCase):
    def test_three_bursts_become_three_clips_in_the_band(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "src.WAV"
            silence = np.zeros(int(1.2 * 48000), dtype=np.float32)
            write_source(src, [silence,
                               speechlike(3.0, seed=1), silence,
                               speechlike(2.5, seed=2), silence,
                               speechlike(4.0, seed=3), silence])
            out = td / "out"
            made = brc.slice_utterances(src, out, prefix="t")
            self.assertEqual(len(made), 3, f"got {[p.name for p in made]}")
            for path in made:
                with wave.open(str(path), "rb") as w:
                    self.assertEqual(w.getframerate(), 16000)
                    self.assertEqual(w.getnchannels(), 1)
                    self.assertEqual(w.getsampwidth(), 2)
                    seconds = w.getnframes() / 16000.0
                self.assertGreaterEqual(seconds, brc.BAND_LO_S)
                self.assertLessEqual(seconds, brc.BAND_HI_S)

    def test_clips_outside_the_band_are_dropped_not_padded(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "src.WAV"
            silence = np.zeros(int(1.2 * 48000), dtype=np.float32)
            write_source(src, [silence,
                               speechlike(0.4, seed=4), silence,   # too short
                               speechlike(3.0, seed=5), silence])
            made = brc.slice_utterances(src, td / "out", prefix="t")
            self.assertEqual(len(made), 1)

    def test_silence_only_source_yields_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "src.WAV"
            write_source(src, [np.zeros(int(4.0 * 48000), dtype=np.float32)])
            self.assertEqual(brc.slice_utterances(src, td / "out", prefix="t"), [])


class UsesTheProductionSegmenter(unittest.TestCase):
    def test_the_importer_cuts_with_the_production_segmenter(self):
        """A second, importer-local energy heuristic would make the corpus a
        fiction. Identity, not a source-string match: the symbol the importer
        actually cuts with must BE the shipped class."""
        import client.resample
        import client.segmenter

        self.assertIs(brc.Segmenter, client.segmenter.Segmenter)
        self.assertIs(brc.StreamingResampler, client.resample.StreamingResampler)


if __name__ == "__main__":
    unittest.main()
