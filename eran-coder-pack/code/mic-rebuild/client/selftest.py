"""KESHEV selftest — K14 (PHASE2-DESIGN.md section 2 selftest.py row;
criterion 8; PHASE1-INQUIRY.md scar 19).

WHY THIS EXISTS (verbatim scar): for weeks the old mic "typed ok" and
nothing appeared. The CLI terminal ran at HIGH integrity, the mic at
MEDIUM, and Windows UIPI silently drops synthetic input crossing that
boundary upward. Microsoft documents it exactly:

    "This function fails when it is blocked by UIPI. Note that neither
     GetLastError nor the return value will indicate the failure."
                                                  — SendInput, MSDN

So NO success return value is ever trusted (scar 19). This module types
through the REAL typer into a SAME-INTEGRITY child window it spawns
itself, then reads back what the child ACTUALLY received and compares
verbatim. Round-trip or it did not happen.

Three round-trips (criterion 8, all with the hallmark probe — 100+ chars,
mixed Hebrew+English, spaces everywhere):

  tk / paste       the production path (clipboard + Ctrl+V, 4 events)
  tk / sendinput   the fallback path — chunked per-char KEYEVENTF_UNICODE
                   (regression proof for the 79-char lost-spaces scar)
  terminal / paste a REAL console window this module spawns (criterion 8's
                   Windows-Terminal clause; terminals discard
                   KEYEVENTF_UNICODE, so paste is the only door) — typed
                   text plus the separate Enter burst (scar 36) and read
                   back through the console's own input buffer.

FOCUS DISCIPLINE: the probe is typed ONLY after the child window is
verified foreground — never into "whatever happens to be in front"
(guardrail: a selftest must not type into a window it did not create).

Device-open audit (criteria 14/23, scar 22): `device_open_audit` is
DELEGATED to client/devices.py — one copy of the law, re-exported here so
callers of the selftest module find both halves in one place.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, NamedTuple, Optional

from client.devices import device_open_audit  # noqa: F401  (re-export — ONE copy, scar 22)
from client.focus import FocusGuard, Win32FocusApi, strip_cf
from client.typer import Typer, Win32InputApi

HERE = Path(__file__).resolve().parent

# The hallmark probe: mixed he/en, spaces preserved, > 100 chars — the exact
# failure class of the 79-char scar plus criterion 8's Hebrew clause.
PROBE_HE_EN = (
    "מה עם אפליקציית המיקרופון? Can you fix it please? So it types in any "
    "window. Over. גם בעברית עם רווחים בין המילים 12345"
)

_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_CONSOLE = 0x00000010
VK_MENU = 0x12  # ALT


class SelftestResult(NamedTuple):
    ok: bool
    kind: str          # "tk" | "terminal"
    method: str        # "paste" | "sendinput"
    probe_len: int
    got: str
    elapsed_s: float
    detail: str


def _python_exe() -> str:
    return sys.executable.replace("pythonw.exe", "python.exe")


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _wait_for_file(path: Path, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.1)
    return False


def _find_window_by_title_nonce(nonce: str) -> int:
    """EnumWindows fallback for the Windows-Terminal-hosted console, whose
    GetConsoleWindow() is a hidden pseudo-window. Title is used for
    DISCOVERY only — the focus guard never trusts titles for identity."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if nonce in strip_cf(buf.value):
                found.append(int(hwnd))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def _focus_window(hwnd: int, focus_api: Win32FocusApi,
                  input_api: Win32InputApi) -> bool:
    """Bring OUR child window to the foreground and VERIFY it took.

    Plain restore first; if Windows holds the foreground lock, the ALT tap
    (a synthetic ALT press satisfies the 'recently received input' rule —
    ported knowledge from alma-mic selftest_uipi.py) and one retry; last,
    SwitchToThisWindow (the forced alt-tab switch — console windows often
    refuse SetForegroundWindow even after AttachThreadInput). Every path is
    VERIFIED by re-reading the foreground; no path types blind."""
    if focus_api.restore_focus(hwnd):
        return True
    input_api.send_input([("vk", VK_MENU, False), ("vk", VK_MENU, True)])
    time.sleep(0.05)
    if focus_api.restore_focus(hwnd):
        return True
    try:
        user32 = ctypes.windll.user32
        user32.SwitchToThisWindow(ctypes.c_void_p(hwnd), True)
        for _ in range(30):                     # verify — never trust the call
            if focus_api.foreground_hwnd() == hwnd:
                return True
            time.sleep(0.02)
    except Exception as e:
        _ = e                                   # fall through to honest False
    return False


def _make_typer(state_dir: Path, emit=None) -> tuple[Typer, Win32FocusApi, Win32InputApi]:
    focus_api = Win32FocusApi()
    input_api = Win32InputApi()
    guard = FocusGuard(api=focus_api, emit=emit)
    guard.set_policy(anywhere=True)
    # clipboard_restore=True: the OPT-IN path (scar 32 — wait >= 1.0s, restore
    # only if unchanged). The selftest must not eat the user's clipboard, and
    # this exercises the opt-in discipline against a real window for free.
    typer = Typer(guard=guard, input_api=input_api, state_dir=state_dir,
                  emit=emit, clipboard_restore=True)
    return typer, focus_api, input_api


