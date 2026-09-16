"""Correctness tests for the replacement feature space.

The next phase's learners all read `feature_space.frame_features`, so the
properties that make it a fix rather than a change are pinned here: it must be
level-invariant, it must not need to see the rest of the file, and it must not
have silently altered the legacy vector it is being compared against.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feature_space as F
from acoustic_units import EXEMPLAR_RATE, features, load_wav, resample_samples

ROOT = Path(__file__).resolve().parents[1]


def a_recording() -> np.ndarray:
    for folder in ("corpus-combined/train", "corpus-syllables/train", "recordings"):
        paths = sorted((ROOT / folder).glob("*.wav"))
        if paths:
            audio = load_wav(paths[0])
            return resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    raise unittest.SkipTest("no corpus audio available")


def synthetic(seconds: float = 1.0, seed: int = 7007) -> np.ndarray:
    """A vowel-ish signal: a 120 Hz buzz through three resonances, plus noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * EXEMPLAR_RATE)) / EXEMPLAR_RATE
    source = np.sign(np.sin(2 * np.pi * 120 * t))
    out = np.zeros_like(t)
    for f, gain in ((700.0, 1.0), (1220.0, 0.5), (2600.0, 0.25)):
        out += gain * np.sin(2 * np.pi * f * t) * source
    out += 0.01 * rng.standard_normal(len(t))
    return (0.2 * out / np.abs(out).max()).astype(np.float32)


class TestLegacyIsUnchanged(unittest.TestCase):
    def test_matches_acoustic_units(self):
        """legacy14 must reproduce the shipped extractor, or no comparison holds."""
        for path in sorted((ROOT / "corpus-combined" / "train").glob("*.wav"))[:5]:
            audio = load_wav(path)
            expected, _ = features(audio)
            actual = F.extract("legacy14",
                               resample_samples(audio.samples, audio.rate,
                                                EXEMPLAR_RATE))
            self.assertEqual(expected.shape, actual.shape)
            self.assertLess(float(np.abs(expected - actual).max()), 1e-5)


class TestRecommended(unittest.TestCase):
    def setUp(self):
        self.x = synthetic()

    def test_shape_and_declared_dimension(self):
        out = F.frame_features(self.x)
        self.assertEqual(out.shape[1], 26)
        self.assertEqual(out.shape[1], F.RECOMMENDED.dim)
        expected_frames = 1 + (len(self.x) - F.FRAME) // F.HOP
        self.assertEqual(out.shape[0], expected_frames)
        self.assertTrue(np.isfinite(out).all())

    def test_level_invariance_is_exact(self):
        """A gain change must not move the vector.  This is the whole point."""
        reference = F.frame_features(self.x)
        for gain in (0.5, 0.25, 0.125, 2.0, 4.0):
            moved = float(np.abs(F.frame_features(self.x * gain) - reference).max())
            self.assertLess(moved, 1e-9, f"gain {gain} moved the vector by {moved}")

    def test_silence_does_not_explode(self):
        quiet = (1e-7 * synthetic(seed=11)).astype(np.float32)
        out = F.frame_features(quiet)
        self.assertTrue(np.isfinite(out).all())
        self.assertLess(float(np.abs(out).max()), 1e4)

    def test_needs_no_utterance_statistics(self):
        """Featurising a slice must equal the matching slice of the whole file.

        Ants never share weights; they must not need to share a file either.
        Only the six delta columns look outside their own frame, and only by
        the regression half-width.
        """
        whole = F.frame_features(self.x)
        start, count = 20, 30
        piece = F.frame_features(self.x[start * F.HOP:(start + count) * F.HOP + F.FRAME])
        inner = slice(5, count - 5)
        self.assertLess(
            float(np.abs(piece[inner] - whole[start:start + count][inner]).max()),
            1e-9)

    def test_deterministic(self):
        self.assertTrue(np.array_equal(F.frame_features(self.x),
                                       F.frame_features(self.x)))

    def test_canonical_alias_agrees(self):
        self.assertIs(F.SETS[F.CANONICAL], F.RECOMMENDED)
        self.assertTrue(np.array_equal(F.frame_features(self.x),
                                       F.SETS[F.CANONICAL](self.x)))


