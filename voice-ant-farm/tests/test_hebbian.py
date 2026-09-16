"""Correctness tests for the competitive Hebbian learner.

The properties that make this a Hebbian learner rather than k-means with extra
steps are the ones pinned here:

  * the update is normalised, so weights provably cannot blow up -- and plain
    Hebb on the same data provably does;
  * the soft neighbourhood makes units differentiate instead of collapsing, and
    leaves the map topologically ordered;
  * the conscience keeps units alive when the input distribution is lopsided;
  * it is incremental -- folding a chunk in twice equals one two-epoch fit, and
    the map is still plastic after its nominal horizon;
  * the interface the colony depends on is unchanged: encode(audio) -> unit ids
    and one real 400-sample waveform exemplar per unit, so the existing
    synthesiser runs on these checkpoints without modification;
  * ants share nothing.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feature_space as F
import hebbian as H
import hebbian_eval as E
from acoustic_units import fit_codebook, load_checkpoint, synthesize_units

ROOT = Path(__file__).resolve().parents[1]


def clusters(n_per: int = 300, k: int = 8, dim: int = 6, seed: int = 3,
             spread: float = 0.05) -> np.ndarray:
    """k well-separated Gaussian blobs: the textbook competitive-learning input."""
    rng = np.random.default_rng(seed)
    centres = rng.standard_normal((k, dim)) * 4.0
    return np.concatenate([c + spread * rng.standard_normal((n_per, dim))
                           for c in centres])


def ring(n: int = 2000, dim: int = 3, seed: int = 5) -> np.ndarray:
    """A 1-D curve embedded in 3-D: a manifold a map should be able to follow."""
    rng = np.random.default_rng(seed)
    t = np.sort(rng.random(n)) * 2 * np.pi
    x = np.stack([np.cos(t), np.sin(t), 0.1 * np.sin(3 * t)], axis=1)
    return x + 0.01 * rng.standard_normal((n, dim))


def synthetic_audio(seconds: float = 1.0, seed: int = 7007) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * H.EXEMPLAR_RATE)) / H.EXEMPLAR_RATE
    source = np.sign(np.sin(2 * np.pi * 120 * t))
    out = np.zeros_like(t)
    for f, gain in ((700.0, 1.0), (1220.0, 0.5), (2600.0, 0.25)):
        out += gain * np.sin(2 * np.pi * f * t) * source
    out += 0.01 * rng.standard_normal(len(t))
    return (0.2 * out / np.abs(out).max()).astype(np.float32)


class TestStability(unittest.TestCase):
    """Plain Hebbian is unstable.  This measures it, then measures the fix."""

    def test_plain_hebbian_diverges_and_oja_does_not(self):
        report = H.unstable_hebbian_demo(clusters(), eta=0.05, steps=2000)
        self.assertGreater(report["plain_hebbian_norm_growth"], 1e6,
                           "plain Hebb was expected to blow up and did not")
        self.assertAlmostEqual(report["oja_norm_end"], 1.0, delta=0.05)

    def test_weights_stay_inside_the_convex_hull_of_the_data(self):
        """The batch step is a convex combination, so this is a guarantee."""
        x = clusters()
        m = H.HebbianMap(16, x.shape[1], seed=7007).fit(x, epochs=10)
        self.assertTrue((m.w >= x.min(axis=0) - 1e-9).all())
        self.assertTrue((m.w <= x.max(axis=0) + 1e-9).all())

    def test_a_long_run_does_not_grow_the_weights(self):
        x = clusters()
        m = H.HebbianMap(16, x.shape[1], seed=7007, horizon=2000)
        norms = []
        for _ in range(30):
            m.partial_fit(x)
            norms.append(float(np.abs(m.w).max()))
        self.assertTrue(np.isfinite(m.w).all())
        self.assertLess(norms[-1], 2.0 * norms[0] + 1.0)

    def test_survives_a_degenerate_input(self):
        x = np.repeat(np.zeros((1, 5)), 400, axis=0)
        x[:200] += 1e-12
        m = H.HebbianMap(8, 5, seed=7007).fit(x, epochs=3)
        self.assertTrue(np.isfinite(m.w).all())


class TestCompetition(unittest.TestCase):
    def test_every_cluster_gets_a_unit_of_its_own(self):
        x = clusters(k=8, dim=6, spread=0.5)
        for units in (16, 64):
            m = H.HebbianMap(units, x.shape[1], seed=7007).fit(x, epochs=15)
            ids = m.encode(x)
            truth = np.repeat(np.arange(8), len(x) // 8)
            for blob in range(8):
                mine = set(np.unique(ids[truth == blob]).tolist())
                theirs = set(np.unique(ids[truth != blob]).tolist())
                self.assertTrue(mine - theirs,
                                f"k={units}: blob {blob} has no unit of its own")

    def test_the_map_covers_the_data_it_is_given(self):
        """64 units on the unit square: full spread, nothing dead, quantisation
        at the theoretical scale for 64 cells.  A contracted or half-dead map
        fails all three."""
        x = np.random.default_rng(7).random((4000, 2))
        m = H.HebbianMap(64, 2, seed=7007).fit(x, epochs=20)
        self.assertEqual(m.dead_units(x), 0)
        self.assertGreater(float(m.w.std(axis=0).mean()),
                           0.9 * float(x.std(axis=0).mean()))
        self.assertLess(float(H.sqdist(x, m.w).min(axis=1).mean()), 0.005)

    def test_annealing_the_radius_is_what_prevents_collapse(self):
        """A neighbourhood that never shrinks drags every unit to one point.

        This is the failure mode the brief names -- units collapsing onto the
        same prototype -- reproduced on purpose, so the claim that the annealed
        schedule prevents it is a comparison and not an assurance.
        """
        x = ring()
        annealed = H.HebbianMap(64, x.shape[1], seed=7007).fit(x, epochs=20)
        stuck = H.HebbianMap(64, x.shape[1], seed=7007,
                             sigma0=100.0, sigma_min=100.0).fit(x, epochs=20)
        spread_annealed = float(np.mean(annealed.w.std(axis=0)))
        spread_stuck = float(np.mean(stuck.w.std(axis=0)))
        self.assertLess(spread_stuck, 1e-4 * float(np.mean(x.std(axis=0))),
                        "the collapse control did not collapse")
        self.assertGreater(spread_annealed, 0.1 * float(np.mean(x.std(axis=0))))
        # a collapsed codebook is one prototype wearing 64 hats, so it cannot
        # represent the data however many units it nominally has
        self.assertLess(float(H.sqdist(x, annealed.w).min(axis=1).mean()),
                        0.1 * float(H.sqdist(x, stuck.w).min(axis=1).mean()))

    def test_soft_neighbourhood_orders_the_map(self):
        """Grid neighbours must end up closer in feature space than random pairs."""
        x = ring()
        m = H.HebbianMap(64, x.shape[1], seed=7007).fit(x, epochs=25)
        ordered = H.topology_report(m.w, m.rows, m.cols)
        shuffled = H.topology_report(
            m.w[np.random.default_rng(1).permutation(m.units)], m.rows, m.cols)
        self.assertLess(ordered["neighbour_ratio"], 0.6)
        self.assertLess(ordered["neighbour_ratio"], shuffled["neighbour_ratio"])
        self.assertGreater(ordered["pearson_grid_vs_feature_distance"], 0.3)

    def test_zero_radius_removes_the_ordering(self):
        """The topology is caused by the neighbourhood, not by the data."""
        x = ring()
        wide = H.HebbianMap(64, x.shape[1], seed=7007).fit(x, epochs=25)
        narrow = H.HebbianMap(64, x.shape[1], seed=7007, sigma0=0.05,
                              sigma_min=0.05).fit(x, epochs=25)
        self.assertLess(H.topology_report(wide.w, wide.rows, wide.cols)["neighbour_ratio"],
                        H.topology_report(narrow.w, narrow.rows,
                                          narrow.cols)["neighbour_ratio"])


class TestHomeostasis(unittest.TestCase):
    """What the conscience does, and one thing it measurably does not do.

    It equalises win frequency among the units that are alive (Gini 0.36 -> 0.06
    on the lopsided fixture below).  It does NOT by itself reduce the dead-unit
    count on that fixture -- measured, 32 dead -> 44 dead with a neighbourhood,
    0 -> 6 without one -- because it pushes units towards the empty space
    between a dense cluster and its outliers.  The dead-unit count on the real
    task is reported by `hebbian_eval`, not asserted here.
    """

    def lopsided(self) -> np.ndarray:
        """95% of the mass in one tight blob: the shape that kills k-means units."""
        rng = np.random.default_rng(11)
        dense = 0.02 * rng.standard_normal((3800, 4))
        sparse = 6.0 * rng.standard_normal((200, 4))
        return np.concatenate([dense, sparse])

    def test_the_conscience_biases_the_competition_but_not_the_interface(self):
        """The mechanism itself: an over-winning unit loses a fight it would win.

        A unit is placed exactly on the input and its win estimate is inflated;
        during training the conscience must hand the win to someone else, while
        `encode` -- which the colony depends on -- must still return the nearest
        prototype.
        """
        m = H.HebbianMap(4, 2, seed=7007, conscience=0.5)
        m.w = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        m.initialised = True
        m._dscale = 1.0
        x = np.array([[0.02, 0.0]])
        m.p[:] = 0.0
        m.p[0] = 1.0                                   # unit 0 hogs every frame
        biased = (H.sqdist(x, m.w) + m._bias()[None, :]).argmin(axis=1)
        self.assertNotEqual(int(biased[0]), 0)
        self.assertEqual(int(m.encode(x)[0]), 0)

    def test_conscience_evens_out_the_win_distribution(self):
        x = self.lopsided()
        off = H.HebbianMap(64, 4, seed=7007, conscience=0.0,
                           sigma0=0.05, sigma_min=0.05).fit(x, epochs=15)
        on = H.HebbianMap(64, 4, seed=7007, conscience=0.5,
                          sigma0=0.05, sigma_min=0.05).fit(x, epochs=15)
        self.assertLess(H.gini(on.win_counts.astype(float)),
                        H.gini(off.win_counts.astype(float)))

    def test_gini_endpoints(self):
        self.assertAlmostEqual(H.gini(np.ones(50)), 0.0, places=9)
        winner_takes_all = np.zeros(50)
        winner_takes_all[0] = 1000.0
        self.assertGreater(H.gini(winner_takes_all), 0.95)


class TestSchedule(unittest.TestCase):
    """The annealing horizon.  This class exists because getting it wrong is
    silent: a horizon longer than the run leaves sigma near sigma0 throughout,
    the map never specialises, and the only symptom is a mediocre score."""

    def test_horizon_defaults_to_the_run_it_is_given(self):
        x = clusters()
        m = H.HebbianMap(16, x.shape[1], seed=7007).fit(x, epochs=7)
        self.assertEqual(m.horizon, 7 * len(x))
        self.assertAlmostEqual(m.sigma(), m.sigma_min, places=9)
        self.assertAlmostEqual(m.eta(), m.eta_min, places=9)

    def test_radius_and_rate_fall_monotonically(self):
        x = clusters()
        m = H.HebbianMap(16, x.shape[1], seed=7007, horizon=4 * len(x))
        sigmas, etas = [m.sigma()], [m.eta()]
        for _ in range(4):
            m.partial_fit(x)
            sigmas.append(m.sigma())
            etas.append(m.eta())
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(sigmas, sigmas[1:])))
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(etas, etas[1:])))
        self.assertAlmostEqual(sigmas[0], m.sigma0, places=9)
        self.assertAlmostEqual(sigmas[-1], m.sigma_min, places=9)

    def test_streamed_frames_get_the_documented_default_horizon(self):
        m = H.HebbianMap(16, 6, seed=7007)
        m.partial_fit(clusters())
        self.assertEqual(m.horizon, H.STREAM_HORIZON)


class TestIncremental(unittest.TestCase):
    def test_partial_fit_twice_equals_two_epochs(self):
        """Streaming and batch must be the same learner, given the same schedule."""
        x = clusters()
        horizon = 2 * len(x)
        a = H.HebbianMap(16, x.shape[1], seed=7007, horizon=horizon)
        a.partial_fit(x)
        a.partial_fit(x)
        b = H.HebbianMap(16, x.shape[1], seed=7007, horizon=horizon).fit(x, epochs=2)
        np.testing.assert_allclose(a.w, b.w, atol=1e-12)
        self.assertEqual(a.seen, b.seen)

    def test_still_plastic_after_the_horizon(self):
        """An ant that runs for a week must not freeze."""
        x = clusters()
        m = H.HebbianMap(16, x.shape[1], seed=7007, horizon=1000).fit(x, epochs=5)
        self.assertGreaterEqual(m.eta(), m.eta_min - 1e-12)
        before = m.w.copy()
        m.partial_fit(clusters(seed=99))
        self.assertGreater(float(np.abs(m.w - before).max()), 1e-6)

    def test_new_data_is_actually_learned(self):
        x = clusters(seed=3)
        m = H.HebbianMap(32, x.shape[1], seed=7007, horizon=5000).fit(x, epochs=5)
        fresh = clusters(seed=77) + 20.0
        far = float(H.sqdist(fresh, m.w).min(axis=1).mean())
        m.partial_fit(fresh)
        near = float(H.sqdist(fresh, m.w).min(axis=1).mean())
        self.assertLess(near, far)


class TestEncodeInterface(unittest.TestCase):
    def test_encode_is_a_plain_argmin_with_no_conscience(self):
        """The conscience is a training-time term; the interface must be pure."""
        x = clusters()
        m = H.HebbianMap(16, x.shape[1], seed=7007, conscience=0.9).fit(x, epochs=5)
        m.p[:] = 0.0
        m.p[0] = 1.0                       # a maximally biased conscience
        np.testing.assert_array_equal(m.encode(x), H.sqdist(x, m.w).argmin(axis=1))

    def test_encode_samples_gives_one_unit_per_frame(self):
        audio = synthetic_audio(0.5)
        m = H.HebbianMap(16, 26, seed=7007).fit(F.frame_features(audio), epochs=2)
        ids = m.encode_samples(audio)
        self.assertEqual(len(ids), len(F.frame_features(audio)))
        self.assertTrue((ids >= 0).all() and (ids < 16).all())

    def test_scaler_is_applied_consistently(self):
        audio = synthetic_audio(0.5)
        x = F.frame_features(audio)
        m = H.HebbianMap(16, 26, seed=7007)
        m.fit_scaler(x)
        m.fit(x / m.scale, epochs=2)
        np.testing.assert_array_equal(m.encode_samples(audio), m.encode(x / m.scale))

    def test_snap_puts_every_prototype_on_a_real_frame(self):
        x = clusters()
        m = H.HebbianMap(16, x.shape[1], seed=7007).fit(x, epochs=5)
        m.snap_to_frames(x)
        for row in m.w:
            self.assertTrue(np.any(np.all(np.isclose(x, row), axis=1)))


class TestIndependence(unittest.TestCase):
    def test_same_seed_is_reproducible(self):
        x = clusters()
        a = H.HebbianMap(16, x.shape[1], seed=7019).fit(x, epochs=4)
        b = H.HebbianMap(16, x.shape[1], seed=7019).fit(x, epochs=4)
        np.testing.assert_array_equal(a.w, b.w)

    def test_different_ants_do_not_coincide(self):
        """Four ants, four seeds, no shared parameter anywhere."""
        x = clusters()
        maps = [H.HebbianMap(16, x.shape[1], seed=s).fit(x, epochs=4)
                for s in H.DEFAULT_SEEDS]
        self.assertEqual(len(set(H.DEFAULT_SEEDS)), 4)
        for i in range(4):
            for j in range(i + 1, 4):
                self.assertFalse(np.array_equal(maps[i].w, maps[j].w))

    def test_a_scaler_is_fitted_per_ant_from_its_own_frames(self):
        a = H.HebbianMap(8, 6, seed=7007).fit_scaler(clusters(seed=1))
        b = H.HebbianMap(8, 6, seed=7007).fit_scaler(clusters(seed=2))
        self.assertFalse(np.array_equal(a.scale, b.scale))


class TestGrid(unittest.TestCase):
    def test_shapes_factorise(self):
        for k in (64, 128, 256, 512, 100):
            rows, cols = H.grid_shape(k)
            self.assertEqual(rows * cols, k)
            self.assertLessEqual(rows, cols)

    def test_grid_distance_is_a_metric(self):
        d = H.grid_sqdist(4, 5)
        self.assertEqual(d.shape, (20, 20))
        np.testing.assert_array_equal(d, d.T)
        np.testing.assert_array_equal(np.diag(d), np.zeros(20))

    def test_sqdist_matches_the_naive_form(self):
        rng = np.random.default_rng(2)
        x, w = rng.standard_normal((20, 5)), rng.standard_normal((7, 5))
        naive = ((x[:, None, :] - w[None, :, :]) ** 2).sum(axis=2)
        np.testing.assert_allclose(H.sqdist(x, w), naive, atol=1e-9)


class TestCheckpoint(unittest.TestCase):
    """A Hebbian checkpoint must be a checkpoint the rest of the colony can use."""

    @classmethod
    def setUpClass(cls):
        folder = ROOT / "corpus-combined" / "train"
        if not sorted(folder.glob("*.wav")):
            raise unittest.SkipTest("no corpus audio available")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.checkpoint, cls.path = H.train_ant(
            "ant-a", 7007, [folder], Path(cls.tmp.name), units=8, epochs=2,
            file_limit=6, verbose=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_passes_the_shipped_loader(self):
        loaded = load_checkpoint(self.path)
        self.assertEqual(loaded["checkpoint_sha256"],
                         self.checkpoint["checkpoint_sha256"])
        self.assertEqual(loaded["architecture"], H.ARCHITECTURE)
        self.assertFalse(loaded["codebooks_merged"])

    def test_one_real_400_sample_exemplar_per_unit(self):
        pcm = np.asarray(self.checkpoint["exemplars_pcm16"])
        self.assertEqual(pcm.shape, (8, 400))
        self.assertEqual(self.checkpoint["exemplar_rate"], 16_000)
        self.assertEqual(len(self.checkpoint["exemplar_source_hashes"]), 8)
        self.assertTrue(all(h for h in self.checkpoint["exemplar_source_hashes"]))
        self.assertGreater(int(np.abs(pcm).max()), 0)

    def test_the_shipped_synthesiser_runs_on_it(self):
        ids = np.array([0, 3, 5, 5, 2, 7, 1], dtype=np.int64)
        out = synthesize_units(
            ids, f"{self.checkpoint['checkpoint_sha256']}:unit_id", self.checkpoint)
        self.assertEqual(len(out), (len(ids) - 1) * 160 + 400)
        self.assertTrue(np.isfinite(out).all())
        self.assertLessEqual(float(np.abs(out).max()), 1.0)

    def test_round_trip_encode(self):
        centers, scale, checkpoint = H.load_hebbian(self.path)
        wav = sorted((ROOT / "corpus-combined" / "train").glob("*.wav"))[0]
        ids = H.encode_wav(wav, centers, scale)
        self.assertTrue((ids >= 0).all() and (ids < checkpoint["units"]).all())
        self.assertEqual(checkpoint["feature_spec"]["feature_set"], "recommended26")

    def test_provenance_states_the_subsampling(self):
        p = self.checkpoint["corpus_provenance"]
        self.assertEqual(p["file_limit_per_folder"], 6)
        self.assertEqual(p["frame_stride"], 1)
        self.assertGreater(p["train_frame_count"], 0)
        self.assertIn("train_seconds", p)


class TestEvalHelpers(unittest.TestCase):
    def test_blocked_kmeans_matches_the_shipped_one(self):
        x = clusters(n_per=40, k=6, dim=4).astype(np.float32)
        mine = E.kmeans(x.astype(np.float64), 6, seed=7007, block=17)
        theirs = fit_codebook(x, 6, seed=7007)
        np.testing.assert_allclose(np.sort(mine, axis=0),
                                   np.sort(theirs, axis=0), atol=1e-4)

    def test_random_real_frames_are_real_frames(self):
        x = clusters()
        picked = E.random_real_frames(x, 12, seed=7007)
        for row in picked:
            self.assertTrue(np.any(np.all(x == row, axis=1)))

    def test_topographic_error_is_lower_for_an_ordered_map(self):
        x = ring()
        m = H.HebbianMap(64, x.shape[1], seed=7007).fit(x, epochs=25)
        shuffled = m.w[np.random.default_rng(4).permutation(m.units)]
        self.assertLess(E.topographic_error(x, m.w, m.rows, m.cols),
                        E.topographic_error(x, shuffled, m.rows, m.cols))


if __name__ == "__main__":
    unittest.main()
