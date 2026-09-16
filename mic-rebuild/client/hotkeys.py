"""KESHEV global hotkeys — RegisterHotKey, honestly bound or loudly not.

WHY THIS EXISTS (2026-08-17): `hotkey_pause` has lived in config since K1 and
`tray.parse_hotkey` refuses malformed specs with a lecture about how "a
hotkey that silently did not bind is a pause key that does nothing when Iddo
needs it" — and then NOTHING in production ever called RegisterHotKey. The
parse was guarded; the binding did not exist. That is the fourth guard
species in the repo's own taxonomy: a guard structurally unable to fire.
This module is the binding.

It also carries the push-to-arm hotkey (presence.ArmSwitch, KESHEV B's one
surviving verdict) when armed mode is enabled.

Win32 rules that shaped the design:
  * RegisterHotKey binds to the CALLING THREAD; WM_HOTKEY is delivered to
    that thread's message queue. So one dedicated thread registers AND
    pumps, and stop() posts WM_QUIT to that thread id.
  * A failed registration (chord taken by another app) returns 0 — the ONLY
    honest response is a journal line and a visible count, never silence.

Injectable API boundary like every other Win32 seam in this client
(focus_api, input_api, clipboard, idle api): tests drive the pump with a
deterministic fake and never touch user32.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from client.tray import Hotkey

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000


class Win32HotkeyApi:
    """The real user32 boundary. Instantiated lazily on the pump thread."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class MSG(ctypes.Structure):
            _fields_ = (("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                        ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                        ("time", wintypes.DWORD), ("pt", wintypes.LONG * 2))

        self._ctypes = ctypes
        self._MSG = MSG
        self._u = ctypes.WinDLL("user32", use_last_error=True)
        self._k = ctypes.WinDLL("kernel32", use_last_error=True)

    def thread_id(self) -> int:
        return int(self._k.GetCurrentThreadId())

    def register(self, hk_id: int, mods: int, vk: int) -> bool:
        return bool(self._u.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk))

    def unregister(self, hk_id: int) -> None:
        self._u.UnregisterHotKey(None, hk_id)

    def get_message(self) -> tuple[int, int]:
        """Block for one message; (message, wParam). (-1, 0) on error,
        (WM_QUIT, 0) on quit."""
        msg = self._MSG()
        r = self._u.GetMessageW(self._ctypes.byref(msg), None, 0, 0)
        if r == 0:
            return (WM_QUIT, 0)
        if r == -1:
            return (-1, 0)
        return (int(msg.message), int(msg.wParam))

    def post_quit(self, thread_id: int) -> None:
        self._u.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)


class HotkeyListener:
    """Owns one pump thread; every binding registers there and fires there.

    Callback exceptions are journalled, never fatal — a broken action must
    not take the pump (and every OTHER hotkey) down with it.
    """

    def __init__(self, emit: Optional[Callable[..., None]] = None,
                 api_factory: Callable[[], object] = Win32HotkeyApi):
        self._emit = emit or (lambda *a, **k: None)
        self._api_factory = api_factory
        self._bindings: list[tuple[Hotkey, Callable[[], None]]] = []
        self._thread: Optional[threading.Thread] = None
        self._api = None
        self._tid: Optional[int] = None
        self._tid_ready = threading.Event()
        self.bound: list[str] = []           # labels that actually registered
        self.failed: list[str] = []          # labels that did not

    def add(self, hotkey: Hotkey, action: Callable[[], None]) -> None:
        if self._thread is not None:
            raise RuntimeError("add() before start() — bindings are fixed "
                               "for the life of the pump thread")
        self._bindings.append((hotkey, action))

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if not self._bindings:
            return                            # nothing to bind, nothing to pump
        self._thread = threading.Thread(target=self._run,
                                        name="keshev-hotkeys", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        if self._thread is None:
            return
        if self._tid_ready.wait(timeout) and self._api is not None:
            try:
                self._api.post_quit(self._tid)
            except Exception as exc:  # noqa: BLE001 — shutdown stays loud
                self._emit("STATE", level="ERROR", state="HOTKEY_STOP_ERROR",
                           err=f"{type(exc).__name__}: {str(exc)[:80]}")
        self._thread.join(timeout=timeout)

    # ----------------------------------------------------------------- pump

    def _run(self) -> None:
        try:
            api = self._api_factory()
        except Exception as exc:  # noqa: BLE001 — no user32 = no hotkeys, said loudly
            self._emit("STATE", level="ERROR", state="HOTKEY_API_UNAVAILABLE",
                       err=f"{type(exc).__name__}: {str(exc)[:80]}")
            return
        self._api = api
        self._tid = api.thread_id()
        self._tid_ready.set()
        self._pump(api)

    def _pump(self, api) -> None:
        """Register, loop, unregister. Split from _run so tests can drive it
        with a fake api and no thread at all."""
        actions: dict[int, Callable[[], None]] = {}
        for i, (hk, action) in enumerate(self._bindings, start=1):
            if api.register(i, hk.mods, hk.vk):
                actions[i] = action
                self.bound.append(hk.label)
                self._emit("STATE", state="HOTKEY_BOUND", chord=hk.label)
            else:
                # The chord belongs to another app, or the OS refused. The
                # feature this key serves is OFF and the human must know.
                self.failed.append(hk.label)
                self._emit("STATE", level="ERROR", state="HOTKEY_BIND_FAIL",
                           chord=hk.label)
        try:
            while True:
                message, wparam = api.get_message()
                if message == WM_QUIT or message == -1:
                    return
                if message == WM_HOTKEY and wparam in actions:
                    try:
                        actions[wparam]()
                    except Exception as exc:  # noqa: BLE001 — one bad action ≠ dead pump
                        self._emit("STATE", level="ERROR",
                                   state="HOTKEY_ACTION_ERROR",
                                   err=f"{type(exc).__name__}: {str(exc)[:80]}")
        finally:
            for i in actions:
                try:
                    api.unregister(i)
                except Exception as exc:  # noqa: BLE001 — cleanup stays loud (G1)
                    self._emit("STATE", level="ERROR",
                               state="HOTKEY_UNREGISTER_ERROR",
                               err=f"{type(exc).__name__}: {str(exc)[:80]}")