class TestBuildingBlocks(unittest.TestCase):
    def test_mel_filters_are_ordered_and_normalised(self):
        fb = F.mel_filterbank(26)
        self.assertEqual(fb.shape[0], 26)
        self.assertTrue((fb >= 0).all())
        np.testing.assert_allclose(fb.sum(axis=1), 1.0, atol=1e-9)
        peaks = fb.argmax(axis=1)
        self.assertTrue((np.diff(peaks) > 0).all(), "mel filters must ascend")

    def test_mel_scale_round_trips(self):
        hz = np.array([0.0, 100.0, 1000.0, 4000.0, 8000.0])
        np.testing.assert_allclose(F.mel_to_hz(F.hz_to_mel(hz)), hz, atol=1e-6)

    def test_dct_is_orthonormal(self):
        d = F.dct2_matrix(26, 26)
        np.testing.assert_allclose(d @ d.T, np.eye(26), atol=1e-9)

    def test_dct_decorrelates_a_shifted_spectrum(self):
        """Adding a constant to every log-mel band must move c0 alone."""
        base = np.random.default_rng(3).standard_normal((50, 26))
        d = F.dct2_matrix(26, 26)
        delta = (base + 4.0) @ d.T - base @ d.T
        self.assertGreater(abs(delta[:, 0]).min(), 1.0)
        self.assertLess(float(np.abs(delta[:, 1:]).max()), 1e-9)

    def test_deltas_are_zero_on_a_constant(self):
        x = np.repeat(np.arange(5.0)[None, :], 12, axis=0)
        np.testing.assert_allclose(F.deltas(x), 0.0, atol=1e-12)

    def test_deltas_recover_a_known_slope(self):
        slope = np.arange(40.0)[:, None] * np.array([[1.0, -2.0]])
        middle = F.deltas(slope, width=2)[5:-5]
        expected = np.repeat(np.array([[1.0, -2.0]]), len(middle), axis=0)
        np.testing.assert_allclose(middle, expected, atol=1e-9)

    def test_lpc_recovers_a_known_pole(self):
        """A signal from a two-pole filter must give back that filter."""
        rng = np.random.default_rng(5)
        a_true = np.array([1.0, -1.2, 0.81])
        x = np.zeros(4000)
        e = rng.standard_normal(4000)
        for n in range(2, len(x)):
            x[n] = e[n] - a_true[1] * x[n - 1] - a_true[2] * x[n - 2]
        a, _ = F.lpc(x[None, 1000:1400] * np.hanning(400), order=2)
        np.testing.assert_allclose(a[0], a_true, atol=0.08)

    def test_formants_find_a_planted_resonance(self):
        x = synthetic()
        f = F._formants6(x)
        self.assertEqual(f.shape[1], 6)
        median_f1 = float(np.median(f[:, 0]))
        self.assertTrue(0.4 < median_f1 < 1.0, f"F1 estimate was {median_f1} kHz")

    def test_voicing_separates_a_buzz_from_noise(self):
        rng = np.random.default_rng(9)
        noise = (0.2 * rng.standard_normal(16000)).astype(np.float32)
        self.assertGreater(float(np.median(F.voicing(synthetic())[:, 0])),
                           float(np.median(F.voicing(noise)[:, 0])) + 0.2)

    def test_every_registered_set_is_finite_and_declared_correctly(self):
        x = synthetic(0.5)
        mask = np.ones(1 + (len(x) - F.FRAME) // F.HOP, dtype=bool)
        for name, fs in F.SETS.items():
            out = fs(x, mask)
            self.assertEqual(out.shape[1], fs.dim, f"{name} declared {fs.dim}")
            self.assertTrue(np.isfinite(out).all(), f"{name} produced non-finite values")


if __name__ == "__main__":
    unittest.main()
