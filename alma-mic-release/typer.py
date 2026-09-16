"""alma-mic / typer.py — type recognized text into the focused window.

ALMAWARE-pure: our own Windows SendInput via ctypes. No external automation library.
Unicode path (KEYEVENTF_UNICODE) so Hebrew types correctly into any app.
We type into whatever window currently has focus — we never steal focus (No Screen Hijack).
"""
from __future__ import annotations
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D

ULONG_PTR = ctypes.c_size_t  # pointer-sized, for dwExtraInfo


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR))


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR))


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))


class _IUNION(ctypes.Union):
    _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _IUNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _key_unicode(code: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_IUNION(ki=_KEYBDINPUT(0, code, flags, 0, 0)))


def _key_vk(vk: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_IUNION(ki=_KEYBDINPUT(vk, 0, flags, 0, 0)))


def _send(events: list[_INPUT]) -> int:
    if not events:
        return 0
    arr = (_INPUT * len(events))(*events)
    return user32.SendInput(len(events), arr, ctypes.sizeof(_INPUT))


def type_text(text: str, enter: bool = False, enter_delay: float = 0.12) -> int:
    """Type `text` into the focused window (Unicode). Optionally press Enter to submit.

    The Enter is sent as a SEPARATE input burst after a short `enter_delay`, so the
    submit never races ahead of the characters — the old single-burst version could
    fire Enter before a slow app (chat box / web field) finished ingesting the Hebrew,
    sending an empty or half line. Text first, let it land, THEN send.
    Returns the number of input events the OS accepted."""
    events: list[_INPUT] = []
    for ch in text:
        for code in _codes(ch):          # surrogate pair for chars outside the BMP
            events.append(_key_unicode(code, up=False))
            events.append(_key_unicode(code, up=True))
    n = _send(events)
    if enter:
        time.sleep(max(0.0, enter_delay))            # let the app ingest the text first
        n += _send([_key_vk(VK_RETURN, up=False), _key_vk(VK_RETURN, up=True)])
    return n


def _codes(ch: str):
    cp = ord(ch)
    if cp > 0xFFFF:                       # encode astral chars as UTF-16 surrogates
        cp -= 0x10000
        return (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF))
    return (cp,)


if __name__ == "__main__":  # manual check: focus an editor within 3s, then run
    import time
    print("focus a text field; typing in 3s…")
    time.sleep(3)
    n = type_text("שלום מ-ALMA-MIC ", enter=False)
    print(f"sent {n} events")
