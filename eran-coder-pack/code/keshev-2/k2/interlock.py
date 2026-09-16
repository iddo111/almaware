"""KESHEV 2 rival interlock — REFUSE to capture while KESHEV A lives.

KESHEV A is king of the microphone until KESHEV 2 provably beats it.
Opening a second capture of the BRIO beside A's live capture is the
double-mic scar and can disrupt Iddo's live dictation mid-sentence. So the
interlock is not a policy, it is a STRUCTURE:

  THE TICKET LAW (guard species #4 countermeasure). The only way to start
  capture — today's state machine, tomorrow's real capture module — is to
  hold a `CaptureTicket`. The only constructor of a CaptureTicket is
  `InterlockVerdict.grant()`, and grant() RAISES RivalAliveError when the
  verdict says the rival is alive. The verdict cannot fail to reach the
  decision because the verdict IS the door. (A's mic-switch audit computed
  `can_prove_free` correctly and the switch decision never consulted it —
  the verdict reached the report, not the refusal. Never again.)

  DETECTION — belt and suspenders, both read-only (ruling D-002, council
  Q2 held with all four 4D workers, see DECISIONS.md):

  (a) OpenMutexW probe of A's named kernel mutex (the RIVAL_MUTEX_NAME
      constant below). A holds it for process life; the OS
      releases it on death, so a hit is proof of a LIVE process, zero
      false-positives from crashes. NEVER CreateMutexW on A's name —
      creating it would SQUAT the name and block A's next start (lint gate
      G5 makes that a build failure).
      ERROR_ACCESS_DENIED still means the mutex EXISTS -> rival alive.
  (b) A-journal freshness: mtime of D:\\CLAUDE\\mic-rebuild\\state\\
      events.jsonl. A journals every event and heartbeats every 60s, so a
      journal younger than RIVAL_JOURNAL_FRESH_S means A is (or seconds
      ago was) alive. Catches windows where the mutex probe errors.

  EITHER detector positive -> rival alive. Both must come back clean for a
  grant. Detector failure (probe error + unreadable journal) fails CLOSED:
  an unprovable "A is dead" is never permission to open his microphone.

The state the app announces is IDLE_RIVAL_ALIVE — honest, by name, with
the detector that fired recorded in the journal (RIVAL_ALIVE via=...).

stdlib ctypes only. This module opens no device, reads no audio, and
touches nothing of A's except OpenMutexW and one stat() call.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from typing import Callable, NamedTuple, Optional

# A's mutex name — VERBATIM from mic-rebuild client/mutexguard.py. The only
# legal use of this string is the read-only probe below (lint gate G5).
RIVAL_MUTEX_NAME = "Global\\ALMAWARE_KESHEV_SINGLE"

# K2's OWN single-instance mutex (scar 1) — a DIFFERENT name, so K2 and A
# can coexist as processes (A typing, K2 in shadow mode) while capture
# exclusivity is enforced by the ticket law, not by sharing A's mutex.
K2_MUTEX_NAME = "Global\\ALMAWARE_KESHEV2_SINGLE"

RIVAL_JOURNAL_PATH = r"D:\CLAUDE\mic-rebuild\state\events.jsonl"
RIVAL_JOURNAL_FRESH_S = 180.0     # A heartbeats every 60s; 3 missed = stale

IDLE_RIVAL_ALIVE = "IDLE_RIVAL_ALIVE"

_SYNCHRONIZE = 0x00100000
_ERROR_FILE_NOT_FOUND = 2
_ERROR_ACCESS_DENIED = 5


class RivalAliveError(RuntimeError):
    """Raised by grant() — capture requested while KESHEV A is alive."""


class RivalUnprovableError(RuntimeError):
    """Raised by grant() — detectors failed; 'A is dead' cannot be proven.
    Fails CLOSED: unprovable is never permission."""


class CaptureTicket:
    """Proof that the interlock passed at grant time. Deliberately dumb:
    its VALUE is that only InterlockVerdict.grant() constructs it — any
    future capture code demands one as its first argument, so a capture
    start without a fresh interlock check is a TypeError, not a review
    comment."""

    __slots__ = ("granted_at", "via")

    def __init__(self, *, _token: object, granted_at: float, via: str):
        if _token is not _TICKET_TOKEN:
            raise TypeError(
                "CaptureTicket cannot be constructed directly — only "
                "InterlockVerdict.grant() issues tickets (the ticket law)")
        self.granted_at = granted_at
        self.via = via


_TICKET_TOKEN = object()


class InterlockVerdict(NamedTuple):
    rival_alive: bool
    provable: bool          # False = detectors failed, fail CLOSED
    via: str                # which detector(s) decided, e.g. "mutex" / "journal"
    detail: str

    def grant(self) -> CaptureTicket:
        """The ONE door to capture. Raises unless the rival is provably gone."""
        if self.rival_alive:
            raise RivalAliveError(
                f"KESHEV A is alive (via {self.via}: {self.detail}) — "
                f"state {IDLE_RIVAL_ALIVE}, capture refused")
        if not self.provable:
            raise RivalUnprovableError(
                f"cannot prove KESHEV A is gone ({self.detail}) — "
                f"failing closed, capture refused")
        return CaptureTicket(_token=_TICKET_TOKEN,
                             granted_at=time.time(), via=self.via)


# ----------------------------------------------------------- detectors


def probe_rival_mutex(name: str = RIVAL_MUTEX_NAME) -> Optional[bool]:
    """READ-ONLY existence probe of A's mutex. True = exists (A alive),
    False = not found (A not running), None = probe failed (unknown).

    OpenMutexW only. It cannot create, cannot acquire ownership, and the
    handle is closed immediately — A never notices."""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.argtypes = (
            wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.OpenMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenMutexW(_SYNCHRONIZE, False, name)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        err = ctypes.get_last_error()
        if err == _ERROR_FILE_NOT_FOUND:
            return False
        if err == _ERROR_ACCESS_DENIED:
            return True          # exists but we lack rights — still ALIVE
        return None              # unexpected error -> unknown, recorded
    except Exception:            # ctypes/environment failure -> unknown
        return None


def rival_journal_age_s(path: str = RIVAL_JOURNAL_PATH,
                        now: Callable[[], float] = time.time
                        ) -> Optional[float]:
    """Seconds since A last journalled, or None if unreadable/absent."""
    try:
        return max(0.0, now() - os.stat(path).st_mtime)
    except OSError:
        return None


# ----------------------------------------------------------- the check


def check(mutex_probe: Callable[[], Optional[bool]] = probe_rival_mutex,
          journal_age: Callable[[], Optional[float]] = rival_journal_age_s,
          fresh_s: float = RIVAL_JOURNAL_FRESH_S,
          emit: Optional[Callable[..., None]] = None) -> InterlockVerdict:
    """Run both detectors, journal the honest outcome, return the verdict.

    EITHER positive -> rival_alive. Both clean -> grantable. Both detectors
    dark -> provable=False (fail closed). Detectors are injectable so tests
    prove every branch CAN fire (the reachability law)."""
    m = mutex_probe()
    age = journal_age()

    if m is True:
        v = InterlockVerdict(True, True, "mutex",
                             f"{RIVAL_MUTEX_NAME} is held by a live process")
    elif age is not None and age < fresh_s:
        v = InterlockVerdict(True, True, "journal",
                             f"A journalled {age:.0f}s ago (< {fresh_s:.0f}s)")
    elif m is False:
        detail = (f"mutex absent; journal "
                  f"{'unreadable' if age is None else f'{age:.0f}s old'}")
        v = InterlockVerdict(False, True, "mutex+journal", detail)
    else:
        # mutex probe failed AND journal is stale/unreadable -> unknown
        detail = (f"mutex probe failed; journal "
                  f"{'unreadable' if age is None else f'{age:.0f}s old'}")
        v = InterlockVerdict(False, False, "none", detail)

    if emit is not None:
        if v.rival_alive:
            emit("RIVAL_ALIVE", via=v.via, detail=v.detail)
        else:
            emit("RIVAL_CLEAR", via=v.via, provable=v.provable,
                 detail=v.detail)
    return v


# ------------------------------------------- K2's own single instance
# Scar 1, ported from A's mutexguard: kernel mutex, held for process life,
# duplicate exits <1s with one line. K2's OWN name only — CreateMutexW on
# A's name is forbidden by lint gate G5 and by the docstring law above.

_EXIT_DUPLICATE = 11
_ERROR_ALREADY_EXISTS = 183
_HELD: list[int] = []           # anchors the winner's handle for process life


def _create_own_mutex(name: str) -> tuple[int, int]:
    """The raw Win32 call, separated so every branch of the decision below
    is reachable by tests (the reachability law). Returns (handle, err)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (
        wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, True, name)
    return (int(handle) if handle else 0), ctypes.get_last_error()


