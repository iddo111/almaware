"""Type test v4 - use pywin32 to reliably focus Notepad (handles 64-bit HWND),
apply the ALT-key SetForegroundWindow workaround, paste Hebrew, read back via
clipboard select-all+copy.
"""
import sys, time, subprocess
sys.stdout.reconfigure(encoding="utf-8")
import win32gui, win32con, win32api
import pyperclip, keyboard as kb
import typer as kbd

TXT = "שלום עידו voice input עובד 123"
subprocess.Popen(["notepad.exe"])
time.sleep(1.8)

hwnd = win32gui.GetForegroundWindow()
title = win32gui.GetWindowText(hwnd)
# find a notepad window if foreground isn't it
def find_np():
    res=[]
    def cb(h,_):
        t=win32gui.GetWindowText(h)
        if "Notepad" in t or "פנקס" in t:
            res.append(h)
    win32gui.EnumWindows(cb,None)
    return res
nps = find_np()
if nps:
    hwnd = nps[0]
print("target hwnd:", hwnd, "title:", win32gui.GetWindowText(hwnd))

# ALT workaround to bypass foreground lock
win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
try:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
except Exception as e:
    print("SetForeground err:", e)
time.sleep(0.5)
print("foreground now:", win32gui.GetWindowText(win32gui.GetForegroundWindow()))

# paste Hebrew (plain Ctrl+V)
kbd.paste_text(TXT, auto_enter=False, terminal_paste=False)
time.sleep(0.6)

# read back
kb.send("ctrl+a"); time.sleep(0.2); kb.send("ctrl+c"); time.sleep(0.35)
got = pyperclip.paste()
print("EXPECTED:", TXT)
print("GOT     :", repr(got))
print("RESULT(paste):", "PASS" if TXT.strip() in got else "FAIL")

# also test SendInput unicode after clearing
kb.send("ctrl+a"); time.sleep(0.15); kb.send("delete"); time.sleep(0.2)
kbd.type_unicode(TXT, char_delay=0.01)
time.sleep(0.4)
kb.send("ctrl+a"); time.sleep(0.2); kb.send("ctrl+c"); time.sleep(0.35)
got2 = pyperclip.paste()
print("GOT(sendinput):", repr(got2))
print("RESULT(sendinput):", "PASS" if TXT.strip() in got2 else "FAIL")

# close no-save
win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
time.sleep(0.5)
kb.send("alt+n")
