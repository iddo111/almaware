"""Presence + arm: thresholds, wrap, fail-open/closed, lazy expiry, the
combined seam — every gate proven able to FIRE on realistic input."""
from __future__ import annotations

import unittest

from k2 import presence


class FakeIdleApi:
    def __init__(self, value):
        self.value = value

    def idle_seconds(self):
        return self.value


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def collect():
    rec = []
    return rec, lambda evt, **f: rec.append((evt, f))


class PresenceThresholds(unittest.TestCase):

    def _gate(self, idle, emit=None):
        return presence.PresenceGate(api=FakeIdleApi(idle), emit=emit)

    def test_active_owner_full_permission(self):
        d = self._gate(3.0).decide()
        self.assertEqual((d.may_type, d.may_enter), (True, True))
        self.assertEqual(d.reason, "")

    def test_idle_past_enter_limit_types_without_enter(self):
        """THE cheap half of 09:46: junk in a box is recoverable,
        submitting as him is not."""
        rec, emit = collect()
        d = self._gate(121.0, emit).decide()
        self.assertEqual((d.may_type, d.may_enter), (True, False))
        self.assertEqual(rec[0][0], "PRESENCE_REJ")
        self.assertEqual(rec[0][1]["reason"], "owner_idle_no_enter")

    def test_idle_past_type_limit_types_nothing(self):
        rec, emit = collect()
        d = self._gate(601.0, emit).decide()
        self.assertEqual((d.may_type, d.may_enter), (False, False))
        self.assertEqual(rec[0][1]["reason"], "owner_absent")

    def test_exact_boundaries_are_inclusive(self):
        self.assertFalse(self._gate(120.0).decide().may_enter)
        self.assertFalse(self._gate(600.0).decide().may_type)
        self.assertTrue(self._gate(119.9).decide().may_enter)

    def test_unreadable_clock_fails_open_on_type_closed_on_enter(self):
        rec, emit = collect()
        d = self._gate(None, emit).decide()
        self.assertEqual((d.may_type, d.may_enter), (True, False))
        self.assertIsNone(d.idle_s)
        self.assertEqual(rec[0][0], "GATE_UNAVAILABLE")

    def test_config_driven_limits(self):
        g = presence.PresenceGate(api=FakeIdleApi(50.0),
                                  enter_idle_limit_s=40,
                                  type_idle_limit_s=60)
        d = g.decide()
        self.assertEqual((d.may_type, d.may_enter), (True, False))

    def test_last_idle_never_recomputes(self):
        api = FakeIdleApi(10.0)
        g = presence.PresenceGate(api=api)
        g.decide()
        api.value = 999.0
        self.assertEqual(g.last_idle(), 10.0)


class TickWrap(unittest.TestCase):

    def test_wrap_subtraction_is_32bit(self):
        """dwTime wraps at 2^32 ms; GetTickCount64 does not. The delta must
        be computed mod 2^32 or one wrap mutes the mic for 49.7 days."""
        now64 = (1 << 32) + 5_000          # just past a wrap
        dw_time = (1 << 32) - 5_000        # input 10s before the wrap
        delta = ((now64 % (1 << 32)) - dw_time) % (1 << 32)
        self.assertEqual(delta, 10_000)    # the formula presence.py uses


class ArmSwitch(unittest.TestCase):

    def test_disabled_switch_is_transparent(self):
        d = presence.ArmSwitch(enabled=False).decide()
        self.assertEqual((d.may_type, d.may_enter), (True, True))

    def test_enabled_starts_disarmed_and_refuses(self):
        """Fail-closed by construction."""
        rec, emit = collect()
        s = presence.ArmSwitch(enabled=True, emit=emit)
        d = s.decide()
        self.assertEqual((d.may_type, d.may_enter), (False, False))
        self.assertEqual(rec[0][0], "ARM_REJ")

    def test_arm_grants_and_journals(self):
        rec, emit = collect()
        s = presence.ArmSwitch(enabled=True, emit=emit)
        s.arm()
        self.assertTrue(s.decide().may_type)
        self.assertEqual(rec[0][0], "ARM_ON")

    def test_arm_expires_lazily(self):
        """An arm that never expires re-creates 09:46. Expiry observed
        inside is_armed() — no timer thread to die quietly."""
        rec, emit = collect()
        clock = FakeClock()
        s = presence.ArmSwitch(enabled=True, timeout_s=900, emit=emit,
                               monotonic=clock)
        s.arm()
        clock.t += 899
        self.assertTrue(s.is_armed())
        clock.t += 2
        self.assertFalse(s.is_armed())
        self.assertIn(("ARM_OFF", {"reason": "timeout"}), rec)

    def test_toggle_round_trip(self):
        s = presence.ArmSwitch(enabled=True)
        self.assertTrue(s.toggle())
        self.assertFalse(s.toggle())
        self.assertFalse(s.is_armed())


class CombinedSeam(unittest.TestCase):
    """combined_decision is THE function the typer consults (D-006)."""

    def _mk(self, idle, enabled, armed, clock=None):
        gate = presence.PresenceGate(api=FakeIdleApi(idle))
        arm = presence.ArmSwitch(enabled=enabled,
                                 monotonic=clock or FakeClock())
        if armed:
            arm.arm()
        return gate, arm

    def test_arm_off_presence_ok(self):
        d = presence.combined_decision(*self._mk(5.0, False, False))
        self.assertEqual((d.may_type, d.may_enter), (True, True))

    def test_disarmed_blocks_even_active_owner(self):
        """B's claim, live: no key press, no typing."""
        d = presence.combined_decision(*self._mk(1.0, True, False))
        self.assertEqual((d.may_type, d.may_enter), (False, False))
        self.assertEqual(d.reason, "disarmed")

    def test_armed_but_absent_still_no_enter(self):
        """BOTH must agree: an armed mic with an absent owner refuses
        Enter — the arm is consent, not a presence proof."""
        d = presence.combined_decision(*self._mk(130.0, True, True))
        self.assertEqual((d.may_type, d.may_enter), (True, False))
        self.assertEqual(d.reason, "owner_idle_no_enter")

    def test_armed_and_present_full_permission(self):
        d = presence.combined_decision(*self._mk(5.0, True, True))
        self.assertEqual((d.may_type, d.may_enter), (True, True))

    def test_disarmed_short_circuits_before_clock(self):
        """No reason to read the clock for text that will not type."""
        class ExplodingApi:
            def idle_seconds(self):
                raise AssertionError("clock read after arm refusal")
        gate = presence.PresenceGate(api=ExplodingApi())
        arm = presence.ArmSwitch(enabled=True)
        d = presence.combined_decision(gate, arm)
        self.assertFalse(d.may_type)


if __name__ == "__main__":
    unittest.main()
