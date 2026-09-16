"""supervisor tests — last night's three false restarts must be unrepeatable."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.supervisor import (FAULTS, HEALTHY, MUTE, MUTE_SOFT, NO_MIC,  # noqa: E402
                            QUIET, STARTING, Supervisor)


class _MemJournal:
    def __init__(self):
        self.events = []

    def event(self, name, **fields):
        self.events.append((name, fields))
        return {"evt": name, **fields}

    def names(self):
        return [n for n, _ in self.events]


def sup(**kw):
    return Supervisor(_MemJournal(), **kw)


class VerdictTests(unittest.TestCase):
    def test_silent_room_with_heartbeats_is_quiet_not_a_fault(self):
        """THE scar of last night: a sleeping house restarted the mic all
        night. Zero segments = QUIET, never a fault."""
        s = sup()
        s._born -= 10_000                      # long past startup grace
        v, _ = s.verdict()
        self.assertEqual(v, QUIET)
        self.assertNotIn(v, FAULTS)

    def test_young_quiet_app_is_starting(self):
        s = sup()
        v, _ = s.verdict()
        self.assertEqual(v, STARTING)

    def test_no_usb_mic_is_idle_not_fault(self):
        s = Supervisor(_MemJournal(), mic_present_fn=lambda: False)
        self.assertEqual(s.verdict()[0], NO_MIC)

    def test_gated_decodes_are_healthy(self):
        """Iddo away with a TV: many decodes, zero typed, all gated —
        the mic WORKING. The old watchdog restarted it for this."""
        s = sup()
        s._born -= 10_000
        for _ in range(10):
            s.note_seg(); s.note_decode(); s.note_gated()
        self.assertEqual(s.verdict()[0], HEALTHY)

    def test_parked_decodes_are_not_mute(self):
        """A dead STT server parks records; parked ≠ dead middle."""
        s = sup()
        s._born -= 10_000
        for _ in range(5):
            s.note_seg(); s.note_parked()
        self.assertNotEqual(s._raw_verdict(1e9)[0], MUTE)

    def test_true_dead_middle_is_mute_after_persistence(self):
        s = sup()
        s._born -= 10_000
        for _ in range(5):
            s.note_seg()
        v1, _ = s.verdict(now=1000.0)          # first sighting → suspect
        self.assertEqual(v1, QUIET)
        v2, _ = s.verdict(now=1000.0 + 60)     # not persisted yet
        self.assertEqual(v2, QUIET)
        v3, _ = s.verdict(now=1000.0 + 121)    # persisted → real fault
        self.assertEqual(v3, MUTE)

    def test_fault_that_heals_resets_persistence(self):
        s = sup()
        s._born -= 10_000
        for _ in range(5):
            s.note_seg()
        s.verdict(now=1000.0)                  # suspect starts
        s.note_decode()                        # the middle came back
        v, _ = s.verdict(now=1000.0 + 200)
        self.assertNotIn(v, FAULTS)
        self.assertIsNone(s._fault_since)

    def test_unexplained_no_typing_is_soft_alarm_only(self):
        s = sup()
        s._born -= 10_000
        for _ in range(9):
            s.note_seg(); s.note_decode()
        s.verdict(now=2000.0)
        v, detail = s.verdict(now=2000.0 + 121)
        self.assertEqual(v, MUTE_SOFT)
        self.assertIn("never restart", detail)


class HeartbeatTests(unittest.TestCase):
    def test_heartbeat_carries_the_three_numbers(self):
        j = _MemJournal()
        s = Supervisor(j)
        s.note_seg(); s.note_decode(); s.note_typed()
        rec = s.heartbeat()
        for k in ("seg", "decode", "typed", "gated", "parked", "verdict"):
            self.assertIn(k, rec)

    def test_fault_heartbeat_raises_alarm_event(self):
        j = _MemJournal()
        s = Supervisor(j)
        s._born -= 10_000
        for _ in range(5):
            s.note_seg()
        s.verdict(now=3000.0)
        s.heartbeat(now=3000.0 + 121)
        self.assertIn("ALARM", j.names())

    def test_healthy_heartbeat_no_alarm(self):
        j = _MemJournal()
        s = Supervisor(j)
        s.note_seg(); s.note_decode(); s.note_typed()
        s.heartbeat()
        self.assertNotIn("ALARM", j.names())

    def test_roll_clears_the_window(self):
        s = sup()
        s.note_seg()
        s.roll()
        self.assertEqual(s.win.seg, 0)


if __name__ == "__main__":
    unittest.main()
