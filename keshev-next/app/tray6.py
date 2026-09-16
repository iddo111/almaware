"""tray6.py -- a system-tray icon for the KESHEV 6 window (stdlib ctypes; Pillow optional).

Iddo, 2026-09-15 03:11: "נעלם לי הגואי של קשב - תן לו טריי אייקון".
The badge is an overrideredirect window with no taskbar button, so once it was
minimized (found at -32000,-32000) there was nowhere to click it back from.
The tray icon is that place: left click = show the window; right click = a
two-item menu (show / minimize). There is deliberately no "exit" item --
closing the window stops the microphone, and a tray menu is too easy to misclick.

Threading: Win32 tray messages arrive on this module's own thread. Tk is not
thread-safe, so the thread only puts words ("show" / "hide") into a queue and
gui6 drains it with root.after(). Nothing here touches the microphone or the engine.

Self-test:  python tray6.py --selftest   (adds the icon for ~1.5 s, removes it)
"""
import ctypes
import ctypes.wintypes as W
import os
import queue
import sys
import threading

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

WM_NULL, WM_DESTROY, WM_CLOSE, WM_CONTEXTMENU = 0x0000, 0x0002, 0x0010, 0x007B
WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0202, 0x0203, 0x0205
WM_APP = 0x8000
CB_MSG = WM_APP + 1
NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
IDI_APPLICATION = 32512
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x0002, 0x0080, 0x0100
MF_STRING = 0x0
ID_SHOW, ID_HIDE = 1001, 1002


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                ("lpszClassName", W.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
                ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
                ("uVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", W.HICON)]


user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = W.ATOM
user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
user32.CreateWindowExW.restype = W.HWND
user32.DestroyWindow.argtypes = [W.HWND]
user32.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
user32.LoadImageW.restype = W.HANDLE
user32.LoadIconW.argtypes = [W.HINSTANCE, W.LPVOID]
user32.LoadIconW.restype = W.HICON
user32.GetMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
user32.GetMessageW.restype = W.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(W.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(W.MSG)]
user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.RegisterWindowMessageW.argtypes = [W.LPCWSTR]
user32.RegisterWindowMessageW.restype = W.UINT
user32.CreatePopupMenu.restype = W.HMENU
user32.AppendMenuW.argtypes = [W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR]
user32.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.LPVOID]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [W.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(W.POINT)]
user32.SetForegroundWindow.argtypes = [W.HWND]
shell32.Shell_NotifyIconW.argtypes = [W.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = W.BOOL
kernel32.GetModuleHandleW.argtypes = [W.LPCWSTR]
kernel32.GetModuleHandleW.restype = W.HMODULE


def make_icon(path):
    """Write a small green KESHEV dot as .ico once. Returns the path, or None."""
    if path and os.path.exists(path):
        return path
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill=(46, 158, 91, 255))
        d.ellipse((24, 14, 40, 40), fill=(255, 255, 255, 255))      # the mic head
        d.rectangle((30, 40, 34, 50), fill=(255, 255, 255, 255))    # its stem
        img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
        return path
    except Exception:
        return None


class Tray:
    def __init__(self, tip="קשב 6", icon_path=None):
        self.events = queue.Queue()
        self.tip = tip[:127]
        self.icon_path = icon_path
        self.hwnd = None
        self.ok = False
        self._ready = threading.Event()
        self._thread = None
        self._proc = WNDPROC(self._wndproc)          # keep a reference: ctypes callbacks die if collected
        self._hicon = None
        self._taskbar_created = 0

    # -- public ---------------------------------------------------------------
    def start(self, timeout=3.0):
        self._thread = threading.Thread(target=self._run, name="keshev-tray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self.ok

    def stop(self, timeout=2.0):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(timeout)

    def drain(self):
        words = []
        while True:
            try:
                words.append(self.events.get_nowait())
            except queue.Empty:
                return words

    # -- win32 thread ---------------------------------------------------------
    def _nid(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        return nid

    def _add(self):
        nid = self._nid()
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = CB_MSG
        nid.hIcon = self._hicon
        nid.szTip = self.tip
        return bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))

    def _delete(self):
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))

    def _menu(self, hwnd):
        menu = user32.CreatePopupMenu()
        try:
            user32.AppendMenuW(menu, MF_STRING, ID_SHOW, "הצג את חלון קשב")
            user32.AppendMenuW(menu, MF_STRING, ID_HIDE, "מזער")
            pt = W.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)          # without this the menu never closes
            cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD,
                                        pt.x, pt.y, 0, hwnd, None)
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)
            if cmd == ID_SHOW:
                self.events.put("show")
            elif cmd == ID_HIDE:
                self.events.put("hide")
        finally:
            user32.DestroyMenu(menu)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == CB_MSG:
                ev = lparam & 0xFFFF
                if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.events.put("show")
                elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._menu(hwnd)
                return 0
            if self._taskbar_created and msg == self._taskbar_created:
                self._add()                            # explorer restarted: put the icon back
                return 0
            if msg == WM_CLOSE:
                self._delete()
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        try:
            hinst = kernel32.GetModuleHandleW(None)
            cls = WNDCLASSW()
            cls.lpfnWndProc = self._proc
            cls.hInstance = hinst
            cls.lpszClassName = "KeshevTray6_%d" % os.getpid()
            user32.RegisterClassW(ctypes.byref(cls))
            # A hidden top-level window (never shown, so no taskbar button). Not a
            # message-only window: those miss the TaskbarCreated broadcast.
            self.hwnd = user32.CreateWindowExW(0, cls.lpszClassName, "KESHEV tray", 0,
                                               0, 0, 0, 0, None, None, hinst, None)
            self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
            path = make_icon(self.icon_path) if self.icon_path else None
            if path:
                self._hicon = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
            if not self._hicon:
                self._hicon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
            self.ok = bool(self.hwnd) and self._add()
        except Exception:
            self.ok = False
        finally:
            self._ready.set()
        if not self.ok:
            return
        msg = W.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__" and "--selftest" in sys.argv:
    import tempfile
    import time
    ico = os.path.join(tempfile.gettempdir(), "keshev-tray-selftest.ico")
    t = Tray(tip="KESHEV tray self-test", icon_path=ico)
    ok = t.start()
    print("started:", ok, "hwnd:", t.hwnd, "icon file:", os.path.exists(ico))
    t.events.put("show")
    time.sleep(1.5)
    words = t.drain()
    t.stop()
    alive = t._thread.is_alive()
    print("drained:", words, "thread alive after stop:", alive)
    print("TRAY-SELFTEST-OK" if ok and words == ["show"] and not alive else "TRAY-SELFTEST-FAIL")
