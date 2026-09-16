"""Screenshot helper for gui6.py --selftest-render ONLY. Not part of the mic.

It grabs the SCREEN RECTANGLE the window occupies (a desktop BitBlt) instead of
sending WM_PRINT to the window. That distinction matters: a synchronous
PrintWindow into the KESHEV window once froze every Tk after() callback for
3.5 minutes, and those callbacks are what keep the microphone alive.
"""

import ctypes
import ctypes.wintypes as wt


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]


def window_rect(hwnd):
    r = RECT()
    if not ctypes.windll.user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r)):
        return None
    return r.left, r.top, r.right, r.bottom


def grab_window(hwnd, path, pad=0):
    """Save the screen area under `hwnd` to `path` (PNG). True on success."""
    try:
        from PIL import ImageGrab
    except Exception:
        return False
    box = window_rect(hwnd)
    if not box:
        return False
    left, top, right, bottom = box
    box = (left - pad, top - pad, right + pad, bottom + pad)
    if box[2] <= box[0] or box[3] <= box[1]:
        return False
    img = ImageGrab.grab(bbox=box, all_screens=True)
    img.save(path)
    return True
