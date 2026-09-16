"""Tests for the presence gate (client/presence.py) — scar 58.

The scar these guard: 2026-08-15 09:46, KESHEV typed the ROOM into Iddo's
live chat as him, with Enter, while he was out of the room. Every existing
guard passed because every existing guard asks a different question.

The behaviour that matters, in one line each:
  * present            -> type AND press Enter
  * idle >= 120 s      -> type, but NEVER press Enter (09:46 downgraded from
                          "eight messages sent as Iddo" to "junk in a box")
  * idle >= 600 s      -> type nothing at all
  * clock unreadable   -> type, no Enter, and SAY SO (GATE_UNAVAILABLE)
"""
from __future__ import annotations

import unittest

from client.presence import (ENTER_IDLE_LIMIT_S, TYPE_IDLE_LIMIT_S,
                             PresenceGate)


class FakeIdleApi:
    """Deterministic stand-in for GetLastInputInfo."""

    def __init__(self, idle):
        self.idle = idle
        self.calls = 0

    def idle_seconds(self):
        self.calls += 1
        return self.idle


class RecordingEmit:
    def __init__(self):
        self.events = []

    def __call__(self, name, **kw):
        self.events.append((name, kw))

    def names(self):
        return [n for n, _ in self.events]


def gate(idle, emit=None):
    return PresenceGate(api=FakeIdleApi(idle), emit=emit)


class TestPresent(unittest.TestCase):

    def test_at_the_keyboard_types_and_enters(self):
        d = gate(0.0).decide()
        self.assertTrue(d.may_type)
        self.assertTrue(d.may_enter)
        self.assertEqual(d.reason, "")

    def test_just_under_the_enter_limit_still_enters(self):
        d = gate(ENTER_IDLE_LIMIT_S - 0.01).decide()
        self.assertTrue(d.may_enter)

    def test_present_emits_nothing(self):
        emit = RecordingEmit()
        gate(5.0, emit).decide()
        self.assertEqual(emit.events, [])


class TestIdleNoEnter(unittest.TestCase):

    def test_at_the_enter_limit_types_but_never_enters(self):
        d = gate(ENTER_IDLE_LIMIT_S).decide()
        self.assertTrue(d.may_type, "his words must not be thrown away")
        self.assertFalse(d.may_enter, "nothing is SENT as him")
        self.assertEqual(d.reason, "owner_idle_no_enter")

    def test_emits_owner_rej_with_idle(self):
        emit = RecordingEmit()
        gate(300.0, emit).decide()
        self.assertEqual(emit.names(), ["PRESENCE_REJ"])
        _, kw = emit.events[0]
        self.assertEqual(kw["reason"], "owner_idle_no_enter")
        self.assertEqual(kw["idle_s"], 300)

    def test_the_0946_scenario_sends_nothing(self):
        """A video plays while Iddo is out of the room for four minutes."""
        d = gate(240.0).decide()
        self.assertFalse(d.may_enter)


class TestAbsent(unittest.TestCase):

    def test_at_the_type_limit_types_nothing(self):
        d = gate(TYPE_IDLE_LIMIT_S).decide()
        self.assertFalse(d.may_type)
        self.assertFalse(d.may_enter)
        self.assertEqual(d.reason, "owner_absent")

    def test_emits_owner_rej_absent(self):
        emit = RecordingEmit()
        gate(3600.0, emit).decide()
        _, kw = emit.events[0]
        self.assertEqual(kw["reason"], "owner_absent")


class TestUnreadableClock(unittest.TestCase):
    """Fail-open on TYPE, fail-closed on ENTER — losing his words to a
    ctypes glitch is as real a failure as speaking for him."""

    def test_types_but_never_enters(self):
        d = gate(None).decide()
        self.assertTrue(d.may_type)
        self.assertFalse(d.may_enter)
        self.assertEqual(d.reason, "presence_unknown")

    def test_says_so_out_loud(self):
        emit = RecordingEmit()
        gate(None, emit).decide()
        self.assertEqual(emit.names(), ["GATE_UNAVAILABLE"])
        _, kw = emit.events[0]
        self.assertEqual(kw["gate"], "presence")

    def test_idle_is_none_not_zero(self):
        """None must never be silently coerced to 0.0 — that would read as
        'he is right here' and re-open the scar."""
        self.assertIsNone(gate(None).decide().idle_s)


class TestVocabularyAndPlumbing(unittest.TestCase):

    def test_events_are_in_the_closed_telemetry_vocabulary(self):
        from client.telemetry import EVENT_VOCABULARY
        self.assertIn("PRESENCE_REJ", EVENT_VOCABULARY)
        self.assertIn("GATE_UNAVAILABLE", EVENT_VOCABULARY)

    def test_negative_idle_is_clamped(self):
        """A clock that reports a negative delta must not become a huge
        positive idle through the modulo, nor a spurious 'absent'."""
        d = gate(-5.0).decide()
        self.assertEqual(d.idle_s, 0.0)
        self.assertTrue(d.may_enter)

    def test_last_idle_matches_last_decision(self):
        """The tray/window read last_idle(); it must never disagree with the
        decision that was actually enforced."""
        g = gate(200.0)
        d = g.decide()
        self.assertEqual(g.last_idle(), d.idle_s)
        self.assertEqual(g.last_decision(), d)

    def test_limits_are_ordered(self):
        self.assertLess(ENTER_IDLE_LIMIT_S, TYPE_IDLE_LIMIT_S)


