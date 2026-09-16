"""ALMA v0.4 — what the CHORD must do, and what it must refuse.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז״ל.

THE RULE THIS FILE IS WRITTEN UNDER
-----------------------------------
Of ten failures caught in this workspace on 2026-09-05, **zero** were caught by
whoever built the thing. So the tests here are not written to show the chord
working. They are written to try to make it lie, in the four ways it plausibly
could:

  1. it quietly repeats instead of scaling      (TestTheRepetitionTrap)
  2. it quietly broadcasts a mismatch away      (TestWidthIsRefusedNotFixed)
  3. it quietly promotes a v0.3 scalar          (TestV03IsUntouched)
  4. it quietly drops voices when written down  (TestTheTranscriptCarriesIt)

And one test exists to prove the SUITE can fail at all: `TestTheGuardIsLoadBearing`
switches the width check off, reruns the identical weave, and demands a silently
WRONG answer. If that test ever passes with the guard still on, the guard is
decoration and every other test in this file is worth nothing.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alma import (Chord, ChordWidthError, Loom, Strand, Weave, WeaveError,  # noqa: E402
                  chord, from_json, parse_voice, to_json, to_voice, spells)
from alma import chords as chordmod                                         # noqa: E402


def run(w: Weave, beats: int | None = None):
    return Loom().run(w, beats)


# ---------------------------------------------------------------- 1. the trap

class TestTheRepetitionTrap(unittest.TestCase):
    """`tuple * int` is REPETITION. The loom multiplies a spark by a weight on
    every beat of every run. If Chord had inherited that operator, an integer
    weight would have made a 3-voice colour into a 9-voice nothing — and the
    render would still have produced a picture."""

    def test_the_danger_is_real_not_hypothetical(self):
        # what the INHERITED operator does, called explicitly. This assertion is
        # the reason the overrides exist; if tuple ever stops doing this, the
        # overrides can be reconsidered.
        c = chord(1.0, 2.0)
        self.assertEqual(len(tuple.__mul__(c, 3)), 6)
        self.assertEqual(len(tuple.__add__(c, c)), 4)

    def test_a_chord_times_an_int_scales(self):
        self.assertEqual(chord(1.0, 2.0) * 3, chord(3.0, 6.0))
        self.assertEqual(3 * chord(1.0, 2.0), chord(3.0, 6.0))
        self.assertEqual(len(chord(1.0, 2.0) * 3), 2)

    def test_a_chord_plus_a_chord_adds(self):
        self.assertEqual(chord(1.0, 2.0) + chord(3.0, 4.0), chord(4.0, 6.0))
        self.assertEqual(len(chord(1.0, 2.0) + chord(3.0, 4.0)), 2)

    def test_an_integer_weight_through_a_real_loom_scales(self):
        """The trap sprung in situ: a whole-number strand weight."""
        w = Weave("int-weight")
        w.knot("a").knot("out", verb="fringe")
        w.thread("a", "out", strands=[Strand(weight=3, delay=1)])   # int, not 3.0
        w.seed("a", [0.2, 0.4, 0.6])
        got = run(w, 6).fringe("out")[0]
        self.assertIsInstance(got, Chord)
        self.assertEqual(len(got), 3, "an int weight repeated the chord")
        for a, b in zip(got, (0.6, 1.2, 1.8)):
            self.assertAlmostEqual(a, b)

    def test_a_negative_weight_flips_every_voice(self):
        w = Weave("neg")
        w.knot("a").knot("out", verb="fringe")
        w.thread("a", "out", strands=[Strand(weight=-1.0)])
        w.seed("a", [1.0, -2.0])
        self.assertEqual(run(w, 6).fringe("out")[0], chord(-1.0, 2.0))


# ------------------------------------------------------- 2. width is refused

class TestWidthIsRefusedNotFixed(unittest.TestCase):

    def _meet(self, left, right):
        """Two sparks arriving at ONE knot on ONE beat."""
        w = Weave("meet")
        w.knot("a").knot("b").knot("out", verb="fringe")
        w.thread("a", "out")
        w.thread("b", "out")
        w.seed("a", left)
        w.seed("b", right)
        return w

    def test_a_scalar_and_a_chord_do_not_meet(self):
        with self.assertRaises(WeaveError) as cm:
            run(self._meet(1.0, [1.0, 2.0]), 6)
        msg = str(cm.exception)
        self.assertIn("out", msg)          # the knot, by name
        self.assertIn("beat", msg)         # and when
        self.assertIn("scalar spark", msg)
        self.assertIn("chord of 2 voices", msg)

    def test_two_chords_of_different_width_do_not_meet(self):
        with self.assertRaises(WeaveError) as cm:
            run(self._meet([1.0, 2.0, 3.0], [1.0, 2.0]), 6)
        self.assertIn("chord of 3 voices", str(cm.exception))
        self.assertIn("chord of 2 voices", str(cm.exception))

    def test_a_pool_keeps_the_width_it_was_born_with(self):
        w = Weave("pool-width")
        w.knot("a").knot("b").knot("p", verb="pool").knot("out", verb="fringe")
        w.thread("a", "p")
        w.thread("b", "p")
        w.thread("p", "out")
        w.seed("a", [1.0, 1.0], beat=1)
        w.seed("b", 5.0, beat=3)           # a scalar into a 2-voice pool
        with self.assertRaises(WeaveError) as cm:
            run(w, 12)
        self.assertIn("'p'", str(cm.exception))

    def test_a_pool_of_chords_accumulates_voice_by_voice(self):
        w = Weave("pool-ok")
        w.knot("a").knot("b").knot("p", verb="pool").knot("out", verb="fringe")
        w.thread("a", "p")
        w.thread("b", "p")
        w.thread("p", "out")
        w.seed("a", [1.0, 10.0], beat=1)
        w.seed("b", [2.0, 20.0], beat=4)
        got = run(w, 16).fringe("out")
        self.assertEqual(got[0], chord(1.0, 10.0))
        self.assertEqual(got[1], chord(3.0, 30.0))

    def test_a_chord_of_no_voices_is_not_a_spark(self):
        with self.assertRaises(ChordWidthError):
            Chord([])

    def test_a_word_is_not_a_chord(self):
        for bad in ("red", b"red", [1.0, "x"], [1.0, None], [True, 1.0],
                    [1.0, 2j], 7, None):
            with self.assertRaises(ChordWidthError, msg=repr(bad)):
                Chord(bad)

    def test_a_seed_that_is_not_a_spark_is_refused_by_name(self):
        w = Weave("bad-seed").knot("a")
        with self.assertRaises(WeaveError) as cm:
            w.seed("a", "red")
        self.assertIn("not a spark", str(cm.exception))


# ------------------------------------------------------- 3. v0.3 is untouched

class TestV03IsUntouched(unittest.TestCase):
    """The other 111 tests in this suite are the real regression proof — they are
    all v0.3 weaves and they all still pass. What is checked HERE is the thing
    those tests could not see: that nothing got silently promoted on the way."""

    def test_a_scalar_weave_still_speaks_plain_floats(self):
        w = Weave("plain")
        w.knot("a").knot("out", verb="fringe")
        w.thread("a", "out", strands=[Strand(weight=2.0)])
        w.seed("a", 3.0)
        got = run(w, 6).fringe("out")[0]
        self.assertIs(type(got), float, "a scalar spark was promoted to a chord")
        self.assertEqual(got, 6.0)

    def test_a_one_voice_chord_is_not_the_number_it_holds(self):
        self.assertNotEqual(chord(2.0), 2.0)
        self.assertEqual(chordmod.width(2.0), 0)
        self.assertEqual(chordmod.width(chord(2.0)), 1)

    def test_a_scalar_and_a_one_voice_chord_still_do_not_meet(self):
        """The most tempting broadcast of all, and it is refused like the rest."""
        w = Weave("one-voice")
        w.knot("a").knot("b").knot("out", verb="fringe")
        w.thread("a", "out")
        w.thread("b", "out")
        w.seed("a", 1.0)
        w.seed("b", [1.0])
        with self.assertRaises(WeaveError):
            run(w, 6)

    def test_the_golden_fib_still_runs_and_is_still_scalar(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "golden_fib.json"), encoding="utf-8") as f:
            w = from_json(f.read())
        res = run(w)
        for name, vals in res.fringes.items():
            for _, v in vals:
                self.assertIs(type(v), float, f"{name} stopped being scalar")


# ---------------------------------------------------------- 4. the transcript

class TestTheTranscriptCarriesIt(unittest.TestCase):
    """v0.2 dropped `drift` in silence when a weave was written down. That must
    not happen to a chord's voices."""

    def _w(self):
        w = Weave("paint")
        w.knot("stroke").knot("canvas", verb="fringe")
        w.thread("stroke", "canvas", strands=[Strand(weight=0.5, delay=3)])
        w.seed("stroke", [0.84, 0.36, 0.26], beat=2)
        return w

    def test_json_round_trip_keeps_every_voice(self):
        back = from_json(to_json(self._w()))
        self.assertEqual(back.seeds[0].value, chord(0.84, 0.36, 0.26))
        self.assertEqual(back.seeds[0].beat, 2)
        self.assertEqual(run(back, 12).fringe("canvas")[0],
                         chord(0.42, 0.18, 0.13))

    def test_json_writes_a_chord_as_a_list_and_a_scalar_as_a_number(self):
        d = json.loads(to_json(self._w()))
        self.assertEqual(d["seeds"][0]["value"], [0.84, 0.36, 0.26])
        w2 = Weave("s").knot("a")
        w2.seed("a", 2.0)
        self.assertEqual(json.loads(to_json(w2))["seeds"][0]["value"], 2.0)

    def test_a_one_voice_chord_survives_json_as_a_chord(self):
        w = Weave("one").knot("a")
        w.seed("a", [2.0])
        self.assertEqual(from_json(to_json(w)).seeds[0].value, chord(2.0))
        self.assertIsInstance(from_json(to_json(w)).seeds[0].value, Chord)

    def test_voice_round_trip_keeps_every_voice(self):
        said = to_voice(self._w())
        self.assertIn("chord 3 0.84 0.36 0.26", said)
        back = parse_voice(said)
        self.assertEqual(back.seeds[0].value, chord(0.84, 0.36, 0.26))
        self.assertEqual(back.seeds[0].beat, 2)
        self.assertEqual(to_voice(back), said)

    def test_a_spoken_chord_can_be_written_by_hand(self):
        w = parse_voice("weave p\nknot canvas fringe\n"
                        "seed canvas chord 3 0.1 0.2 0.3 at beat 1\n")
        self.assertEqual(w.seeds[0].value, chord(0.1, 0.2, 0.3))

    def test_a_miscounted_chord_is_refused_not_truncated(self):
        with self.assertRaises(WeaveError) as cm:
            parse_voice("weave p\nknot c fringe\nseed c chord 4 0.1 0.2\n")
        self.assertIn("chord says 4 voices", str(cm.exception))

    def test_a_bad_chord_in_json_is_refused_by_name(self):
        bad = ('{"weave":"b","knots":[{"name":"a"}],'
               '"seeds":[{"to":"a","value":[0.1,"red"]}]}')
        with self.assertRaises(WeaveError) as cm:
            from_json(bad)
        self.assertIn("seed to 'a'", str(cm.exception))

    def test_a_knot_may_not_be_named_chord(self):
        with self.assertRaises(WeaveError):
            Weave("x").knot("chord").validate()


