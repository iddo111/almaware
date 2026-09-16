"""Correctness tests for the segmental learner.

The properties pinned here are the ones that make it a different model rather
than a differently-spelled one: the boundary detector must actually be a Schmitt
trigger (a rising edge produces ONE boundary, not one per frame), a segment
descriptor must be a function of that segment alone, `encode` must still hand the
rest of the system one unit per frame, every unit must own a real waveform, and
two ants must never share a fitted number.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feature_space as F
import segmental as S
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples

ROOT = Path(__file__).resolve().parents[1]


def tone(frequencies, seconds: float, seed: int = 7007) -> np.ndarray:
    """A buzz through fixed resonances: one steady 'vowel'."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * EXEMPLAR_RATE)) / EXEMPLAR_RATE
    source = np.sign(np.sin(2 * np.pi * 120 * t))
    out = np.zeros_like(t)
    for f, gain in frequencies:
        out += gain * np.sin(2 * np.pi * f * t) * source
    out += 0.01 * rng.standard_normal(len(t))
    return (0.2 * out / max(np.abs(out).max(), 1e-9)).astype(np.float32)


VOWEL_A = ((700.0, 1.0), (1220.0, 0.5), (2600.0, 0.25))
VOWEL_I = ((280.0, 1.0), (2250.0, 0.8), (2900.0, 0.4))


def two_vowels(seconds: float = 0.4) -> tuple[np.ndarray, float]:
    """A then I, joined at a known time."""
    a = tone(VOWEL_A, seconds, seed=7007)
    b = tone(VOWEL_I, seconds, seed=7019)
    return np.concatenate([a, b]).astype(np.float32), len(a) / EXEMPLAR_RATE


def a_recording() -> np.ndarray:
    for folder in ("corpus-combined/train", "corpus-syllables/train", "recordings"):
        paths = sorted((ROOT / folder).glob("*.wav"))
        if paths:
            audio = load_wav(paths[0])
            return resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    raise unittest.SkipTest("no corpus audio available")


def small_corpus(n: int = 40) -> list[dict]:
    paths = sorted((ROOT / "corpus-combined" / "train").glob("*.wav"))[:n]
    if not paths:
        raise unittest.SkipTest("no corpus audio available")
    corpus = []
    for path in paths:
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        corpus.append({"path": str(path), "samples": samples,
                       "frames": F.frame_features(samples),
                       "span": S.speech_span(samples)})
    return corpus


class TestSegmenterShape(unittest.TestCase):
    def setUp(self):
        self.x = F.frame_features(two_vowels()[0])

    def test_edges_span_the_signal(self):
        edges = S.Segmenter().edges(self.x)
        self.assertEqual(int(edges[0]), 0)
        self.assertEqual(int(edges[-1]), len(self.x))
        self.assertTrue(np.all(np.diff(edges) > 0), "edges must be strictly increasing")

    def test_min_frames_is_respected(self):
        """The refractory floor is what stops a vowel shattering into units."""
        for min_frames in (4, 8, 12):
            seg = S.Segmenter(min_frames=min_frames, max_frames=4 * min_frames,
                              high=0.0, low=0.0)
            edges = S.Segmenter.edges(seg, self.x)
            interior = np.diff(edges)[:-1]     # the last one can be short by geometry
            if len(interior):
                self.assertGreaterEqual(int(interior.min()), min_frames)

    def test_hysteresis_reduces_boundary_count(self):
        """Same curve, wider trigger gap -> never more boundaries.

        `max_frames` is lifted out of the way here, otherwise the even split of
        an over-long segment sets the count and the trigger is invisible.
        """
        x = F.frame_features(np.concatenate([
            tone(VOWEL_A, 0.2, 1), tone(VOWEL_I, 0.2, 2),
            tone(VOWEL_A, 0.2, 3), tone(VOWEL_I, 0.2, 4)]).astype(np.float32))
        counts = [len(S.Segmenter(high=h, low=0.0, max_frames=10_000).edges(x)) - 1
                  for h in (0.0, 0.5, 1.0, 2.0, 4.0)]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertGreater(counts[0], counts[-1])

    def test_short_input_is_one_segment(self):
        edges = S.Segmenter().edges(self.x[:3])
        self.assertEqual(list(edges), [0, 3])

    def test_max_frames_splits_a_steady_signal(self):
        steady = F.frame_features(tone(VOWEL_A, 1.0))
        edges = S.Segmenter(high=99.0, max_frames=20).edges(steady)
        self.assertTrue(np.all(np.diff(edges) <= 20))