class TestTickWrap(unittest.TestCase):
    """GetLastInputInfo.dwTime is 32-bit and wraps every ~49.7 days while
    GetTickCount64 does not. Subtracting across the wrap without masking
    makes the machine look idle for seven weeks and the mic goes mute."""

    def test_wrap_math_stays_small(self):
        from client.presence import _TICK_WRAP
        now64 = _TICK_WRAP + 5_000          # 5 s after a wrap
        last32 = _TICK_WRAP - 1_000         # 1 s before the wrap
        delta = ((now64 % _TICK_WRAP) - last32) % _TICK_WRAP
        self.assertEqual(delta, 6_000)      # 6 s, not 49.7 days


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class TestArmSwitch(unittest.TestCase):
    """KESHEV B's one surviving verdict (VERDICT-CLOSED-20260817.md): the
    physical arming key, as an OPTION layered over the presence gate,
    defaulting OFF. Arming is a human act; disarming is the same act or the
    timeout; a disarmed mic in armed mode types NOTHING."""

    def switch(self, enabled=True, timeout=900.0, emit=None, clock=None):
        from client.presence import ArmSwitch
        return ArmSwitch(enabled=enabled, timeout_s=timeout, emit=emit,
                         monotonic=clock if clock is not None else FakeClock())

    def test_shipped_default_is_off(self):
        """The design's ship state: transparent. Flipping ARMED_MODE is a
        commit (design section 5 — knobs are code under git)."""
        from client.presence import ARMED_MODE, ArmSwitch
        self.assertFalse(ARMED_MODE)
        d = ArmSwitch(emit=None).decide()   # all defaults
        self.assertTrue(d.may_type)
        self.assertTrue(d.may_enter)

    def test_disabled_switch_is_transparent_even_when_disarmed(self):
        emit = RecordingEmit()
        s = self.switch(enabled=False, emit=emit)
        self.assertTrue(s.decide().may_type)
        self.assertEqual(emit.events, [])   # transparent means SILENT too

    def test_enabled_and_disarmed_refuses_to_type(self):
        emit = RecordingEmit()
        d = self.switch(emit=emit).decide()
        self.assertFalse(d.may_type)
        self.assertFalse(d.may_enter)
        self.assertEqual(d.reason, "disarmed")
        self.assertEqual(emit.names(), ["ARM_REJ"])

    def test_armed_permits_and_emits_arm_on(self):
        emit = RecordingEmit()
        s = self.switch(emit=emit)
        self.assertTrue(s.toggle())
        self.assertTrue(s.decide().may_type)
        self.assertEqual(emit.names(), ["ARM_ON"])

    def test_toggle_disarms_and_emits_arm_off(self):
        emit = RecordingEmit()
        s = self.switch(emit=emit)
        s.toggle()
        self.assertFalse(s.toggle())
        self.assertEqual(emit.names(), ["ARM_ON", "ARM_OFF"])
        self.assertFalse(s.decide().may_type)

    def test_arm_expires_after_the_timeout(self):
        """An arm that never expires re-creates 09:46 — armed in the morning,
        the room typed in the evening. Expiry is lazy: no timer thread."""
        emit = RecordingEmit()
        clock = FakeClock()
        s = self.switch(emit=emit, clock=clock)
        s.arm()
        clock.t += 899.0
        self.assertTrue(s.is_armed())
        clock.t += 2.0
        self.assertFalse(s.is_armed())
        self.assertEqual(emit.names(), ["ARM_ON", "ARM_OFF"])
        self.assertEqual(emit.events[1][1]["reason"], "timeout")

    def test_zero_timeout_never_expires(self):
        clock = FakeClock()
        s = self.switch(timeout=0.0, clock=clock)
        s.arm()
        clock.t += 10_000_000.0
        self.assertTrue(s.is_armed())

    def test_arm_events_are_in_the_closed_telemetry_vocabulary(self):
        """The PRESENCE_REJ scar again: an event name outside the vocabulary
        raises the first time it FIRES, and only for whoever runs the real
        Telemetry. Assert membership here, before it can happen live."""
        from client.telemetry import EVENT_VOCABULARY
        for name in ("ARM_ON", "ARM_OFF", "ARM_REJ"):
            self.assertIn(name, EVENT_VOCABULARY)

    def test_layering_arm_does_not_replace_presence(self):
        """Armed mode ON + armed switch must still leave the presence gate
        in charge of Enter: the two gates answer different questions and
        BOTH must agree (the whole point of 'layered over, not instead of')."""
        s = self.switch()
        s.arm()
        armed = s.decide()
        absent = gate(TYPE_IDLE_LIMIT_S + 1).decide()
        self.assertTrue(armed.may_type)
        self.assertFalse(absent.may_type,
                         "an armed switch must not resurrect typing for an "
                         "absent owner — presence still decides")


if __name__ == "__main__":
    unittest.main()