# ----------------------------------------------------------------- the verbs

class TestEveryVerbLearnedChords(unittest.TestCase):

    def _two_in(self, verb, **kw):
        w = Weave(verb)
        w.knot("a").knot("b").knot("k", verb=verb, **kw).knot("out", verb="fringe")
        w.thread("a", "k")
        w.thread("b", "k")
        if verb != "fringe":
            w.thread("k", "out")
        w.seed("a", [1.0, 2.0, 3.0])
        w.seed("b", [10.0, 20.0, 30.0])
        return w

    def test_sum(self):
        self.assertEqual(run(self._two_in("sum"), 8).fringe("out")[0],
                         chord(11.0, 22.0, 33.0))

    def test_prod(self):
        self.assertEqual(run(self._two_in("prod"), 8).fringe("out")[0],
                         chord(10.0, 40.0, 90.0))

    def test_pass_is_still_sum(self):
        self.assertEqual(run(self._two_in("pass"), 8).fringe("out")[0],
                         chord(11.0, 22.0, 33.0))

    def test_fringe_records_the_chord_itself(self):
        w = self._two_in("fringe")
        got = run(w, 8).fringe("k")[0]
        self.assertEqual(got, chord(11.0, 22.0, 33.0))
        self.assertEqual(run(w, 8).width("k"), 3)

    def test_bias_lands_on_every_voice_because_a_constant_has_no_width(self):
        w = self._two_in("sum", bias=0.5)
        self.assertEqual(run(w, 8).fringe("out")[0],
                         chord(11.5, 22.5, 33.5))

    def test_a_gate_key_is_a_verdict_not_a_chord(self):
        """A key answers open/shut. A chord key totals ALL its voices, so no
        voice is silently privileged — and a scalar key behaves as in v0.3."""
        for key, opens in (([1.0, -0.5], True),      # totals +0.5
                           ([1.0, -1.0], False),     # totals 0.0
                           ([-1.0, -1.0], False),
                           (2.0, True)):
            w = Weave("g")
            w.knot("a").knot("k2").knot("g", verb="gate").knot("out", verb="fringe")
            w.thread("a", "g")
            w.thread("k2", "g", port="key")
            w.thread("g", "out")
            w.seed("a", [1.0, 2.0])
            w.seed("k2", key)
            got = run(w, 8).fringe("out")
            self.assertEqual(bool(got), opens, f"key={key!r}")
            if opens:
                self.assertEqual(got[0], chord(1.0, 2.0))

    def test_a_rise_trigger_counts_every_voice(self):
        w = Weave("rise")
        w.knot("a").knot("k", trigger="rise 5").knot("out", verb="fringe")
        w.thread("a", "k")
        w.thread("k", "out")
        w.seed("a", [2.0, 2.0, 2.0])          # totals 6 >= 5
        self.assertEqual(run(w, 8).fringe("out")[0], chord(2.0, 2.0, 2.0))

    def test_a_rise_trigger_that_does_not_reach_stays_silent(self):
        w = Weave("rise2")
        w.knot("a").knot("k", trigger="rise 5").knot("out", verb="fringe")
        w.thread("a", "k")
        w.thread("k", "out")
        w.seed("a", [1.0, 1.0, 1.0])          # totals 3 < 5
        self.assertEqual(run(w, 8).fringe("out"), [])

    def test_a_spell_may_answer_a_chord(self):
        spells.teach("greyer", lambda vs: [sum(v[i] for v in vs) / len(vs)
                                           for i in range(len(vs[0]))],
                     replace=True)
        w = Weave("sp")
        w.knot("a").knot("b")
        w.knot("k", verb="spell", spell="greyer").knot("out", verb="fringe")
        w.thread("a", "k")
        w.thread("b", "k")
        w.thread("k", "out")
        w.seed("a", [1.0, 2.0])
        w.seed("b", [3.0, 6.0])
        self.assertEqual(run(w, 8).fringe("out")[0], chord(2.0, 4.0))

    def test_a_spell_that_answers_nonsense_is_refused_by_name(self):
        spells.teach("liar", lambda vs: "red", replace=True)
        w = Weave("sp2")
        w.knot("a").knot("k", verb="spell", spell="liar").knot("out", verb="fringe")
        w.thread("a", "k")
        w.thread("k", "out")
        w.seed("a", [1.0, 2.0])
        with self.assertRaises(WeaveError) as cm:
            run(w, 8)
        self.assertIn("liar", str(cm.exception))
        self.assertIn("chord of numbers", str(cm.exception))

    def test_plasticity_still_works_under_chords(self):
        """`drift` adjusts ONE number — the weight — so a chord must not change
        how a cord learns."""
        w = Weave("plastic")
        w.knot("a").knot("out", verb="fringe")
        w.thread("a", "out", strands=[Strand(weight=1.0, drift=0.5)])
        w.seed("a", [1.0, 1.0], beat=1)
        res = run(w, 8)
        self.assertIsNotNone(res.learned)
        self.assertEqual(len(res.learned), 1)
        self.assertGreater(res.learned[0], 1.0)   # the cord helped 'out' fire


