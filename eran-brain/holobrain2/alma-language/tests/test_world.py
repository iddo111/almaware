"""The engine claim, tested: a gang of children and a broken radio are one object.

    python -m unittest discover -s tests -v      (from the repo root)

Every test in TestSameObject calls only `thing`, `ear`, `bond`, `set_bond` and
`tell`. Nothing in `alma/world.py` knows which of the two it is running.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alma.loom import WeaveError                            # noqa: E402
from alma.world import World                                # noqa: E402


def alley():
    """1936, one alley. Shmulik trusts Rachel. Nobody trusts the Templar."""
    w = World("alley")
    w.thing("shmulik", listens=0.5)
    w.thing("rachel", listens=0.5)
    w.thing("templar", listens=0.5)
    w.ear("rumour")
    w.bond("shmulik", "rachel", 0.8)
    w.bond("shmulik", "templar", 0.2)
    w.bond("rachel", "rumour", 1.0)
    w.bond("templar", "rumour", 1.0)
    return w


def radio():
    """One broken radio. The aerial lead is cut; everything else is sound."""
    w = World("radio")
    w.thing("battery", listens=0.5)
    w.thing("coil", listens=0.5)
    w.thing("aerial", listens=0.5)
    w.ear("speaker")
    w.bond("battery", "coil", 1.0)
    w.bond("battery", "aerial", 0.0)        # the cut
    w.bond("coil", "speaker", 1.0)
    w.bond("aerial", "speaker", 1.0)
    return w


class TestGossip(unittest.TestCase):
    def test_a_strong_bond_carries_and_a_weak_one_does_not(self):
        heard = alley().tell("shmulik")
        # 1.0 x 0.8 = 0.8 clears Rachel's 0.5; 1.0 x 0.2 does not clear the Templar's.
        self.assertEqual(heard["rumour"], [0.8])

    def test_trust_earned_changes_what_the_world_does(self):
        w = alley()
        self.assertEqual(w.tell("shmulik")["rumour"], [0.8])
        w.nudge("shmulik", "templar", +0.4)          # you did him a favour
        # Both mouths now reach the rumour on the same beat, so the ear hears
        # ONE thing, louder, by exactly the bond that opened: 0.8 + 0.6.
        self.assertAlmostEqual(w.tell("shmulik")["rumour"][0], 1.4)

    def test_trust_lost_silences_a_mouth_that_used_to_speak(self):
        w = alley()
        w.set_bond("shmulik", "rachel", 0.3)         # she saw you lie
        self.assertEqual(w.tell("shmulik")["rumour"], [])


class TestCircuit(unittest.TestCase):
    def test_the_radio_is_broken(self):
        self.assertEqual(radio().tell("battery")["speaker"], [1.0])

    def test_repairing_the_lead_lights_the_second_path(self):
        w = radio()
        w.set_bond("battery", "aerial", 1.0)         # the minigame's one move
        self.assertEqual(w.tell("battery")["speaker"], [2.0])

    def test_a_cut_bond_is_not_the_same_as_no_bond(self):
        w = radio()
        self.assertEqual(w.bond_of("battery", "aerial"), 0.0)
        with self.assertRaises(WeaveError):
            w.bond("battery", "aerial", 1.0)         # it is tied; it is just dead


class TestSameObject(unittest.TestCase):
    """The claim itself. Same calls, same code path, two worlds."""

    def test_both_worlds_answer_the_same_five_methods(self):
        for w, source, ear in ((alley(), "shmulik", "rumour"),
                               (radio(), "battery", "speaker")):
            self.assertEqual(len(w.tell(source)[ear]), 1)

    def test_one_repair_raises_the_ear_by_the_bond_it_opened(self):
        # A favour and a soldering iron are the same move on the same graph:
        # open a bond of weight w, and the ear rises by exactly w.
        for w, source, ear, a, b in ((alley(), "shmulik", "rumour", "shmulik", "templar"),
                                     (radio(), "battery", "speaker", "battery", "aerial")):
            before = w.tell(source)[ear][0]
            w.set_bond(a, b, 0.7)
            after = w.tell(source)[ear][0]
            self.assertAlmostEqual(after - before, 0.7)

    def test_delay_is_distance_in_both(self):
        # News that has to cross the alley twice arrives a beat later, and so
        # does current through a longer lead. Same strand, same beat count.
        w = World("far")
        w.thing("a").thing("b").ear("end")
        w.bond("a", "b", 1.0, delay=3)
        w.bond("b", "end", 1.0, delay=1)
        # seeded at beat 1 -> a fires -> b at beat 4 -> b fires -> end at beat 5.
        self.assertEqual(w.tell("a", beats=4)["end"], [])
        self.assertEqual(w.tell("a", beats=5)["end"], [1.0])


class TestAskingTwiceDoesNotAskLouder(unittest.TestCase):
    def test_seeds_do_not_accumulate_across_queries(self):
        w = alley()
        first = w.tell("shmulik")["rumour"]
        for _ in range(5):
            again = w.tell("shmulik")["rumour"]
        self.assertEqual(first, again)


if __name__ == "__main__":
    unittest.main()