def _close_handle(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle(handle)


def acquire_own_mutex_or_exit(name: str = K2_MUTEX_NAME,
                              log: Optional[Callable[[str], None]] = None,
                              _exit: Callable[[int], None] = None,
                              _create: Callable[[str], tuple[int, int]]
                              = _create_own_mutex) -> int:
    """First statement of app.py. Winner returns the held handle;
    duplicate logs ONE line and exits 11.

    ACCESS_DENIED on the name is a DUPLICATE, not a crash (adversarial
    find, gpt-oss, partially accepted): the name exists but our token
    cannot open it — a K2 under a DIFFERENT ELEVATION holds it. Crashing
    there would let an elevated and a non-elevated K2 fight; exiting 11
    is the same one-line refusal as any duplicate."""
    import sys
    exit_fn = _exit if _exit is not None else sys.exit
    handle, err = _create(name)
    if not handle:
        if err == _ERROR_ACCESS_DENIED:
            line = (f"KESHEV2 duplicate instance refused: mutex {name} "
                    f"exists under another elevation (access denied) — "
                    f"exit {_EXIT_DUPLICATE}")
            if log is None:
                print(line, file=sys.stderr, flush=True)
            else:
                log(line)
            exit_fn(_EXIT_DUPLICATE)
            return 0              # only reached when _exit is a test fake
        raise OSError(f"CreateMutexW failed for {name!r}: WinError {err}")
    if err == _ERROR_ALREADY_EXISTS:
        line = (f"KESHEV2 duplicate instance refused: mutex {name} held by "
                f"a live process — exit {_EXIT_DUPLICATE}")
        if log is None:
            import sys as _s
            print(line, file=_s.stderr, flush=True)
        else:
            log(line)
        _close_handle(handle)
        exit_fn(_EXIT_DUPLICATE)
        return 0                  # only reached when _exit is a test fake
    _HELD.append(handle)
    return handle
