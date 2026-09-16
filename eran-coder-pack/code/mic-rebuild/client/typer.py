"""KESHEV typer — K14 (PHASE2-DESIGN.md section 2 typer.py row;
PHASE1-INQUIRY.md scars 31/32/33/35/36).

THE single serialization point: `Typer.type()` is the only door through
which text reaches a window, it holds a lock, and the router is its only
caller (design section 4.1). Knowledge ported from alma-mic typer.py —
knowledge, not imports:

  PASTE-FIRST, FOR EVERY WINDOW (scar 31). Per-character SendInput sends
  2 events per character and a receiving app that cannot drain its message
  queue fast enough silently LOSES some. On 2026-08-06 a 79-character
  utterance arrived with all its spaces stripped — all 162 events were
  sent, the receiver dropped some. A paste is ONE atomic clipboard read:
  4 events regardless of length. Unicode SendInput remains as fallback,
  CHUNKED (small bursts, breather between, target re-verified per chunk)
  so a long burst can never silently thin out again.

  TERMINALS DISCARD KEYEVENTF_UNICODE ENTIRELY (scar 31): SendInput
  returns success, the log says TYPED ok, nothing appears. So when the
  target is a console host and the paste path fails, the fallback is an
  HONEST REFUSAL (parked, logged) — never the unicode path.

  NO automatic clipboard restore (scar 32). Ctrl+V is only a REQUEST —
  the app reads the clipboard when it gets around to it; restoring after
  120-230ms pasted the user's PREVIOUS clipboard for a whole night.
  Restore is opt-in: wait >= 1.0s, put the old contents back ONLY if the
  clipboard still holds exactly what we pasted.

  Clipboard ctypes discipline (scar 33): c_void_p handles everywhere
  (int truncation -> ERROR_INVALID_HANDLE), wstring_at reads (c_wchar_p
  from a raw pointer segfaults), ~12x OpenClipboard retry (any process
  may hold it).

  Enter is a SEPARATE burst after ~0.35s that re-verifies the SAME
  target (scar 36) — single-burst Enter raced slow apps and submitted
  empty/half lines.

  HOLD WHILE HE IS TYPING (2026-08-17 night). He typed "מיק" and a voiced
  "Hello." landed INSIDE it: "מיHello.ק". The mic must NEVER fight his
  hands for the cursor. Before any burst the typer reads the OS last-input
  clock (GetLastInputInfo, same boundary the presence gate uses): if a
  human touched keyboard/mouse within the last HOLD_QUIET_S, it WAITS,
  polling, for a HOLD_QUIET_S quiet gap — bounded by HOLD_MAX_WAIT_S,
  after which the text is PARKED (scar 35: divert, never drop) and
  TYPING_COLLISION is journaled. THE TRAP: our OWN SendInput also updates
  that clock, so a naive gate waits for itself forever. Every injection
  timestamps _last_inject, and an input-clock update at/just after our own
  burst (within OWN_INPUT_GRACE_S) is attributed to US, not him. The same
  attribution guards auto-Enter: a keypress of HIS between the text burst
  and the Enter burst withholds the Enter — pasting into his sentence is
  recoverable, submitting it is not.

Refused text is PARKED to state\\parked.txt as a JSONL record — real
error, recoverable, never a silent drop (scar 35; criterion 9).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable, NamedTuple, Optional, Sequence

from client.focus import (
    FocusGuard,
    FocusGuardError,
    Target,
    exe_name,
    is_terminal,
    same_target,
)

# ------------------------------------------------------------- constants

VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_V = 0x56

ENTER_DELAY_S = 0.35             # scar 36: let the app ingest the text first
CLIPBOARD_RESTORE_WAIT_S = 1.0   # scar 32: opt-in restore waits a FULL second
CLIPBOARD_OPEN_RETRIES = 12      # scar 33: any process may hold the clipboard
CHUNK_EVENTS = 32                # scar 31: fallback bursts stay small…
INTER_CHUNK_SLEEP_S = 0.008      # …with a breather so the receiver can drain

# Hold-while-typing gate (the "מיHello.ק" collision, 2026-08-17 night):
HOLD_QUIET_S = 1.5               # required keyboard-quiet gap before a burst
HOLD_MAX_WAIT_S = 9.0            # bounded wait; beyond it the text is PARKED
HOLD_POLL_S = 0.1                # poll cadence while yielding to his hands
# Input-clock updates within this window after our OWN SendInput are OURS
# (SendInput lands in the input queue within ms; GetLastInputInfo ticks at
# ~15.6 ms granularity; the rest is margin for a busy scheduler). Larger
# would blind the gate to real keys right after a burst; smaller risks the
# self-deadlock the gate exists to avoid.
OWN_INPUT_GRACE_S = 0.15

# Events are plain tuples until the real layer converts them — fakes can
# introspect them and unit tests never build ctypes structures:
#   ("vk", virtual_key, key_up)        classic virtual-key event
#   ("unicode", utf16_code_unit, key_up)  KEYEVENTF_UNICODE event
Event = tuple


def utf16_units(text: str) -> list[int]:
    """UTF-16 code units for `text` — surrogate pairs for astral chars
    (scar 31: the fallback must type emoji and rare CJK correctly)."""
    units: list[int] = []
    for ch in text:
        cp = ord(ch)
        if cp > 0xFFFF:
            cp -= 0x10000
            units.append(0xD800 + (cp >> 10))
            units.append(0xDC00 + (cp & 0x3FF))
        else:
            units.append(cp)
    return units


class Outcome(NamedTuple):
    """What the router journals off (design 4.1: TYPED / TYPE_FAIL_PARKED)."""
    ok: bool
    method: str          # "paste" | "sendinput" | "none"
    reason: str          # "" on success; stable machine code on refusal
    events: int          # input events the OS accepted
    parked: bool         # True -> the text (or its remainder) is in parked.txt
    enter_ok: Optional[bool]   # None = no enter requested
    exe: str             # target executable name ("" if none)


# ------------------------------------------------------- real Win32 layer


class Win32InputApi:
    """SendInput boundary. Ctypes structures ported from alma-mic typer.py."""

    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP = 0x0002
    _KEYEVENTF_UNICODE = 0x0004

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        ULONG_PTR = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ULONG_PTR))

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR))

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                        ("wParamH", wintypes.WORD))

        class IUNION(ctypes.Union):
            _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))

        class INPUT(ctypes.Structure):
            _fields_ = (("type", wintypes.DWORD), ("u", IUNION))

        u = ctypes.WinDLL("user32", use_last_error=True)
        u.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        u.SendInput.restype = wintypes.UINT
        self._ctypes = ctypes
        self._u = u
        self._INPUT = INPUT
        self._KEYBDINPUT = KEYBDINPUT
        self._IUNION = IUNION

    def _to_input(self, ev: Event):
        kind, code, up = ev
        if kind == "unicode":
            flags = self._KEYEVENTF_UNICODE | (self._KEYEVENTF_KEYUP if up else 0)
            ki = self._KEYBDINPUT(0, code, flags, 0, 0)
        else:  # "vk"
            flags = self._KEYEVENTF_KEYUP if up else 0
            ki = self._KEYBDINPUT(code, 0, flags, 0, 0)
        return self._INPUT(type=self._INPUT_KEYBOARD, u=self._IUNION(ki=ki))

    def send_input(self, events: Sequence[Event]) -> int:
        if not events:
            return 0
        arr = (self._INPUT * len(events))(*(self._to_input(e) for e in events))
        return int(self._u.SendInput(len(arr), arr, self._ctypes.sizeof(self._INPUT)))


class Win32Clipboard:
    """CF_UNICODETEXT get/set with the scar-33 discipline: c_void_p handles,
    wstring_at reads, bounded OpenClipboard retry."""

    _CF_UNICODETEXT = 13
    _GMEM_MOVEABLE = 0x0002

    def __init__(self):
        import ctypes

        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        # Handles MUST be c_void_p — the default int return truncates a
        # 64-bit HANDLE and SetClipboardData fails with ERROR_INVALID_HANDLE.
        u.OpenClipboard.argtypes = (ctypes.c_void_p,)
        u.OpenClipboard.restype = ctypes.c_int
        u.CloseClipboard.restype = ctypes.c_int
        u.EmptyClipboard.restype = ctypes.c_int
        u.GetClipboardData.argtypes = (ctypes.c_uint,)
        u.GetClipboardData.restype = ctypes.c_void_p
        u.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
        u.SetClipboardData.restype = ctypes.c_void_p
        k.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
        k.GlobalAlloc.restype = ctypes.c_void_p
        k.GlobalLock.argtypes = (ctypes.c_void_p,)
        k.GlobalLock.restype = ctypes.c_void_p
        k.GlobalUnlock.argtypes = (ctypes.c_void_p,)
        k.GlobalUnlock.restype = ctypes.c_int
        k.GlobalSize.argtypes = (ctypes.c_void_p,)
        k.GlobalSize.restype = ctypes.c_size_t
        self._ctypes, self._u, self._k = ctypes, u, k

    def _open(self) -> bool:
        for _ in range(CLIPBOARD_OPEN_RETRIES):
            if self._u.OpenClipboard(0):
                return True
            time.sleep(0.02)
        return False

    def get(self) -> Optional[str]:
        ctypes = self._ctypes
        try:
            if not self._open():
                return None
            try:
                h = self._u.GetClipboardData(self._CF_UNICODETEXT)
                if not h:
                    return None
                ptr = self._k.GlobalLock(h)
                if not ptr:
                    return None
                try:
                    # wstring_at, NOT c_wchar_p(ptr).value — constructing a
                    # c_wchar_p from a raw void* and reading .value segfaults.
                    size = int(self._k.GlobalSize(h) or 0)
                    if size < 2:
                        return None
                    return ctypes.wstring_at(ptr, (size // 2) - 1)
                finally:
                    self._k.GlobalUnlock(h)
            finally:
                self._u.CloseClipboard()
        except Exception:
            return None

    def set(self, text: str) -> bool:
        ctypes = self._ctypes
        try:
            buf = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(buf)
            h = self._k.GlobalAlloc(self._GMEM_MOVEABLE, size)
            if not h:
                return False
            ptr = self._k.GlobalLock(h)
            ctypes.memmove(ptr, buf, size)
            self._k.GlobalUnlock(h)
            if not self._open():
                return False
            try:
                self._u.EmptyClipboard()
                return bool(self._u.SetClipboardData(self._CF_UNICODETEXT, h))
            finally:
                self._u.CloseClipboard()
        except Exception:
            return False


# ------------------------------------------------------------------ typer


class Typer:
    """The ONE serialization point (design section 2: single call site,
    router is the only caller; a lock enforces at-most-one burst in flight)."""

    CHUNK_EVENTS = CHUNK_EVENTS

    def __init__(
        self,
        guard: FocusGuard,
        input_api=None,
        clip=None,
        state_dir: Path | str = Path("state"),
        emit: Optional[Callable[..., None]] = None,
        clipboard_restore: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        idle_api=None,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self._guard = guard
        self._input = input_api if input_api is not None else Win32InputApi()
        self._clip = clip if clip is not None else Win32Clipboard()
        self._emit = emit
        self._clipboard_restore = bool(clipboard_restore)   # scar 32: opt-in ONLY
        self._sleep = sleep
        # Hold-while-typing gate. None = gate OFF (transparent) — the REAL
        # default (presence.Win32IdleApi) is wired by build_app, exactly like
        # the presence gate itself: a Typer that default-constructed the real
        # clock would make every unit test depend on whether a human touched
        # the keyboard while it ran (the scar test_type_fn_carries_auto_enter
        # _from_config already paid for once). build_app never passes None;
        # tests/test_app.py asserts that wiring.
        self._idle = idle_api
        self._mono = monotonic
        self._last_inject: Optional[float] = None   # our own SendInput times
        self._lock = threading.Lock()
        self.parked_path = Path(state_dir) / "parked.txt"

    # ------------------------------------------------------------ parking

    def park(self, text: str, reason: str) -> None:
        """Append refused text to state\\parked.txt — recoverable, never a
        silent drop (scar 35). JSONL so multiline text survives verbatim."""
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "reason": reason,
            "text": text,
        }
        self.parked_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with open(self.parked_path, "a", encoding="utf-8") as fh:
            fh.write(line)

    # ------------------------------------------------------------- typing

    def type(self, text: str, enter: bool = False,
             enter_delay: float = ENTER_DELAY_S,
             force_sendinput: bool = False) -> Outcome:
        """Type `text` into the verified foreground window.

        `force_sendinput` exists for the UIPI selftest ONLY — it proves the
        per-char fallback path (chunked batching) against a real window.
        Production always tries paste first (scar 31)."""
        with self._lock:
            return self._type_locked(text, enter, enter_delay, force_sendinput)

    def _type_locked(self, text: str, enter: bool, enter_delay: float,
                     force_sendinput: bool) -> Outcome:
        if not text and not enter:
            return Outcome(True, "none", "", 0, False, None, "")

        # Hold gate FIRST — before the focus snapshot, deliberately: the
        # wait may outlast an Alt-Tab, and the burst must land in the window
        # that is current when we actually inject, not the one from before
        # the wait ("מיHello.ק", 2026-08-17).
        proceed, waited_ms = self._hold_for_quiet()
        if not proceed:
            if text:
                self.park(text, "typing_collision")
            if self._emit is not None:
                self._emit("TYPING_COLLISION", action="parked",
                           wait_ms=waited_ms)
            return Outcome(False, "none", "typing_collision", 0, bool(text),
                           None, "")
        if waited_ms > 0 and self._emit is not None:
            self._emit("TYPING_COLLISION", action="held", wait_ms=waited_ms)

        # Snapshot 1 — the guard refuses loudly; refusals park the text.
        try:
            target = self._guard.require_allowed_target()
        except FocusGuardError as e:
            if text:
                self.park(text, e.reason)
            return Outcome(False, "none", e.reason, 0, bool(text), None, "")

        exe = exe_name(target.image_path)
        n_sent = 0
        method = "none"

        if text:
            if force_sendinput:
                ok, n_sent, reason = self._send_unicode_chunked(text, target)
                method = "sendinput"
                if not ok:
                    return Outcome(False, method, reason, n_sent, True, None, exe)
            else:
                pasted, n_sent, paste_reason = self._paste(text, target)
                if pasted:
                    method = "paste"
                elif paste_reason == "focus_changed":
                    self.park(text, paste_reason)
                    return Outcome(False, "paste", paste_reason, 0, True, None, exe)
                elif is_terminal(target.image_path):
                    # Terminals DISCARD KEYEVENTF_UNICODE: falling back would
                    # be the "TYPED ok lied for weeks" hole. Honest refusal.
                    reason = "terminal_paste_failed"
                    self.park(text, reason)
                    if self._emit is not None:
                        self._emit("FOCUS_BLOCK", reason=reason, exe=exe)
                    return Outcome(False, "paste", reason, 0, True, None, exe)
                else:
                    ok, n_sent, reason = self._send_unicode_chunked(text, target)
                    method = "sendinput"
                    if not ok:
                        return Outcome(False, method, reason, n_sent, True, None, exe)

        enter_ok: Optional[bool] = None
        if enter:
            enter_ok = self._send_enter(target, enter_delay, exe)
            if enter_ok:
                n_sent += 2

        return Outcome(True, method, "", n_sent, False, enter_ok, exe)

    # ---------------------------------------------------------- internals

    def _send(self, events: Sequence[Event]) -> int:
        """THE one door to SendInput. Timestamps every accepted burst so the
        hold gate can tell OUR input-clock updates from HIS (the trap: our
        own injections update GetLastInputInfo too — an unattributed gate
        waits for itself forever)."""
        n = self._input.send_input(events)
        if n > 0:
            self._last_inject = self._mono()
        return n

    def _user_typing(self) -> Optional[bool]:
        """Did a HUMAN touch keyboard/mouse within HOLD_QUIET_S?

        True = yes, and it was not our own injection. False = quiet, or the
        only recent input was OUR OWN SendInput echo. None = the clock is
        unreadable — which is never a reason to lose his words (the same
        fail-open-on-type law the presence gate states)."""
        idle = self._idle.idle_seconds()
        if idle is None:
            return None
        idle = max(0.0, float(idle))
        if idle >= HOLD_QUIET_S:
            return False
        # Recent input exists. Attribute it: GetLastInputInfo's tick clock
        # and time.monotonic tick together closely enough that (now - idle)
        # names the moment of last input on our own clock within ~ms.
        last_input = self._mono() - idle
        if (self._last_inject is not None
                and last_input <= self._last_inject + OWN_INPUT_GRACE_S):
            return False                       # our own burst's echo
        return True

    def _hold_for_quiet(self) -> tuple[bool, int]:
        """The hold-while-typing gate. Returns (proceed, waited_ms).

        proceed=False means the keyboard never went quiet inside
        HOLD_MAX_WAIT_S — the caller parks the text (scar 35), never types
        over his hands, never drops a word."""
        if self._idle is None:                 # gate unwired (unit tests)
            return True, 0
        start = self._mono()
        waited = 0.0
        while True:
            if self._user_typing() is not True:
                return True, int(waited * 1000)
            waited = self._mono() - start
            if waited >= HOLD_MAX_WAIT_S:
                return False, int(waited * 1000)
            self._sleep(HOLD_POLL_S)
            waited = self._mono() - start

    def _verify_same(self, expected: Target) -> bool:
        """Snapshot the foreground immediately before a burst and require
        the SAME identity (HWND+PID+exe, never title — scar 34)."""
        try:
            now = self._guard.require_allowed_target()
        except FocusGuardError:
            return False
        return same_target(now, expected)

    def _paste(self, text: str, target: Target) -> tuple[bool, int, str]:
        """Clipboard + Ctrl+V: 4 events, atomic, length-independent (scar 31)."""
        prev = self._clip.get() if self._clipboard_restore else None
        if not self._clip.set(text):
            return False, 0, "clipboard_set_failed"
        # Snapshot 2 — deliberately adjacent to the SendInput call: closes
        # the race where the user Alt-Tabs between recognition and typing.
        if not self._verify_same(target):
            return False, 0, "focus_changed"
        n = self._send([
            ("vk", VK_CONTROL, False), ("vk", VK_V, False),
            ("vk", VK_V, True), ("vk", VK_CONTROL, True),
        ])
        if n < 4:
            return False, n, "sendinput_rejected"
        if self._clipboard_restore and prev is not None:
            # scar 32: opt-in only, wait a FULL second, restore ONLY if the
            # clipboard still holds exactly what we pasted.
            self._sleep(CLIPBOARD_RESTORE_WAIT_S)
            if self._clip.get() == text:
                self._clip.set(prev)
        return True, n, ""

    def _send_unicode_chunked(self, text: str,
                              target: Target) -> tuple[bool, int, str]:
        """Per-char KEYEVENTF_UNICODE fallback, in small verified chunks.

        The 79-char scar: one giant burst overflows the receiver's queue and
        events vanish (spaces first). Small bursts with a breather survive;
        re-verifying the target per chunk means an Alt-Tab mid-utterance
        stops the burst instead of spraying a second window — the un-typed
        remainder is parked, recoverable.

        DOCUMENTED MARGIN (scar 19): SendInput acceptance is not delivery —
        a chunk already accepted but not yet DISPATCHED by the receiver's
        thread when focus flips can be dropped by the OS. The park boundary
        is the send boundary, so that margin is at most one chunk
        (<= CHUNK_EVENTS/2 chars). True delivery proof is the UIPI
        round-trip selftest (criterion 8); the soak counts both delivery
        destinations (criterion 12)."""
        events: list[Event] = []
        for unit in utf16_units(text):
            events.append(("unicode", unit, False))
            events.append(("unicode", unit, True))

        sent = 0
        for i in range(0, len(events), self.CHUNK_EVENTS):
            chunk = events[i:i + self.CHUNK_EVENTS]
            if not self._verify_same(target):
                remainder = text[sent // 2:]
                self.park(remainder, "focus_changed_mid_burst")
                if self._emit is not None:
                    self._emit("FOCUS_BLOCK", reason="focus_changed_mid_burst",
                               exe=exe_name(target.image_path))
                return False, sent, "focus_changed_mid_burst"
            n = self._send(chunk)
            sent += n
            if n < len(chunk):
                remainder = text[sent // 2:]
                self.park(remainder, "sendinput_rejected")
                return False, sent, "sendinput_rejected"
            if i + self.CHUNK_EVENTS < len(events):
                self._sleep(INTER_CHUNK_SLEEP_S)
        return True, sent, ""

    def _send_enter(self, target: Target, enter_delay: float, exe: str) -> bool:
        """Scar 36: Enter as a SEPARATE burst after the delay, re-verifying
        the SAME target — never race a slow app into submitting half a line."""
        self._sleep(max(0.0, enter_delay))
        if not self._verify_same(target):
            if self._emit is not None:
                self._emit("FOCUS_BLOCK", reason="enter_target_changed", exe=exe)
            return False
        # A keypress of HIS between our text burst and this Enter burst
        # means he is mid-thought at the keyboard: pasting into his sentence
        # is recoverable, SUBMITTING it is not. Positive evidence only —
        # an unreadable clock does not withhold (the presence gate owns the
        # fail-closed absence law at its own, longer scale).
        if self._idle is not None and self._user_typing() is True:
            if self._emit is not None:
                self._emit("TYPING_COLLISION", action="enter_suppressed",
                           wait_ms=0)
            return False
        n = self._send([
            ("vk", VK_RETURN, False), ("vk", VK_RETURN, True),
        ])
        return n >= 2
