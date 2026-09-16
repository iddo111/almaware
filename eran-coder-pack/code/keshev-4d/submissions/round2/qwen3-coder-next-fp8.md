```python
import dataclasses
import os
import sys
from typing import Callable, Tuple, Optional, Set

# Ensure D:\CLAUDE\keshev-4d is on sys.path for imports
sys.path.insert(0, r"D:\CLAUDE\keshev-4d")

from app.journal import Journal


@dataclasses.dataclass
class FocusInfo:
    hwnd: int
    pid: int
    exe: str

    def same_window(self, other: "FocusInfo") -> bool:
        return (self.hwnd == other.hwnd and
                self.pid == other.pid and
                self.exe.lower() == other.exe.lower())


class Typer:
    VOCAB = {
        "TYPED": "TYPED",
        "DROP": "DROP",
        "GATED": "GATED",
        "STATE": "STATE"
    }

    def __init__(
        self,
        journal: Journal,
        presence_verdict: Callable[[], Tuple[bool, bool, str]],
        focus_fn: Callable[[], FocusInfo],
        send_text: Callable[[str], bool],
        send_enter: Callable[[], bool],
        avoid_exes: Tuple[str, ...] = ()
    ):
        self._journal = journal
        self._presence_verdict = presence_verdict
        self._focus_fn = focus_fn
        self._send_text = send_text
        self._send_enter = send_enter
        self._avoid_exes = tuple(exe.lower() for exe in avoid_exes)
        self._typed_ids: Set[str] = set()

    def deliver(self, rec_id: str, text: str) -> Tuple[bool, str]:
        # Dedup check
        if rec_id in self._typed_ids:
            self._journal.event(self.VOCAB["DROP"], f"dup rec_id={rec_id}")
            return False, "dup"

        # Presence check
        may_type, may_enter, why = self._presence_verdict()
        if not may_type:
            self._journal.event(self.VOCAB["GATED"], f"presence_refused: {why}")
            return False, "presence"

        # Focus check
        focus = self._focus_fn()
        if focus.exe.lower() in self._avoid_exes:
            self._journal.event(self.VOCAB["DROP"], f"avoided_exe={focus.exe}")
            return False, "avoided_exe"

        # Send text
        ok = self._send_text(text)
        if not ok:
            self._journal.event(self.VOCAB["DROP"], f"send_text_failed for rec_id={rec_id}")
            return False, "send_failed"

        # Record success
        self._typed_ids.add(rec_id)
        self._journal.event(self.VOCAB["TYPED"], f"rec_id={rec_id}")
        return True, "ok"

    def enter(self, rec_id: str, focus_at_type: FocusInfo) -> Tuple[bool, str]:
        # Re-check presence (for may_enter)
        may_type, may_enter, why = self._presence_verdict()
        if not may_enter:
            self._journal.event(self.VOCAB["GATED"], f"enter_gated: {why}")
            return False, "presence"

        # Re-read focus and verify same window
        focus_now = self._focus_fn()
        if not focus_now.same_window(focus_at_type):
            self._journal.event(self.VOCAB["STATE"], f"window_changed: hwnd={focus_now.hwnd} vs {focus_at_type.hwnd}")
            return False, "window_changed"

        # Send enter
        ok = self._send_enter()
        if not ok:
            self._journal.event(self.VOCAB["DROP"], f"send_enter_failed for rec_id={rec_id}")
            return False, "send_failed"

        # Record success (no new TYPED event for enter)
        self._journal.event(self.VOCAB["TYPED"], f"enter rec_id={rec_id}")
        return True, "ok"
```


```python
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
```