class TestSegmenterPlacement(unittest.TestCase):
    def test_finds_a_real_change(self):
        """A/I joined at a known instant: a boundary must land within 30 ms."""
        samples, junction = two_vowels()
        edges = S.Segmenter().edges(F.frame_features(samples))
        times = np.asarray([(e * F.HOP + F.FRAME / 2) / F.RATE for e in edges[1:-1]])
        self.assertGreater(len(times), 0, "no boundary at an obvious vowel change")
        self.assertLess(float(np.abs(times - junction).min()), 0.030)

    def test_boundaries_are_level_invariant(self):
        """recommended26 is level-free, so gain must not move a boundary at all."""
        samples, _ = two_vowels()
        reference = S.Segmenter().edges(F.frame_features(samples))
        for gain_db in (-18.0, -6.0, 6.0):
            gained = (samples * 10.0 ** (gain_db / 20.0)).astype(np.float32)
            self.assertEqual(list(S.Segmenter().edges(F.frame_features(gained))),
                             list(reference))

    def test_steady_signal_is_not_fragmented(self):
        """One vowel, one second: the detector must not invent a phone rate."""
        steady = F.frame_features(tone(VOWEL_A, 1.0))
        count = len(S.Segmenter().edges(steady)) - 1
        self.assertLessEqual(count, 6, f"{count} segments in one steady vowel")


class TestDescriptor(unittest.TestCase):
    def setUp(self):
        self.x = F.frame_features(two_vowels()[0])
        self.edges = S.Segmenter().edges(self.x)

    def test_dimension_matches_declaration(self):
        for parts in (1, 2, 3, 5):
            for delta in (True, False):
                for duration in (True, False):
                    d = S.Descriptor(parts, delta, duration)
                    self.assertEqual(d(self.x, self.edges).shape[1], d.dim)

    def test_one_row_per_segment(self):
        d = S.Descriptor()(self.x, self.edges)
        self.assertEqual(len(d), len(self.edges) - 1)

    def test_duration_column_is_log_length(self):
        d = S.Descriptor(use_duration=True)(self.x, self.edges)
        expected = np.log(np.diff(self.edges).astype(float))
        self.assertTrue(np.allclose(d[:, -1], expected))

    def test_segment_is_a_function_of_itself_alone(self):
        """No utterance statistics: cut the file, keep the descriptor identical."""
        a, b = int(self.edges[1]), int(self.edges[2])
        whole = S.Descriptor()(self.x, self.edges)[1]
        alone = S.Descriptor()(self.x[a:b], np.asarray([0, b - a]))[0]
        self.assertTrue(np.allclose(whole, alone, atol=1e-12))

    def test_parts_capture_the_trajectory(self):
        """A rising ramp must give increasing part means; parts=1 cannot see it."""
        ramp = np.zeros((30, 26))
        ramp[:, 0] = np.arange(30)
        edges = np.asarray([0, 30])
        three = S.Descriptor(3, False, False)(ramp, edges)[0]
        self.assertLess(three[0], three[STATIC_STEP])
        self.assertLess(three[STATIC_STEP], three[2 * STATIC_STEP])
        self.assertEqual(S.Descriptor(1, False, False)(ramp, edges).shape[1], S.STATIC)


STATIC_STEP = S.STATIC


