"""KESHEV 2 Win32 OS layer — the real implementation of typer.OsLayer.

Knowledge ported from A (scar 33, each rule was a crash or silent failure
in production):

  * clipboard handles are c_void_p EVERYWHERE — int truncation on 64-bit
    yields ERROR_INVALID_HANDLE;
  * OpenClipboard retried ~12x with a small sleep — ANY process may hold
    the clipboard at any moment;
  * SetClipboardData success means the SYSTEM owns the memory — we never
    GlobalFree after a successful set;
  * there is NO clipboard-restore code (scar 32) — by ruling D-006 the
    capability does not exist in this repo.

SendInput here reports what the OS ACCEPTED, not what the receiver got —
success return values lie (scar 19). Round-trip verification is the
selftest's job (A's selftest.py pattern; inherited task, see acceptance
notes — not run tonight beside the live mic).

stdlib ctypes only.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from typing import Optional, Sequence

from k2.typer import Target

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
CLIPBOARD_OPEN_RETRIES = 12
CLIPBOARD_RETRY_SLEEP_S = 0.05

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_u32.GetForegroundWindow.restype = wintypes.HWND
_u32.GetWindowThreadProcessId.argtypes = (wintypes.HWND,
                                          ctypes.POINTER(wintypes.DWORD))
_u32.OpenClipboard.argtypes = (wintypes.HWND,)
_u32.OpenClipboard.restype = wintypes.BOOL
_u32.EmptyClipboard.restype = wintypes.BOOL
_u32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
_u32.SetClipboardData.restype = ctypes.c_void_p       # scar 33: c_void_p
_u32.CloseClipboard.restype = wintypes.BOOL

_k32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
_k32.GlobalAlloc.restype = ctypes.c_void_p
_k32.GlobalLock.argtypes = (ctypes.c_void_p,)
_k32.GlobalLock.restype = ctypes.c_void_p
_k32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
_k32.GlobalFree.argtypes = (ctypes.c_void_p,)
_k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD))
_k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)))


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT),)
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


def _vk_event(vk: int, up: bool) -> _INPUT:
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = _KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
    return inp


def _unicode_event(unit: int, up: bool) -> _INPUT:
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    inp.ki = _KEYBDINPUT(0, unit, flags, 0, None)
    return inp


def _send(events: Sequence[_INPUT]) -> bool:
    n = len(events)
    arr = (_INPUT * n)(*events)
    sent = _u32.SendInput(n, arr, ctypes.sizeof(_INPUT))
    return int(sent) == n


class Win32OsLayer:
    """The production OsLayer. One instance per process."""

    # ------------------------------------------------------------ identity

    def own_pid(self) -> int:
        return os.getpid()

    def foreground(self) -> Optional[Target]:
        hwnd = _u32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        exe = self._exe_of(pid.value)
        if exe is None:
            return None
        return Target(hwnd=int(hwnd), pid=int(pid.value), exe=exe)

    @staticmethod
    def _exe_of(pid: int) -> Optional[str]:
        handle = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                  False, pid)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(4096)
            buf = ctypes.create_unicode_buffer(size.value)
            if not _k32.QueryFullProcessImageNameW(handle, 0, buf,
                                                   ctypes.byref(size)):
                return None
            return os.path.basename(buf.value).lower()
        finally:
            _k32.CloseHandle(handle)

    # ----------------------------------------------------------- clipboard

    def clipboard_set(self, text: str) -> bool:
        """CF_UNICODETEXT set with the scar-33 discipline. True only when
        the system accepted ownership of the data."""
        data = text.encode("utf-16-le") + b"\x00\x00"
        opened = False
        for _ in range(CLIPBOARD_OPEN_RETRIES):
            if _u32.OpenClipboard(None):
                opened = True
                break
            time.sleep(CLIPBOARD_RETRY_SLEEP_S)
        if not opened:
            return False
        handle = None
        try:
            if not _u32.EmptyClipboard():
                return False
            handle = _k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not handle:
                return False
            locked = _k32.GlobalLock(handle)
            if not locked:
                return False
            ctypes.memmove(locked, data, len(data))
            _k32.GlobalUnlock(handle)
            if not _u32.SetClipboardData(CF_UNICODETEXT, handle):
                return False
            handle = None       # success: the SYSTEM owns it now
            return True
        finally:
            if handle is not None:
                _k32.GlobalFree(handle)
            _u32.CloseClipboard()

    # ----------------------------------------------------------- keystrokes

    def send_paste(self) -> bool:
        """Ctrl+V — 4 events, atomic burst (scar 31)."""
        return _send([
            _vk_event(VK_CONTROL, up=False),
            _vk_event(VK_V, up=False),
            _vk_event(VK_V, up=True),
            _vk_event(VK_CONTROL, up=True),
        ])

    def send_enter(self) -> bool:
        return _send([
            _vk_event(VK_RETURN, up=False),
            _vk_event(VK_RETURN, up=True),
        ])

    def send_unicode_chunk(self, units: Sequence[int]) -> bool:
        events: list[_INPUT] = []
        for unit in units:
            events.append(_unicode_event(unit, up=False))
            events.append(_unicode_event(unit, up=True))
        return _send(events)
