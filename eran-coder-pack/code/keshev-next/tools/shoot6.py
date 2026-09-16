"""Photograph the KESHEV 6 window -- from OUTSIDE it. Dev tool, not the mic.

    python -X utf8 tools\\shoot6.py <outdir>

Spawns app/gui6.py in --selftest-hold mode (dry: no engine, no audio device, no
heartbeat, no PAUSED) and takes the picture from THIS process with PrintWindow.

The separate process is the whole point. PrintWindow is synchronous: called from
inside the window's own Tk callback it deadlocks, and that Tk loop is what keeps
Iddo's microphone alive (a PrintWindow into the KESHEV window once froze every
after() callback for 3.5 minutes). From another process the target simply
answers WM_PRINT from its idle event loop.
"""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW_RENDERFULLCONTENT = 0x00000002


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def top_window_of(pid):
    """The visible top-level window belonging to `pid` (the badge has no title)."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _l):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 20 and r.bottom - r.top > 20:
                found.append((hwnd, (r.right - r.left) * (r.bottom - r.top)))
        return True

    user32.EnumWindows(cb, 0)
    if not found:
        return None
    found.sort(key=lambda t: -t[1])
    return found[0][0]


def print_window(hwnd, path):
    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h          # top-down
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    img.save(path)
    return (path, w, h, bool(ok))


Q, BS = "'", "\\"
DEMO_HEADER = [
    "[mic] device='Microphone (Logitech BRIO)' [Windows DirectSound] (index 19 at "
    "pick time, re-resolved at open, fenced) native=44100Hz resample=160/441 -> "
    "16000Hz block=64ms",
    "[mic] decoder READY",
]


def _heb(*codepoints):
    return Q + "".join(BS + "u%04x" % c for c in codepoints) + Q


DEMO_LIVE = [
    "[mic] status_events=1 dropped_blocks=3",
    "[segment] bytes=16384 secs=0.51 peak_rms=255 floor=600 SKIP too-quiet",
    "[segment] bytes=161792 secs=5.06 peak_rms=9100 gate=0.612/PASS lp=-0.44 "
    "decode=ok route=he text=" + _heb(0x5EA, 0x5D5, 0x5D3, 0x5D4, 0x20, 0x5E9,
                                      0x5DC, 0x5D5, 0x5DD),
    "[segment] bytes=57344 secs=1.79 peak_rms=2611 gate=0.671/PASS decode=empty route=- text=-",
    "[textguard] dropped segment (99999 bytes): blocklist:תודה",
    "[segment] bytes=99999 secs=3.00 peak_rms=5000 gate=0.600/PASS lp=-0.50 "
    "decode=ok route=he text=" + _heb(0x5EA, 0x5D5, 0x5D3, 0x5D4),
    "[segment] bytes=132000 secs=4.10 peak_rms=7400 gate=0.588/PASS lp=-0.52 "
    "decode=ok route=he text=" + _heb(0x5D0, 0x5E0, 0x5D9, 0x20, 0x5E8, 0x5D5,
                                      0x5E6, 0x5D4, 0x20, 0x5EA, 0x5D2, 0x20,
                                      0x5E9, 0x5DE, 0x5E8, 0x5D7, 0x5E3),
]


def _demo_setup(outdir):
    """A populated, healthy window: a fake engine on :8738 plus a synthetic log."""
    synth = os.path.join(outdir, "demo-trial.log")
    with open(synth, "w", encoding="utf-8") as fh:
        fh.write("\n".join(DEMO_HEADER) + "\n")
    os.environ["KESHEV_STT_URL"] = "http://127.0.0.1:8738/v1/transcribe"
    os.environ["KESHEV_STT_FALLBACK_URL"] = "http://<lan-ip>:8737/v1/transcribe"
    with open(os.path.join(outdir, "mic.pid"), "w") as fh:
        fh.write(str(os.getpid()))          # the demo's own pid IS the fake engine
    return synth


def shoot(mode, outdir, seconds=6.0, demo=False):
    os.makedirs(outdir, exist_ok=True)
    hwnd_file = os.path.join(outdir, "hold.hwnd")
    if os.path.exists(hwnd_file):
        os.remove(hwnd_file)
    synth = _demo_setup(outdir) if demo else None
    argv = [sys.executable, "-X", "utf8", os.path.join(ROOT, "app", "gui6.py"),
            f"--selftest-dir={outdir}", f"--selftest-hold={seconds}", f"--mode={mode}"]
    if synth:
        argv.append(synth)
    proc = subprocess.Popen(argv, cwd=ROOT,
                            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    pid = None
    for _ in range(80):
        time.sleep(0.1)
        if os.path.exists(hwnd_file):
            try:
                pid = int(open(hwnd_file).read().split()[0])
                break
            except Exception:
                pass
    if synth:
        time.sleep(1.5)                     # past catching_up, so these are LIVE
        with open(synth, "a", encoding="utf-8") as fh:
            for line in DEMO_LIVE:
                fh.write(line + "\n")
                fh.flush()
                time.sleep(0.12)
    result = None
    if pid:
        time.sleep(1.2)                     # let it paint and settle
        hwnd = top_window_of(pid)
        if hwnd:
            result = print_window(hwnd, os.path.join(outdir, f"{mode}.png"))
    proc.wait(timeout=seconds + 20)
    return result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    demo = "--demo" in sys.argv
    out = args[0] if args else os.path.join(ROOT, "state", "gui6-shots")
    for m in ("pill", "full"):
        print(m, "->", shoot(m, out, demo=demo))
