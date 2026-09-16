"""The seventh verb: `spell` — a knot that computes.

    python -m unittest discover -s tests -v      (from the repo root)

Two things are on trial here.

1. THE CLAIM: one `spell` knot computes XOR, which no single plain knot can.
   That claim has a FLOOR it can fall through: `TestFloor` exhaustively searches
   every plain single-knot weave in a grid of verbs x triggers x biases x strand
   weights, and the same search is run against AND as a positive control. If the
   search finds AND but not XOR, the impossibility is measured, not asserted.

2. THE SAFETY: a weave is DATA. Loading one must never run code. The hostile
   weaves below carry payloads in every field that could plausibly smuggle
   source, and a canary file on disk proves nothing ran.
"""
import os
import sys
import tempfile
import unittest
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alma import Loom, Strand, Weave, WeaveError         # noqa: E402
from alma import from_dict, from_json, to_dict, to_json  # noqa: E402
from alma import parse_voice, to_voice                   # noqa: E402
from alma import spells                                  # noqa: E402


def run(w, beats=None):
    return Loom().run(w, beats)


# The harness both halves of the XOR question share: two source knots feed one
# middle knot on the same beat; the middle knot's answer reaches a fringe.
def _two_in(a, b, verb, trigger="any", bias=0.0, spell="", w1=1.0, w2=1.0):
    return (Weave("xor")
            .knot("a").knot("b")
            .knot("d", verb, trigger, bias, spell=spell)
            .knot("out", "fringe")
            .thread("a", "d", strands=[Strand(w1, 1)])
            .thread("b", "d", strands=[Strand(w2, 1)])
            .thread("d", "out")
            .seed("a", a).seed("b", b))


ROWS = ((0, 0), (0, 1), (1, 0), (1, 1))
XOR = [(0.0,), (1.0,), (1.0,), (0.0,)]
AND = [(0.0,), (0.0,), (0.0,), (1.0,)]


def _table(**kw):
    """What this knot answers for each row of the truth table."""
    return [tuple(run(_two_in(a, b, **kw), 8).fringe("out")) for a, b in ROWS]


class TestTheSeventhVerb(unittest.TestCase):
    def test_one_spell_knot_computes_xor(self):
        self.assertEqual(_table(verb="spell", spell="xor"), XOR)

    def test_bias_is_added_to_the_spell_like_every_other_verb(self):
        w = (Weave().knot("d", "spell", bias=10, spell="xor")
             .knot("o", "fringe").thread("d", "o").seed("d", 1))
        self.assertEqual(run(w).fringe("o"), [11.0])

    def test_a_spell_may_speak_nothing_and_the_knot_stays_silent(self):
        spells.teach("mute", lambda vs: None, replace=True)
        w = (Weave().knot("d", "spell", spell="mute").knot("o", "fringe")
             .thread("d", "o").seed("d", 5))
        self.assertEqual(run(w).fringe("o"), [])

    def test_max_over_a_tray(self):
        w = (Weave().knot("d", "spell", trigger="count 3", spell="max")
             .knot("o", "fringe").thread("d", "o")
             .seed("d", 2).seed("d", 9).seed("d", 4))
        self.assertEqual(run(w).fringe("o"), [9.0])

    def test_the_spell_sees_the_in_tray_in_arrival_order(self):
        spells.teach("first", lambda vs: vs[0], replace=True)
        w = (Weave().knot("d", "spell", trigger="count 2", spell="first")
             .knot("o", "fringe").thread("d", "o")
             .seed("d", 7).seed("d", 3))
        self.assertEqual(run(w).fringe("o"), [7.0])

    def test_a_spell_that_answers_nonsense_is_a_weave_error(self):
        spells.teach("junk", lambda vs: "not a number", replace=True)
        w = (Weave().knot("d", "spell", spell="junk").knot("o", "fringe")
             .thread("d", "o").seed("d", 1))
        with self.assertRaises(WeaveError):
            run(w)

    def test_a_spell_that_raises_names_the_knot_and_the_spell(self):
        spells.teach("boom", lambda vs: 1 / 0, replace=True)
        w = (Weave().knot("d", "spell", spell="boom").knot("o", "fringe")
             .thread("d", "o").seed("d", 1))
        with self.assertRaises(WeaveError) as cm:
            run(w)
        self.assertIn("boom", str(cm.exception))
        self.assertIn("'d'", str(cm.exception))


class TestFloor(unittest.TestCase):
    """Could a plain knot have done it? Search, do not assume."""

    VERBS = ("pass", "sum", "prod", "pool", "gate")   # fringe has no voice
    TRIGGERS = ("any", "count 1", "count 2", "rise 0.5", "rise 1", "rise 2")
    NUMS = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)

    def _search(self, target):
        for verb, trig, bias, w1, w2 in product(
                self.VERBS, self.TRIGGERS, self.NUMS, self.NUMS, self.NUMS):
            if _table(verb=verb, trigger=trig, bias=bias,
                      w1=w1, w2=w2) == target:
                return (verb, trig, bias, w1, w2)
        return None

    def test_the_search_can_succeed_and_finds_AND(self):
        # Positive control. A search that cannot succeed proves nothing.
        self.assertIsNotNone(self._search(AND))

    def test_no_plain_single_knot_computes_xor(self):
        self.assertIsNone(self._search(XOR))


