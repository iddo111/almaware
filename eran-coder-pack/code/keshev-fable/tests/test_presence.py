"""presence tests — the 09:46 scar must be unrepeatable under this gate."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.presence import (ARM_TTL_S, IDLE_NO_ENTER_S, IDLE_NO_TYPE_S,  # noqa: E402
                          Presence)


class PresenceGateTests(unittest.TestCase):
    def test_constants_are_the_d003_ruling(self):
        self.assertEqual((IDLE_NO_ENTER_S, IDLE_NO_TYPE_S, ARM_TTL_S),
                         (120, 600, 900))

    def test_present_types_and_enters(self):
        p = Presence(idle_fn=lambda: 5.0)
        self.assertEqual(p.verdict(), (True, True, "ok"))

    def test_0946_shape_cannot_recur(self):
        """Iddo away 9 minutes, a video talking: may type, NEVER Enter."""
        p = Presence(idle_fn=lambda: 540.0)
        may_type, may_enter, reason = p.verdict()
        self.assertTrue(may_type)
        self.assertFalse(may_enter, "Enter as him while away IS the scar")
        self.assertEqual(reason, "idle_no_enter")

    def test_long_idle_types_nothing(self):
        p = Presence(idle_fn=lambda: 700.0)
        self.assertEqual(p.verdict(), (False, False, "idle_no_type"))

    def test_unreadable_clock_fails_open_type_closed_enter(self):
        p = Presence(idle_fn=lambda: None)
        self.assertEqual(p.verdict(), (True, False, "clock_unreadable"))

    def test_boundaries_are_inclusive(self):
        self.assertEqual(Presence(idle_fn=lambda: 120.0).verdict()[2],
                         "idle_no_enter")
        self.assertEqual(Presence(idle_fn=lambda: 600.0).verdict()[2],
                         "idle_no_type")


class ArmSwitchTests(unittest.TestCase):
    def test_armed_mode_default_off(self):
        self.assertFalse(Presence().armed_mode, "D-001: opt-in, never default")

    def test_armed_mode_blocks_without_arm(self):
        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)
        self.assertEqual(p.verdict(), (False, False, "arm_required"))

    def test_arm_grants_and_expires(self):
        """An arm that never expires re-creates 09:46 — expiry is the point."""
        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)
        p.arm(now=1000.0)
        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S - 1),
                         (True, True, "armed"))
        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S + 1),
                         (False, False, "arm_required"))

    def test_disarm_immediate(self):
        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)
        p.arm(now=1000.0)
        p.disarm()
        self.assertEqual(p.verdict(now=1001.0), (False, False, "arm_required"))


if __name__ == "__main__":
    unittest.main()
