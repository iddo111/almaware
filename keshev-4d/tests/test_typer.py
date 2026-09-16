import unittest
import sys
import os

sys.path.insert(0, r"D:\CLAUDE\keshev-4d")

from app.typer import Typer, FocusInfo


class MockJournal:
    def __init__(self):
        self.events = []

    def event(self, name: str, msg: str):
        self.events.append((name, msg))


class TestTyper(unittest.TestCase):
    def test_dup_refusal_reachability(self):
        # Realistic input: same rec_id used twice
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: True
        )
        # First call succeeds
        ok1, reason1 = typer.deliver("rec1", "hello")
        self.assertTrue(ok1)
        self.assertEqual(reason1, "ok")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("TYPED", "rec_id=rec1"))

        # Second call with same rec_id must refuse
        ok2, reason2 = typer.deliver("rec1", "world")
        self.assertFalse(ok2)
        self.assertEqual(reason2, "dup")
        self.assertEqual(len(journal.events), 2)
        self.assertEqual(journal.events[1], ("DROP", "dup rec_id=rec1"))

    def test_dup_refusal_wiring(self):
        # Prove deliver() calls journal.event exactly once for dup
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: True
        )
        typer.deliver("rec1", "a")
        typer.deliver("rec1", "b")
        self.assertEqual(len(journal.events), 2)
        self.assertEqual(journal.events[0][0], "TYPED")
        self.assertEqual(journal.events[1][0], "DROP")
        self.assertIn("dup", journal.events[1][1])

    def test_presence_refusal_reachability(self):
        # Realistic input: presence_verdict returns may_type=False
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (False, True, "mic_muted"),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: True
        )
        ok, reason = typer.deliver("rec1", "hello")
        self.assertFalse(ok)
        self.assertEqual(reason, "presence")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("GATED", "presence_refused: mic_muted"))

    def test_avoided_exe_refusal_reachability(self):
        # Realistic input: focus.exe in avoid_exes
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="EXCEL.EXE"),
            send_text=lambda t: True,
            send_enter=lambda: True,
            avoid_exes=("excel.exe",)
        )
        ok, reason = typer.deliver("rec1", "hello")
        self.assertFalse(ok)
        self.assertEqual(reason, "avoided_exe")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("DROP", "avoided_exe=EXCEL.EXE"))

    def test_send_text_failure_refusal_reachability(self):
        # Realistic input: send_text returns False
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: False,
            send_enter=lambda: True
        )
        ok, reason = typer.deliver("rec1", "hello")
        self.assertFalse(ok)
        self.assertEqual(reason, "send_failed")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("DROP", "send_text_failed for rec_id=rec1"))

    def test_happy_path_journals_TYPED(self):
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: True
        )
        ok, reason = typer.deliver("rec1", "hello")
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("TYPED", "rec_id=rec1"))

    def test_enter_window_changed_refusal_reachability(self):
        # Realistic input: focus changed between text and enter
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=200, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: True
        )
        focus_at_type = FocusInfo(hwnd=100, pid=200, exe="notepad.exe")
        ok, reason = typer.enter("rec1", focus_at_type)
        self.assertFalse(ok)
        self.assertEqual(reason, "window_changed")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("STATE", "window_changed: hwnd=200 vs 100"))

    def test_enter_presence_refusal_reachability(self):
        # Realistic input: presence_verdict says may_enter=False
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, False, "no_focus"),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: True
        )
        focus_at_type = FocusInfo(hwnd=100, pid=200, exe="notepad.exe")
        ok, reason = typer.enter("rec1", focus_at_type)
        self.assertFalse(ok)
        self.assertEqual(reason, "presence")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("GATED", "enter_gated: no_focus"))

    def test_enter_send_failure_refusal_reachability(self):
        # Realistic input: send_enter returns False
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: False
        )
        focus_at_type = FocusInfo(hwnd=100, pid=200, exe="notepad.exe")
        ok, reason = typer.enter("rec1", focus_at_type)
        self.assertFalse(ok)
        self.assertEqual(reason, "send_failed")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("DROP", "send_enter_failed for rec_id=rec1"))

    def test_enter_happy_path_journals_TYPED(self):
        journal = MockJournal()
        typer = Typer(
            journal=journal,
            presence_verdict=lambda: (True, True, ""),
            focus_fn=lambda: FocusInfo(hwnd=100, pid=200, exe="notepad.exe"),
            send_text=lambda t: True,
            send_enter=lambda: True
        )
        focus_at_type = FocusInfo(hwnd=100, pid=200, exe="notepad.exe")
        ok, reason = typer.enter("rec1", focus_at_type)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0], ("TYPED", "enter rec_id=rec1"))

    def test_focus_same_window_case_insensitive_exe(self):
        # Realistic input: exe differs only in case
        focus1 = FocusInfo(hwnd=100, pid=200, exe="Notepad.exe")
        focus2 = FocusInfo(hwnd=100, pid=200, exe="NOTEPAD.EXE")
        self.assertTrue(focus1.same_window(focus2))

    def test_focus_same_window_different_hwnd(self):
        focus1 = FocusInfo(hwnd=100, pid=200, exe="notepad.exe")
        focus2 = FocusInfo(hwnd=101, pid=200, exe="notepad.exe")
        self.assertFalse(focus1.same_window(focus2))

    def test_focus_same_window_different_pid(self):
        focus1 = FocusInfo(hwnd=100, pid=200, exe="notepad.exe")
        focus2 = FocusInfo(hwnd=100, pid=201, exe="notepad.exe")
        self.assertFalse(focus1.same_window(focus2))


if __name__ == "__main__":
    unittest.main()