class TestTextRoundTrip(unittest.TestCase):
    def _weave(self):
        return (Weave("dendrite")
                .knot("d", "spell", trigger="count 2", bias=0.5, spell="xor")
                .knot("o", "fringe")
                .thread("d", "o").seed("d", 1).seed("d", 0))

    def test_json_round_trip_is_bit_identical(self):
        first = to_json(self._weave())
        self.assertEqual(to_json(from_json(first)), first)

    def test_json_carries_the_spell_name(self):
        d = to_dict(self._weave())
        self.assertEqual(d["knots"][0]["spell"], "xor")

    def test_voice_round_trip_is_bit_identical(self):
        first = to_voice(self._weave())
        self.assertIn("spell xor", first)
        self.assertEqual(to_voice(parse_voice(first)), first)

    def test_a_spell_weave_still_runs_after_a_round_trip(self):
        w = from_json(to_json(_two_in(1, 0, verb="spell", spell="xor")))
        self.assertEqual(run(w, 8).fringe("out"), [1.0])


class TestTheBookIsTheOnlyDoor(unittest.TestCase):
    """A weave carries a NAME. Only Python can put code behind that name."""

    def setUp(self):
        self.canary = Path(tempfile.gettempdir()) / (
            "alma_spell_canary_%d.txt" % os.getpid())
        if self.canary.exists():
            self.canary.unlink()

    tearDown = setUp

    def _payload(self):
        return ("__import__('pathlib').Path(%r).write_text('pwned')"
                % str(self.canary))

    def test_loading_a_hostile_weave_runs_nothing(self):
        hostile = {"alma": "0.1", "weave": "trojan",
                   "knots": [{"name": "d", "verb": "spell",
                              "spell": self._payload()},
                             {"name": "o", "verb": "fringe"}],
                   "threads": [{"from": "d", "to": "o"}],
                   "seeds": [{"to": "d", "value": 1}], "run": 4}
        w = from_dict(hostile)              # loading is pure data
        self.assertFalse(self.canary.exists())
        with self.assertRaises(WeaveError) as cm:
            run(w)                          # and running refuses, loudly
        self.assertIn("no such spell", str(cm.exception))
        self.assertFalse(self.canary.exists())

    def test_no_field_smuggles_source_into_a_weave(self):
        smuggle = {"alma": "0.1", "weave": "smuggle",
                   "knots": [{"name": "d", "verb": "sum",
                              "source": self._payload(),
                              "code": self._payload(),
                              "bias": 0}],
                   "threads": [], "seeds": [{"to": "d", "value": 1}],
                   "run": 3}
        w = from_dict(smuggle)
        run(w)
        self.assertFalse(self.canary.exists())
        # the extra fields are not part of the format and do not survive
        self.assertNotIn("source", to_dict(w)["knots"][0])
        self.assertNotIn("code", to_dict(w)["knots"][0])

    def test_the_voice_grammar_cannot_define_a_spell(self):
        with self.assertRaises(WeaveError):
            parse_voice("weave v\nknot d spell %s" % self._payload())
        self.assertFalse(self.canary.exists())

    def test_teach_refuses_a_string_it_would_have_to_evaluate(self):
        with self.assertRaises(WeaveError):
            spells.teach("evil", self._payload())
        self.assertFalse(self.canary.exists())

    def test_teach_refuses_to_silently_shadow_a_known_spell(self):
        with self.assertRaises(WeaveError):
            spells.teach("xor", lambda vs: 999.0)
        self.assertEqual(_table(verb="spell", spell="xor"), XOR)

    def test_teach_replaces_only_when_told_to(self):
        spells.teach("temp", lambda vs: 1.0, replace=True)
        spells.teach("temp", lambda vs: 2.0, replace=True)
        w = (Weave().knot("d", "spell", spell="temp").knot("o", "fringe")
             .thread("d", "o").seed("d", 0))
        self.assertEqual(run(w).fringe("o"), [2.0])

    def test_teach_refuses_a_name_the_text_formats_would_lose(self):
        for bad in ("weight", "value", "the", "bias", ""):
            with self.assertRaises(WeaveError):
                spells.teach(bad, lambda vs: 1.0)


class TestValidation(unittest.TestCase):
    def test_a_spell_knot_needs_a_spell(self):
        w = Weave().knot("d", "spell").knot("o", "fringe").thread("d", "o")
        with self.assertRaises(WeaveError):
            w.validate()

    def test_a_spell_name_on_a_plain_verb_is_refused(self):
        w = Weave().knot("d", "sum", spell="xor")
        with self.assertRaises(WeaveError):
            w.validate()

    def test_spell_is_the_seventh_verb(self):
        from alma.loom import VERBS
        self.assertEqual(len(VERBS), 7)
        self.assertIn("spell", VERBS)


if __name__ == "__main__":
    unittest.main()
