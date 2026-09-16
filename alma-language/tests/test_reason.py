# -*- coding: utf-8 -*-
"""Tests for alma_reason — the שקלא וטריא weave (B2 of the holobrain).

    python -m unittest discover -s tests -v      (from the repo root)

The centrepiece is `TestTheGateIsLoadBearing`, in the shape `test_chords.py`
already set for this repo: it switches the דחייה mechanism off, reruns the same
debate, and REQUIRES the concession to stop happening. Without that, "a seat
that loses its standing falls silent" is a sentence in a docstring rather than
a property of the machine.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alma import Loom                                            # noqa: E402
from alma.loom import Strand, Thread                             # noqa: E402

from alma_reason import encoding, machloket, syllogism           # noqa: E402
from alma_reason.build_dataset import (feature_names,            # noqa: E402
                                       stratified_split,
                                       syllogism_corpus)
from alma_reason.encoding import (SEAT_M, SEAT_Q,                # noqa: E402
                                  encode_syllogism,
                                  syllogism_feature_names)
from alma_reason.syllogism import Syllogism, all_syllogisms      # noqa: E402
from alma_reason.weave import (CHAZAKA, DEFAULT_BEATS, build,    # noqa: E402
                               conclude, debate, learned_strands,
                               seed_argument)

RAW = syllogism_feature_names("raw")


def _debate(arg, seed=1, beats=DEFAULT_BEATS, **kw):
    w = build(RAW, seed=seed, beats=beats, **kw)
    return debate(Loom(), w, arg, beats=beats)


class TestTheLabelsAreNotOpinions(unittest.TestCase):
    """The whole corpus rests on this. If it fails, no number below means anything."""

    def test_rule_engine_reproduces_the_24_classical_moods(self):
        syllogism.self_test()

    def test_barbara_stands_and_its_second_figure_twin_falls(self):
        self.assertTrue(Syllogism(1, "AAA").valid())      # Barbara
        self.assertFalse(Syllogism(2, "AAA").valid())     # undistributed middle
        self.assertEqual(Syllogism(2, "AAA").fault(), "undistributed-middle")

    def test_every_invalid_mood_names_exactly_one_fault(self):
        for s in all_syllogisms():
            self.assertEqual(bool(s.fault()), not s.valid(), s.key())

    def test_the_boolean_reading_is_a_strict_subset(self):
        trad = {s.key() for s in all_syllogisms() if s.valid()}
        bool_ = {s.key() for s in all_syllogisms() if s.boolean_valid()}
        self.assertTrue(bool_ < trad)
        self.assertEqual(len(trad), 24)
        self.assertEqual(len(bool_), 15)


class TestEncoding(unittest.TestCase):

    def test_self_test(self):
        encoding.self_test()

    def test_no_feature_leaks_the_verdict(self):
        """A feature named after the answer would make every number a lie."""
        for fs in ("raw", "distrib"):
            for name in syllogism_feature_names(fs):
                self.assertNotIn("valid", name)
                self.assertNotIn("fault", name)

    def test_booleans_are_one_hot_not_presence(self):
        """Absence must never quietly mean `false` — see encoding.py's corollary."""
        s = Syllogism(1, "AAA")
        f = encoding.syllogism_features(s, "distrib")
        for key in s.facts():
            self.assertNotEqual(key in f, f"not_{key}" in f, key)

    def test_two_syllogisms_that_differ_get_different_features(self):
        a = encoding.syllogism_features(Syllogism(1, "AAA"), "raw")
        b = encoding.syllogism_features(Syllogism(2, "AAA"), "raw")
        self.assertNotEqual(a, b)

    def test_machloket_seating_swap_flips_the_winner(self):
        machloket.self_test()
        for m in machloket.corpus():
            x = encoding.encode_machloket(m, False)
            y = encoding.encode_machloket(m, True)
            self.assertNotEqual(x.winner, y.winner, m.id)

    def test_the_rule_of_psak_is_never_a_feature(self):
        names = set(feature_names("machloket", "machloket"))
        for m in machloket.corpus():
            self.assertNotIn(m.psak_rule, names)


