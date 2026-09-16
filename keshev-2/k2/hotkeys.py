"""KESHEV 2 arm hotkey — a REAL RegisterHotKey, or an honest refusal.

Guard species #5 (A's hotkey_pause, found 2026-08-17): a config promised a
pause key since K1, `parse_hotkey` refused malformed specs with a lecture —
and NO production code ever called RegisterHotKey. Pressing it did nothing,
silently. K2 nearly shipped the same bug on night one: presence.ARM_HOTKEY
existed, ArmSwitch.toggle() existed, and nothing connected the key to the
switch. With armed_mode=true that is not a missing feature — it is a mic
that can NEVER be armed: total mute with no path out.

The law here (ruling D-008):
  * Binding is real: RegisterHotKey on the pump thread, WM_HOTKEY pumped
    via GetMessageW, the callback is ArmSwitch.toggle.
  * Binding is journalled: HOTKEY_BOUND on success, HOTKEY_BIND_FAIL on
    refusal (the combo may be taken by another app — that is an
    environment fact, not an exception to swallow).
  * A failed bind DISABLES the arm layer loudly (STATE arm_layer=disabled)
    rather than leaving an enabled-but-unarmable switch. Privacy fails
    closed; DEAFNESS FAILS OPEN — a switch nobody can flip must not mute
    the mic forever.

Win32 rules honored: RegisterHotKey and GetMessage must share a thread, so
both live on the pump thread; stop() posts WM_QUIT with PostThreadMessageW
and joins.

stdlib ctypes only; the Win32 surface is injectable for tests.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_HOTKEY_ID = 0xA1A                    # arbitrary, stable, ours

_VK_BY_NAME = {"a": 0x41}             # extend as combos are added


class HotkeySpecError(ValueError):
    """Malformed spec — refused loudly at parse time, never half-bound."""


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'ctrl+alt+a' -> (modifiers, vk). Raises on anything unknown."""
    mods = 0
    vk: Optional[int] = None
    for part in spec.lower().split("+"):
        part = part.strip()
        if part == "ctrl":
            mods |= MOD_CONTROL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part in _VK_BY_NAME:
            if vk is not None:
                raise HotkeySpecError(f"two keys in {spec!r}")
            vk = _VK_BY_NAME[part]
        else:
            raise HotkeySpecError(f"unknown token {part!r} in {spec!r}")
    if vk is None:
        raise HotkeySpecError(f"no key in {spec!r}")
    if not mods:
        raise HotkeySpecError(
            f"{spec!r} has no modifier — a bare key would eat normal typing")
    return mods, vk


class _RealWin32:
    """The real hotkey API. Constructed lazily on the PUMP thread."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class MSG(ctypes.Structure):
            _fields_ = (("hwnd", wintypes.HWND),
                        ("message", wintypes.UINT),
                        ("wParam", wintypes.WPARAM),
                        ("lParam", wintypes.LPARAM),
                        ("time", wintypes.DWORD),
                        ("pt_x", wintypes.LONG),
                        ("pt_y", wintypes.LONG))

        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int,
                                     wintypes.UINT, wintypes.UINT)
        u.RegisterHotKey.restype = wintypes.BOOL
        u.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        u.GetMessageW.argtypes = (ctypes.POINTER(MSG), wintypes.HWND,
                                  wintypes.UINT, wintypes.UINT)
        u.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT,
                                         wintypes.WPARAM, wintypes.LPARAM)
        self._ctypes, self._u, self._k, self._MSG = ctypes, u, k, MSG

    def register(self, mods: int, vk: int) -> bool:
        return bool(self._u.RegisterHotKey(None, _HOTKEY_ID,
                                           mods | MOD_NOREPEAT, vk))

    def unregister(self) -> None:
        self._u.UnregisterHotKey(None, _HOTKEY_ID)

    def pump_one(self) -> Optional[str]:
        """Block on GetMessageW. 'hotkey' | 'quit' | None (other)."""
        msg = self._MSG()
        r = self._u.GetMessageW(self._ctypes.byref(msg), None, 0, 0)
        if r == 0:
            return "quit"
        if r == -1:
            return "quit"                     # pump broken — end honestly
        if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
            return "hotkey"
        return None

    def current_thread_id(self) -> int:
        return int(self._k.GetCurrentThreadId())

    def post_quit(self, thread_id: int) -> None:
        self._u.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)


class ArmHotkey:
    """The pump. start() returns True only after the OS ACCEPTED the
    registration (the pump thread reports back) — a False return means the
    arm layer must be disabled loudly by the caller (D-008)."""

    def __init__(self, spec: str, on_hotkey: Callable[[], object],
                 emit: Optional[Callable[..., None]] = None,
                 api_factory: Callable[[], object] = _RealWin32) -> None:
        self.mods, self.vk = parse_hotkey(spec)     # refuse bad specs NOW
        self.spec = spec
        self._on_hotkey = on_hotkey
        self._emit = emit
        self._api_factory = api_factory
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._api = None
        self._bound = threading.Event()
        self._bind_failed = threading.Event()

    # ------------------------------------------------------------ lifecycle

    def start(self, timeout_s: float = 5.0) -> bool:
        if self._thread is not None:
            raise RuntimeError("hotkey pump already started")
        self._thread = threading.Thread(target=self._run,
                                        name="k2-arm-hotkey", daemon=True)
        self._thread.start()
        # wait for the pump thread's verdict — no silent half-bound state
        self._bound.wait(timeout_s)
        if self._bound.is_set():
            if self._emit is not None:
                self._emit("HOTKEY_BOUND", spec=self.spec)
            return True
        if self._emit is not None:
            self._emit("HOTKEY_BIND_FAIL", spec=self.spec,
                       reason="register_refused_or_timeout")
        return False

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._api is not None and self._thread_id is not None:
            self._api.post_quit(self._thread_id)
        self._thread.join(timeout=5)
        self._thread = None

    # ------------------------------------------------------------ the pump

    def _run(self) -> None:
        api = self._api_factory()
        self._api = api
        self._thread_id = api.current_thread_id()
        if not api.register(self.mods, self.vk):
            self._bind_failed.set()
            return                              # start() times out -> False
        self._bound.set()
        try:
            while True:
                kind = api.pump_one()
                if kind == "quit":
                    return
                if kind == "hotkey":
                    self._on_hotkey()
        finally:
            api.unregister()
