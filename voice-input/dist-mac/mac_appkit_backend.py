"""mac_appkit_backend.py — OPTIONAL native (pyobjc / AppKit / Quartz) backend.

This is a SCAFFOLD / future drop-in, NOT the active backend. The shipping mac
backend is voice-input/backends/mac.py, which drives typing/paste/focus through
AppleScript "System Events" (no extra pip deps — works out of the box). That one
is already complete and is what run.sh uses.

This file exists because the task asked for an AppKit/pyobjc native path that
mirrors win.py / linux.py. A native CGEvent path can be sturdier than AppleScript
for some apps (and avoids the per-keystroke osascript spawn), at the cost of a
pyobjc dependency and the same Accessibility grant.

STATUS: HONEST STUB. The Quartz CGEvent keystroke + AppKit clipboard code below
is real and structurally complete, but it is UNVERIFIED — it was authored on
Windows and has never been exercised on macOS. Unicode CGEvent injection in
particular (keyboardSetUnicodeString) needs validation on a real Mac across
target apps before this should replace the AppleScript backend. Until then, the
methods marked `# STUB` fall back to the AppleScript MacBackend so nothing
silently breaks.

To try it on a Mac:
    pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz
    VOICEINPUT_BACKEND=mac VOICEINPUT_MAC_NATIVE=1 python ../voice_input_xplat.py --cpu
  (wiring VOICEINPUT_MAC_NATIVE would be a one-line change in backends/__init__.py
   once this backend is verified — left undone on purpose; see README_MAC.md.)

Audio note: capture is NOT a backend responsibility. mic.py already uses
sounddevice (PortAudio), which is cross-platform and works on macOS as-is — so
there is no "mac audio backend" to write. This class only covers typing / paste /
focus / undo / duck, exactly like win.py and linux.py.

לזכרה של עלמה ז״ל · ALMAWARE · iddoperez.ai
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

# Import the abstract contract + the shipping AppleScript backend (used as the
# safe fallback for anything not yet verified natively). We add the core dir to
# sys.path so `from backends...` resolves whether run loose or bundled.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, ".."))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from backends.base import InputBackend          # noqa: E402
from backends.mac import MacBackend             # noqa: E402  (AppleScript fallback)

logger = logging.getLogger("voiceinput.backends.mac_appkit")

# ── optional native deps — degrade gracefully if pyobjc is absent ────────────
try:
    from AppKit import NSPasteboard, NSStringPboardType  # type: ignore
    import Quartz  # type: ignore
    _HAVE_PYOBJC = True
except Exception as e:  # noqa: BLE001
    logger.info("pyobjc not available (%s) — native backend will fully defer to "
                "AppleScript MacBackend", e)
    _HAVE_PYOBJC = False


class MacAppKitBackend(InputBackend):
    """Native macOS backend via Quartz CGEvent + AppKit NSPasteboard.

    Anything not yet verified natively delegates to a private AppleScript
    MacBackend instance, so this class is always at least as capable as the
    shipping backend."""

    name = "mac-appkit"

    def __init__(self):
        self._fallback = MacBackend()  # AppleScript — known-good
        self._native = _HAVE_PYOBJC
        logger.info("mac-appkit backend: native=%s (else AppleScript fallback)",
                    self._native)

    # ── typing (Quartz CGEvent Unicode injection) ────────────────────────────
    def type_text(self, text: str, enter: bool = False) -> None:
        if not self._native:
            return self._fallback.type_text(text, enter=enter)
        try:
            self._cg_type_unicode(text)
            if enter:
                time.sleep(0.02)
                self._cg_key(0x24)  # kVK_Return
        except Exception as e:  # noqa: BLE001
            logger.warning("native type_text failed (%s) — AppleScript fallback", e)
            self._fallback.type_text(text, enter=enter)

    def _cg_type_unicode(self, text: str) -> None:
        """Inject `text` as a Unicode keyboard event. REAL but UNVERIFIED on Mac.
        CGEventKeyboardSetUnicodeString handles arbitrary Unicode (incl. Hebrew)
        without keycode mapping — chunk to stay under the event string limit."""
        for i in range(0, len(text), 20):
            chunk = text[i:i + 20]
            down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(down, len(chunk), chunk)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
            Quartz.CGEventKeyboardSetUnicodeString(up, len(chunk), chunk)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            time.sleep(0.012)

    def _cg_key(self, keycode: int, flags: int = 0) -> None:
        down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
        if flags:
            Quartz.CGEventSetFlags(down, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
        if flags:
            Quartz.CGEventSetFlags(up, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    # ── paste (AppKit NSPasteboard + Cmd+V via CGEvent) ──────────────────────
    def paste_text(self, text: str, enter: bool = False) -> None:
        if not self._native:
            return self._fallback.paste_text(text, enter=enter)
        try:
            pb = NSPasteboard.generalPasteboard()
            prev = pb.stringForType_(NSStringPboardType)
            pb.clearContents()
            pb.setString_forType_(text, NSStringPboardType)
            time.sleep(0.05)
            # Cmd+V : keycode 9 = 'v', kCGEventFlagMaskCommand = 1<<20
            self._cg_key(9, Quartz.kCGEventFlagMaskCommand)
            time.sleep(0.08)
            if enter:
                self._cg_key(0x24)  # Return
            time.sleep(0.1)
            if prev is not None:
                pb.clearContents()
                pb.setString_forType_(prev, NSStringPboardType)
        except Exception as e:  # noqa: BLE001
            logger.warning("native paste_text failed (%s) — AppleScript fallback", e)
            self._fallback.paste_text(text, enter=enter)

    def set_clipboard(self, text: str) -> None:
        if not self._native:
            return self._fallback.set_clipboard(text)
        try:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(text, NSStringPboardType)
        except Exception as e:  # noqa: BLE001
            logger.debug("native set_clipboard failed (%s) — fallback", e)
            self._fallback.set_clipboard(text)

    # ── window discovery / focus ─────────────────────────────────────────────
    # STUB: a full native window list needs the Accessibility (AX) API
    # (AXUIElement) which is non-trivial and permission-gated. The AppleScript
    # path already does best-effort enumeration, so defer to it for now.
    def get_foreground_window(self) -> Any | None:
        return self._fallback.get_foreground_window()          # STUB -> fallback

    def focus_window(self, handle: Any) -> bool:
        return self._fallback.focus_window(handle)             # STUB -> fallback

    def enum_windows(self) -> list[tuple[Any, str, str]]:
        return self._fallback.enum_windows()                   # STUB -> fallback

    def send_undo(self, handle: Any) -> None:
        if not self._native:
            return self._fallback.send_undo(handle)
        try:
            self.focus_window(handle)
            time.sleep(0.05)
            self._cg_key(6, Quartz.kCGEventFlagMaskCommand)    # Cmd+Z (keycode 6='z')
        except Exception as e:  # noqa: BLE001
            logger.warning("native send_undo failed (%s) — fallback", e)
            self._fallback.send_undo(handle)

    # ── audio ducking — defer to AppleScript global volume (cfg ships duck off) ─
    def duck(self) -> list[str]:
        return self._fallback.duck()                           # STUB -> fallback

    def restore(self) -> None:
        self._fallback.restore()                               # STUB -> fallback

    # ── misc ──────────────────────────────────────────────────────────────────
    def beep(self) -> None:
        self._fallback.beep()

    def open_path(self, path: str) -> None:
        self._fallback.open_path(path)
