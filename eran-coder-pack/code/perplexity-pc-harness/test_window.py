from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes


WINDOW_TITLE = "PPLX-SAFE-TEST-WINDOW"
ENTRY_ID = 1001
BUTTON_ID = 1002
RESULT_ID = 1003

WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
BN_CLICKED = 0
SW_SHOW = 5
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
WS_BORDER = 0x00800000
WS_OVERLAPPEDWINDOW = 0x00CF0000
ES_AUTOHSCROLL = 0x0080
BS_DEFPUSHBUTTON = 0x00000001
SS_CENTER = 0x00000001
WM_SETFONT = 0x0030


def loword(value: int) -> int:
    return value & 0xFFFF


def hiword(value: int) -> int:
    return (value >> 16) & 0xFFFF


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic local UI acceptance target")
    parser.add_argument("--expected-marker", default="PPLX_REAL_UI_MARKER_20260724")
    args = parser.parse_args()

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    hinstance = kernel32.GetModuleHandleW(None)
    controls: dict[str, int] = {}

    wndproc_type = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    )
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HANDLE,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.SetWindowTextW.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadCursorW.restype = wintypes.HANDLE

    @wndproc_type
    def wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == WM_COMMAND:
            control_id = loword(wparam)
            notification = hiword(wparam)
            if control_id == BUTTON_ID and notification == BN_CLICKED:
                buffer = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(controls["entry"], buffer, len(buffer))
                marker = buffer.value
                if marker == args.expected_marker:
                    user32.SetWindowTextW(controls["result"], marker)
                    user32.SetWindowTextW(hwnd, f"{WINDOW_TITLE} — {marker}")
                else:
                    user32.SetWindowTextW(controls["result"], "MARKER_MISMATCH")
                return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", wndproc_type),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class_name = "PplxSafeAcceptanceWindow"
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    window_class = WNDCLASSW()
    window_class.lpfnWndProc = wndproc
    window_class.hInstance = hinstance
    window_class.hCursor = user32.LoadCursorW(
        None,
        ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR),
    )
    window_class.hbrBackground = ctypes.c_void_p(6)
    window_class.lpszClassName = class_name
    if not user32.RegisterClassW(ctypes.byref(window_class)):
        error = ctypes.get_last_error()
        if error != 1410:  # ERROR_CLASS_ALREADY_EXISTS
            raise ctypes.WinError(error)

    hwnd = user32.CreateWindowExW(
        0,
        class_name,
        WINDOW_TITLE,
        WS_OVERLAPPEDWINDOW,
        160,
        140,
        720,
        420,
        None,
        None,
        hinstance,
        None,
    )
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())

    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.UpdateWindow.argtypes = [wintypes.HWND]
    user32.UpdateWindow.restype = wintypes.BOOL
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.IsDialogMessageW.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.MSG)]
    user32.IsDialogMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t

    def create_control(
        class_value: str,
        text: str,
        style: int,
        x: int,
        y: int,
        width: int,
        height: int,
        control_id: int,
    ) -> int:
        handle = user32.CreateWindowExW(
            0,
            class_value,
            text,
            WS_CHILD | WS_VISIBLE | style,
            x,
            y,
            width,
            height,
            hwnd,
            ctypes.c_void_p(control_id),
            hinstance,
            None,
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    heading = create_control("STATIC", "Perplexity Safe Computer-Use Acceptance", SS_CENTER, 70, 42, 560, 32, 1101)
    instructions = create_control(
        "STATIC",
        "Type the exact marker, then activate Commit marker.",
        SS_CENTER,
        90,
        92,
        520,
        24,
        1102,
    )
    controls["entry"] = create_control(
        "EDIT",
        "",
        WS_TABSTOP | WS_BORDER | ES_AUTOHSCROLL,
        110,
        132,
        480,
        34,
        ENTRY_ID,
    )
    controls["result"] = create_control("STATIC", "READY", SS_CENTER, 110, 196, 480, 34, RESULT_ID)
    controls["button"] = create_control(
        "BUTTON",
        "Commit marker",
        WS_TABSTOP | BS_DEFPUSHBUTTON,
        230,
        260,
        240,
        46,
        BUTTON_ID,
    )

    font = gdi32.CreateFontW(
        -20,
        0,
        0,
        0,
        400,
        0,
        0,
        0,
        1,
        0,
        0,
        5,
        0,
        "Segoe UI",
    )
    for control in (heading, instructions, controls["entry"], controls["result"], controls["button"]):
        user32.SendMessageW(control, WM_SETFONT, font, True)

    user32.ShowWindow(hwnd, SW_SHOW)
    user32.UpdateWindow(hwnd)
    user32.SetFocus(controls["entry"])

    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        if not user32.IsDialogMessageW(hwnd, ctypes.byref(message)):
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))


if __name__ == "__main__":
    main()