class TestTheWeaveIsAWeave(unittest.TestCase):

    def test_it_validates(self):
        build(RAW, seed=0).validate()

    def test_the_form_is_given_and_carries_no_drift(self):
        """Structure cords must not learn. The שקלא וטריא is not up for training."""
        w = build(RAW, seed=0)
        structural = {("one", "M_arg"), ("M_arg", "M_arg"), ("M_arg", "M_gate"),
                      ("M_stand", "M_gate"), ("M_gate", "M_stand"),
                      ("M_gate", "Q_stand"), ("M_stand", "say_M")}
        seen = set()
        for t in w.threads:
            if (t.src, t.dst) in structural:
                seen.add((t.src, t.dst))
                for st in t.strands:
                    self.assertEqual(st.drift, 0.0, f"{t.src}->{t.dst} drifts")
        self.assertEqual(seen, structural, "a structural cord went missing")

    def test_the_reading_is_learned_and_does_drift(self):
        w = build(RAW, seed=0, drift_in=0.0, drift_out=0.04)
        out = [st for t in w.threads if t.src.startswith("M_h")
               and t.dst == "M_arg" for st in t.strands]
        self.assertTrue(out)
        self.assertTrue(all(st.drift == 0.04 for st in out))

    def test_a_kushia_is_negative_and_a_tirutz_positive(self):
        """The signs ARE the dialectic. Flip one and it stops being an argument."""
        w = build(RAW, seed=0)
        for t in w.threads:
            if t.src == "M_gate" and t.dst == "Q_stand":
                self.assertLess(t.strands[0].weight, 0)      # קושיא
            if t.src == "M_gate" and t.dst == "M_stand":
                self.assertGreater(t.strands[0].weight, 0)   # תירוץ

    def test_every_weight_starts_random_nothing_is_hand_set(self):
        a = [st.weight for st in learned_strands(build(RAW, seed=0))]
        b = [st.weight for st in learned_strands(build(RAW, seed=1))]
        self.assertNotEqual(a, b)


class TestTheDebateRuns(unittest.TestCase):

    def test_it_reaches_a_maskana(self):
        c, _ = _debate(encode_syllogism(Syllogism(1, "AAA"), "raw"))
        self.assertIn(c.winner, (SEAT_M, SEAT_Q, "תיקו"))
        self.assertTrue(c.line().startswith("מסקנה:"))

    def test_six_rounds_at_the_default_horizon(self):
        c, _ = _debate(encode_syllogism(Syllogism(1, "AAA"), "raw"))
        self.assertEqual(len(c.rounds), 6)
        self.assertEqual([r.beat for r in c.rounds], [4, 6, 8, 10, 12, 14])

    def test_both_seats_speak_in_round_one_because_of_chazaka(self):
        """A position is presumed to stand. Nobody earns the right to open."""
        for key, fig in (("AAA", 1), ("EIO", 3), ("OOO", 2), ("IAI", 4)):
            c, _ = _debate(encode_syllogism(Syllogism(fig, key), "raw"))
            self.assertTrue(c.rounds[0].m_spoke, f"{key}-{fig}")
            self.assertTrue(c.rounds[0].q_spoke, f"{key}-{fig}")

    def test_a_seat_that_concedes_never_speaks_again(self):
        """דחייה is a fixed point, not a flag. Once folded, folded."""
        found = False
        for s in all_syllogisms()[:60]:
            c, _ = _debate(encode_syllogism(s, "raw"))
            for seat, at in ((SEAT_M, c.conceded_m), (SEAT_Q, c.conceded_q)):
                if at is None:
                    continue
                found = True
                spoke_after = [r.index for r in c.rounds[at:]
                               if (r.m_spoke if seat == SEAT_M else r.q_spoke)]
                self.assertEqual(spoke_after, [], f"{s.key()} {seat} spoke again")
        self.assertTrue(found, "no concession anywhere — the test proved nothing")

    def test_the_run_is_deterministic(self):
        arg = encode_syllogism(Syllogism(1, "AII"), "raw")
        a, _ = _debate(arg, seed=3)
        b, _ = _debate(arg, seed=3)
        self.assertEqual((a.winner, a.stand_m, a.stand_q),
                         (b.winner, b.stand_m, b.stand_q))

    def test_a_last_round_standing_is_never_reported_as_zero_by_accident(self):
        """It was, until the weave was actually run. 0.00 must mean measured-zero."""
        c, _ = _debate(encode_syllogism(Syllogism(1, "AAA"), "raw"))
        self.assertEqual(c.rounds[-1].stand_m, c.stand_m)
        self.assertEqual(c.rounds[-1].stand_q, c.stand_q)

    def test_different_evidence_produces_different_debates(self):
        """If every syllogism argued the same way the weave would be reading nothing."""
        seen = {_debate(encode_syllogism(s, "raw"))[0].stand_m
                for s in all_syllogisms()[:40]}
        self.assertGreater(len(seen), 20)


