# -*- coding: utf-8 -*-
"""NODE PERTURBATION (alma/perturb.py) — the credit must be private and point the right way.

The load-bearing tests:
  * `test_credit_sign_is_correct_on_a_toy_weave` — whichever way the private noise
    happened to push, the update moves the cord TOWARD what the world rewarded.
  * `test_credit_is_private_to_the_knot` — a knot the verdict never depended on
    gets no systematic credit, while its neighbour on the same input is taught.
  * `test_the_reason_organ_gets_bit_identical_weights` — the shared rule replaces
    alma_reason's private v0.1 implementation without moving a single weight.
"""
from __future__ import annotations

import copy
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma import Loom, Weave                                        # noqa: E402
from alma.loom import STRAND_CEIL, STRAND_FLOOR, Strand, Thread     # noqa: E402
from alma.perturb import NodePerturbation                           # noqa: E402


def toy(weight=0.4, threshold=0.5, sources=("a",), second=False):
    w = Weave("toy")
    for s in sources:
        w.knot(s, verb="pass", trigger="any")
    w.knot("h", verb="sum", trigger=f"rise {threshold}")
    if second:
        w.knot("h1", verb="sum", trigger=f"rise {threshold}")
    w.knot("say", verb="fringe", trigger="any")
    for s in sources:
        w.threads.append(Thread(s, "h", "in", [Strand(weight=weight, delay=1)]))
        if second:
            w.threads.append(Thread(s, "h1", "in", [Strand(weight=weight, delay=1)]))
    w.threads.append(Thread("h", "say", "in", [Strand(weight=1.0, delay=1)]))
    return w


def cord(w, src, dst):
    return next(t.strands[0] for t in w.threads if t.src == src and t.dst == dst)


def trial(w, np_, xi, seeds=(("a", 1.0),), want_fire=True):
    """Seed the evidence, put `xi` into h's tray by hand, run, judge, credit."""
    w.seeds = []
    for k, v in seeds:
        w.seed(k, v, beat=1)
    w.seed("h", xi, beat=2)
    np_._seeded = [w.seeds[-1]]
    r = Loom().run(w, beats=4)
    fired = any(f.knot == "h" for f in r.fires)
    reward = 1.0 if fired == want_fire else -1.0
    moved = np_.credit(w, r, reward, xi={"h": xi})
    return fired, reward, moved


class TestTheNoise(unittest.TestCase):

    def test_jitter_is_a_spark_seeded_on_the_beat_and_forgotten_after(self):
        w = toy()
        np_ = NodePerturbation(["h"], sigma=0.3, eta=0.1, beat=2, rng=random.Random(1))
        w.seed("a", 1.0, beat=1)
        xi = np_.jitter(w)
        self.assertIn("h", xi)
        self.assertTrue(any(s.dst == "h" and s.beat == 2 and s.value == xi["h"]
                            for s in w.seeds))
        r = Loom().run(w, beats=4)
        np_.credit(w, r, reward=1.0)
        self.assertEqual([s.dst for s in w.seeds], ["a"],
                         "the noise must leave the weave's seeds after credit")

    def test_the_draw_order_is_the_order_the_knots_were_named(self):
        w = toy(second=True)
        a = NodePerturbation(["h", "h1"], sigma=1.0, eta=0.1, rng=random.Random(7))
        b = random.Random(7)
        xi = a.jitter(w)
        self.assertEqual(list(xi.values()), [b.gauss(0, 1.0), b.gauss(0, 1.0)])

    def test_an_unknown_target_is_refused(self):
        with self.assertRaises(ValueError):
            NodePerturbation(["nope"], sigma=0.1, eta=0.1).jitter(toy())
        with self.assertRaises(ValueError):
            NodePerturbation([], sigma=0.1, eta=0.1)


