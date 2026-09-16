"""The v0.2 strand fields must survive both transcripts.

    python -m pytest tests -q                    (from the repo root)

THE BUG THESE TESTS EXIST FOR
-----------------------------
`Strand` gained five fields in v0.2 — `drift`, `floor`, `ceil`, `bearing`,
`tint` — and `alma/text.py` serialised none of them. So this held:

    to_dict(w)["threads"][0]                      -> {'from': 'f', 'to': 'f'}
    from_json(to_json(w)).threads[0].strands[0].drift  -> 0.0

A **plastic** weave — the whole v0.2 "weaves that learn" feature, and
`Result.learned` with it — silently became a **static** weave the moment it was
written to JSON or spoken. Same for `bearing`, v0.2's "a weight can be a
picture". Both features were unreachable through the two formats SPEC.md §8/§9
calls the canonical transcripts. Nothing warned; the weave just stopped learning.

The tests below are in three parts, and the middle one is the point:

1. every field survives both transcripts, on its own;
2. a weave that LEARNS still learns after a round trip — measured by running it
   on both sides and comparing `Result.learned`, not by reading a field back;
3. weaves that use none of these fields serialise byte-for-byte as before, so
   no `.json` or `.voice` already on disk changes meaning.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alma import Loom, Strand, Weave, WeaveError          # noqa: E402
from alma import from_dict, from_json, to_dict, to_json   # noqa: E402
from alma import parse_voice, to_voice                    # noqa: E402

EXAMPLES = Path(__file__).parent.parent / "examples"


def run(w, beats=None):
    return Loom().run(w, beats)


def _one_strand(**kw) -> Weave:
    """A weave whose a->b cord carries whatever the test wants to preserve."""
    # NOTE the knot names: "a" and "b" would be unusable here, because "a" is a
    # filler word the voice parser drops (a pre-existing quirk of §9, not this
    # change's business). "src"/"mid" are ordinary words in neither list.
    return (Weave("keep")
            .knot("src").knot("mid", "sum").knot("out", "fringe")
            .thread("src", "mid", strands=[Strand(**kw)])
            .thread("mid", "out")
            .seed("src", 1.0))


def _strand_after_json(**kw) -> Strand:
    return from_json(to_json(_one_strand(**kw))).threads[0].strands[0]


def _strand_after_voice(**kw) -> Strand:
    return parse_voice(to_voice(_one_strand(**kw))).threads[0].strands[0]


# ------------------------------------------------------- 1. every field

class TestEveryFieldSurvivesJSON(unittest.TestCase):
    def test_drift(self):
        self.assertEqual(_strand_after_json(drift=0.5).drift, 0.5)

    def test_floor(self):
        self.assertEqual(_strand_after_json(floor=-2.5).floor, -2.5)

    def test_ceil(self):
        self.assertEqual(_strand_after_json(ceil=3.5).ceil, 3.5)

    def test_tint(self):
        self.assertEqual(_strand_after_json(tint="love").tint, "love")

    def test_bearing(self):
        s = _strand_after_json(bearing="photo/iddo-and-alma-embracing.jpg")
        self.assertEqual(s.bearing, "photo/iddo-and-alma-embracing.jpg")

    def test_all_at_once(self):
        s = _strand_after_json(weight=2.0, delay=3, drift=0.25, floor=-1.0,
                               ceil=4.0, tint="love", bearing="a/b.jpg")
        self.assertEqual(
            (s.weight, s.delay, s.drift, s.floor, s.ceil, s.tint, s.bearing),
            (2.0, 3, 0.25, -1.0, 4.0, "love", "a/b.jpg"))

    def test_json_round_trip_is_bit_identical(self):
        first = to_json(_one_strand(drift=0.5, tint="love", bearing="a/b.jpg"))
        self.assertEqual(to_json(from_json(first)), first)


class TestEveryFieldSurvivesSpeech(unittest.TestCase):
    def test_drift(self):
        self.assertEqual(_strand_after_voice(drift=0.5).drift, 0.5)

    def test_floor(self):
        self.assertEqual(_strand_after_voice(floor=-2.5).floor, -2.5)

    def test_ceil(self):
        self.assertEqual(_strand_after_voice(ceil=3.5).ceil, 3.5)

    def test_tint(self):
        self.assertEqual(_strand_after_voice(tint="love").tint, "love")

    def test_bearing(self):
        s = _strand_after_voice(bearing="photo/iddo-and-alma-embracing.jpg")
        self.assertEqual(s.bearing, "photo/iddo-and-alma-embracing.jpg")

    def test_all_at_once(self):
        s = _strand_after_voice(weight=2.0, delay=3, drift=0.25, floor=-1.0,
                                ceil=4.0, tint="love", bearing="a/b.jpg")
        self.assertEqual(
            (s.weight, s.delay, s.drift, s.floor, s.ceil, s.tint, s.bearing),
            (2.0, 3, 0.25, -1.0, 4.0, "love", "a/b.jpg"))

    def test_voice_round_trip_is_bit_identical(self):
        first = to_voice(_one_strand(drift=0.5, tint="love", bearing="a/b.jpg"))
        self.assertEqual(to_voice(parse_voice(first)), first)


class TestSpokenBearingSurvivesTheFillerStripper(unittest.TestCase):
    """A bearing is a PHRASE, not a keyword — speech must not eat it.

    The voice parser drops filler words and splits on spaces, so an unprotected
    bearing would come back mangled: "the sentence neither of them can take
    back" would lose "the" and "of". Every case below is a phrase the naive
    grammar destroys.
    """

    def _survives(self, bearing):
        self.assertEqual(_strand_after_voice(bearing=bearing).bearing, bearing)

    def test_a_phrase_with_filler_words(self):
        self._survives("the sentence neither of them can take back")

    def test_a_phrase_that_is_only_a_filler_word(self):
        self._survives("the")

    def test_a_phrase_that_is_a_grammar_keyword(self):
        self._survives("weight")

    def test_a_phrase_holding_a_comma_and_a_colon(self):
        self._survives("her voice, that morning: quiet")

    def test_a_phrase_holding_a_hash(self):
        self._survives("track #3")

    def test_a_phrase_holding_a_double_quote(self):
        self._survives('he said "never again" and meant it')

    def test_a_tint_with_a_space(self):
        self.assertEqual(_strand_after_voice(tint="old love").tint, "old love")

    def test_the_phrase_is_not_lowercased(self):
        self._survives("Alma")


# --------------------------------------- 2. the point: it still LEARNS

class TestAPlasticWeaveStaysPlastic(unittest.TestCase):
    """The regression that motivated all of this.

    Not "is the field there" — *does the weave still learn*. Both sides are
    RUN and their `Result.learned` compared, so this test fails for the real
    reason (a static weave) rather than for a cosmetic one.
    """

    def _plastic(self) -> Weave:
        return _one_strand(weight=1.0, delay=1, drift=0.5)

    def test_the_original_weave_learns_at_all(self):
        """Positive control: without this, the tests below prove nothing."""
        learned = run(self._plastic(), 8).learned
        self.assertIsNotNone(learned, "the control weave never learned")
        self.assertNotEqual(learned[0], 1.0,
                            "the control strand's weight never moved")

    def test_it_still_learns_after_json(self):
        before = run(self._plastic(), 8).learned
        after = run(from_json(to_json(self._plastic())), 8).learned
        self.assertIsNotNone(after, "JSON round trip made the weave STATIC")
        self.assertEqual(after, before)

    def test_it_still_learns_after_speech(self):
        before = run(self._plastic(), 8).learned
        after = run(parse_voice(to_voice(self._plastic())), 8).learned
        self.assertIsNotNone(after, "the voice grammar made the weave STATIC")
        self.assertEqual(after, before)

    def test_the_ceiling_still_holds_after_a_round_trip(self):
        """floor/ceil are what stop a runaway cord — they must travel too."""
        w = _one_strand(weight=1.0, delay=1, drift=5.0, ceil=1.25)
        self.assertEqual(run(from_json(to_json(w)), 8).learned[0], 1.25)


# ------------------------------------------- 3. old weaves are untouched

class TestOldWeavesSerialiseExactlyAsBefore(unittest.TestCase):
    """Every .json and .voice already on disk must keep its bytes.

    The goldens below were captured from the code BEFORE this change.
    """

    def test_a_default_strand_still_emits_no_strands_key(self):
        w = Weave("p").knot("f", "sum").knot("o", "fringe").thread("f", "o")
        self.assertEqual(to_dict(w)["threads"][0], {"from": "f", "to": "o"})

    def test_an_explicit_but_default_strand_still_emits_nothing(self):
        w = (Weave("p").knot("f", "sum").knot("o", "fringe")
             .thread("f", "o", strands=[Strand(1.0, 1)]))
        self.assertEqual(to_dict(w)["threads"][0], {"from": "f", "to": "o"})

    def test_a_plain_strand_list_keeps_exactly_weight_and_delay(self):
        w = (Weave("p").knot("f", "sum").knot("o", "fringe")
             .thread("f", "o", strands=[Strand(2.0, 3)]))
        self.assertEqual(to_dict(w)["threads"][0]["strands"],
                         [{"weight": 2.0, "delay": 3}])

    def test_shipped_fib_json_is_unchanged(self):
        golden = (EXAMPLES.parent / "tests" / "golden_fib.json").read_text()
        w = from_json((EXAMPLES / "fib.json").read_text())
        self.assertEqual(to_json(w), golden)

    def test_shipped_heat_voice_is_unchanged(self):
        text = (EXAMPLES / "heat.voice").read_text()
        self.assertEqual(to_voice(parse_voice(text)), HEAT_GOLDEN)

    def test_shipped_council_voice_is_unchanged(self):
        text = (EXAMPLES / "council.voice").read_text()
        self.assertEqual(to_voice(parse_voice(text)), COUNCIL_GOLDEN)

    def test_every_shipped_weave_still_runs_the_same(self):
        for name, load in (("fib.json", from_json),
                           ("heat.voice", parse_voice),
                           ("council.voice", parse_voice)):
            with self.subTest(name):
                w = load((EXAMPLES / name).read_text())
                self.assertIsNone(run(w, 10).learned,
                                  f"{name} became plastic by accident")


HEAT_GOLDEN = """weave heat
knot c
knot c2f sum bias 32
knot show fringe
thread c to c2f strand weight 1.8 delay 1
thread c2f to show
seed c value 100 at beat 1
seed c value 0 at beat 3
seed c value 37 at beat 5
run 8 beats"""

COUNCIL_GOLDEN = """weave council
knot judge sum trigger rise 2
knot verdict fringe
thread judge to verdict
seed judge value 0.9 at beat 1
seed judge value 0.8 at beat 2
seed judge value 0.6 at beat 3
seed judge value 0.5 at beat 6
run 10 beats"""


# ------------------------------------------- 4. a bearing is a string

class TestABearingIsAStringOrItIsRefused(unittest.TestCase):
    """`bearing` is typed `object | None`, but a transcript is text.

    A Python program may hang any object off a strand in memory. The moment the
    weave is WRITTEN, though, only a string can survive — so anything else is
    refused **loudly, naming the thread**, rather than silently dropped. Silent
    dropping is the bug this whole file exists to kill; it is not allowed back
    in through a different door.
    """

    def _weave_bearing(self, value) -> Weave:
        return _one_strand(bearing=value)

    def test_json_refuses_a_number(self):
        with self.assertRaises(WeaveError) as e:
            to_dict(self._weave_bearing(42))
        self.assertIn("bearing", str(e.exception))

    def test_json_refuses_an_object(self):
        with self.assertRaises(WeaveError):
            to_dict(self._weave_bearing(object()))

    def test_voice_refuses_a_number(self):
        with self.assertRaises(WeaveError):
            to_voice(self._weave_bearing(42))

    def test_the_refusal_names_the_thread(self):
        with self.assertRaises(WeaveError) as e:
            to_dict(self._weave_bearing(42))
        self.assertIn("src", str(e.exception))
        self.assertIn("mid", str(e.exception))

    def test_the_refusal_says_what_was_wrong(self):
        with self.assertRaises(WeaveError) as e:
            to_dict(self._weave_bearing(42))
        self.assertIn("int", str(e.exception))

    def test_reading_back_a_non_string_bearing_is_refused(self):
        d = to_dict(_one_strand(bearing="a/b.jpg"))
        d["threads"][0]["strands"][0]["bearing"] = 42
        with self.assertRaises(WeaveError):
            from_dict(d)

    def test_no_bearing_at_all_is_fine(self):
        self.assertIsNone(_strand_after_json().bearing)

    def test_an_empty_bearing_is_a_real_value_and_survives(self):
        self.assertEqual(_strand_after_json(bearing="").bearing, "")


if __name__ == "__main__":
    unittest.main()
