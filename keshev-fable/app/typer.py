"""typer.py — text into HIS window only. The gates live INSIDE the door.

Laws inherited (INSIGHTS §1.4, §1.7, §1.11; keshev-2 typer rulings):
- Success return values lie: SendInput reports ok while UIPI discards
  everything. Delivery is only believed after round-trip verification of
  what the receiver GOT (wired in a later module: selftest/pulse).
- Compare windows by HWND+PID+exe, never title. Titles change mid-burst.
- Enter is a SEPARATE burst: re-verify focus AND re-ask the presence gate
  before it. The 09:46 scar submitted as him; typing junk is recoverable,
  submitting is not.
- One serialization point: all deliveries pass through ONE Typer instance;
  request-id dedup makes double-typing structurally impossible, not policed.
- park-never-drop: a refused delivery journals and returns the record to
  the caller; no text is silently lost.
- No clipboard-restore code exists (keshev-2 ruling): restoring a clipboard
  we clobbered is how OTHER apps' data gets corrupted; we type, not paste,
  until a verified paste path earns its way in.
- The gates are consulted INSIDE deliver()/enter() — a caller cannot forget
  them (species-4: the verdict must reach the DECISION).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class _JournalLike(Protocol):
    def event(self, name: str, **fields: object) -> dict: ...


@dataclass(frozen=True)
class FocusInfo:
    """Identity of the window that will receive keystrokes."""
    hwnd: int
    pid: int
    exe: str

    def same_window(self, other: "FocusInfo") -> bool:
        # HWND+PID+exe, never title (INSIGHTS §1.7)
        return (self.hwnd, self.pid, self.exe.casefold()) == \
               (other.hwnd, other.pid, other.exe.casefold())


class Typer:
    """The one serialization point. All text passes here or nowhere.

    send_text/send_enter/focus_fn are injectable: tests run without a
    desktop, production wires win32 implementations.
    """

    def __init__(self,
                 journal: _JournalLike,
                 presence_verdict: Callable[[], tuple[bool, bool, str]],
                 focus_fn: Callable[[], FocusInfo | None],
                 send_text: Callable[[str], bool],
                 send_enter: Callable[[], bool],
                 avoid_exes: tuple[str, ...] = ()) -> None:
        self.journal = journal
        self.presence_verdict = presence_verdict
        self.focus_fn = focus_fn
        self.send_text = send_text
        self.send_enter = send_enter
        self.avoid_exes = tuple(e.casefold() for e in avoid_exes)
        self._delivered_ids: set[str] = set()

    # ------------------------------------------------------------ deliver --
    def deliver(self, rec_id: str, text: str) -> tuple[bool, str]:
        """Type text into the focused window. (ok, reason).
        reason ∈ ok | dup | presence | no_focus | avoided_exe | send_failed
        """
        if rec_id in self._delivered_ids:
            # dedup is structural: the same record can NEVER type twice
            self.journal.event("GUARD_DROP", id=rec_id, reason="dup")
            return False, "dup"

        may_type, _may_enter, why = self.presence_verdict()
        if not may_type:
            self.journal.event("PRESENCE_REJ", id=rec_id, reason=why)
            return False, "presence"

        focus = self.focus_fn()
        if focus is None:
            self.journal.event("FOCUS_REJ", id=rec_id, reason="no_focus")
            return False, "no_focus"
        if focus.exe.casefold() in self.avoid_exes:
            self.journal.event("FOCUS_REJ", id=rec_id, reason="avoided_exe",
                               exe=focus.exe)
            return False, "avoided_exe"

        if not self.send_text(text):
            self.journal.event("TYPE_VERIFY_FAIL", id=rec_id)
            return False, "send_failed"

        self._delivered_ids.add(rec_id)
        self.journal.event("TYPED", id=rec_id, len=len(text))
        return True, "ok"

    # -------------------------------------------------------------- enter --
    def enter(self, rec_id: str, focus_at_type: FocusInfo | None) -> tuple[bool, str]:
        """Enter is its own burst: presence RE-asked, focus RE-verified and
        compared to the window that received the text. (ok, reason).
        reason ∈ ok | presence | no_focus | window_changed | send_failed
        """
        _may_type, may_enter, why = self.presence_verdict()
        if not may_enter:
            self.journal.event("PRESENCE_REJ", id=rec_id, stage="enter",
                               reason=why)
            return False, "presence"

        focus_now = self.focus_fn()
        if focus_now is None:
            self.journal.event("FOCUS_REJ", id=rec_id, stage="enter",
                               reason="no_focus")
            return False, "no_focus"
        if focus_at_type is None or not focus_now.same_window(focus_at_type):
            # the text landed in one window; Enter must not land in another
            self.journal.event("FOCUS_REJ", id=rec_id, stage="enter",
                               reason="window_changed")
            return False, "window_changed"

        if not self.send_enter():
            self.journal.event("TYPE_VERIFY_FAIL", id=rec_id, stage="enter")
            return False, "send_failed"

        self.journal.event("ENTER", id=rec_id)
        return True, "ok"
