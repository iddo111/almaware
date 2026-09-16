"""typer tests — gates INSIDE the door, Enter re-verified, dedup structural."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.typer import FocusInfo, Typer  # noqa: E402


class _MemJournal:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def event(self, name, **fields):
        self.events.append((name, fields))
        return {"evt": name, **fields}

    def names(self):
        return [n for n, _ in self.events]


def make_typer(j, *, presence=(True, True, "ok"),
               focus=FocusInfo(100, 200, "claude.exe"),
               send_ok=True, avoid=()):
    return Typer(
        journal=j,
        presence_verdict=lambda: presence,
        focus_fn=lambda: focus,
        send_text=lambda t: send_ok,
        send_enter=lambda: send_ok,
        avoid_exes=avoid,
    )


class DeliverTests(unittest.TestCase):
    def setUp(self):
        self.j = _MemJournal()

    def test_happy_path_types_and_journals(self):
        t = make_typer(self.j)
        self.assertEqual(t.deliver("r-1", "שלום"), (True, "ok"))
        self.assertIn("TYPED", self.j.names())

    def test_dup_is_structurally_impossible(self):
        t = make_typer(self.j)
        t.deliver("r-1", "שלום")
        self.assertEqual(t.deliver("r-1", "שלום"), (False, "dup"))
        self.assertEqual(self.j.names().count("TYPED"), 1)

    def test_presence_gate_is_inside_the_door(self):
        """species-4: the verdict reaches the DECISION — a caller cannot
        deliver without presence being asked."""
        t = make_typer(self.j, presence=(False, False, "idle_no_type"))
        self.assertEqual(t.deliver("r-1", "x"), (False, "presence"))
        self.assertIn("PRESENCE_REJ", self.j.names())
        self.assertNotIn("TYPED", self.j.names())

    def test_no_focus_refuses(self):
        t = make_typer(self.j, focus=None)
        self.assertEqual(t.deliver("r-1", "x"), (False, "no_focus"))
        self.assertIn("FOCUS_REJ", self.j.names())

    def test_avoided_exe_refuses(self):
        t = make_typer(self.j, avoid=("KeePass.exe",),
                       focus=FocusInfo(1, 2, "keepass.exe"))
        self.assertEqual(t.deliver("r-1", "x"), (False, "avoided_exe"))

    def test_send_failure_journals_and_refuses(self):
        """Success return values lie — but a False one is at least honest."""
        t = make_typer(self.j, send_ok=False)
        self.assertEqual(t.deliver("r-1", "x"), (False, "send_failed"))
        self.assertIn("TYPE_VERIFY_FAIL", self.j.names())

    def test_every_refusal_journals_exactly_one_line(self):
        t = make_typer(self.j, focus=None)
        t.deliver("r-1", "x")
        self.assertEqual(len(self.j.events), 1)


class EnterTests(unittest.TestCase):
    def setUp(self):
        self.j = _MemJournal()
        self.at_type = FocusInfo(100, 200, "claude.exe")

    def test_enter_re_asks_presence(self):
        """09:46: idle 9 min → text may flow, Enter must NOT."""
        t = make_typer(self.j, presence=(True, False, "idle_no_enter"))
        self.assertEqual(t.enter("r-1", self.at_type), (False, "presence"))

    def test_enter_refuses_when_window_changed(self):
        t = make_typer(self.j, focus=FocusInfo(999, 200, "claude.exe"))
        ok, reason = t.enter("r-1", self.at_type)
        self.assertEqual((ok, reason), (False, "window_changed"))
        self.assertIn("FOCUS_REJ", self.j.names())

    def test_enter_same_window_succeeds(self):
        t = make_typer(self.j, focus=self.at_type)
        self.assertEqual(t.enter("r-1", self.at_type), (True, "ok"))
        self.assertIn("ENTER", self.j.names())

    def test_enter_without_recorded_focus_refuses(self):
        t = make_typer(self.j)
        self.assertEqual(t.enter("r-1", None), (False, "window_changed"))

    def test_exe_comparison_case_insensitive_title_ignored(self):
        t = make_typer(self.j, focus=FocusInfo(100, 200, "CLAUDE.EXE"))
        self.assertEqual(t.enter("r-1", self.at_type), (True, "ok"))


if __name__ == "__main__":
    unittest.main()
