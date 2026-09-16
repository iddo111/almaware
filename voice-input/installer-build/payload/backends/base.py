"""base.py - the ONE input-backend interface for the Hebrew mic.

Every platform backend (Windows / Linux / macOS) implements exactly this
contract. Callers (voice_input.py) talk only to this interface and never touch
ctypes / Win32 / xdotool / AppleScript directly.

Handle type is OPAQUE and backend-defined:
  - Windows: an HWND (int) from EnumWindows / GetForegroundWindow
  - Linux  : an X11 window id string (e.g. "0x03a00007") from wmctrl/xdotool
  - macOS  : a process id (int) of the owning app, or an app-name string
Callers must treat the handle as a token only - pass it back to focus_window /
send_undo, never inspect or compare its internals.

rez.ai
"""
from __future__ import annotations

import abc
from typing import Any


class InputBackend(abc.ABC):
    """Abstract OS input backend. The eight methods below are the complete
    surface the voice loop needs. Implementations MUST NOT raise for the
    "tool/permission missing" case - they should log clearly and degrade
    (return None / [] / False / no-op) so the dictation loop keeps running."""

    # ── identity (handy for logging / VOICEINPUT_BACKEND override) ────────────
    name: str = "base"

    # ── typing ────────────────────────────────────────────────────────────────
    @abc.abstractmethod
    def type_text(self, text: str, enter: bool = False) -> None:
        """Type `text` char-by-char as Unicode keystrokes into the focused
        window. If `enter` is True, press Enter/Return afterwards."""

    @abc.abstractmethod
    def paste_text(self, text: str, enter: bool = False) -> None:
        """Copy `text` to the clipboard, send the paste shortcut into the
        focused window, then restore the previous clipboard contents. If
        `enter` is True, press Enter/Return afterwards."""

    # ── clipboard (cross-platform helper used by callers' fallback paths) ─────
    def set_clipboard(self, text: str) -> None:
        """Put `text` on the system clipboard. Default impl uses pyperclip
        (cross-platform); backends may override with a native path."""
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception:  # noqa: BLE001
            pass

    # ── window discovery / focus ──────────────────────────────────────────────
    @abc.abstractmethod
    def get_foreground_window(self) -> Any | None:
        """Return an opaque handle for the currently-focused window, or None."""

    @abc.abstractmethod
    def focus_window(self, handle: Any) -> bool:
        """Raise + focus the window named by `handle`. Return False on failure
        (so the caller can refuse to type into the wrong place)."""

    @abc.abstractmethod
    def enum_windows(self) -> list[tuple[Any, str, str]]:
        """Return a list of (handle, window_title, proc_name_lowercase).
        `proc_name` is the lowercased process exe / owner name. May return a
        partial or empty list on locked-down display servers (e.g. Wayland)."""

    @abc.abstractmethod
    def send_undo(self, handle: Any) -> None:
        """Focus `handle` then send the undo shortcut (Ctrl+Z, or Cmd+Z on
        macOS)."""

    # ── audio ducking ─────────────────────────────────────────────────────────
    @abc.abstractmethod
    def duck(self) -> list[str]:
        """Lower the volume of OTHER apps while the user is talking. Return the
        names of the sessions actually ducked. No-op backends return []."""

    @abc.abstractmethod
    def restore(self) -> None:
        """Restore any audio ducked by a prior duck() call."""

    # ── misc OS niceties (non-abstract; sane cross-platform defaults) ─────────
    def beep(self) -> None:
        """Audible notification. Default: terminal bell. Windows overrides with
        MessageBeep."""
        try:
            print("\a", end="", flush=True)
        except Exception:  # noqa: BLE001
            pass

    def open_path(self, path: str) -> None:
        """Open a file/URL with the OS default handler. Default: best-effort
        webbrowser. Backends override with startfile / xdg-open / open."""
        try:
            import webbrowser
            webbrowser.open(path)
        except Exception:  # noqa: BLE001
            pass