# ------------------------------------------- the test that proves it can fail

class TestTheGuardIsLoadBearing(unittest.TestCase):
    """Make the suite fail on purpose, once, to prove it can.

    Every other refusal test above passes because `chord._widths` raises. If that
    function were decoration — if the loom would have produced the same refusal
    anyway — those tests would prove nothing. So: switch the width check off,
    replace it with the broadcasting behaviour every other array language has,
    and run the IDENTICAL weave. It must then produce a silently wrong answer.

    That is the failure mode being defended against, demonstrated rather than
    described.
    """

    def test_without_the_width_check_the_wrong_answer_is_silent(self):
        w = Weave("meet")
        w.knot("a").knot("b").knot("out", verb="fringe")
        w.thread("a", "out")
        w.thread("b", "out")
        w.seed("a", 1.0)
        w.seed("b", [10.0, 20.0])

        # 1. with the guard: a refusal that names the knot
        with self.assertRaises(WeaveError):
            run(w, 6)

        # 2. without it: numpy-style broadcasting, and NO complaint
        real_widths = chordmod._widths
        real_add = Chord.__add__

        def broadcasting_widths(sparks):
            return max((chordmod.width(s) for s in sparks), default=0)

        def broadcasting_add(self, other):
            if isinstance(other, Chord) and len(self) != len(other):
                short, long = sorted((self, other), key=len)
                return Chord(a + b for a, b in
                             zip(list(short) * len(long), long))
            return real_add(self, other)

        chordmod._widths = broadcasting_widths
        Chord.__add__ = broadcasting_add
        try:
            got = run(w, 6).fringe("out")
        finally:
            chordmod._widths = real_widths
            Chord.__add__ = real_add

        self.assertTrue(got, "the mutation should have produced an answer")
        self.assertEqual(got[0], chord(11.0, 21.0),
                         "the mutation did not produce the silent wrong answer "
                         "this test exists to demonstrate")

        # 3. and with the guard restored, the refusal is back — so the mutation
        #    really was the only thing standing between silence and a name.
        with self.assertRaises(WeaveError):
            run(w, 6)


