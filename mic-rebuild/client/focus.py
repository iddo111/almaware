"""KESHEV focus guard — K14 (PHASE2-DESIGN.md section 2 focus.py row;
PHASE1-INQUIRY.md scars 34/35/37/38).

SendInput has NO destination argument: whatever is foreground receives the
events. This module is the ONLY authority on whether typing may proceed,
and it enforces, in order:

  1. A usable foreground window exists (hwnd + pid readable) — an
     unreadable window is never permission to type (scar 34).
  2. The app's OWN window is a feedback loop: hard-blocked always. Focus
     is then put BACK where the user was — Z-order-behind first, watcher
     memory second — and the change is VERIFIED before typing (scar 34;
     restoring the user's window is the ONE sanctioned focus move,
     scar 38 — KESHEV never brings ITSELF forward).
  3. Title-less windows are hard-blocked EVEN in "anywhere" mode, with an
     HONEST error naming the image path (typing into the desktop renames
     files — scar 34).
  4. Allowlist mode: browser top-levels are DENIED (a top-level HWND
     cannot distinguish chat content from the address bar — scar 34);
     otherwise the cf-stripped, casefolded title must contain a
     configured target substring. "Anywhere" mode allows any titled,
     non-own window. Default policy is allowlist with ZERO targets —
     fail closed.
  5. Unicode Cf format controls are stripped before ANY match — titles
     arrive RTL-wrapped and exe names can be spoofed with invisibles
     (scar 34).
  6. Window identity is HWND + PID + image path, NEVER the caption — a
     terminal spinner rewrites its title every tick (scar 34).

Every refusal raises FocusGuardError (real error, parkable — scar 35) AND
emits FOCUS_BLOCK with the EXE name only, never the title (privacy law,
section 8).

Ctypes knowledge ported from alma-mic typer.py (the _Win32Api boundary,
AttachThreadInput restore dance, GW_HWNDNEXT walk) — knowledge, not a
dependency: KESHEV imports nothing from alma-mic.
"""
from __future__ import annotations

import threading
import time
import unicodedata
from typing import Callable, NamedTuple, Optional

# ------------------------------------------------------------------ types


