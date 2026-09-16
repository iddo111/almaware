"""KESHEV 2 typer — THE single door text passes to reach a window.

Ruling D-006. Every protection here is scar-paid, and the 09:46 ones are
baked in FROM DAY ONE — not retrofitted after the first incident like in A:

  ONE SERIALIZATION POINT (scar 53): `Typer.type()` holds a lock; the
  router is its only caller; request-id dedup lives HERE, at the choke
  point — the same id types at most once, whichever engine answered.

  GATES INSIDE THE DOOR (09:46): the combined presence+arm decision is
  consulted INSIDE type(), not by the caller. A caller that forgets the
  gate is impossible — there is no gate-free entrance to a window.

  ENTER IS A SEPARATE ACT (scar 36 + D-003's K2 improvement): the Enter
  burst fires ~0.35s after the text, re-verifies the SAME target
  (HWND+PID+exe, never title — scar 34), and RE-ASKS the gates. A's gate
  answered once per utterance; K2's Enter is a second question at Enter
  time, because SUBMITTING as him is the irreversible half of 09:46.

  PASTE-FIRST FOR EVERY WINDOW (scar 31): a paste is 4 events regardless
  of length; per-char SendInput silently thins under load (the 79-char
  utterance that lost all its spaces). The unicode fallback is CHUNKED
  with breathers — and REFUSED for terminal hosts, which discard
  KEYEVENTF_UNICODE entirely while reporting success.

  NO CLIPBOARD RESTORE (scar 32): there is no restore code in this repo.
  Absent code cannot race. (The 120-230ms restore pasted the PREVIOUS
  clipboard for a whole night.)

  PARK, NEVER DROP (scar 35): every refusal appends the full text to
  state\\parked.txt as JSONL and journals TYPE_FAIL_PARKED (length only —
  transcript text is unrepresentable in the journal). Parked text is
  recoverable; dropped text is a lie.

The OS layer is injected (fakes in tests, k2/win32type.py in production).
stdlib only.
"""
from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Callable, NamedTuple, Optional, Protocol, Sequence

from k2.presence import Decision

ENTER_DELAY_S = 0.35        # scar 36: let the app ingest the text first
CHUNK_EVENTS = 32           # scar 31: fallback bursts stay small…
INTER_CHUNK_SLEEP_S = 0.008  # …with a breather so the receiver drains
DEDUP_LRU_SIZE = 512

# Console hosts that discard KEYEVENTF_UNICODE while reporting success.
TERMINAL_EXES = frozenset({
    "windowsterminal.exe", "wt.exe", "conhost.exe", "openconsole.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "mintty.exe",
})


class Target(NamedTuple):
    """A window identity. Compared by HWND+PID+exe, NEVER by title —
    terminal spinner glyphs rewrite titles every tick (scar 34), and
    titles on disk are a surveillance record (scar 49)."""
    hwnd: int
    pid: int
    exe: str        # lowercase basename, e.g. "chrome.exe"


def same_target(a: Optional[Target], b: Optional[Target]) -> bool:
    if a is None or b is None:
        return False
    return a.hwnd == b.hwnd and a.pid == b.pid and a.exe == b.exe


class OsLayer(Protocol):
    """The injected boundary. k2/win32type.py implements it for real."""

    def foreground(self) -> Optional[Target]: ...
    def clipboard_set(self, text: str) -> bool: ...
    def send_paste(self) -> bool: ...
    def send_enter(self) -> bool: ...
    def send_unicode_chunk(self, units: Sequence[int]) -> bool: ...
    def own_pid(self) -> int: ...


class TypeOutcome(NamedTuple):
    typed: bool
    entered: bool
    reason: str          # "" on full success


def utf16_units(text: str) -> list[int]:
    """UTF-16 code units — surrogate pairs for astral chars (scar 31: the
    fallback must type emoji and rare CJK correctly)."""
    units: list[int] = []
    for ch in text:
        cp = ord(ch)
        if cp <= 0xFFFF:
            units.append(cp)
        else:
            cp -= 0x10000
            units.append(0xD800 | (cp >> 10))
            units.append(0xDC00 | (cp & 0x3FF))
    return units


def chunks(units: Sequence[int], size: int = CHUNK_EVENTS) -> list[Sequence[int]]:
    return [units[i:i + size] for i in range(0, len(units), size)]


