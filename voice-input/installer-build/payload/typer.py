"""typer.py - send transcribed text into the focused window (the Claude Code
terminal). Two strategies:

  1) clipboard paste (default, most reliable for Hebrew + bursts): copy text to
     clipboard, send Ctrl+V (or Ctrl+Shift+V for terminals), restore clipboard.
  2) SendInput Unicode keystrokes (fallback): types char-by-char via the Windows
     KEYEVENTF_UNICODE path - handles Hebrew, but slow / can drop chars in some
     terminals.

auto_enter=True presses Enter after, for fully hands-free send.

"""
from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

logger = logging.getLogger("voiceinput.typer")

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_V = 0x56

ULONG_PTR = ctypes.wintypes.WPARAM  # pointer-sized unsigned (correct on 32/64-bit)

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]

class _U(ctypes.Union):
    # union must be sized for its largest member (MOUSEINPUT) so sizeof(_INPUT)
    # matches what SendInput expects (40 bytes on x64). Omitting the other
    # members made the struct too small -> SendInput failed with error 87.
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]

def _emit(wVk, wScan, flags):
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(wVk, wScan, flags, 0, 0)
    n = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    if n != 1:
        logger.warning("SendInput rejected (n=%s err=%s)", n,
                       ctypes.windll.kernel32.GetLastError())

def _key(vk, down=True):
    _emit(vk, 0, 0 if down else KEYEVENTF_KEYUP)

def _press_enter():
    _key(VK_RETURN, True)
    _key(VK_RETURN, False)

def type_unicode(text: str, char_delay: float = 0.004, auto_enter: bool = False):
    """Char-by-char Unicode SendInput. Robust for Hebrew, slower."""
    for ch in text:
        if ch == "\n":
            _press_enter()
        else:
            code = ord(ch)
            _emit(0, code, KEYEVENTF_UNICODE)
            _emit(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        time.sleep(char_delay)
    if auto_enter:
        time.sleep(0.05)
        _press_enter()

def paste_text(text: str, auto_enter: bool = False, terminal_paste: bool = True):
    """Clipboard paste into the focused window. Most reliable for Hebrew bursts.
    Saves + restores the previous clipboard contents."""
    import pyperclip
    prev = ""
    try:
        prev = pyperclip.paste()
    except Exception:  # noqa: BLE001
        pass
    pyperclip.copy(text)
    time.sleep(0.06)
    # Ctrl+(Shift)+V. Windows Terminal & most CLIs accept Ctrl+Shift+V; classic
    # edit boxes accept Ctrl+V. Try plain Ctrl+V which Claude Code's input takes.
    _key(VK_CONTROL, True)
    if terminal_paste:
        _key(VK_SHIFT, True)
    _key(VK_V, True)
    _key(VK_V, False)
    if terminal_paste:
        _key(VK_SHIFT, False)
    _key(VK_CONTROL, False)
    time.sleep(0.08)
    if auto_enter:
        _press_enter()
    # restore clipboard shortly after paste lands
    time.sleep(0.15)
    try:
        pyperclip.copy(prev)
    except Exception:  # noqa: BLE001
        pass

def send(text: str, use_clipboard: bool = True, auto_enter: bool = False,
         char_delay: float = 0.004, terminal_paste: bool = True):
    if not text:
        return
    if use_clipboard:
        try:
            paste_text(text, auto_enter=auto_enter, terminal_paste=terminal_paste)
            return
        except Exception as e:  # noqa: BLE001
            logger.warning("clipboard paste failed (%s) - falling back to keystrokes", e)
    type_unicode(text, char_delay=char_delay, auto_enter=auto_enter)

def send_to_window(hwnd, text: str, use_clipboard: bool = True,
                   auto_enter: bool = False, char_delay: float = 0.004,
                   terminal_paste: bool = False) -> bool:
    """Focus `hwnd` first, then type. Returns False if focus failed (so the
    caller can refuse to type rather than leak text into the wrong window)."""
    import router
    if not router.focus_window(hwnd):
        logger.warning("could not focus target window hwnd=%s; NOT typing", hwnd)
        return False
    time.sleep(0.08)
    send(text, use_clipboard=use_clipboard, auto_enter=auto_enter,
         char_delay=char_delay, terminal_paste=terminal_paste)
    return True

if __name__ == "__main__":
    import sys
    txt = " ".join(sys.argv[1:]) or "שלום עידו, this is a Hebrew + English test"
    print("Focus a window in 2s ...")
    time.sleep(2)
    send(txt, use_clipboard=True, auto_enter=False, terminal_paste=False)