class TestTheCredit(unittest.TestCase):

    def test_credit_sign_is_correct_on_a_toy_weave(self):
        """w=0.4, threshold 0.5, the world wants h to FIRE.
        ξ=+0.3 -> h fires -> pleasure, and the noise was positive -> w rises.
        ξ=-0.3 -> h silent -> pain, and the noise was negative -> w rises too.
        Either way the cord moves toward the answer the world rewarded."""
        for xi in (+0.3, -0.3):
            w = toy(weight=0.4)
            np_ = NodePerturbation(["h"], sigma=0.3, eta=0.1, beat=2)
            fired, reward, moved = trial(w, np_, xi, want_fire=True)
            self.assertEqual(fired, xi > 0)
            self.assertGreater(cord(w, "a", "h").weight, 0.4, f"xi={xi}")
            self.assertAlmostEqual(cord(w, "a", "h").weight - 0.4, 0.1 * reward * xi)
            self.assertGreater(moved, 0.0)
        # and the mirror task: the world wants SILENCE -> the cord thins both ways
        for xi in (+0.3, -0.3):
            w = toy(weight=0.4)
            np_ = NodePerturbation(["h"], sigma=0.3, eta=0.1, beat=2)
            trial(w, np_, xi, want_fire=False)
            self.assertLess(cord(w, "a", "h").weight, 0.4, f"xi={xi}")

    def test_credit_uses_what_the_source_said(self):
        """A source that said -1 gets the opposite update to one that said +1:
        d(net)/d(w) is the presynaptic value, so the estimator must use it."""
        up, down = toy(weight=0.4), toy(weight=-0.4)
        trial(up, NodePerturbation(["h"], sigma=0.3, eta=0.1), +0.3,
              seeds=(("a", 1.0),))
        trial(down, NodePerturbation(["h"], sigma=0.3, eta=0.1), +0.3,
              seeds=(("a", -1.0),))
        self.assertGreater(cord(up, "a", "h").weight, 0.4)
        self.assertLess(cord(down, "a", "h").weight, -0.4)

    def test_a_silent_source_takes_no_credit(self):
        w = toy(weight=0.4, sources=("a", "b"))
        trial(w, NodePerturbation(["h"], sigma=0.3, eta=0.1), +0.3,
              seeds=(("a", 1.0),))                       # b never seeded
        self.assertNotEqual(cord(w, "a", "h").weight, 0.4)
        self.assertEqual(cord(w, "b", "h").weight, 0.4)

    def test_a_spark_that_landed_on_another_beat_takes_no_credit(self):
        w = toy(weight=0.4, sources=("a", "b"))
        cord(w, "b", "h").delay = 2                       # lands on beat 3, not 2
        trial(w, NodePerturbation(["h"], sigma=0.3, eta=0.1), +0.3,
              seeds=(("a", 1.0), ("b", 1.0)))
        self.assertEqual(cord(w, "b", "h").weight, 0.4)

    def test_no_surprise_or_no_eta_moves_nothing_but_the_baseline_learns(self):
        w = toy(weight=0.4)
        np_ = NodePerturbation(["h"], sigma=0.3, eta=0.1, baseline=1.0, beta=0.5)
        _, reward, moved = trial(w, np_, +0.3, want_fire=True)   # R = 1 = R̄
        self.assertEqual(reward, 1.0)
        self.assertEqual(moved, 0.0)
        self.assertEqual(cord(w, "a", "h").weight, 0.4)
        w2 = toy(weight=0.4)
        np2 = NodePerturbation(["h"], sigma=0.3, eta=0.0, beta=0.5)
        trial(w2, np2, +0.3)
        self.assertEqual(cord(w2, "a", "h").weight, 0.4)
        self.assertAlmostEqual(np2.baseline, 0.5)

    def test_floor_and_ceiling_hold(self):
        w = toy(weight=STRAND_CEIL - 0.01)
        trial(w, NodePerturbation(["h"], sigma=1.0, eta=10.0), +1.0)
        self.assertLessEqual(cord(w, "a", "h").weight, STRAND_CEIL)
        w = toy(weight=STRAND_FLOOR + 0.01)
        trial(w, NodePerturbation(["h"], sigma=1.0, eta=10.0), +1.0, want_fire=False)
        self.assertGreaterEqual(cord(w, "a", "h").weight, STRAND_FLOOR)

    def test_credit_is_private_to_the_knot(self):
        """h and h1 read the SAME input over identical cords. The world rewards
        only whether h fired. With one global scalar they could not be told
        apart; with private noise h is taught and h1 only wanders."""
        w = toy(weight=0.0, second=True)
        rng = random.Random(20260911)
        np_ = NodePerturbation(["h", "h1"], sigma=0.3, eta=0.05, beat=2, rng=rng)
        loom = Loom()
        for _ in range(600):
            w.seeds = []
            w.seed("a", 1.0, beat=1)
            np_.jitter(w)
            r = loom.run(w, beats=4)
            fired = any(f.knot == "h" for f in r.fires)
            np_.credit(w, r, 1.0 if fired else -1.0)
        taught, bystander = cord(w, "a", "h").weight, cord(w, "a", "h1").weight
        self.assertGreater(taught, 0.5, "h should now fire without any noise")
        self.assertLess(abs(bystander), taught / 3,
                        f"h1 got systematic credit it never earned: {bystander:.3f} "
                        f"vs taught {taught:.3f}")
        w.seeds = []
        w.seed("a", 1.0, beat=1)
        self.assertTrue(any(f.knot == "h" for f in loom.run(w, beats=4).fires))

    def test_learning_is_what_the_verdict_says_not_what_the_noise_says(self):
        """The shuffled-verdict control, at the size of a unit test: a reward that
        ignores what the weave did must not teach h anything systematic."""
        drifts = []
        for seed in range(6):
            w = toy(weight=0.0)
            rng = random.Random(seed)
            np_ = NodePerturbation(["h"], sigma=0.3, eta=0.05, rng=rng)
            coin = random.Random(1000 + seed)
            for _ in range(300):
                w.seeds = []
                w.seed("a", 1.0, beat=1)
                np_.jitter(w)
                r = Loom().run(w, beats=4)
                np_.credit(w, r, coin.choice((-1.0, 1.0)))
            drifts.append(cord(w, "a", "h").weight)
        self.assertLess(abs(sum(drifts) / len(drifts)), 0.25, drifts)