def uipi_roundtrip(
    kind: str = "tk",
    method: str = "paste",
    probe: str = PROBE_HE_EN,
    timeout_s: float = 30.0,
    emit: Optional[Callable[..., None]] = None,
    spin_title: bool = False,
) -> SelftestResult:
    """ONE round-trip: spawn the child, verify focus, type through the real
    typer, read back what the child received, compare VERBATIM."""
    t0 = time.monotonic()
    tmp = Path(tempfile.mkdtemp(prefix="keshev-uipi-"))
    got_file = tmp / "got.txt"
    ready_file = tmp / "ready.json"
    done_file = tmp / "done.flag"

    def result(ok: bool, got: str, detail: str) -> SelftestResult:
        r = SelftestResult(ok, kind, method, len(probe), got,
                           round(time.monotonic() - t0, 2), detail)
        if emit is not None:
            emit("UIPI_SELFTEST", ok=r.ok, kind=r.kind, method=r.method,
                 probe_len=r.probe_len, got_len=len(r.got), detail=r.detail)
        return r

    if kind == "tk":
        argv = [_python_exe(), str(HERE / "_selftest_target.py"),
                str(got_file), str(ready_file), str(done_file),
                f"UIPI-TARGET-{os.getpid()}"]
        if spin_title:
            argv.append("spin")
        child = subprocess.Popen(argv, cwd=str(HERE), creationflags=_CREATE_NO_WINDOW)
    elif kind == "terminal":
        child = subprocess.Popen(
            [_python_exe(), str(HERE / "_selftest_console.py"),
             str(got_file), str(ready_file)],
            cwd=str(HERE), creationflags=_CREATE_NEW_CONSOLE)
    else:
        raise ValueError(f"unknown selftest kind: {kind!r}")

    try:
        if not _wait_for_file(ready_file, 15.0):
            return result(False, "", "child window never became ready")
        ready = json.loads(ready_file.read_text(encoding="utf-8"))
        hwnd = int(ready.get("hwnd") or 0)

        typer, focus_api, input_api = _make_typer(tmp, emit=emit)

        if kind == "terminal":
            # Under a Windows-Terminal default host, GetConsoleWindow() is a
            # TITLE-LESS pseudo window — it can even be brought foreground,
            # where the focus guard (correctly) refuses it. Prefer the
            # visible window carrying the nonce title; keep the raw console
            # hwnd only if it has a readable title (classic conhost).
            nonce_hwnd = 0
            for _ in range(20):
                nonce_hwnd = _find_window_by_title_nonce(ready["title"])
                if nonce_hwnd:
                    break
                time.sleep(0.2)
            if nonce_hwnd:
                hwnd = nonce_hwnd
            elif not (hwnd and strip_cf(focus_api.window_title(hwnd))):
                hwnd = 0
        if not hwnd:
            return result(False, "", "could not locate the child window")

        # Never type into "whatever happens to be in front": focus OUR
        # child and verify, or abort honestly.
        time.sleep(0.3)
        if not _focus_window(hwnd, focus_api, input_api):
            return result(False, "", "could not bring the child window to foreground")

        outcome = typer.type(probe, enter=(kind == "terminal"),
                             force_sendinput=(method == "sendinput"))
        if not outcome.ok:
            return result(False, "", f"typer refused: {outcome.reason}")
        if kind == "terminal" and outcome.enter_ok is False:
            return result(False, "", "enter burst was refused")

        if kind == "tk":
            time.sleep(1.0)                    # let the paste/burst fully land
            done_file.write_text("done", encoding="utf-8")

        if not _wait_for_file(got_file, timeout_s):
            return result(False, "", "child never reported received text")
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.terminate()
        got = got_file.read_text(encoding="utf-8")
        ok = got == probe
        return result(ok, got, "verbatim" if ok else "MISMATCH")
    finally:
        if child.poll() is None:
            child.terminate()


def run_criterion8(emit: Optional[Callable[..., None]] = None) -> list[SelftestResult]:
    """The full criterion-8 battery: paste, sendinput-fallback, terminal."""
    results = [
        uipi_roundtrip(kind="tk", method="paste", emit=emit),
        uipi_roundtrip(kind="tk", method="sendinput", emit=emit),
        uipi_roundtrip(kind="terminal", method="paste", emit=emit),
    ]
    return results


if __name__ == "__main__":  # manual run: prints each leg, exit 0 only on 3/3
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"KESHEV UIPI selftest — integrity: {'HIGH (elevated)' if is_elevated() else 'MEDIUM'}")
    rs = run_criterion8()
    for r in rs:
        print(f"  {r.kind}/{r.method}: {'PASS' if r.ok else 'FAIL'} "
              f"({r.probe_len} chars, {r.elapsed_s}s, {r.detail})")
    sys.exit(0 if all(r.ok for r in rs) else 1)