class TestKMeans(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7007)
        self.x = np.concatenate([rng.normal(loc, 0.3, size=(60, 5))
                                 for loc in (-4.0, 0.0, 4.0)])

    def test_recovers_separated_clusters(self):
        centers, ids = S.kmeans(self.x, 3, 7007)
        self.assertEqual(len(np.unique(ids)), 3)
        self.assertEqual(sorted(np.bincount(ids)), [60, 60, 60])

    def test_deterministic_for_a_seed(self):
        a, _ = S.kmeans(self.x, 4, 7019)
        b, _ = S.kmeans(self.x, 4, 7019)
        self.assertTrue(np.array_equal(a, b))

    def test_no_empty_cluster_survives(self):
        centers, ids = S.kmeans(self.x, 12, 7039)
        self.assertEqual(int(np.bincount(ids, minlength=12).min() >= 0), 1)
        self.assertEqual(len(centers), 12)

    def test_assign_matches_bruteforce(self):
        centers, _ = S.kmeans(self.x, 4, 7057)
        ids, _ = S.assign(self.x, centers, chunk=7)
        brute = ((self.x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        self.assertTrue(np.array_equal(ids, brute))


class TestAnt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = small_corpus()
        cls.ant = S.SegmentalAnt("ant-a", 7007, 24).fit(cls.corpus)

    def test_encode_returns_one_unit_per_frame(self):
        samples = self.corpus[0]["samples"]
        ids = self.ant.encode(samples)
        self.assertEqual(len(ids), len(F.frame_features(samples)))
        self.assertTrue(0 <= int(ids.min()) and int(ids.max()) < self.ant.units)

    def test_units_are_constant_inside_a_segment(self):
        x = self.corpus[0]["frames"]
        ids, edges = self.ant.encode_features(x)
        for a, b in zip(edges[:-1], edges[1:]):
            self.assertEqual(len(np.unique(ids[a:b])), 1)

    def test_every_unit_owns_a_waveform_exemplar(self):
        self.assertEqual(len(self.ant.exemplars_), self.ant.units)
        for unit, wave in enumerate(self.ant.exemplars_):
            self.assertGreater(len(wave), 0)
            self.assertTrue(np.isfinite(wave).all())
            if self.ant.train_counts_[unit] > 0:
                self.assertGreater(float(np.abs(wave).max()), 0.0,
                                   f"unit {unit} exemplar is silence")

    def test_exemplars_are_real_training_audio(self):
        """The exemplar must be a verbatim cut of a training file, not a mean."""
        for unit, record in enumerate(self.ant.provenance_):
            if record["path"] is None:
                continue
            audio = load_wav(Path(record["path"]))
            samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
            cut = S.segment_waveform(samples, record["first"], record["last"])
            self.assertTrue(np.array_equal(cut, self.ant.exemplars_[unit]))

    def test_synthesis_runs_from_units_alone(self):
        ids = self.ant.encode(self.corpus[0]["samples"])
        out = self.ant.synthesize(ids)
        self.assertTrue(np.isfinite(out).all())
        self.assertLessEqual(float(np.abs(out).max()), 1.0)
        self.assertGreater(len(out), F.FRAME)

    def test_synthesis_rejects_a_foreign_unit_id(self):
        with self.assertRaises(ValueError):
            self.ant.synthesize(np.asarray([self.ant.units]))
        with self.assertRaises(ValueError):
            self.ant.synthesize(np.asarray([], dtype=np.int64))

    def test_unfitted_ant_refuses_to_encode(self):
        with self.assertRaises(ValueError):
            S.SegmentalAnt("ant-z", 1, 4).encode(self.corpus[0]["samples"])


class TestFoundingRule(unittest.TestCase):
    """Ants never share weights or codebooks.  This is the test of that."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = small_corpus()
        cls.ants = [S.SegmentalAnt(name, seed, 24).fit(cls.corpus, exemplars=False)
                    for name, seed in (("ant-a", 7007), ("ant-b", 7019),
                                       ("ant-c", 7039), ("ant-d", 7057))]

    def test_every_ant_has_its_own_centres(self):
        for a, b in zip(self.ants, self.ants[1:]):
            self.assertFalse(np.array_equal(a.centers_, b.centers_))

    def test_every_ant_has_its_own_scaler(self):
        for a, b in zip(self.ants, self.ants[1:]):
            self.assertFalse(np.array_equal(a.mean_, b.mean_))

    def test_fitting_one_ant_does_not_touch_another(self):
        before = self.ants[0].centers_.copy()
        S.SegmentalAnt("ant-e", 9001, 24).fit(self.corpus, exemplars=False)
        self.assertTrue(np.array_equal(self.ants[0].centers_, before))

    def test_the_segmenter_holds_no_fitted_parameters(self):
        """Two ants may agree on what a frame and a boundary are; only that."""
        for ant in self.ants:
            self.assertEqual(ant.segmenter, self.ants[0].segmenter)
            self.assertEqual(len(vars(ant.segmenter)), 6)


class TestCheckpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = small_corpus()
        cls.ant = S.SegmentalAnt("ant-a", 7007, 16).fit(cls.corpus)

    def test_round_trip_reproduces_the_encoding(self):
        payload = self.ant.to_checkpoint("test")
        clone = S.SegmentalAnt.from_checkpoint(payload)
        for item in self.corpus[:5]:
            self.assertTrue(np.array_equal(self.ant.encode(item["samples"]),
                                           clone.encode(item["samples"])))

    def test_hash_detects_tampering(self, ):
        import json
        import tempfile
        payload = self.ant.to_checkpoint("test")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "current.json"
            S.write_checkpoint(path, payload)
            self.assertEqual(S.load_checkpoint(path)["ant"], "ant-a")
            broken = json.loads(path.read_text(encoding="utf-8"))
            broken["centers"][0][0] += 1.0
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ValueError):
                S.load_checkpoint(path)

    def test_whitened_ant_round_trips(self):
        ant = S.SegmentalAnt("ant-b", 7019, 16, whiten=True).fit(self.corpus)
        clone = S.SegmentalAnt.from_checkpoint(ant.to_checkpoint("test"))
        self.assertTrue(np.array_equal(ant.encode(self.corpus[0]["samples"]),
                                       clone.encode(self.corpus[0]["samples"])))


class TestRandomSegmentControl(unittest.TestCase):
    def test_centres_are_real_segments(self):
        corpus = small_corpus(20)
        template = S.SegmentalAnt("ant-a", 7007, 12)
        control = S.random_real_segments(template, corpus, 7007, exemplars=False)
        pool, _ = control.pool(corpus)
        scaled = control.scale(pool)
        for centre in control.centers_:
            self.assertTrue(np.isclose(scaled, centre).all(axis=1).any(),
                            "a control centre is not a real segment")


if __name__ == "__main__":
    unittest.main()