if __name__ == "__main__":
    unittest.main()


# ------------------------------------- the bug this file found in the OLD code

class TestAKnotMayBeCalledA(unittest.TestCase):
    """A weave whose knot is named for a FILLER word must still round-trip.

    Found 2026-09-05 while probing the chord work, in code that predates it:
    `to_voice` wrote `knot a` bare, the §9 filler stripper ate the name on the way
    back in, and `parse_voice` raised an IndexError **on its own output**. Every
    weave in the existing suite is named for what it does (`f`, `show`, `heat`), so
    nothing ever pointed the format at itself with a name like `a`.

    It is the same shape as the v0.2 scar `alma/text.py` already carries a
    paragraph about — a transcript that quietly loses part of the weave — so the
    fix is the one that module already had to hand: quote a name that needs it.
    """

    FILLER_NAMES = ("a", "an", "the", "to", "in", "of", "and", "on", "from",
                    "value", "beat", "named", "with", "into", "then", "at")

    def test_every_filler_word_survives_being_a_knot_name(self):
        for name in self.FILLER_NAMES:
            with self.subTest(name=name):
                w = Weave("t")
                w.knot(name).knot("out", verb="fringe")
                w.thread(name, "out")
                w.seed(name, [1.0, 2.0])
                said = to_voice(w)
                back = parse_voice(said)
                self.assertIn(name, back.knots, f"'{name}' vanished from {said!r}")
                self.assertEqual(to_voice(back), said)
                self.assertEqual(run(back, 8).fringe("out")[0], chord(1.0, 2.0))

    def test_a_weave_may_be_called_the(self):
        w = Weave("the").knot("k", verb="fringe")
        w.seed("k", 1.0)
        self.assertEqual(parse_voice(to_voice(w)).name, "the")

    def test_a_port_may_be_called_a_filler_word(self):
        w = Weave("t")
        w.knot("src").knot("g", verb="gate").knot("out", verb="fringe")
        w.thread("src", "g", port="in")
        w.thread("src", "g", port="of")        # a filler word as a port name
        w.thread("g", "out")
        w.seed("src", 1.0)
        back = parse_voice(to_voice(w))
        self.assertEqual([t.port for t in back.threads], ["in", "of", "in"])

    def test_an_ordinary_name_is_still_written_bare(self):
        """The fix must not churn every .voice file already on disk."""
        w = Weave("fib").knot("f", verb="sum").knot("show", verb="fringe")
        w.thread("f", "show")
        w.seed("f", 1.0)
        said = to_voice(w)
        self.assertIn("weave fib", said)
        self.assertIn("knot f sum", said)
        self.assertIn("thread f to show", said)
        self.assertIn("seed f value 1 at beat 1", said)
        self.assertNotIn('"', said)


