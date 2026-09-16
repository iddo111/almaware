"""Unit tests for the ALMA<->Godot bridge (alma/godot.py).

    python -m unittest discover -s tests -v      (from the repo root)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alma import Loom, Strand, Weave                        # noqa: E402
from alma.godot import layout, spark_trace, weave_scene      # noqa: E402
from alma.text import from_dict, to_dict                     # noqa: E402


def run(w, beats=None):
    return Loom().run(w, beats)


def _fib() -> Weave:
    return (Weave("fib")
            .knot("f", "sum").knot("show", "fringe")
            .thread("f", "f", strands=[Strand(1, 1), Strand(1, 2)])
            .thread("f", "show")
            .seed("f", 1))


def _heat() -> Weave:
    return (Weave("heat")
            .knot("c").knot("c2f", "sum", bias=32).knot("show", "fringe")
            .thread("c", "c2f", strands=[Strand(1.8, 1)])
            .thread("c2f", "show")
            .seed("c", 100).seed("c", 0, beat=3).seed("c", 37, beat=5))


def _council() -> Weave:
    return (Weave("council")
            .knot("judge", "sum", trigger="rise 2").knot("verdict", "fringe")
            .thread("judge", "verdict")
            .seed("judge", 0.9, 1).seed("judge", 0.8, 2)
            .seed("judge", 0.6, 3).seed("judge", 0.5, 6))


def _cycle() -> Weave:
    # a->b->a with weight 1 echoes forever: the horizon cuts it, but the
    # layout must still place both knots (SPEC.md: cycles are legal).
    return (Weave("loop")
            .knot("a", "sum").knot("b", "sum")
            .thread("a", "b").thread("b", "a")
            .seed("a", 1))


class TestLayoutDeterminism(unittest.TestCase):
    def test_same_weave_same_positions(self):
        for maker in (_fib, _heat, _council, _cycle):
            a = layout(maker())
            b = layout(maker())
            self.assertEqual(a, b, maker.__name__)

    def test_every_knot_appears_exactly_once(self):
        for maker in (_fib, _heat, _council, _cycle):
            w = maker()
            pos = layout(w)
            self.assertEqual(sorted(pos), sorted(w.knots))
            self.assertEqual(len(pos), len(w.knots))

    def test_cycle_still_lays_out(self):
        w = _cycle()
        pos = layout(w)
        self.assertEqual(set(pos), {"a", "b"})
        for p in pos.values():
            self.assertEqual(len(p), 3)

    def test_unreachable_knot_gets_its_own_ring(self):
        w = _fib()
        w.knot("stray")                 # no thread, no seed reaches it
        pos = layout(w)
        self.assertIn("stray", pos)
        # placed behind the seed layer (negative Z), not folded into it
        self.assertLess(pos["stray"][2], pos["f"][2])


class TestStrandsBecomeCords(unittest.TestCase):
    def test_strand_count_preserved_in_scene_json(self):
        for maker in (_fib, _heat, _council):
            w = maker()
            d = weave_scene(w)
            w2 = from_dict(d)
            total_before = sum(len(t.strands) for t in w.threads)
            total_after = sum(len(t.strands) for t in w2.threads)
            self.assertEqual(total_before, total_after, maker.__name__)
            # and each thread's own strand count matches, in order
            for t1, t2 in zip(w.threads, w2.threads):
                self.assertEqual(len(t1.strands), len(t2.strands))


class TestTraceMatchesLoom(unittest.TestCase):
    def test_fib_spark_arrivals_match_fringe_beats(self):
        w = _fib()
        r = run(w, beats=10)
        sparks = spark_trace(w, r)
        # 'show' has bias 0 and exactly one incoming strand per fire, so
        # every fringe record must be reproduced, beat for beat and value
        # for value, by exactly one scheduled spark arrival.
        recorded = sorted(r.fringes["show"])
        arrivals = sorted(
            (s["arrival_beat"], s["value"]) for s in sparks if s["to"] == "show")
        self.assertEqual(recorded, arrivals)

    def test_council_verdict_arrival_matches_run(self):
        w = _council()
        r = run(w, beats=10)
        sparks = spark_trace(w, r)
        got = r.fringe("verdict")
        self.assertEqual(len(got), 1)
        matching = [s for s in sparks
                    if s["to"] == "verdict" and abs(s["value"] - got[0]) < 1e-9]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["arrival_beat"], r.fringes["verdict"][0][0])

    def test_no_sparks_emitted_from_fringe_or_closed_gate(self):
        w = (Weave().knot("g", "gate").knot("o", "fringe").thread("g", "o")
             .seed("g", 5))               # no 'key' spark: gate stays shut
        r = run(w)
        self.assertEqual(r.fringe("o"), [])
        self.assertEqual(spark_trace(w, r), [])


class TestSceneIsAdditive(unittest.TestCase):
    def test_json_round_trips_through_from_dict_unchanged(self):
        for maker in (_fib, _heat, _council, _cycle):
            w = maker()
            r = run(w, beats=10)
            scene = weave_scene(w, r)
            self.assertIn("scene", scene)
            self.assertIn("trace", scene)
            w2 = from_dict(scene)
            self.assertEqual(run(w).fringes, run(w2).fringes)
            self.assertEqual(to_dict(w), to_dict(w2))

    def test_weave_scene_without_result_has_no_trace(self):
        d = weave_scene(_fib())
        self.assertNotIn("trace", d)
        self.assertIn("scene", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
