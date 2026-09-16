"""Robust type test v2: open Notepad, force-focus via AttachThreadInput, click
center to place caret, then PASTE Hebrew (clipboard). Read back via select-all+copy.
"""
import sys, time, subprocess, ctypes
from ctypes import wintypes
sys.stdout.reconfigure(encoding="utf-8")
import pyperclip, keyboard as kb
import typer as kbd

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
TXT = "שלום עידו voice input עובד 123"

subprocess.Popen(["notepad.exe"])
time.sleep(1.6)
hwnd = user32.GetForegroundWindow()
# force foreground robustly
fg_thread = user32.GetWindowThreadProcessId(hwnd, None)
cur_thread = kernel32.GetCurrentThreadId()
user32.AttachThreadInput(cur_thread, fg_thread, True)
user32.ShowWindow(hwnd, 9)  # SW_RESTORE
user32.SetForegroundWindow(hwnd)
user32.SetFocus(hwnd)
user32.AttachThreadInput(cur_thread, fg_thread, False)
time.sleep(0.4)

# click center of the window to put the caret in the text area
rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
cx = (rect.left + rect.right)//2
cy = (rect.top + rect.bottom)//2
user32.SetCursorPos(cx, cy)
time.sleep(0.1)
# left click
user32.mouse_event(0x0002,0,0,0,0); user32.mouse_event(0x0004,0,0,0,0)
time.sleep(0.3)

# PASTE Hebrew (plain Ctrl+V for Notepad)
kbd.paste_text(TXT, auto_enter=False, terminal_paste=False)
time.sleep(0.6)

# read back
kb.send("ctrl+a"); time.sleep(0.15); kb.send("ctrl+c"); time.sleep(0.3)
got = pyperclip.paste()
print("EXPECTED:", TXT)
print("GOT     :", repr(got))
print("RESULT:", "PASS" if TXT.strip() in got else "FAIL")

# close without saving
user32.PostMessageW(hwnd, 0x0010, 0, 0)
time.sleep(0.5)
kb.send("alt+n")
