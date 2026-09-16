"""KING'S CANONICAL TESTS - presence. Workers may not edit this file.

The law: 120s idle kills Enter, 600s kills typing; unreadable clock types
but never Enters; armed strictly BEFORE arm_time+ARM_TTL_S, expired AT it.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.presence import (ARM_TTL_S, IDLE_NO_ENTER_S, IDLE_NO_TYPE_S,  # noqa: E402
                          Presence)


class ConstantsTests(unittest.TestCase):
    def test_the_d003_ruling(self):
        self.assertEqual((IDLE_NO_ENTER_S, IDLE_NO_TYPE_S, ARM_TTL_S),
                         (120, 600, 900))


class IdleTests(unittest.TestCase):
    def test_present_types_and_enters(self):
        p = Presence(idle_fn=lambda: 5.0)
        self.assertEqual(p.verdict(), (True, True, "ok"))

    def test_idle_540_types_never_enters(self):
        p = Presence(idle_fn=lambda: 540.0)
        self.assertEqual(p.verdict(), (True, False, "idle_no_enter"))

    def test_idle_700_types_nothing(self):
        p = Presence(idle_fn=lambda: 700.0)
        self.assertEqual(p.verdict(), (False, False, "idle_no_type"))

    def test_boundaries_inclusive(self):
        self.assertEqual(Presence(idle_fn=lambda: 120.0).verdict()[2],
                         "idle_no_enter")
        self.assertEqual(Presence(idle_fn=lambda: 600.0).verdict()[2],
                         "idle_no_type")

    def test_unreadable_clock_fails_open_type_closed_enter(self):
        p = Presence(idle_fn=lambda: None)
        self.assertEqual(p.verdict(), (True, False, "clock_unreadable"))


class ArmTests(unittest.TestCase):
    def test_armed_mode_blocks_without_arm(self):
        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)
        self.assertEqual(p.verdict(now=1000.0),
                         (False, False, "arm_required"))

    def test_armed_strictly_before_ttl_expired_at_ttl(self):
        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)
        p.arm(now=1000.0)
        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S - 1)[2], "armed")
        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S)[2], "arm_required")

    def test_disarm_immediate(self):
        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)
        p.arm(now=1000.0)
        p.disarm()
        self.assertEqual(p.verdict(now=1001.0)[2], "arm_required")

    def test_rearm_extends(self):
        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)
        p.arm(now=1000.0)
        p.arm(now=1000.0 + 800)
        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S + 100)[2], "armed")


if __name__ == "__main__":
    unittest.main()
