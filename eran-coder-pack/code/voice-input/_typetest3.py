"""Type test v3 - prove Hebrew Unicode delivery WITHOUT relying on OS foreground
steal (which the sandbox blocks). We create a real Win32 multiline EDIT control
in our own window, give IT focus, run typer.type_unicode (the same SendInput
path the daemon uses), then read the control's text via WM_GETTEXT.

This isolates the question 'do our SendInput Unicode keystrokes deliver correct
Hebrew to the focused edit control?' from 'can the test harness steal foreground'.
"""
import sys, time, ctypes
from ctypes import wintypes
sys.stdout.reconfigure(encoding="utf-8")
import typer as kbd

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
ES_MULTILINE = 0x0004
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_SETTEXT = 0x000C

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

def wndproc(h, msg, w, l):
    if msg == 0x0002:  # WM_DESTROY
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(h, msg, w, l)

class WNDCLASS(ctypes.Structure):
    _fields_=[("style",wintypes.UINT),("lpfnWndProc",WNDPROC),
              ("cbClsExtra",ctypes.c_int),("cbWndExtra",ctypes.c_int),
              ("hInstance",wintypes.HINSTANCE),("hIcon",wintypes.HICON),
              ("hCursor",wintypes.HANDLE),("hbrBackground",wintypes.HBRUSH),
              ("lpszMenuName",wintypes.LPCWSTR),("lpszClassName",wintypes.LPCWSTR)]

hInst = kernel32.GetModuleHandleW(None)
wc = WNDCLASS()
wc.lpfnWndProc = WNDPROC(wndproc)
wc.hInstance = hInst
wc.lpszClassName = "VITestWnd"
wc.hCursor = user32.LoadCursorW(0, 32512)
user32.RegisterClassW(ctypes.byref(wc))

hwnd = user32.CreateWindowExW(0, "VITestWnd", "VI Test", WS_OVERLAPPEDWINDOW|WS_VISIBLE,
                              100,100,500,300, 0,0,hInst,None)
edit = user32.CreateWindowExW(0, "EDIT", None,
                              WS_CHILD|WS_VISIBLE|ES_MULTILINE,
                              0,0,480,260, hwnd, 0, hInst, None)
user32.SetForegroundWindow(hwnd)
user32.SetFocus(edit)
time.sleep(0.4)
# pump messages briefly so the window is ready
msg = wintypes.MSG()
end = time.time()+0.3
while time.time()<end and user32.PeekMessageW(ctypes.byref(msg),0,0,0,1):
    user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))

user32.SetFocus(edit)
TXT = "שלום עידו voice input עובד 123"
kbd.type_unicode(TXT, char_delay=0.008, auto_enter=False)
# pump again
end = time.time()+0.4
while time.time()<end and user32.PeekMessageW(ctypes.byref(msg),0,0,0,1):
    user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))

length = user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, 0)
buf = ctypes.create_unicode_buffer(length+1)
user32.SendMessageW(edit, WM_GETTEXT, length+1, buf)
got = buf.value
print("EXPECTED:", TXT)
print("GOT     :", repr(got))
print("RESULT (SendInput Unicode):", "PASS" if TXT in got else "FAIL")

# now test clipboard paste path into the same control
import pyperclip
user32.SendMessageW(edit, WM_SETTEXT, 0, "")  # clear
user32.SetFocus(edit)
kbd.paste_text(TXT, auto_enter=False, terminal_paste=False)
end = time.time()+0.5
while time.time()<end and user32.PeekMessageW(ctypes.byref(msg),0,0,0,1):
    user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))
length = user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, 0)
buf2 = ctypes.create_unicode_buffer(length+1)
user32.SendMessageW(edit, WM_GETTEXT, length+1, buf2)
got2 = buf2.value
print("GOT(paste):", repr(got2))
print("RESULT (clipboard paste):", "PASS" if TXT in got2 else "FAIL")

user32.DestroyWindow(hwnd)