class TestTheGateIsLoadBearing(unittest.TestCase):
    """Switch the דחייה off and require the concession to stop happening.

    Same shape as `tests/test_chords.py::TestTheGuardIsLoadBearing`. A mechanism
    nobody has disabled is a mechanism nobody has demonstrated.
    """

    @staticmethod
    def _find_a_concession():
        for s in all_syllogisms():
            arg = encode_syllogism(s, "raw")
            c, _ = _debate(arg)
            if c.conceded_q is not None or c.conceded_m is not None:
                return arg, c
        raise AssertionError("no debate in the whole corpus ends in a דחייה")

    def test_with_the_key_cord_cut_nobody_ever_concedes(self):
        arg, before = self._find_a_concession()
        self.assertTrue(before.conceded_q is not None or
                        before.conceded_m is not None)

        # Cut the standing-pool out of the gate's `key` port and hold both keys
        # open instead. The evidence, the weights and the beats are otherwise
        # byte-identical — only the דחייה mechanism is gone.
        #
        # The propping-open knot needs its OWN self-thread at delay 2, and that
        # is not a detail: a single key spark opens the gate for exactly one
        # round and then drains with the tray, after which the gate fires on two
        # accumulated `in` sparks with an empty key and falls silent — which
        # looks exactly like a concession and is not one. The first draft of
        # this test did that and failed, correctly. A key must pulse every round
        # for as long as the seat is meant to keep speaking.
        w = build(RAW, seed=1)
        w.threads = [t for t in w.threads if t.port != "key"]
        w.knot("openkey", verb="pass", trigger="any")
        w.threads.append(Thread("openkey", "openkey", "in",
                                [Strand(weight=1.0, delay=2, drift=0.0)]))
        for seat in (SEAT_M, SEAT_Q):
            w.threads.append(Thread("openkey", f"{seat}_gate", "key",
                                    [Strand(weight=1.0, delay=1, drift=0.0)]))
        seed_argument(w, arg)
        w.seed("openkey", 1.0, beat=1)
        after = conclude(Loom().run(w, beats=DEFAULT_BEATS, verdict=None),
                         DEFAULT_BEATS)

        self.assertIsNone(after.conceded_m, "M still conceded with the gate open")
        self.assertIsNone(after.conceded_q, "Q still conceded with the gate open")
        self.assertTrue(after.machloket_stands)
        # …and every round now has both seats speaking, which is the thing the
        # key port was suppressing.
        for r in after.rounds:
            self.assertTrue(r.m_spoke and r.q_spoke, f"round {r.index}")

    def test_chazaka_is_what_lets_the_first_round_happen(self):
        """Seed the standing at zero and the debate cannot start at all."""
        arg = encode_syllogism(Syllogism(1, "AAA"), "raw")
        w = build(RAW, seed=1)

        def no_chazaka(weave, a):
            seed_argument(weave, a)
            weave.seeds = [s for s in weave.seeds if not s.dst.endswith("_stand")]

        no_chazaka(w, arg)
        c = conclude(Loom().run(w, beats=DEFAULT_BEATS, verdict=None),
                     DEFAULT_BEATS)
        self.assertFalse(any(r.m_spoke or r.q_spoke for r in c.rounds),
                         "a seat spoke with no חזקה behind it")
        self.assertGreater(CHAZAKA, 0)


class TestTheCorpusAndSplit(unittest.TestCase):

    def test_the_split_is_stratified_and_disjoint(self):
        items = syllogism_corpus("raw")
        tr, te = stratified_split(items)
        self.assertEqual(len(tr) + len(te), 256)
        self.assertFalse({a.id for a in tr} & {a.id for a in te})
        share = lambda g: sum(1 for a in g if a.winner == SEAT_M) / len(g)
        self.assertAlmostEqual(share(tr), share(te), delta=0.03)

    def test_the_split_is_the_same_every_time(self):
        a = [x.id for x in stratified_split(syllogism_corpus("raw"))[1]]
        b = [x.id for x in stratified_split(syllogism_corpus("raw"))[1]]
        self.assertEqual(a, b)

    def test_no_dispute_appears_on_both_sides_of_the_line(self):
        """The leak that made the first machloket number worthless.

        Each dispute is in the corpus twice, seats swapped. Split item-wise and
        the "held-out" half is the training half with the chairs moved.
        """
        from alma_reason.build_dataset import machloket_arguments
        tr, te = stratified_split(machloket_arguments())
        a = {x.meta["dispute"] for x in tr}
        b = {x.meta["dispute"] for x in te}
        self.assertFalse(a & b, f"dispute on both sides: {sorted(a & b)}")
        self.assertEqual(len(a) + len(b), 14)
        # and both seatings of every dispute travel together
        for group in (tr, te):
            counts = {}
            for x in group:
                counts[x.meta["dispute"]] = counts.get(x.meta["dispute"], 0) + 1
            self.assertTrue(all(n == 2 for n in counts.values()), counts)

    def test_no_machloket_item_claims_to_be_verified(self):
        for m in machloket.corpus():
            self.assertFalse(m.verified, m.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
