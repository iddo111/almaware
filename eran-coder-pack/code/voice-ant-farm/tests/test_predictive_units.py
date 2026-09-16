"""Correctness tests for the predictive-coding learner.

The claims this file pins are the ones the result rests on:

  * the contrastive objective is computed correctly (checked against a slow,
    obviously-right reference), and it is *not* gameable by unpredictable
    targets -- shuffling the futures must destroy the score;
  * `encode` is a pure function of one frame, so the unit sequence needs no
    future and no rest-of-file statistics, and it is level-invariant;
  * a (context, future) pair never straddles a file boundary;
  * four ants with four seeds share no fitted quantity whatsoever;
  * beta = 0 collapses exactly onto k-means, so the k-means control in the
    report is the same code and not a different implementation;
  * a checkpoint round-trips and a tampered one is rejected.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feature_space as F
import predictive_units as P
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples

ROOT = Path(__file__).resolve().parents[1]


def a_recording() -> np.ndarray:
    for folder in ("corpus-combined/train", "corpus-syllables/train", "recordings"):
        paths = sorted((ROOT / folder).glob("*.wav"))
        if paths:
            audio = load_wav(paths[0])
            return resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    raise unittest.SkipTest("no corpus audio available")


def toy_corpus(files: int = 6, frames: int = 400, dim: int = 8,
               seed: int = 1, feature_set: str = "toy") -> P.FrameCorpus:
    """A corpus with real temporal structure: each file is a smooth random walk
    through a handful of attractors, so the future is genuinely predictable."""
    rng = np.random.default_rng(seed)
    blocks, starts = [], [0]
    anchors = rng.normal(size=(5, dim)) * 3.0
    for _ in range(files):
        which = rng.integers(0, len(anchors), size=frames // 20)
        path = np.repeat(anchors[which], 20, axis=0)
        smooth = np.cumsum(rng.normal(scale=0.15, size=(len(path), dim)), axis=0)
        block = path + smooth
        blocks.append(block)
        starts.append(starts[-1] + len(block))
    return P.FrameCorpus(np.concatenate(blocks), np.asarray(starts), [], 1.0,
                         feature_set)


class PairIndex(unittest.TestCase):
    def test_pairs_never_cross_a_file_boundary(self):
        corpus = toy_corpus(files=4, frames=100)
        for delta in (1, 3, 8):
            idx = corpus.pair_index(delta)
            file_of = np.searchsorted(corpus.starts, idx, side="right") - 1
            file_of_target = (np.searchsorted(corpus.starts, idx + delta,
                                              side="right") - 1)
            self.assertTrue(np.array_equal(file_of, file_of_target))
            self.assertTrue((idx + delta < corpus.n).all())

    def test_every_in_file_pair_is_kept(self):
        corpus = toy_corpus(files=3, frames=50)
        delta = 4
        expected = sum(max(0, (b - a) - delta)
                       for a, b in zip(corpus.starts[:-1], corpus.starts[1:]))
        self.assertEqual(len(corpus.pair_index(delta)), expected)


class Neighbours(unittest.TestCase):
    def test_nearest_matches_brute_force(self):
        rng = np.random.default_rng(3)
        z = rng.normal(size=(500, 7))
        centers = rng.normal(size=(37, 7))
        brute = ((z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        self.assertTrue(np.array_equal(P.nearest(z, centers, chunk=64), brute))

    def test_n_nearest_ids_and_distances_match_brute_force(self):
        rng = np.random.default_rng(5)
        z = rng.normal(size=(300, 6))
        centers = rng.normal(size=(23, 6))
        full = ((z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        ids, dist = P.n_nearest(z, centers, 5, chunk=50)
        order = np.argsort(full, axis=1, kind="stable")[:, :5]
        self.assertTrue(np.array_equal(np.sort(ids, axis=1), np.sort(order, axis=1)))
        np.testing.assert_allclose(dist, np.take_along_axis(full, ids, axis=1),
                                   atol=1e-9)
        self.assertTrue((np.diff(dist, axis=1) >= -1e-12).all())


class Ridge(unittest.TestCase):
    def test_recovers_a_known_affine_map_per_unit(self):
        rng = np.random.default_rng(11)
        z = rng.normal(size=(4000, 5))
        ids = rng.integers(0, 3, size=len(z))
        true_w = rng.normal(size=(3, 5, 5))
        true_b = rng.normal(size=(3, 5))
        y = np.einsum("nij,nj->ni", true_w[ids], z) + true_b[ids]
        w = P.ridge_fit(z, y, ids, 3, lam=1e-8, min_members=10)
        np.testing.assert_allclose(w[:, :, :5], true_w, atol=1e-6)
        np.testing.assert_allclose(w[:, :, 5], true_b, atol=1e-6)

    def test_sparse_units_fall_back_to_the_global_predictor(self):
        rng = np.random.default_rng(13)
        z = rng.normal(size=(200, 4))
        y = rng.normal(size=(200, 4))
        ids = np.zeros(len(z), dtype=np.int64)
        ids[:3] = 1
        w = P.ridge_fit(z, y, ids, 3, lam=1.0, min_members=50)
        np.testing.assert_allclose(w[1], w[2], atol=1e-12)   # both the global fit
        self.assertFalse(np.allclose(w[0], w[1]))


class ConstantPredictor(unittest.TestCase):
    def test_is_the_per_unit_mean_future(self):
        rng = np.random.default_rng(43)
        z = rng.normal(size=(600, 4))
        y = rng.normal(size=(600, 3))
        ids = rng.integers(0, 4, size=600)
        w = P.ridge_fit(z, y, ids, 4, lam=1.0, min_members=10,
                        predictor="constant")
        self.assertEqual(w.shape, (4, 3, 5))
        np.testing.assert_allclose(w[:, :, :4], 0.0, atol=0.0)
        for u in range(4):
            np.testing.assert_allclose(w[u, :, 4], y[ids == u].mean(axis=0),
                                       atol=1e-12)

    def test_carries_no_information_about_the_frame(self):
        """The point of the ablation: with a constant predictor the discrete
        unit is the only thing that can predict, so two different frames in one
        unit must get the identical prediction."""
        corpus = toy_corpus(seed=45)
        book = P.fit(corpus, 12, seed=7007, rounds=3, candidates=4, negatives=32,
                     predictor="constant")
        z = book.normalise(corpus.x[:200])
        ids = P.nearest(z, book.centers)
        p = book.predict(z, ids)
        for u in np.unique(ids):
            rows = p[ids == u]
            np.testing.assert_allclose(rows, np.repeat(rows[:1], len(rows), axis=0),
                                       atol=1e-12)

    def test_rejects_an_unknown_predictor(self):
        with self.assertRaises(ValueError):
            P.ridge_fit(np.zeros((10, 2)), np.zeros((10, 2)),
                        np.zeros(10, dtype=np.int64), 2, 1.0, 1, predictor="mlp")


class InfoNCE(unittest.TestCase):
    def reference(self, z, y, cand, weights, negatives, tau):
        """Deliberately slow and obviously right."""
        out = np.zeros(cand.shape)
        for t in range(len(z)):
            for j, u in enumerate(cand[t]):
                p = weights[u][:, :-1] @ z[t] + weights[u][:, -1]
                scores = [-((p - y[t]) ** 2).sum() / (2 * tau)]
                scores += [-((p - n) ** 2).sum() / (2 * tau) for n in negatives]
                m = max(scores)
                lse = m + np.log(sum(np.exp(s - m) for s in scores))
                out[t, j] = scores[0] - lse
        return out

    def setUp(self):
        rng = np.random.default_rng(17)
        self.z = rng.normal(size=(40, 4))
        self.y = rng.normal(size=(40, 4))
        self.cand = rng.integers(0, 6, size=(40, 3))
        self.weights = rng.normal(size=(6, 4, 5)) * 0.4
        self.negatives = rng.normal(size=(9, 4))

    def test_matches_the_slow_reference(self):
        for tau in (0.5, 1.0, 3.0):
            fast = P.infonce(self.z, self.y, self.cand, self.weights,
                             self.negatives, tau, chunk=7)
            slow = self.reference(self.z, self.y, self.cand, self.weights,
                                  self.negatives, tau)
            np.testing.assert_allclose(fast, slow, atol=1e-10)

    def test_chunking_does_not_change_the_answer(self):
        a = P.infonce(self.z, self.y, self.cand, self.weights, self.negatives,
                      1.0, chunk=3)
        b = P.infonce(self.z, self.y, self.cand, self.weights, self.negatives,
                      1.0, chunk=10_000)
        np.testing.assert_allclose(a, b, atol=1e-12)

    def test_is_bounded_above_by_zero_and_reaches_it_for_a_perfect_predictor(self):
        s = P.infonce(self.z, self.y, self.cand, self.weights, self.negatives, 1.0)
        self.assertLessEqual(s.max(), 1e-12)
        # a predictor that lands exactly on the future, with a tiny temperature,
        # makes the positive dominate the partition function
        weights = np.zeros((1, 4, 5))
        cand = np.zeros((len(self.z), 1), dtype=np.int64)
        perfect = P.infonce(self.z, np.zeros_like(self.y), cand, weights,
                            self.negatives, 0.01)
        self.assertGreater(perfect.mean(), -1e-3)

    def test_unpredictable_targets_cannot_beat_chance(self):
        """The property k-means does not have: noise cannot win this objective.

        Quantisation error can be driven arbitrarily low by an unstructured
        target -- that is the measured result that made it useless as evidence.
        Here the same best-possible linear fit to an i.i.d. future scores at or
        below the -log(M + 1) floor, while a genuinely predictable future scores
        far above it, through the identical code.
        """
        rng = np.random.default_rng(19)
        n, m = 4000, 64
        z = rng.normal(size=(n, 4))
        cand = np.zeros((n, 1), dtype=np.int64)
        chance = -np.log(m + 1)

        noise = rng.normal(size=(n, 4))
        w = P.ridge_fit(z, noise, cand.ravel(), 1, lam=1e-6, min_members=10)
        unpredictable = float(P.infonce(z, noise, cand, w,
                                        rng.normal(size=(m, 4)), 1.0).mean())
        self.assertLessEqual(unpredictable, chance + 0.02)

        future = z @ rng.normal(size=(4, 4)) + 0.05 * rng.normal(size=(n, 4))
        w = P.ridge_fit(z, future, cand.ravel(), 1, lam=1e-6, min_members=10)
        predictable = float(P.infonce(z, future, cand, w,
                                      future[:m], 1.0).mean())
        self.assertGreater(predictable, chance + 3.0)
        self.assertGreater(predictable, unpredictable + 3.0)


class Training(unittest.TestCase):
    def test_the_objective_improves_and_beats_chance(self):
        corpus = toy_corpus(seed=21)
        book = P.fit(corpus, 16, seed=7007, rounds=5, negatives=64, candidates=4)
        first, last = book.history[0], book.history[-1]
        self.assertGreater(last["mean_infonce_nats"], first["mean_infonce_nats"])
        self.assertGreater(last["mean_infonce_nats"], last["chance_infonce_nats"])

    def test_learned_units_predict_the_real_future_better_than_a_shuffled_one(self):
        """Shuffling the futures breaks the temporal pairing and nothing else."""
        corpus = toy_corpus(seed=23)
        book = P.fit(corpus, 16, seed=7019, rounds=5, negatives=64, candidates=4)
        idx = corpus.pair_index(book.delta)
        z = book.normalise(corpus.x[idx])
        y = book.normalise(corpus.x[idx + book.delta])
        ids = P.nearest(z, book.centers)[:, None]
        rng = np.random.default_rng(0)
        shuffled = y[rng.permutation(len(y))]
        negatives = y[rng.choice(len(y), 128, replace=False)]
        true = P.infonce(z, y, ids, book.weights, negatives, 1.0).mean()
        fake = P.infonce(z, shuffled, ids, book.weights, negatives, 1.0).mean()
        self.assertGreater(true, fake + 0.5)

    def test_beta_zero_is_exactly_k_means(self):
        corpus = toy_corpus(seed=27)
        a = P.fit(corpus, 12, seed=7039, beta=0.0, rounds=4, candidates=4)
        b = P.fit_kmeans(corpus, 12, seed=7039, rounds=4)
        np.testing.assert_allclose(a.centers, b.centers, atol=1e-12)

    def test_beta_changes_the_partition(self):
        corpus = toy_corpus(seed=29)
        a = P.fit(corpus, 16, seed=7057, beta=0.0, rounds=5, candidates=4)
        b = P.fit(corpus, 16, seed=7057, beta=4.0, rounds=5, candidates=4,
                  negatives=64)
        z = b.normalise(corpus.x)
        self.assertFalse(np.array_equal(P.nearest(z, a.centers),
                                        P.nearest(z, b.centers)))

    def test_shuffling_the_futures_kills_the_objective(self):
        """The control the report leans on: same machinery, no real future."""
        corpus = toy_corpus(seed=30)
        real = P.fit(corpus, 16, seed=7007, rounds=5, candidates=4, negatives=64)
        fake = P.fit(corpus, 16, seed=7007, rounds=5, candidates=4, negatives=64,
                     shuffle_targets=True)
        chance = real.history[-1]["chance_infonce_nats"]
        self.assertGreater(real.history[-1]["mean_infonce_nats"], chance + 1.0)
        self.assertLess(fake.history[-1]["mean_infonce_nats"], chance + 0.5)

    def test_the_shuffled_control_starts_from_the_identical_codebook(self):
        """Otherwise the control would differ by its initialisation too.

        At round 0 every unit still holds the same global predictor, so the
        contrastive term is a constant across candidates and the first E-step is
        pure Voronoi.  The two runs must therefore agree exactly after one round
        and diverge only once the predictors differentiate.
        """
        corpus = toy_corpus(seed=32)
        one = [P.fit(corpus, 12, seed=7019, rounds=1, candidates=4, negatives=32,
                     shuffle_targets=s) for s in (False, True)]
        np.testing.assert_allclose(one[0].centers, one[1].centers, atol=0.0)
        many = [P.fit(corpus, 12, seed=7019, rounds=6, candidates=4, negatives=32,
                      shuffle_targets=s) for s in (False, True)]
        self.assertFalse(np.allclose(many[0].centers, many[1].centers))

    def test_same_seed_is_deterministic(self):
        corpus = toy_corpus(seed=31)
        a = P.fit(corpus, 12, seed=7007, rounds=3, candidates=4, negatives=32)
        b = P.fit(corpus, 12, seed=7007, rounds=3, candidates=4, negatives=32)
        np.testing.assert_allclose(a.centers, b.centers, atol=0.0)
        np.testing.assert_allclose(a.weights, b.weights, atol=0.0)

    def test_four_ants_share_no_fitted_quantity(self):
        corpus = toy_corpus(seed=33)
        books = [P.fit(corpus, 12, seed=s, rounds=3, candidates=4, negatives=32)
                 for s in (7007, 7019, 7039, 7057)]
        for i in range(len(books)):
            for j in range(i + 1, len(books)):
                self.assertFalse(np.allclose(books[i].centers, books[j].centers))
                self.assertFalse(np.allclose(books[i].weights, books[j].weights))

    def test_refuses_a_corpus_that_is_too_small_for_the_codebook(self):
        corpus = toy_corpus(files=1, frames=60)
        with self.assertRaises(ValueError):
            P.fit(corpus, 64, seed=7007, rounds=1)


class Encoding(unittest.TestCase):
    def setUp(self):
        self.samples = a_recording()
        corpus = toy_corpus(seed=37, dim=F.SETS[F.CANONICAL].dim,
                            feature_set=F.CANONICAL)
        self.book = P.fit(corpus, 24, seed=7007, rounds=3, candidates=4,
                          negatives=32)

    def test_encode_is_a_pure_function_of_one_frame(self):
        x = F.frame_features(self.samples)
        whole = self.book.assign(x)
        for i in (0, 5, len(x) // 2, len(x) - 1):
            self.assertEqual(int(self.book.assign(x[i:i + 1])[0]), int(whole[i]))

    def test_encode_needs_no_future(self):
        """Truncating the file must not change the units of the frames that
        survive -- the unit sequence is causal in the sense that matters."""
        x = F.frame_features(self.samples)
        half = len(self.samples) // 2
        y = F.frame_features(self.samples[:half])
        n = min(len(y), len(x)) - 5    # the delta window touches the last frames
        self.assertTrue(np.array_equal(self.book.assign(x[:n]),
                                       self.book.assign(y[:n])))

    def test_encode_is_level_invariant(self):
        for gain in (0.5, 0.125, 4.0):
            self.assertTrue(np.array_equal(
                self.book.encode(self.samples),
                self.book.encode(self.samples * gain)))

    def test_one_id_per_hop(self):
        ids = self.book.encode(self.samples)
        self.assertEqual(len(ids), len(F.frame_features(self.samples)))
        self.assertTrue(((ids >= 0) & (ids < self.book.k)).all())


class Exemplars(unittest.TestCase):
    def test_every_unit_gets_a_real_waveform_from_the_training_audio(self):
        folder = ROOT / "corpus-combined" / "train"
        if not sorted(folder.glob("*.wav")):
            raise unittest.SkipTest("no training audio")
        corpus = P.load_frames([folder], F.CANONICAL, limit_files=12, seed=1)
        book = P.fit(corpus, 16, seed=7007, rounds=2, candidates=4, negatives=32)
        P.learn_exemplars(book, [folder], limit_files=12, seed=1)
        self.assertEqual(book.exemplars.shape, (16, P.FRAME_SAMPLES))
        self.assertEqual(len(book.exemplar_sources), 16)
        # the stored waveform must be the file's real samples at the stated offset
        for unit, source in enumerate(book.exemplar_sources):
            audio = load_wav(folder / source["file"])
            samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
            start = source["frame"] * P.HOP_SAMPLES
            np.testing.assert_allclose(
                book.exemplars[unit], samples[start:start + P.FRAME_SAMPLES],
                atol=1e-6)


class Checkpoints(unittest.TestCase):
    def book(self) -> P.PredictiveCodebook:
        corpus = toy_corpus(seed=41)
        book = P.fit(corpus, 12, seed=7007, rounds=2, candidates=4, negatives=32)
        book.exemplars = np.linspace(-1, 1, 12 * P.FRAME_SAMPLES,
                                     dtype=np.float32).reshape(12, -1)
        book.exemplar_sources = [{"file": "x.wav", "frame": i} for i in range(12)]
        return book

    def test_round_trip(self):
        import tempfile
        book = self.book()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ant-a.json"
            P.save(book, path, extra={"arm": "predictive"})
            back = P.load(path)
        np.testing.assert_allclose(back.centers, book.centers, atol=1e-12)
        np.testing.assert_allclose(back.weights, book.weights, atol=1e-12)
        np.testing.assert_allclose(back.mean, book.mean, atol=1e-12)
        np.testing.assert_allclose(back.scale, book.scale, atol=1e-12)
        np.testing.assert_allclose(back.exemplars, book.exemplars, atol=1e-4)
        self.assertEqual(back.delta, book.delta)
        self.assertEqual(back.feature_set, book.feature_set)

    def test_a_tampered_checkpoint_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ant-a.json"
            P.save(self.book(), path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["centers"][0][0] += 1.0
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                P.load(path)


if __name__ == "__main__":
    unittest.main()
