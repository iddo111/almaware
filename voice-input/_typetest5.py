"""Type test v5 - fully detached from any console. Launched via Start-Process so
synthetic SendInput routes to the real GUI foreground. Opens its OWN fresh
Notepad, pastes Hebrew, then writes the round-tripped text + verdict to a result
file we read afterwards. Does NOT touch any pre-existing Notepad.
"""
import time, subprocess, os
import win32gui, win32con, win32api
import pyperclip, keyboard as kb
import typer as kbd

RESULT = r"D:\CLAUDE\voice-input\samples\typetest_result.txt"
TXT = "שלום עידו voice input עובד 123"

# launch a FRESH dedicated notepad (new process), find its window by pid
proc = subprocess.Popen(["notepad.exe"])
time.sleep(2.0)

target = []
def cb(h, _):
    if not win32gui.IsWindowVisible(h):
        return
    import win32process
    try:
        _, pid = win32process.GetWindowThreadProcessId(h)
    except Exception:
        return
    if pid == proc.pid:
        target.append(h)
win32gui.EnumWindows(cb, None)
hwnd = target[0] if target else win32gui.GetForegroundWindow()

win32api.keybd_event(win32con.VK_MENU,0,0,0)
win32api.keybd_event(win32con.VK_MENU,0,win32con.KEYEVENTF_KEYUP,0)
win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception: pass
time.sleep(0.6)

kbd.paste_text(TXT, auto_enter=False, terminal_paste=False)
time.sleep(0.7)
kb.send("ctrl+a"); time.sleep(0.2); kb.send("ctrl+c"); time.sleep(0.4)
got = pyperclip.paste()

with open(RESULT, "w", encoding="utf-8") as f:
    f.write("FOREGROUND=%s\n" % win32gui.GetWindowText(win32gui.GetForegroundWindow()))
    f.write("EXPECTED=%s\n" % TXT)
    f.write("GOT=%r\n" % got)
    f.write("RESULT=%s\n" % ("PASS" if TXT.strip() in got else "FAIL"))

win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
time.sleep(0.5)
kb.send("alt+n")
