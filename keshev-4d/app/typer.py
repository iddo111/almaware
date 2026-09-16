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
