"""KESHEV single-instance guard — K4 (PHASE2-DESIGN.md section 7, scar 1).

`CreateMutexW("Global\\ALMAWARE_KESHEV_SINGLE")` is the FIRST statement of
app.py, before any heavy import. ERROR_ALREADY_EXISTS -> one log line +
exit 11 in <1s. The kernel object is OS-released on process death — there
are NO lock files (a lock file survives a crash; a kernel mutex cannot).

The handle is held for process life: production code NEVER releases it.
`_release_for_test` exists only so unit tests in one process can run
multiple acquire cycles.

stdlib ctypes only. No filesystem access in this module, by design.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

MUTEX_NAME = "Global\\ALMAWARE_KESHEV_SINGLE"
EXIT_DUPLICATE = 11

_ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
_kernel32.ReleaseMutex.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL

# The winner's handle is anchored here so it cannot be garbage-collected —
# held for process life (scar 1).
_HELD: list["MutexHandle"] = []


class MutexHandle:
    """Result of an acquire: the raw kernel handle + whether we lost the race."""

    __slots__ = ("handle", "already_exists", "name")

    def __init__(self, handle: int, already_exists: bool, name: str):
        self.handle = handle
        self.already_exists = already_exists
        self.name = name


def acquire(name: str = MUTEX_NAME) -> MutexHandle:
    """Create/open the named kernel mutex with initial ownership requested.

    Returns a MutexHandle; `.already_exists` True means another live process
    holds the name (we are the duplicate). Fails LOUDLY (scar 6) if the
    kernel call itself fails.
    """
    handle = _kernel32.CreateMutexW(None, True, name)
    err = ctypes.get_last_error()
    if not handle:
        raise OSError(f"CreateMutexW failed for {name!r}: WinError {err}")
    dup = err == _ERROR_ALREADY_EXISTS
    h = MutexHandle(handle, dup, name)
    if not dup:
        _HELD.append(h)  # winner: anchored for process life
    return h


def acquire_or_exit(name: str = MUTEX_NAME, log=None,
                    on_duplicate=None) -> MutexHandle:
    """The app.py front door. Winner: returns the held handle.

    Duplicate: emits exactly ONE log line and exits with code 11 (scar 1).
    `log` is a callable taking one string (telemetry arrives at K3; until
    then callers pass a file/stderr writer). Default: stderr.

    `on_duplicate` is an optional zero-arg callable run before the exit —
    under pythonw the stderr line reaches nobody, and a silent exit 11 reads
    as "KESHEV won't load" (2026-08-25). It may show UI; it must not stop
    the refusal: any exception it raises is logged and the exit proceeds.
    """
    h = acquire(name)
    if h.already_exists:
        line = (f"KESHEV duplicate instance refused: mutex {name} is held "
                f"by a live process — exit 11")
        if log is None:
            print(line, file=sys.stderr, flush=True)
        else:
            log(line)
        if on_duplicate is not None:
            try:
                on_duplicate()
            except Exception as exc:  # noqa: BLE001 — feedback never blocks the refusal
                fb = f"duplicate feedback failed: {type(exc).__name__}: {exc}"
                if log is None:
                    print(fb, file=sys.stderr, flush=True)
                else:
                    log(fb)
        _kernel32.CloseHandle(h.handle)  # our dup handle only; owner unaffected
        sys.exit(EXIT_DUPLICATE)
    return h


def _release_for_test(h: MutexHandle) -> None:
    """TEST-ONLY: release + close so one test process can cycle acquires.

    Production never calls this — the mutex is held for process life and
    the OS releases it on death.
    """
    if h in _HELD:
        _HELD.remove(h)
    if h.handle:
        if not h.already_exists:
            _kernel32.ReleaseMutex(h.handle)
        _kernel32.CloseHandle(h.handle)
        h.handle = 0
