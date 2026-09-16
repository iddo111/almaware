"""Unit tests for the ALMA loom, verbs, triggers, and text formats.

    python -m unittest discover -s tests -v      (from the repo root)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alma import (Loom, Strand, Weave, WeaveError,          # noqa: E402
                  from_json, parse_voice, to_json, to_voice)
from alma.text import from_dict                             # noqa: E402


def run(w, beats=None):
    return Loom().run(w, beats)


class TestVerbsAndStrands(unittest.TestCase):
    def test_weights_and_bias_do_the_arithmetic(self):
        # C->F: strand weight 1.8, knot bias 32. No arithmetic in any knot.
        w = (Weave("heat")
             .knot("c").knot("c2f", "sum", bias=32).knot("show", "fringe")
             .thread("c", "c2f", strands=[Strand(1.8, 1)])
             .thread("c2f", "show")
             .seed("c", 100))
        self.assertEqual(run(w).fringe("show"), [212.0])

    def test_fibonacci_from_two_strands(self):
        # One knot, one self-thread, two strands (d1 and d2).
        w = (Weave("fib")
             .knot("f", "sum").knot("show", "fringe")
             .thread("f", "f", strands=[Strand(1, 1), Strand(1, 2)])
             .thread("f", "show")
             .seed("f", 1))
        vals = [int(v) for v in run(w, beats=10).fringe("show")]
        self.assertEqual(vals, [1, 1, 2, 3, 5, 8, 13, 21, 34])

    def test_prod(self):
        w = (Weave().knot("m", "prod").knot("o", "fringe")
             .thread("m", "o").seed("m", 3).seed("m", 4))
        self.assertEqual(run(w).fringe("o"), [12.0])

    def test_pool_accumulates_across_fires(self):
        w = (Weave().knot("p", "pool").knot("o", "fringe")
             .thread("p", "o")
             .seed("p", 1, beat=1).seed("p", 2, beat=2).seed("p", 3, beat=3))
        self.assertEqual(run(w).fringe("o"), [1.0, 3.0, 6.0])

    def test_gate_blocks_without_key_and_passes_with(self):
        blocked = (Weave().knot("g", "gate").knot("o", "fringe")
                   .thread("g", "o").seed("g", 5))
        self.assertEqual(run(blocked).fringe("o"), [])
        opened = (Weave().knot("g", "gate", trigger="count 2")
                  .knot("o", "fringe").thread("g", "o")
                  .seed("g", 5).seed("g", 1, port="key"))
        self.assertEqual(run(opened).fringe("o"), [5.0])

    def test_negative_weight_subtracts(self):
        w = (Weave().knot("a").knot("d", "sum", trigger="count 2")
             .knot("o", "fringe")
             .thread("a", "d", strands=[Strand(1, 1), Strand(-1, 2)])
             .thread("d", "o")
             .seed("a", 7))
        # 7 arrives at d on beat 2, -7 on beat 3 -> but count 2 waits: 0
        self.assertEqual(run(w).fringe("o"), [0.0])


class TestTriggersAndLoom(unittest.TestCase):
    def test_rise_integrates_across_beats(self):
        w = (Weave().knot("j", "sum", trigger="rise 2")
             .knot("o", "fringe").thread("j", "o")
             .seed("j", 0.9, 1).seed("j", 0.8, 2).seed("j", 0.6, 3)
             .seed("j", 0.5, 6))
        got = run(w, beats=10).fringe("o")
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0], 2.3)

    def test_deterministic(self):
        w = (Weave().knot("f", "sum").knot("o", "fringe")
             .thread("f", "f", strands=[Strand(1, 1), Strand(1, 2)])
             .thread("f", "o").seed("f", 1))
        a, b = run(w, 12), run(w, 12)
        self.assertEqual(a.fringes, b.fringes)
        self.assertEqual([(f.beat, f.knot, f.spoke) for f in a.fires],
                         [(f.beat, f.knot, f.spoke) for f in b.fires])

    def test_halts_when_silent(self):
        w = (Weave().knot("a").knot("o", "fringe")
             .thread("a", "o").seed("a", 1))
        r = run(w, beats=1000)
        self.assertTrue(r.finished)
        self.assertLess(r.beats, 10)


class TestEdgeCases(unittest.TestCase):
    """Cycles, delay guards, and seed-beat guards."""

    def test_cycle_hits_horizon_and_reports_unfinished(self):
        # a->b->a with weight 1 echoes forever; the horizon must cut it
        # and Result.finished must honestly say so.
        w = (Weave("loop")
             .knot("a", "sum").knot("b", "sum")
             .thread("a", "b").thread("b", "a")
             .seed("a", 1))
        r = run(w, beats=16)
        self.assertFalse(r.finished)
        self.assertEqual(r.beats, 16)
        # the spark circulates: exactly one fire per beat (a on odd
        # beats, b on even), so 16 fires in 16 beats.
        self.assertEqual(len(r.fires), 16)
        self.assertEqual([f.knot for f in r.fires[:4]], ["a", "b", "a", "b"])

    def test_negative_and_fractional_delays_rejected(self):
        for bad in (-3, 0.5, -0.1):
            w = (Weave().knot("a").knot("b")
                 .thread("a", "b", strands=[Strand(1, bad)])
                 .seed("a", 1))
            with self.assertRaises(WeaveError, msg=f"delay {bad}"):
                run(w)

    def test_seed_beat_below_one_rejected(self):
        for bad in (0, -2):
            w = Weave().knot("a").seed("a", 1, beat=bad)
            with self.assertRaises(WeaveError, msg=f"beat {bad}"):
                run(w)


class TestValidation(unittest.TestCase):
    def test_nothing_is_instant(self):
        w = (Weave().knot("a").knot("b")
             .thread("a", "b", strands=[Strand(1, 0)]))
        with self.assertRaises(WeaveError):
            run(w)

    def test_unknown_verb(self):
        with self.assertRaises(WeaveError):
            run(Weave().knot("a", "explode"))

    def test_fringe_has_no_voice(self):
        w = (Weave().knot("o", "fringe").knot("b").thread("o", "b"))
        with self.assertRaises(WeaveError):
            run(w)

    def test_thread_to_nowhere(self):
        with self.assertRaises(WeaveError):
            run(Weave().knot("a").thread("a", "ghost"))


class TestTextFormats(unittest.TestCase):
    VOICE = """
        weave heat
        knot c
        knot c2f sum bias 32
        knot show fringe
        thread c to c2f strand weight 1.8 delay 1
        thread c2f to show
        seed c value 100 at beat 1
        run 8 beats
    """

    def test_voice_parses_and_runs(self):
        w = parse_voice(self.VOICE)
        self.assertEqual(w.name, "heat")
        self.assertEqual(w.run_hint, 8)
        self.assertEqual(run(w).fringe("show"), [212.0])

    def test_json_roundtrip_preserves_behaviour(self):
        w = parse_voice(self.VOICE)
        w2 = from_json(to_json(w))
        self.assertEqual(run(w).fringes, run(w2).fringes)

    def test_voice_roundtrip_preserves_behaviour(self):
        w = parse_voice(self.VOICE)
        w3 = parse_voice(to_voice(w))
        self.assertEqual(run(w).fringes, run(w3).fringes)

    def test_filler_words_are_forgiven(self):
        # Natural speech: extra fillers, commas, different order of fillers.
        w = parse_voice("weave t\nknot x\nknot o fringe\n"
                        "thread x into the o\n"
                        "seed x with value 4, at beat 2")
        self.assertEqual(run(w).fringe("o"), [4.0])

    def test_bad_utterance_reports_line(self):
        with self.assertRaises(WeaveError):
            parse_voice("weave t\nabracadabra a b c")


class TestJsonErrors(unittest.TestCase):
    """Malformed JSON/dicts must raise WeaveError, never a raw
    KeyError/ValueError/TypeError/JSONDecodeError."""

    def test_bad_json_syntax(self):
        with self.assertRaises(WeaveError) as cm:
            from_json("{not valid json,,,")
        self.assertIn("bad JSON", str(cm.exception))

    def test_knot_missing_name(self):
        with self.assertRaises(WeaveError) as cm:
            from_dict({"knots": [{"verb": "sum"}]})
        self.assertIn("knot #0", str(cm.exception))
        self.assertIn("name", str(cm.exception))

    def test_thread_missing_to(self):
        with self.assertRaises(WeaveError) as cm:
            from_dict({"knots": [{"name": "a"}],
                       "threads": [{"from": "a"}]})
        msg = str(cm.exception)
        self.assertIn("thread from 'a'", msg)
        self.assertIn("to", msg)

    def test_seed_missing_value(self):
        with self.assertRaises(WeaveError) as cm:
            from_dict({"knots": [{"name": "a"}],
                       "seeds": [{"to": "a"}]})
        msg = str(cm.exception)
        self.assertIn("seed to 'a'", msg)
        self.assertIn("value", msg)

    def test_bad_numeric_coercion(self):
        with self.assertRaises(WeaveError) as cm:
            from_dict({"knots": [{"name": "a"}],
                       "seeds": [{"to": "a", "value": "not-a-number"}]})
        msg = str(cm.exception)
        self.assertIn("seed to 'a'", msg)
        self.assertIn("value", msg)

    def test_valid_dict_still_loads_and_runs(self):
        d = {"weave": "heat",
             "knots": [{"name": "c"},
                       {"name": "c2f", "verb": "sum", "bias": 32},
                       {"name": "show", "verb": "fringe"}],
             "threads": [{"from": "c", "to": "c2f",
                          "strands": [{"weight": 1.8, "delay": 1}]},
                         {"from": "c2f", "to": "show"}],
             "seeds": [{"to": "c", "value": 100}],
             "run": 8}
        w = from_dict(d)
        self.assertEqual(w.name, "heat")
        self.assertEqual(w.run_hint, 8)
        self.assertEqual(run(w).fringe("show"), [212.0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
