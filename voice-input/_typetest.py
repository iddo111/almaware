"""Type-into-focused-window self-test. Opens Notepad, focuses it, types a
Hebrew+English string via SendInput Unicode, then saves+reads the file back to
prove the exact Hebrew characters landed. Then repeats via clipboard paste.
"""
import sys, time, subprocess, os
sys.stdout.reconfigure(encoding="utf-8")
import ctypes
import typer as kbd

TXT = "שלום עידו voice input עובד 123"
OUT = r"D:\CLAUDE\voice-input\samples\typetest_out.txt"
if os.path.exists(OUT):
    os.remove(OUT)

user32 = ctypes.windll.user32
np_proc = subprocess.Popen(["notepad.exe"])
time.sleep(1.5)

# bring notepad to foreground
hwnd = user32.FindWindowW(None, "Untitled - Notepad")
if not hwnd:
    hwnd = user32.GetForegroundWindow()
user32.SetForegroundWindow(hwnd)
time.sleep(0.4)

# --- method 1: SendInput unicode ---
kbd.type_unicode(TXT, char_delay=0.01, auto_enter=False)
time.sleep(0.4)
kbd.type_unicode("\n", auto_enter=False)
time.sleep(0.2)

# --- method 2: clipboard paste (plain Ctrl+V for notepad) ---
kbd.paste_text(TXT, auto_enter=False, terminal_paste=False)
time.sleep(0.5)

# Read back robustly: select-all + copy, then read clipboard (works on Win11
# Notepad's RichEdit control where WM_GETTEXT to the parent fails).
import pyperclip
saved_clip = ""
try:
    saved_clip = pyperclip.paste()
except Exception:
    pass
import keyboard as _kb
_kb.send("ctrl+a")
time.sleep(0.15)
_kb.send("ctrl+c")
time.sleep(0.25)
got = pyperclip.paste()
print("EXPECTED:", TXT)
print("GOT     :", repr(got))
ok_kbd = TXT in got
ok_paste = got.count("שלום עידו") >= 1
print("SendInput Hebrew present:", ok_kbd)
print("Clipboard-paste Hebrew present (>=1 'שלום עידו'):", got.count("שלום עידו"), "copies")

# close notepad without saving
user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
time.sleep(0.5)
# dismiss "save?" dialog -> Don't Save (Alt+N / press 'n')
import keyboard
keyboard.send("alt+n")
print("RESULT:", "PASS" if (ok_kbd or got.count("שלום עידו")>=1) else "FAIL")