class FocusGuardError(RuntimeError):
    """Typing was refused. `reason` is a stable machine code; the message
    is the honest human explanation (scar 35: real error, never silent)."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class FocusChangedError(FocusGuardError):
    """The foreground target changed between guard snapshots."""

    def __init__(self, message: str):
        super().__init__("focus_changed", message)


class Target(NamedTuple):
    hwnd: int
    title: str
    pid: int
    image_path: str


# ------------------------------------------------------------ pure helpers


def strip_cf(s: str) -> str:
    """Remove Unicode Cf (format) controls — RLM/LRM/ZWSP/ZWJ and friends.

    Windows wraps RTL titles in invisible directional controls, and an exe
    name can be spoofed with them; every match in this module runs on the
    stripped form (scar 34)."""
    return "".join(ch for ch in (s or "") if unicodedata.category(ch) != "Cf").strip()


def clean_image_path(image_path: str) -> str:
    cleaned = strip_cf(image_path).replace("/", "\\")
    if cleaned.startswith("\\\\?\\"):
        cleaned = cleaned[4:]
    return cleaned


def exe_name(image_path: str) -> str:
    """Cf-stripped, casefolded basename of an image path."""
    return clean_image_path(image_path).rsplit("\\", 1)[-1].casefold()


# Browser top-level executables (scar 34: denied in allowlist mode — their
# top-level HWND cannot distinguish page focus from address-bar focus).
BROWSER_EXES: frozenset[str] = frozenset({
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
    "opera_gx.exe", "vivaldi.exe", "iexplore.exe",
})

# Console hosts (scar 31 caveat lives in typer.py: these DISCARD
# KEYEVENTF_UNICODE — paste is the only reliable door).
TERMINAL_EXES: frozenset[str] = frozenset({
    "windowsterminal.exe", "conhost.exe", "openconsole.exe",
    "powershell.exe", "pwsh.exe", "cmd.exe", "alacritty.exe",
    "wezterm-gui.exe",
})

# Windows whose title marks them as OURS regardless of PID (tray flyouts and
# balloons can be hosted by explorer): typing into KESHEV is a feedback loop.
OWN_TITLE_MARKERS: tuple[str, ...] = ("keshev",)

# Shell surfaces that are never dictation targets when walking Z-order.
_ZORDER_SKIP_TITLES: frozenset[str] = frozenset({
    "program manager", "windows input experience",
})


def is_browser(image_path: str) -> bool:
    return exe_name(image_path) in BROWSER_EXES


def is_terminal(image_path: str) -> bool:
    return exe_name(image_path) in TERMINAL_EXES


def same_target(left: Target, right: Target) -> bool:
    """Identity = HWND + PID + normalized image path. NEVER the title:
    a Windows Terminal spinner rewrites its caption every tick and only
    the Braille frame differs (scar 34, verbatim incident)."""
    return (
        left.hwnd == right.hwnd
        and left.pid == right.pid
        and clean_image_path(left.image_path).casefold()
        == clean_image_path(right.image_path).casefold()
    )


# ------------------------------------------------------- real Win32 layer


class Win32FocusApi:
    """Narrow Win32 boundary — replaceable by deterministic fakes in tests.

    Instantiated lazily so importing this module never touches user32
    (tests, lint, and the server side import it freely)."""

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _MAX_PATH_CHARS = 32768
    _GW_HWNDNEXT = 2
    _SW_RESTORE = 9

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
        u.GetWindow.restype = wintypes.HWND
        u.IsWindowVisible.argtypes = (wintypes.HWND,)
        u.IsWindowVisible.restype = wintypes.BOOL
        u.SetForegroundWindow.argtypes = (wintypes.HWND,)
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
        u.AttachThreadInput.restype = wintypes.BOOL
        u.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        u.ShowWindow.restype = wintypes.BOOL
        k.GetCurrentThreadId.restype = wintypes.DWORD
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = (wintypes.HANDLE,)
        k.CloseHandle.restype = wintypes.BOOL
        self._u, self._k = u, k

    def foreground_hwnd(self) -> int:
        return int(self._u.GetForegroundWindow() or 0)

    def window_title(self, hwnd: int) -> str:
        if not hwnd:
            return ""
        try:
            length = int(self._u.GetWindowTextLengthW(hwnd))
            if length <= 0:
                return ""
            buf = self._ctypes.create_unicode_buffer(min(length + 1, self._MAX_PATH_CHARS))
            copied = int(self._u.GetWindowTextW(hwnd, buf, len(buf)))
            return buf.value if copied > 0 else ""
        except Exception:
            return ""  # unreadable title is never permission to type

    def process_identity(self, hwnd: int) -> tuple[int, str]:
        if not hwnd:
            return 0, ""
        ctypes, wintypes = self._ctypes, self._wintypes
        pid = wintypes.DWORD(0)
        try:
            tid = int(self._u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)))
            if not tid or not pid.value:
                return 0, ""
            handle = self._k.OpenProcess(
                self._PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if not handle:
                return 0, ""
            try:
                buf = ctypes.create_unicode_buffer(self._MAX_PATH_CHARS)
                size = wintypes.DWORD(len(buf))
                ok = self._k.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
                return (int(pid.value), buf.value[: size.value]) if ok else (0, "")
            finally:
                self._k.CloseHandle(handle)
        except Exception:
            return 0, ""  # unreadable ownership is never permission to type

    def restore_focus(self, hwnd: int) -> bool:
        """Bring a window the user was ALREADY working in back to foreground.

        Windows refuses SetForegroundWindow from a process that does not own
        the foreground, so attach to the current foreground thread's input
        queue first, then detach; returns True only after VERIFYING the
        change took (scar 34/37 — SetForegroundWindow fails silently)."""
        if not hwnd:
            return False
        try:
            cur = self.foreground_hwnd()
            if cur == hwnd:
                return True
            me = self._k.GetCurrentThreadId()
            other = self._u.GetWindowThreadProcessId(cur, None) if cur else 0
            attached = bool(other) and bool(self._u.AttachThreadInput(me, other, True))
            try:
                self._u.ShowWindow(hwnd, self._SW_RESTORE)
                self._u.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    self._u.AttachThreadInput(me, other, False)
            for _ in range(20):                     # give the WM up to ~200 ms
                if self.foreground_hwnd() == int(hwnd):
                    return True
                time.sleep(0.01)
            return False
        except Exception:
            return False

    def windows_behind(self, hwnd: int, limit: int = 8) -> list[int]:
        """Visible, titled top-level windows behind `hwnd` in Z-order —
        the first is what the user was looking at before our window came
        forward."""
        out: list[int] = []
        try:
            cur = int(hwnd or 0)
            for _ in range(60):
                cur = int(self._u.GetWindow(cur, self._GW_HWNDNEXT) or 0)
                if not cur:
                    break
                if not self._u.IsWindowVisible(cur):
                    continue
                if not strip_cf(self.window_title(cur)):
                    continue
                out.append(cur)
                if len(out) >= limit:
                    break
        except Exception as e:   # a broken walk yields fewer candidates, loudly-typed
            _ = e
        return out


# ---------------------------------------------------------------- the guard


class FocusGuard:
    """The single authority on where dictation may land."""

    WATCH_INTERVAL_S = 0.25          # scar 34: the focus watcher cadence

    def __init__(
        self,
        api=None,
        own_pid: Optional[int] = None,
        emit: Optional[Callable[..., None]] = None,
    ):
        import os

        self._api = api if api is not None else Win32FocusApi()
        self._own_pid = int(own_pid if own_pid is not None else os.getpid())
        self._emit = emit
        # Default policy FAILS CLOSED: allowlist mode, zero targets.
        self._policy: dict = {"anywhere": False, "targets": ()}
        self._last_external: Optional[Target] = None
        self._watcher: Optional[threading.Thread] = None
        self._watcher_stop = threading.Event()

    # ------------------------------------------------------------- policy

    def set_policy(self, anywhere: bool = False, targets=()) -> None:
        self._policy = {
            "anywhere": bool(anywhere),
            "targets": tuple(
                strip_cf(t).casefold() for t in (targets or ()) if strip_cf(t)
            ),
        }

    def policy(self) -> dict:
        return dict(self._policy)

    # ------------------------------------------------------------ watcher

    def last_external(self) -> Optional[Target]:
        return self._last_external

    def note_foreground(self) -> None:
        """One watcher tick: remember the last REAL window the user was in.
        Guessing from Z-order at type-time is unreliable; watching focus as
        it happens records the truth (ported knowledge, alma-mic)."""
        try:
            t = self.foreground_target()
        except Exception:
            return
        if not t.hwnd or not t.pid:
            return
        if self._is_own(t):
            return
        if not strip_cf(t.title):
            return
        self._last_external = t

    def start_watcher(self) -> threading.Thread:
        """Start the 0.25s focus watcher (idempotent)."""
        if self._watcher is not None and self._watcher.is_alive():
            return self._watcher

        def loop() -> None:
            while not self._watcher_stop.wait(self.WATCH_INTERVAL_S):
                self.note_foreground()

        self._watcher_stop.clear()
        th = threading.Thread(target=loop, daemon=True, name="keshev-focus-watch")
        th.start()
        self._watcher = th
        return th

    def stop_watcher(self) -> None:
        self._watcher_stop.set()

    # -------------------------------------------------------------- guard

    def foreground_target(self) -> Target:
        hwnd = self._api.foreground_hwnd()
        title = self._api.window_title(hwnd)
        pid, image_path = self._api.process_identity(hwnd)
        return Target(hwnd=hwnd, title=title, pid=pid, image_path=image_path)

    def require_allowed_target(self) -> Target:
        """Return the verified, allowed foreground target — or refuse loudly.

        Called immediately before EVERY SendInput burst (double-snapshot
        discipline lives in typer.py, which calls this twice)."""
        t = self.foreground_target()

        if not t.hwnd or not t.pid:
            self._refuse(t, "no_window", "no usable foreground window")

        if self._is_own(t):
            # Our own window has focus (tray flyout / settings). Typing here
            # is a feedback loop. Put focus BACK where the user was:
            # Z-order-behind first, watcher memory second (scar 34) — and
            # verify BOTH the restore and the restored target's allowedness.
            candidates: list[int] = []
            for h in self._api.windows_behind(t.hwnd):
                ct = self._target_of(h)
                if ct.pid and not self._is_own(ct) and strip_cf(ct.title):
                    low = strip_cf(ct.title).casefold()
                    if low not in _ZORDER_SKIP_TITLES:
                        candidates.append(h)
            remembered = self._last_external
            if remembered is not None and remembered.hwnd not in candidates:
                candidates.append(remembered.hwnd)

            for hwnd in candidates:
                if self._api.restore_focus(hwnd):
                    now = self.foreground_target()
                    if now.hwnd == hwnd:
                        self._check_allowed(now)         # raises if not allowed
                        self._last_external = now
                        return now
            self._refuse(
                t, "own_window_unrecovered",
                "KESHEV's own window has focus and no previous window could "
                "be restored — click the window you want, then speak.",
            )

        self._check_allowed(t)
        self._last_external = t
        return t

    # ----------------------------------------------------------- internals

    def _target_of(self, hwnd: int) -> Target:
        pid, image_path = self._api.process_identity(hwnd)
        return Target(hwnd=hwnd, title=self._api.window_title(hwnd),
                      pid=pid, image_path=image_path)

    def _is_own(self, t: Target) -> bool:
        if t.pid == self._own_pid:
            return True
        low = strip_cf(t.title).casefold()
        return any(marker in low for marker in OWN_TITLE_MARKERS)

    def _check_allowed(self, t: Target) -> None:
        """Rules 3–4 for a non-own target. Raises FocusGuardError."""
        title = strip_cf(t.title)
        if not title:
            # HONEST error: name the image path so Iddo can see who held
            # focus (desktop, lock screen, a tray flyout) — scar 34/35.
            self._refuse(
                t, "no_title",
                "focused window has no title (desktop / lock screen?) — "
                "click into the window you want, then speak. "
                f"(image={clean_image_path(t.image_path)!r})",
            )
        if not self._policy["anywhere"]:
            if is_browser(t.image_path):
                self._refuse(
                    t, "browser_allowlist",
                    "browser top-level windows are not allowed in allowlist "
                    "mode (focus may be in the address bar) — enable "
                    "type-anywhere or use a native app window. "
                    f"(exe={exe_name(t.image_path)!r})",
                )
            low = title.casefold()
            if not any(target in low for target in self._policy["targets"]):
                self._refuse(
                    t, "not_in_allowlist",
                    "focused window is not in the allowlist — enable "
                    "type-anywhere or add the app to the targets. "
                    f"(exe={exe_name(t.image_path)!r})",
                )

    def _refuse(self, t: Target, reason: str, message: str) -> None:
        if self._emit is not None:
            # privacy law (section 8): EXE names only, NEVER window titles
            self._emit("FOCUS_BLOCK", reason=reason,
                       exe=exe_name(t.image_path) or "?")
        raise FocusGuardError(reason, message)