class TestTheOneExceptionToTheWidthRule(unittest.TestCase):
    """`spell` sees its tray as it arrived, mixed widths and all — on purpose.

    Every other verb refuses a mixed tray (TestWidthIsRefusedNotFixed). `spell`
    does not, because `spell` is the verb that exists to do what the six combining
    verbs cannot, and "scale this colour by this number" is exactly that. This
    class exists so the exception is PINNED rather than merely true: if someone
    later tightens the width check across all verbs, these fail and force the
    decision to be made again instead of drifting.
    """

    def _mixed(self, spell_name):
        w = Weave("mix")
        w.knot("num").knot("col")
        w.knot("k", verb="spell", spell=spell_name).knot("out", verb="fringe")
        w.thread("num", "k")
        w.thread("col", "k")
        w.thread("k", "out")
        w.seed("num", 0.5)
        w.seed("col", [0.8, 0.4, 0.2])
        return w

    def test_a_spell_receives_a_scalar_and_a_chord_together(self):
        seen = []
        spells.teach("look", lambda vs: seen.append(vs) or 0.0, replace=True)
        run(self._mixed("look"), 8)
        self.assertEqual(len(seen), 1)
        widths = sorted(chordmod.width(v) for v in seen[0])
        self.assertEqual(widths, [0, 3],
                         "the spell did not get both a scalar and a 3-chord")

    def test_a_spell_can_therefore_scale_a_colour_by_a_number(self):
        def _dim(vs):
            nums = [v for v in vs if not isinstance(v, Chord)]
            cols = [v for v in vs if isinstance(v, Chord)]
            if not nums or not cols:
                return None
            return cols[0] * nums[0]
        spells.teach("dim", _dim, replace=True)
        got = run(self._mixed("dim"), 8).fringe("out")[0]
        self.assertEqual(got, chord(0.4, 0.2, 0.1))

    def test_the_spells_ANSWER_is_still_width_checked_downstream(self):
        """The exception ends at the spell. What it speaks is an ordinary spark."""
        spells.teach("three", lambda vs: [1.0, 2.0, 3.0], replace=True)
        w = Weave("after")
        w.knot("a").knot("k", verb="spell", spell="three").knot("meet")
        w.knot("out", verb="fringe")
        w.thread("a", "k")
        w.thread("k", "meet")
        w.thread("a", "meet", strands=[Strand(delay=2)])   # a SCALAR lands there too
        w.thread("meet", "out")
        w.seed("a", 1.0)
        with self.assertRaises(WeaveError) as cm:
            run(w, 10)
        self.assertIn("'meet'", str(cm.exception))
