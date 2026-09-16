"""win.py - Windows InputBackend = PURE DELEGATION.

This backend changes NOTHING about how the mic behaves on Windows. Every
method forwards to the existing, battle-tested modules:

    type_text            -> typer.type_unicode
    paste_text           -> typer.paste_text   (terminal_paste plumbed from cfg)
    get_foreground_window-> user32.GetForegroundWindow   (same call site as the
                            old voice_input.py:335 'focused' branch)
    focus_window         -> router.focus_window           (AttachThreadInput
                            focus dance untouched)
    enum_windows         -> router._enum_windows          (public passthrough;
                            returns (hwnd, title, proc) already)
    send_undo            -> verbatim copy of voice_input._send_ctrl_z body
                            (same KEYBDINPUT/INPUT structs + SendInput + Ctrl+Z)
    duck / restore       -> a shared ducking.Ducker instance (pycaw / WASAPI)

So the entire ctypes struct/flag layout and the focus dance stay byte-for-byte
identical to the working app. The only requirement on the caller is that
typer.py and router.py are importable on sys.path (they are: backends/ lives
beside them in voice-input/).

rez.ai
"""
from __future__ import annotations

import ctypes
import logging
import os
import time
from typing import Any

from .base import InputBackend

logger = logging.getLogger("voiceinput.backends.win")


def _send_ctrl_z(hwnd) -> None:
    """Verbatim port of voice_input._send_ctrl_z(): focus hwnd, then Ctrl+Z via
    SendInput. Same struct layout / flags as the original."""
    import router

    VK_Z = 0x5A
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _anonymous_ = ("_input",)
        _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT)]

    def key(vk, flags=0):
        i = INPUT()
        i.type = 1
        i.ki.wVk = vk
        i.ki.dwFlags = flags
        ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))

    router.focus_window(hwnd)
    time.sleep(0.05)
    key(0x11)        # Ctrl down
    key(VK_Z)        # Z down
    key(VK_Z, KEYEVENTF_KEYUP)
    key(0x11, KEYEVENTF_KEYUP)


class WindowsBackend(InputBackend):
    name = "windows"

    def __init__(self, terminal_paste: bool = False,
                 duck_pct: int = 100, duck_exclude: set[str] | None = None,
                 ducking_enabled: bool = False):
        # terminal_paste is plumbed from cfg so paste_text keeps the exact same
        # behavior the app uses (config default terminal_paste=false).
        self.terminal_paste = bool(terminal_paste)
        # Lazy single Ducker instance, mirroring VoiceInput.ducker semantics.
        self._duck_pct = duck_pct
        self._duck_exclude = duck_exclude
        self._ducking_enabled = ducking_enabled
        self._ducker = None

    # ── typing ────────────────────────────────────────────────────────────────
    def type_text(self, text: str, enter: bool = False) -> None:
        import typer
        typer.type_unicode(text, auto_enter=enter)

    def paste_text(self, text: str, enter: bool = False) -> None:
        import typer
        typer.paste_text(text, auto_enter=enter,
                         terminal_paste=self.terminal_paste)

    def set_clipboard(self, text: str) -> None:
        # pyperclip is what typer.py itself uses on Windows; keep it consistent.
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception as e:  # noqa: BLE001
            logger.debug("set_clipboard failed: %s", e)

    # ── window discovery / focus ──────────────────────────────────────────────
    def get_foreground_window(self) -> Any | None:
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            return hwnd or None
        except Exception as e:  # noqa: BLE001
            logger.debug("GetForegroundWindow failed: %s", e)
            return None

    def focus_window(self, handle: Any) -> bool:
        import router
        return router.focus_window(handle)

    def enum_windows(self) -> list[tuple[Any, str, str]]:
        import router
        return router._enum_windows()

    def send_undo(self, handle: Any) -> None:
        _send_ctrl_z(handle)

    # ── audio ducking (shared pycaw Ducker) ───────────────────────────────────
    def _get_ducker(self):
        if self._ducker is None:
            from ducking import Ducker
            self._ducker = Ducker(duck_pct=self._duck_pct,
                                  exclude=self._duck_exclude,
                                  enabled=self._ducking_enabled)
        return self._ducker

    def duck(self) -> list[str]:
        try:
            return self._get_ducker().duck()
        except Exception as e:  # noqa: BLE001
            logger.debug("duck failed: %s", e)
            return []

    def restore(self) -> None:
        try:
            self._get_ducker().restore()
        except Exception as e:  # noqa: BLE001
            logger.debug("restore failed: %s", e)

    # ── misc ──────────────────────────────────────────────────────────────────
    def beep(self) -> None:
        try:
            ctypes.windll.user32.MessageBeep(0)
        except Exception:  # noqa: BLE001
            pass

    def open_path(self, path: str) -> None:
        try:
            os.startfile(path)  # type: ignore[attr-defined]  # Windows-only
        except Exception as e:  # noqa: BLE001
            logger.debug("open_path failed: %s", e)