class Typer:
    """The one door. Constructed once by the app with the real gates and
    the real OS layer; the router calls type() and nothing else."""

    def __init__(self, os_layer: OsLayer,
                 decide: Callable[[], Decision],
                 emit: Callable[..., None],
                 parked_path: str | Path,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._os = os_layer
        self._decide = decide           # the combined_decision seam (D-006)
        self._emit = emit
        self._parked = Path(parked_path)
        self._sleep = sleep
        self._lock = threading.Lock()
        self._seen: OrderedDict[str, None] = OrderedDict()

    # ------------------------------------------------------------ the door

    def type(self, text: str, request_id: str,
             want_enter: bool = False) -> TypeOutcome:
        with self._lock:
            return self._type_locked(text, request_id, want_enter)

    def _type_locked(self, text: str, rid: str,
                     want_enter: bool) -> TypeOutcome:
        # 1. dedup at the choke point (scar 53)
        if rid in self._seen:
            self._emit("DUP_DISCARD", rid=rid, len=len(text))
            return TypeOutcome(False, False, "duplicate")
        self._remember(rid)

        # 2. the gates, INSIDE the door (09:46)
        d = self._decide()
        if not d.may_type:
            self._park(text, rid, f"gate:{d.reason}")
            return TypeOutcome(False, False, d.reason)

        # 3. focus verification — double snapshot, own-window hard block
        t1 = self._os.foreground()
        if t1 is None:
            self._park(text, rid, "focus:unverifiable")
            return TypeOutcome(False, False, "focus_unverifiable")
        if t1.pid == self._os.own_pid():
            self._emit("FOCUS_BLOCK", rid=rid, exe=t1.exe, reason="own_window")
            self._park(text, rid, "focus:own_window")
            return TypeOutcome(False, False, "own_window")

        # 4. deliver — paste first, for every window (scar 31)
        delivered = self._deliver(text, rid, t1)
        if not delivered:
            return TypeOutcome(False, False, "delivery_failed")

        self._emit("TYPED", rid=rid, len=len(text), exe=t1.exe,
                   enter=bool(want_enter and d.may_enter))

        # 5. Enter — a separate, re-verified, re-gated act
        if not want_enter:
            return TypeOutcome(True, False, "")
        if not d.may_enter:
            return TypeOutcome(True, False, d.reason or "enter_refused")
        self._sleep(ENTER_DELAY_S)
        d2 = self._decide()             # K2: presence re-asked at Enter time
        if not d2.may_enter:
            self._emit("PRESENCE_REJ", reason=f"enter_recheck:{d2.reason}",
                       idle_s=int(d2.idle_s or -1))
            return TypeOutcome(True, False, f"enter_recheck:{d2.reason}")
        t2 = self._os.foreground()
        if not same_target(t1, t2):
            self._emit("FOCUS_BLOCK", rid=rid,
                       exe=(t2.exe if t2 else "none"),
                       reason="target_changed_before_enter")
            return TypeOutcome(True, False, "target_changed")
        if not self._os.send_enter():
            return TypeOutcome(True, False, "enter_send_failed")
        return TypeOutcome(True, True, "")

    # ------------------------------------------------------------ delivery

    def _deliver(self, text: str, rid: str, t1: Target) -> bool:
        pasted = self._os.clipboard_set(text) and self._paste_verified(t1)
        if pasted:
            return True
        # paste failed: terminals get an HONEST refusal, never unicode
        # (they discard KEYEVENTF_UNICODE while reporting success)
        if t1.exe in TERMINAL_EXES:
            self._park(text, rid, "terminal_paste_failed")
            return False
        return self._unicode_fallback(text, rid, t1)

    def _paste_verified(self, t1: Target) -> bool:
        """Send the paste, then verify the foreground did not move mid-
        flight (the second half of the double snapshot)."""
        if not self._os.send_paste():
            return False
        t2 = self._os.foreground()
        return same_target(t1, t2)

    def _unicode_fallback(self, text: str, rid: str, t1: Target) -> bool:
        """Chunked, breathered, target re-verified per chunk (scar 31)."""
        for chunk in chunks(utf16_units(text)):
            if not same_target(t1, self._os.foreground()):
                self._park(text, rid, "focus_lost_mid_fallback")
                return False
            if not self._os.send_unicode_chunk(chunk):
                self._park(text, rid, "unicode_send_failed")
                return False
            self._sleep(INTER_CHUNK_SLEEP_S)
        return True

    # ------------------------------------------------------------ parking

    def _park(self, text: str, rid: str, reason: str) -> None:
        """Refused text is PARKED with its full content (parked.txt is
        state-local and git-ignored), and journalled by LENGTH only."""
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "rid": rid, "reason": reason, "text": text,
        }
        self._parked.parent.mkdir(parents=True, exist_ok=True)
        with open(self._parked, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._emit("TYPE_FAIL_PARKED", rid=rid, reason=reason, len=len(text))

    def _remember(self, rid: str) -> None:
        self._seen[rid] = None
        while len(self._seen) > DEDUP_LRU_SIZE:
            self._seen.popitem(last=False)
