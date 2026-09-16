r"""wintarget -- window TARGET LOCK for KESHEV 6.

Iddo, 2026-09-12 04:12: "תסדר שיהיה אפשר לבחור הכל - מיק, חלון, הכל, פאוז
וכו', ותן אופציה: נעילה לחלון" -- let him choose everything, including
LOCKING dictation to one specific window.

THE FAILURE THIS FIXES, measured 2026-09-12 03:42: dictation types into
whatever window is in FRONT (app/typer.py's type_string() is one bulk
SendInput into GetForegroundWindow() -- see typer.py's own docstring history,
scars 09-03/09-06). At 03:42 a music player was in front, so his words went
there instead of his chat, and he did not notice until he looked. A LOCK
fixes exactly this: pick a window once, and dictation goes there regardless
of what he clicks afterward.

DESIGN, changing as little as possible in the files that already work:

  * state\target-lock.json is the ONE source of truth, read fresh on every
    utterance -- same pattern as state\mic-choice.json (main.py's
    read_mic_choice) and state\decoder.json (decoder.py's doors()). The
    window (gui6.py) writes it; the engine (main.py) never restarts to see
    a new target, exactly like a mic or decoder change today.

        {"mode": "foreground"}                                   -- default,
            byte-for-byte today's behaviour: type into whatever has focus.
        {"mode": "locked", "hwnd": N, "pid": N, "exe": "...",
         "title": "...", "locked_at": "..."}                     -- locked.

  * SendInput has NO destination argument -- whatever is foreground receives
    the keystrokes, full stop (this is also why typer.py itself only ever
    reads GetForegroundWindow()). So "locked" means: verify the locked window
    still exists, raise it to the foreground for the one burst, let the REAL
    typer.type_string() do exactly what it always does (paste-first admin-
    window refusal, SendInput, auto-Enter), then put back whatever was in
    front before -- so a lock does not steal his screen away from whatever
    else he was doing.

  * LockAwareTyper is the ONLY new object main.py has to know about. It has
    the same three-method shape app\outbox.py's Outbox already expects from
    "the typer" (.user32.GetForegroundWindow(), .is_password_manager_window(),
    .refusal_for_window(hwnd), .type_string(text, auto_enter)) so the outbox
    -- retry, 60 s hold, loud drop, never-a-silent-loss -- keeps working
    UNCHANGED in both modes: in "foreground" mode every call is a transparent
    pass-through to the real app.typer; in "locked" mode the shim answers
    "is the locked window itself alive/elevated/a password manager" instead
    of "what is in front right now", so a retry never drifts onto whatever
    the music player put in front of him a second time.

  * WHEN THE LOCKED WINDOW IS GONE: nothing is typed into a substitute
    window -- ever. Dictation is PAUSED, SIGNED the same way the pause
    button signs it (state\PAUSED carries who/why/at/restore/disables, see
    gui6.py's toggle_pause, 2026-09-06 "sign the pause" -- an unsigned pause
    gets auto-cleared by keshev_delivery_watchdog.py after 15 minutes, and
    the fix here is the same fix: name the intent, and that watchdog leaves
    it alone). This module ONLY EVER WRITES a pause; it never removes one --
    a signed pause, his or ours, is cleared only by the האזן button.

Nothing in this file opens a microphone, touches an audio device, or is
loaded by anything except gui6.py (the window) and main.py (the engine),
exactly like every other client module here.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import sys
import time
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

STATE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "state"))
TARGET_LOCK_FILE = os.path.join(STATE_DIR, "target-lock.json")

# Same tiny set typer.py's is_password_manager_window() checks -- duplicated
# on purpose rather than importing a private name across modules; it is four
# lines and has not changed since it was written.
_PASSWORD_MANAGER_EXES = frozenset({
    "keepass.exe", "1password.exe", "bitwarden.exe", "dashlane.exe", "lastpass.exe",
})

# Windows whose title marks them as KESHEV's own -- never offered in the
# window list and never a valid lock target (typing into ourselves is a
# feedback loop, and the badge/full window titles both carry these words).
_OWN_TITLE_MARKERS = ("קשב", "keshev")

SW_RESTORE = 9
_GW_HWNDNEXT = 2
RAISE_SETTLE_S = 0.12   # let the raised app move keyboard focus onto its own
                        # control before SendInput fires -- measured necessary,
                        # see LockAwareTyper.type_string

# ------------------------------------------------------------------ win32 --
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


# A harmless, released-immediately ALT key nudge (never delivered anywhere --
# see below) alongside AttachThreadInput. MEASURED 2026-09-12: AttachThreadInput
# alone still let a real SetForegroundWindow call fail silently and
# intermittently in this verification run -- same code path, same target, no
# GetLastError, success on a later attempt. Simulating a throwaway ALT
# press/release immediately before the call is the standard, independently
# documented second half of this workaround: Windows' foreground-lock
# heuristic treats a process that just generated real input as allowed to
# steal focus, and a keyboard event from SendInput counts. VK_MENU (Alt) is
# used because a lone Alt down+up is a no-op everywhere (it never combines
# with anything else here), unlike Ctrl or Shift which can trigger app
# shortcuts if anything else is held.
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
               ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
               ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ki", _KEYBDINPUT),
               ("_pad", ctypes.c_byte * 8)]   # union padding for MOUSEINPUT/HARDWAREINPUT


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_VK_MENU = 0x12


def _nudge_input() -> None:
    """A throwaway Alt down+up -- see the block above. Best-effort only:
    if it fails, bring_to_foreground still tries the AttachThreadInput path
    and its own retry loop."""
    try:
        down = _INPUT(type=_INPUT_KEYBOARD,
                     ki=_KEYBDINPUT(_VK_MENU, 0, 0, 0, 0))
        up = _INPUT(type=_INPUT_KEYBOARD,
                   ki=_KEYBDINPUT(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0, 0))
        arr = (_INPUT * 2)(down, up)
        user32.SendInput(2, arr, ctypes.sizeof(_INPUT))
    except Exception:
        pass

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL


def _window_title(hwnd) -> str:
    try:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def _window_pid(hwnd) -> int:
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    try:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    except Exception:
        return 0
    return int(pid.value)


def _exe_name(pid: int) -> str:
    """lower-cased image name, '' when unknown -- same shape as typer.py's
    _process_name, kept independent so this module never depends on typer
    being importable first."""
    if not pid or not HAS_PSUTIL:
        return ""
    try:
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


def _is_own_title(title: str) -> bool:
    low = (title or "").casefold()
    return any(m in low for m in _OWN_TITLE_MARKERS)


# --------------------------------------------------------------- discovery --

def list_windows(exclude_pid: int | None = None) -> list[dict]:
    """Visible, titled top-level windows he can lock onto right now -- never
    KESHEV's own badge/full window, never a titleless window (desktop, lock
    screen). Pure read: no focus change, nothing typed."""
    exclude_pid = os.getpid() if exclude_pid is None else exclude_pid
    out: list[dict] = []

    def _cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            title = _window_title(hwnd)
            if not title.strip() or _is_own_title(title):
                return True
            pid = _window_pid(hwnd)
            if not pid or pid == exclude_pid:
                return True
            out.append({
                "hwnd": int(hwnd), "pid": pid, "title": title,
                "exe": _exe_name(pid),
            })
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    except Exception:
        pass
    return out


def is_alive(hwnd: int, pid: int) -> bool:
    """The locked window's identity is HWND + PID, never the title (a
    terminal or browser tab rewrites its caption constantly). True only when
    the handle still names a real window AND it is still owned by the same
    process -- an HWND can in principle be recycled after the window that
    held it closes."""
    if not hwnd:
        return False
    try:
        if not user32.IsWindow(hwnd):
            return False
        return _window_pid(hwnd) == int(pid)
    except Exception:
        return False


def bring_to_foreground(hwnd: int, attempts: int = 3) -> bool:
    """Raise `hwnd`, verified. SetForegroundWindow alone is refused by
    Windows when called from a process that does not already own the
    foreground, so the calling thread's input queue is attached to the
    current foreground thread's first (ported knowledge -- the same
    AttachThreadInput dance keshev-next's sibling project, mic-rebuild's
    client/focus.py Win32FocusApi.restore_focus, already carries and tests;
    knowledge, not an import). Detaches again in a `finally`.

    MEASURED 2026-09-12 (verification run for this feature, on this machine):
    AttachThreadInput ALONE still let SetForegroundWindow fail silently and
    intermittently -- same process, same target, same code path, no
    GetLastError set, 2 of 3 bare attempts exhausted 15 retries over ~4 s
    before succeeding. Adding a throwaway ALT key nudge via SendInput right
    before the call (_nudge_input -- the standard second half of this
    workaround: Windows' foreground-lock heuristic allows a process that just
    generated real input to steal focus, and a synthetic key event counts)
    made 5 of 5 immediate attempts succeed. Both are kept: the nudge for
    speed, AttachThreadInput because it is the documented mechanism, and this
    retry loop because neither is proven to be 100% -- each try polls
    GetForegroundWindow() for up to ~200 ms (SetForegroundWindow can report
    success before the window manager has actually switched), and a refused
    attempt is retried up to `attempts` times with a short backoff before
    this returns False -- which the caller must treat as "did not raise the
    window", never as "typed into it anyway"."""
    if not hwnd:
        return False
    for attempt in range(max(1, attempts)):
        try:
            cur = user32.GetForegroundWindow()
            if cur == hwnd:
                return True
            my_tid = kernel32.GetCurrentThreadId()
            cur_tid = _thread_id(cur) if cur else 0
            _nudge_input()
            attached = bool(cur_tid) and bool(user32.AttachThreadInput(my_tid, cur_tid, True))
            try:
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(my_tid, cur_tid, False)
            for _ in range(20):
                if user32.GetForegroundWindow() == hwnd:
                    return True
                time.sleep(0.01)
        except Exception:
            pass
        if attempt + 1 < attempts:
            time.sleep(0.05)
    return False


