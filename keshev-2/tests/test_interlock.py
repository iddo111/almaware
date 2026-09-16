"""Interlock: the ticket law, both detectors, fail-closed on unprovable —
and an ENVIRONMENTAL test against the real KESHEV A on this machine."""
from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from k2 import interlock


class TicketLaw(unittest.TestCase):

    def test_ticket_cannot_be_constructed_directly(self):
        """The ONLY constructor is grant() — species-#4 countermeasure."""
        with self.assertRaises(TypeError):
            interlock.CaptureTicket(_token=object(), granted_at=0.0,
                                    via="forged")

    def test_grant_raises_while_rival_alive(self):
        v = interlock.InterlockVerdict(True, True, "mutex", "held")
        with self.assertRaises(interlock.RivalAliveError):
            v.grant()

    def test_grant_raises_when_unprovable(self):
        """Fail CLOSED: detectors dark is never permission."""
        v = interlock.InterlockVerdict(False, False, "none", "all dark")
        with self.assertRaises(interlock.RivalUnprovableError):
            v.grant()

    def test_grant_issues_ticket_when_provably_clear(self):
        v = interlock.InterlockVerdict(False, True, "mutex+journal", "clear")
        t = v.grant()
        self.assertEqual(t.via, "mutex+journal")


class CheckBranches(unittest.TestCase):
    """Every branch of check() proven reachable with injected detectors."""

    def _events(self):
        rec = []
        return rec, lambda evt, **f: rec.append((evt, f))

    def test_mutex_hit_wins_immediately(self):
        rec, emit = self._events()
        v = interlock.check(mutex_probe=lambda: True,
                            journal_age=lambda: 9999.0, emit=emit)
        self.assertTrue(v.rival_alive)
        self.assertEqual(v.via, "mutex")
        self.assertEqual(rec[0][0], "RIVAL_ALIVE")
        self.assertEqual(rec[0][1]["via"], "mutex")

    def test_fresh_journal_alone_means_alive(self):
        rec, emit = self._events()
        v = interlock.check(mutex_probe=lambda: False,
                            journal_age=lambda: 30.0, emit=emit)
        self.assertTrue(v.rival_alive)
        self.assertEqual(v.via, "journal")

    def test_probe_error_but_fresh_journal_means_alive(self):
        v = interlock.check(mutex_probe=lambda: None,
                            journal_age=lambda: 10.0)
        self.assertTrue(v.rival_alive)

    def test_both_clean_is_grantable(self):
        rec, emit = self._events()
        v = interlock.check(mutex_probe=lambda: False,
                            journal_age=lambda: 3600.0, emit=emit)
        self.assertFalse(v.rival_alive)
        self.assertTrue(v.provable)
        v.grant()
        self.assertEqual(rec[0][0], "RIVAL_CLEAR")

    def test_mutex_absent_journal_unreadable_still_grantable(self):
        """The mutex is authoritative for liveness: OS-released on death."""
        v = interlock.check(mutex_probe=lambda: False,
                            journal_age=lambda: None)
        self.assertFalse(v.rival_alive)
        self.assertTrue(v.provable)

    def test_all_detectors_dark_fails_closed(self):
        v = interlock.check(mutex_probe=lambda: None,
                            journal_age=lambda: None)
        self.assertFalse(v.rival_alive)
        self.assertFalse(v.provable)
        with self.assertRaises(interlock.RivalUnprovableError):
            v.grant()

    def test_stale_journal_with_dark_mutex_fails_closed(self):
        v = interlock.check(mutex_probe=lambda: None,
                            journal_age=lambda: 500.0)
        self.assertFalse(v.provable)


class RealProbes(unittest.TestCase):
    """Against the real OS — honest, environmental."""

    def test_probe_of_nonexistent_mutex_is_false(self):
        self.assertIs(
            interlock.probe_rival_mutex(
                "Global\\K2_TEST_NO_SUCH_MUTEX_" + os.urandom(4).hex()),
            False)

    def test_probe_never_creates_the_name(self):
        """Probe twice: if OpenMutexW secretly created the name, the second
        probe would find it. It must stay absent."""
        name = "Global\\K2_TEST_PROBE_" + os.urandom(4).hex()
        self.assertIs(interlock.probe_rival_mutex(name), False)
        self.assertIs(interlock.probe_rival_mutex(name), False)

    def test_real_keshev_a_state_is_reported_honestly(self):
        """Environmental: whatever A's true state on this machine, the two
        detectors must AGREE with each other within their semantics —
        a held mutex with a stale journal (or vice versa) is worth knowing.
        This test never fails on A being up or down; it fails only if the
        real probe ERRORS."""
        m = interlock.probe_rival_mutex()
        self.assertIn(m, (True, False),
                      "real mutex probe errored — investigate before "
                      "trusting the interlock on this machine")

    def test_journal_age_of_real_a_journal(self):
        age = interlock.rival_journal_age_s()
        if age is None:
            self.skipTest("A journal not present on this machine — honest")
        self.assertGreaterEqual(age, 0.0)


class JournalFreshness(unittest.TestCase):

    def test_age_computed_from_mtime(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "events.jsonl"
            p.write_text("{}\n", encoding="utf-8")
            age = interlock.rival_journal_age_s(str(p))
            self.assertLess(age, 5.0)

    def test_missing_file_is_none(self):
        self.assertIsNone(
            interlock.rival_journal_age_s(r"C:\no\such\file.jsonl"))


class OwnMutex(unittest.TestCase):

    def test_duplicate_exits_11_with_one_line(self):
        name = "Global\\K2_TEST_OWN_" + os.urandom(4).hex()
        lines = []
        exits = []
        h = interlock.acquire_own_mutex_or_exit(
            name, log=lines.append, _exit=exits.append)
        self.assertTrue(h)
        self.assertEqual(exits, [])
        interlock.acquire_own_mutex_or_exit(
            name, log=lines.append, _exit=exits.append)
        self.assertEqual(exits, [interlock._EXIT_DUPLICATE])
        self.assertEqual(len(lines), 1)
        self.assertIn("duplicate", lines[0])

    def test_access_denied_is_a_duplicate_not_a_crash(self):
        """Adversarial find (gpt-oss, partial accept): the name held under
        another ELEVATION comes back NULL+ACCESS_DENIED — that is a
        duplicate refusal (exit 11), never an OSError fight. PROOF THE
        BRANCH FIRES (injected create)."""
        lines, exits = [], []
        interlock.acquire_own_mutex_or_exit(
            "Global\\K2_TEST_ELEV", log=lines.append, _exit=exits.append,
            _create=lambda name: (0, interlock._ERROR_ACCESS_DENIED))
        self.assertEqual(exits, [interlock._EXIT_DUPLICATE])
        self.assertIn("another elevation", lines[0])

    def test_other_create_failure_still_raises_loudly(self):
        """scar 6: unknown kernel failure stays a loud OSError."""
        with self.assertRaises(OSError):
            interlock.acquire_own_mutex_or_exit(
                "Global\\K2_TEST_ERR", log=lambda s: None,
                _exit=lambda c: None,
                _create=lambda name: (0, 87))     # ERROR_INVALID_PARAMETER


if __name__ == "__main__":
    unittest.main()
