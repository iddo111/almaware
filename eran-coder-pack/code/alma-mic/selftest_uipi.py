"""alma-mic / selftest_uipi.py — prove that typing reaches an ELEVATED window.

WHY THIS EXISTS
  For weeks the mic "typed ok" and nothing appeared in the Claude CLI. The log was
  not lying and the code was not broken: the CLI terminal runs at HIGH integrity
  (elevated), ALMA-MIC ran at MEDIUM, and Windows UIPI silently drops synthetic
  input that crosses that boundary upward. Microsoft documents this exactly:

      "This function fails when it is blocked by UIPI. Note that neither
       GetLastError nor the return value will indicate the failure."
                                                    -- SendInput, MSDN

  So a green "TYPED ok" proved nothing. This self-test closes that hole: it opens
  a Notepad at the SAME integrity level as this process, types through the real
  typer.py, then reads the text back out of Notepad and compares. Round-trip or
  it did not happen.

RUN
  python selftest_uipi.py           # from a normal shell -> expect FAIL vs elevated
  (elevated) python selftest_uipi.py  # -> expect PASS

Exit code 0 = the text made it. Non-zero = it did not.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

try:                       # pythonw.exe has NO stdout - sys.stdout is None there
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import typer as typer_mod

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Deliberately LONG and space-heavy: length is what triggered the dropped-space bug
# (a short burst kept its spaces, a 79-character one did not). A probe that cannot
# reproduce the failure cannot prove the fix.
PROBE = ("What about the mic app? Can you fix it please? So it types in any window. "
         "Over. גם בעברית עם רווחים בין המילים 12345")


def _clipboard_text() -> str:
    """Read the clipboard as text. Handles are 64-bit -> c_void_p everywhere."""
    user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalSize.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalSize.restype = ctypes.c_size_t
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return ""
    try:
        h = user32.GetClipboardData(13)          # CF_UNICODETEXT
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            n = kernel32.GlobalSize(h)
            return ctypes.wstring_at(p, max(n // 2 - 1, 0))
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _key(vk: int, up: bool = False):
    """One key event through SendInput (same road the typer uses)."""
    class KI(ctypes.Structure):
        _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                    ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class IN(ctypes.Structure):
        _fields_ = [("type", w.DWORD), ("ki", KI), ("pad", ctypes.c_ubyte * 8)]

    i = IN(type=1, ki=KI(wVk=vk, wScan=0, dwFlags=(2 if up else 0), time=0,
                         dwExtraInfo=None))
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(IN))


def _window_of_pid(pid: int):
    """Top-level visible window belonging to pid (Notepad has exactly one)."""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            p = w.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid:
                found.append(hwnd)
        return True

    for _ in range(20):                              # notepad may still be starting
        user32.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.2)
    return None


def main() -> int:
    print("ALMA-MIC  UIPI SELF-TEST")
    print("=" * 64)
    print("this process integrity : %s"
          % ("HIGH (elevated)" if ctypes.windll.shell32.IsUserAnAdmin() else "MEDIUM"))

    # A SEPARATE process at OUR integrity level, with a plain Win32 window. Not
    # notepad: on Windows 11 notepad.exe hands off to a packaged app in another
    # PID, so its window is never found under ours.
    here = os.path.dirname(os.path.abspath(__file__))
    got_file = os.path.join(here, "uipi_target_got.txt")
    if os.path.exists(got_file):
        os.remove(got_file)
    pyw = sys.executable.replace("pythonw.exe", "python.exe")
    np = subprocess.Popen([pyw, os.path.join(here, "_uipi_target.py"), got_file],
                          cwd=here, creationflags=0x08000000)   # no console window
    time.sleep(2.2)

    # Focus OUR target explicitly. Never test against "whatever happens to be in
    # front" - that types the probe into someone else's window and proves nothing.
    hwnd = _window_of_pid(np.pid)
    if not hwnd:
        print("could not find the target window - aborting instead of guessing")
        np.terminate()
        return 2
    # The ALT tap. Windows only honours SetForegroundWindow from a process that
    # "owns" the foreground or has just received input; a synthetic ALT press
    # satisfies that rule and releases the foreground lock. A process launched by
    # Task Scheduler has neither, which is why the plain call kept failing.
    _key(0x12); _key(0x12, up=True)
    time.sleep(0.05)
    if not typer_mod._win32.restore_focus(hwnd):
        print("could not bring the target to the front - aborting")
        np.terminate()
        return 2
    buf = ctypes.create_unicode_buffer(200)
    user32.GetWindowTextW(hwnd, buf, 200)
    print("target window          : %r" % buf.value[:50])

    typer_mod.set_policy(anywhere=True, targets=[])
    n = typer_mod.type_text(PROBE, enter=False)
    print("typer reported         : %d events sent" % n)

    # The target process writes whatever it actually received to a file, then
    # exits. Reading THAT is the honest check - not the sender's return value,
    # which is exactly what lied to us for weeks.
    np.wait(timeout=30)
    got = ""
    if os.path.exists(got_file):
        with open(got_file, encoding="utf-8") as f:
            got = f.read()
    print("target process received: %r" % got[:80])

    landed = PROBE.strip() in got
    print("-" * 64)
    if landed:
        print("PASS - keystrokes crossed into another process at this integrity level.")
    else:
        print("FAIL - SendInput said ok, the other process never got it (UIPI block).")
    return 0 if landed else 1


if __name__ == "__main__":
    sys.exit(main())
