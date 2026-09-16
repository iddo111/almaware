"""alma-mic / hotkey.py — a global pause/resume hotkey, from any window.

ALMAWARE-pure: our own code over the OS primitive (Win32 RegisterHotKey via ctypes —
the standard way to claim a system-wide hotkey, no third-party library). During
dictation the mic window is NOT focused (the target window is), so a clickable button
isn't enough — this lets Iddo pause/resume the typer instantly without leaving his work.

    hk = GlobalHotkey(on_press=lambda: ui_queue.put(("toggle",)))
    hk.start()   # Ctrl+Alt+P toggles; safe no-op if the combo is already taken.

The callback fires on the hotkey thread — it must only enqueue work for the UI thread,
never touch tkinter widgets directly.
"""
from __future__ import annotations
import ctypes
import threading
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
VK_P = 0x50


class GlobalHotkey:
    """Ctrl+Alt+P (default) → calls on_press(). Registers + runs its own message loop
    on a daemon thread; degrades to a silent no-op if registration fails."""

    def __init__(self, on_press, vk: int = VK_P, mods: int = MOD_CONTROL | MOD_ALT,
                 label: str = "Ctrl+Alt+P"):
        self.on_press = on_press
        self.vk = vk
        self.mods = mods
        self.label = label
        self.ok = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="alma-hotkey")
        self._thread.start()

    def _run(self):
        try:
            user32 = ctypes.windll.user32
            if not user32.RegisterHotKey(None, 1, self.mods | MOD_NOREPEAT, self.vk):
                self.ok = False
                return
            self.ok = True
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.on_press()
                    except Exception:
                        pass
            user32.UnregisterHotKey(None, 1)
        except Exception:
            self.ok = False