def _thread_id(hwnd) -> int:
    if not hwnd:
        return 0
    try:
        pid = wintypes.DWORD(0)
        return int(user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)))
    except Exception:
        return 0


# ------------------------------------------------------------ persistence --

def read_target_lock() -> dict | None:
    try:
        with open(TARGET_LOCK_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_target_lock(record: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = TARGET_LOCK_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, TARGET_LOCK_FILE)


def lock_to(window: dict) -> None:
    """window is one entry from list_windows()."""
    write_target_lock({
        "mode": "locked",
        "hwnd": int(window["hwnd"]),
        "pid": int(window["pid"]),
        "exe": window.get("exe", ""),
        "title": window.get("title", ""),
        "locked_at": datetime.now().isoformat(),
    })


def unlock() -> None:
    write_target_lock({"mode": "foreground"})


# ------------------------------------------------------------ delivery -----

class LockRefusal:
    """Falsy, same shape typer.TypeRefusal presents to outbox.submit()
    (reason / proc / integrity / title) -- so `if not answer:` keeps working
    for every existing caller and the outbox files it exactly like any other
    refused sentence (except it will keep waiting on a window that, once
    truly gone, is reported by is_alive() on every retry -- the sentence
    still ages out and is DROPPED OUT LOUD by outbox.py's own 60 s rule if
    the lock is never fixed, which is the honest existing contract, not a
    new one)."""
    __slots__ = ("reason", "proc", "integrity", "title")

    def __init__(self, reason: str, lock: dict | None = None):
        lock = lock or {}
        self.reason = reason
        self.proc = lock.get("exe", "") or ""
        self.integrity = "LOCK"
        self.title = lock.get("title", "") or ""

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"LockRefusal(reason={self.reason!r}, title={self.title!r})"


class _ForegroundShim:
    """Answers app\\outbox.py's `self.typer.user32.GetForegroundWindow()`.

    In 'foreground' mode: delegates to the real typer -- byte-identical to
    today. In 'locked' mode: reports the LOCKED window (or 0 if it is gone),
    so outbox._target_ok()'s next two calls (is_password_manager_window,
    refusal_for_window) evaluate the window Iddo actually chose, not
    whatever a retry happens to find in front of him a second time."""

    def __init__(self, adapter: "LockAwareTyper"):
        self._adapter = adapter

    def GetForegroundWindow(self):
        lock = read_target_lock()
        if lock and lock.get("mode") == "locked":
            hwnd, pid = int(lock.get("hwnd") or 0), int(lock.get("pid") or 0)
            return hwnd if is_alive(hwnd, pid) else 0
        return self._adapter._real.user32.GetForegroundWindow()


class LockAwareTyper:
    """Drop-in replacement for the `typer` module, as far as main.py and
    outbox.Outbox are concerned. See module docstring for the contract."""

    def __init__(self, real_typer_mod, pause_file: str | None = None, log=None):
        self._real = real_typer_mod
        self._pause_file = pause_file
        self._log = log or (lambda m: print(m, file=sys.stderr, flush=True))
        self.user32 = _ForegroundShim(self)

    # -- the three read-only probes outbox._target_ok() calls, in order -----

    def is_password_manager_window(self) -> bool:
        lock = read_target_lock()
        if lock and lock.get("mode") == "locked":
            hwnd, pid = int(lock.get("hwnd") or 0), int(lock.get("pid") or 0)
            if not is_alive(hwnd, pid):
                return False   # is_alive's False already drives GetForegroundWindow() -> 0
            return _exe_name(pid) in _PASSWORD_MANAGER_EXES
        return self._real.is_password_manager_window()

    def refusal_for_window(self, hwnd):
        return self._real.refusal_for_window(hwnd)

    # -- the one write path --------------------------------------------------

    def type_string(self, text, auto_enter: bool = False):
        lock = read_target_lock()
        if not lock or lock.get("mode") != "locked":
            return self._real.type_string(text, auto_enter=auto_enter)

        hwnd, pid = int(lock.get("hwnd") or 0), int(lock.get("pid") or 0)
        if not is_alive(hwnd, pid):
            self._sign_pause(lock)
            return LockRefusal("locked_window_gone", lock)

        prior = self._real.user32.GetForegroundWindow()
        just_raised = prior != hwnd
        if just_raised:
            if not bring_to_foreground(hwnd):
                self._log("[target-lock] could not raise locked window title=%r "
                          "-- text held, not typed elsewhere" % lock.get("title", ""))
                return LockRefusal("locked_window_unraisable", lock)
            # SetForegroundWindow being verified (GetForegroundWindow == hwnd)
            # is not the same moment the app has actually moved KEYBOARD FOCUS
            # onto its own edit control -- measured directly: typing right on
            # the heel of the raise silently truncated a Hebrew sentence to
            # its first word in Notepad (verification run, 2026-09-12). A
            # short settle closes that race; it only ever runs on the burst
            # that had to raise a window, never on an already-foreground one.
            time.sleep(RAISE_SETTLE_S)

        # Re-verify identity immediately before the burst (scar-34-style
        # discipline, ported: the window he locked may have closed in the
        # gap between the raise and this line).
        if not is_alive(hwnd, pid):
            self._sign_pause(lock)
            return LockRefusal("locked_window_gone", lock)

        result = self._real.type_string(text, auto_enter=auto_enter)

        if prior and prior != hwnd and user32.IsWindow(prior):
            bring_to_foreground(prior)   # best-effort courtesy restore; never
                                          # allowed to affect the typed result
        return result

    # -- the auto-pause, signed, on lock-loss --------------------------------

    def _sign_pause(self, lock: dict) -> None:
        """Dictation PAUSES rather than falling back to a random window --
        and SAYS so. Writes ONLY if nothing is paused yet: a signed pause,
        his or one this module wrote a moment ago, is never overwritten or
        cleared here. The האזן button is the only way back (same as any
        other pause)."""
        if self._pause_file is None:
            return
        try:
            if os.path.exists(self._pause_file):
                return
            os.makedirs(os.path.dirname(self._pause_file), exist_ok=True)
            title = lock.get("title", "?")
            with open(self._pause_file, "w", encoding="utf-8") as f:
                json.dump({
                    "who": "KESHEV (נעילת חלון / target lock)",
                    "why": f"החלון הנעול ({title}) נסגר -- אין הקלדה למקום אקראי",
                    "at": datetime.now().isoformat(),
                    "restore": "בחר יעד חדש בחלון קשב ולחץ 'האזן'",
                    "disables": True,
                    "reason": "locked_window_gone",
                    "locked_title": title,
                }, f, ensure_ascii=False, indent=2)
            self._log("[target-lock] locked window gone (title=%r) -- "
                      "PAUSED and signed, not typing anywhere else" % title)
        except Exception as exc:
            self._log("[target-lock] could not sign the pause: %r" % exc)


# --------------------------------------------------------------- selftest --
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        ok = True

        wins = list_windows()
        print(f"list_windows(): {len(wins)} candidate window(s)")
        for w in wins[:5]:
            print(f"   hwnd={w['hwnd']} pid={w['pid']} exe={w['exe']!r} "
                  f"title={w['title'][:50]!r}")
        for w in wins:
            if _is_own_title(w["title"]):
                print("SELFTEST FAIL: KESHEV's own window leaked into list_windows()")
                ok = False

        # is_alive: hwnd 0 and a bogus hwnd are always dead; a real window
        # from the enumeration above (if any) must read alive right now.
        if is_alive(0, 0) is not False:
            print("SELFTEST FAIL: is_alive(0, 0) must be False")
            ok = False
        if is_alive(0xDEADBEE, 999999) is not False:
            print("SELFTEST FAIL: is_alive() on a bogus handle must be False")
            ok = False
        if wins:
            w = wins[0]
            if is_alive(w["hwnd"], w["pid"]) is not True:
                print("SELFTEST FAIL: a window EnumWindows just returned "
                      "must read alive")
                ok = False
            if is_alive(w["hwnd"], w["pid"] + 1) is not False:
                print("SELFTEST FAIL: a PID mismatch on a real HWND must "
                      "read dead (identity is HWND+PID, never title alone)")
                ok = False

        # round-trip the persisted file through a decoy path -- never touch
        # the real state\target-lock.json from a selftest.
        import tempfile
        real_path = TARGET_LOCK_FILE
        try:
            d = tempfile.mkdtemp(prefix="keshev-wintarget-selftest-")
            TARGET_LOCK_FILE = os.path.join(d, "target-lock.json")
            if read_target_lock() is not None:
                print("SELFTEST FAIL: a fresh decoy path must read as None")
                ok = False
            unlock()
            r = read_target_lock()
            if r != {"mode": "foreground"}:
                print(f"SELFTEST FAIL: unlock() round-trip got {r!r}")
                ok = False
            if wins:
                lock_to(wins[0])
                r = read_target_lock()
                if r.get("mode") != "locked" or r.get("hwnd") != wins[0]["hwnd"]:
                    print(f"SELFTEST FAIL: lock_to() round-trip got {r!r}")
                    ok = False
            os.remove(TARGET_LOCK_FILE)
            os.rmdir(d)
        finally:
            TARGET_LOCK_FILE = real_path

        # LockAwareTyper in 'foreground' mode (decoy path -> None -> default)
        # must be a byte-identical pass-through -- never opens a window, never
        # touches SendInput itself (the FAKE real_typer below proves the call
        # reached it unchanged).
        class _FakeReal:
            def __init__(self):
                self.calls = []
                self.user32 = type("u", (), {"GetForegroundWindow": staticmethod(lambda: 4242)})()
            def is_password_manager_window(self):
                self.calls.append("pwcheck")
                return False
            def refusal_for_window(self, hwnd):
                self.calls.append(("refusal", hwnd))
                return None
            def type_string(self, text, auto_enter=False):
                self.calls.append(("type", text, auto_enter))
                return True

        TARGET_LOCK_FILE = os.path.join(tempfile.mkdtemp(prefix="keshev-wintarget-decoy2-"),
                                        "target-lock.json")
        try:
            fake = _FakeReal()
            adapter = LockAwareTyper(fake, pause_file=None, log=lambda m: None)
            if adapter.user32.GetForegroundWindow() != 4242:
                print("SELFTEST FAIL: default mode GetForegroundWindow must pass through")
                ok = False
            r = adapter.type_string("שלום", auto_enter=True)
            if r is not True or fake.calls[-1] != ("type", "שלום", True):
                print(f"SELFTEST FAIL: default-mode type_string did not pass through, calls={fake.calls!r}")
                ok = False
        finally:
            try:
                os.remove(TARGET_LOCK_FILE)
                os.rmdir(os.path.dirname(TARGET_LOCK_FILE))
            except OSError:
                pass
            TARGET_LOCK_FILE = real_path

        print("WINTARGET OK" if ok else "WINTARGET FAIL")
        sys.exit(0 if ok else 1)
    print("Usage: python app/wintarget.py --selftest")