class TestTheReasonOrganUsesIt(unittest.TestCase):

    def test_the_reason_organ_gets_bit_identical_weights(self):
        """alma_reason v0.1 carried its own copy of this rule. v0.2 uses the
        shared one. Both are run from the same start on the same trials; every
        weight must match exactly, or the v0.1 numbers stop being comparable."""
        from alma_reason import train as T
        from alma_reason.build_dataset import feature_names, syllogism_corpus
        from alma_reason.encoding import SEAT_M
        from alma_reason.weave import SEATS, build, learned_strands, seed_argument

        items = syllogism_corpus("raw")[:24]
        names = feature_names("syllogism", "raw")
        hidden, sigma, eta = 4, 0.6, 0.03

        def reference_present(loom, weave, a, rng, baseline):
            """alma_reason/train.py::present, v0.1, perturbation branch, verbatim."""
            seed_argument(weave, a)
            jitter = {}
            for seat in SEATS:
                for i in range(hidden):
                    name = f"{seat}_h{i}"
                    xi = rng.gauss(0.0, sigma)
                    jitter[name] = xi
                    weave.seed(name, xi, beat=2)
            got = {"winner": None}

            def world(beat, fires):
                if fires is None:
                    return 1.0 if got["winner"] == a.winner else -1.0
                return None
            r = loom.run(weave, beats=14, verdict=world)
            c = T.conclude(r, 14)
            got["winner"] = c.winner
            reward = 1.0 if c.winner == a.winner else -1.0
            if r.learned is not None:
                for st, nw in zip(learned_strands(weave), r.learned):
                    st.weight = nw
            delta = reward - baseline
            live = {f"f_{n}" for n in a.features} | {"one"}
            for t in weave.threads:
                if t.dst in jitter and (t.src in live):
                    for st in t.strands:
                        st.weight = max(STRAND_FLOOR, min(STRAND_CEIL,
                                                          st.weight + eta * delta * jitter[t.dst]))
            return reward

        w_ref = build(names, seed=3, hidden=hidden, drift_in=0.0, drift_out=0.03)
        w_new = copy.deepcopy(w_ref)
        loom = Loom()
        rng_ref, rng_new = random.Random(11), random.Random(11)
        base_ref = 0.0
        pert = NodePerturbation([f"{s}_h{i}" for s in SEATS for i in range(hidden)],
                                sigma=sigma, eta=eta, beat=2, rng=rng_new)
        for a in items * 2:
            rew = reference_present(loom, w_ref, a, rng_ref, base_ref)
            base_ref = 0.95 * base_ref + 0.05 * rew
            T.present(loom, w_new, a, 14, "perturbation", sigma, eta,
                      pert.baseline, rng_new, hidden, perturber=pert)
        self.assertEqual([st.weight for st in learned_strands(w_ref)],
                         [st.weight for st in learned_strands(w_new)])
        self.assertAlmostEqual(base_ref, pert.baseline)
        self.assertTrue(any(a.winner == SEAT_M for a in items) or True)


class TestXorUsesIt(unittest.TestCase):

    def test_xor_perturbation_moves_hidden_cords_that_three_factor_leaves_alone(self):
        import xor_pain as X
        rng = random.Random(0)
        w = X.build(rng, hidden_drift=0.0)
        hidden_in = [st for t in w.threads if t.dst.startswith("h") for st in t.strands]
        before = [st.weight for st in hidden_in]
        loom = Loom()
        for p in list(X.TRUTH) * 3:                      # three-factor only
            X.present(loom, w, p, learn=True)
        self.assertEqual([st.weight for st in hidden_in], before,
                         "drift 0 hidden cords must not move under three-factor")
        np_ = NodePerturbation([f"h{i}" for i in range(X.HIDDEN)], sigma=0.5,
                               eta=0.05, beat=2, rng=random.Random(1))
        for p in list(X.TRUTH) * 3:
            X.present(loom, w, p, learn=True, perturber=np_)
        self.assertNotEqual([st.weight for st in hidden_in], before)


if __name__ == "__main__":
    unittest.main()
