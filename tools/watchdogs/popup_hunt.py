"""Popup hunt: 10-minute screen video + a log of every top-level window that
appears, every focus steal, and every new process (with parent + command line).
Read-only observer. BELOW_NORMAL priority for itself and ffmpeg.
usage: python popup_hunt.py <outdir> [seconds]
"""
import ctypes
import ctypes.wintypes as W
import json
import os
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict

OUT = sys.argv[1]
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
FFMPEG = (r"C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe")
os.makedirs(OUT, exist_ok=True)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")

kernel32.GetCurrentProcess.restype = W.HANDLE
kernel32.SetPriorityClass.argtypes = [W.HANDLE, W.DWORD]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.CloseHandle.argtypes = [W.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
kernel32.CreateToolhelp32Snapshot.restype = W.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
ntdll.NtQueryInformationProcess.restype = ctypes.c_long
ntdll.NtQueryInformationProcess.argtypes = [W.HANDLE, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(W.ULONG)]
user32.GetAncestor.restype = W.HWND
user32.GetAncestor.argtypes = [W.HWND, W.UINT]
user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
user32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]
user32.SetWinEventHook.restype = W.HANDLE

kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL

LOG_PATH = os.path.join(OUT, "events.jsonl")
_lock = threading.Lock()
_log = open(LOG_PATH, "a", encoding="utf-8")
T0 = time.time()


def emit(rec):
    now = time.time()
    rec["t"] = round(now, 3)
    rec["video_s"] = round(now - T0, 2)
    rec["clock"] = time.strftime("%H:%M:%S", time.localtime(now)) + f".{int((now % 1) * 1000):03d}"
    with _lock:
        _log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _log.flush()


class PE(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD),
                ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260)]


kernel32.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(PE)]
kernel32.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(PE)]
NAMES = {}  # pid -> (ppid, exe name), kept after exit so parents stay nameable


def snapshot():
    h = kernel32.CreateToolhelp32Snapshot(2, 0)
    d = {}
    if not h or h == W.HANDLE(-1).value:
        return d
    pe = PE()
    pe.dwSize = ctypes.sizeof(PE)
    ok = kernel32.Process32FirstW(h, ctypes.byref(pe))
    while ok:
        d[pe.th32ProcessID] = (pe.th32ParentProcessID, pe.szExeFile)
        ok = kernel32.Process32NextW(h, ctypes.byref(pe))
    kernel32.CloseHandle(h)
    return d


class US(ctypes.Structure):
    _fields_ = [("Length", W.USHORT), ("MaximumLength", W.USHORT), ("Buffer", ctypes.c_void_p)]


def cmdline(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        size = W.ULONG(0)
        n = 8192
        for _ in range(2):
            buf = ctypes.create_string_buffer(n)
            st = ntdll.NtQueryInformationProcess(h, 60, ctypes.addressof(buf), n, ctypes.byref(size))
            if st == 0:
                us = US.from_buffer(buf)
                return ctypes.wstring_at(us.Buffer, us.Length // 2) if us.Buffer else ""
            if st in (-1073741820, -1073741789, -2147483643) and size.value > n:
                n = size.value
                continue
            return None
    finally:
        kernel32.CloseHandle(h)


def exe_path(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        ln = W.DWORD(1024)
        return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(ln)) else None
    finally:
        kernel32.CloseHandle(h)


def lineage(pid, depth=4):
    chain = []
    cur = pid
    for _ in range(depth):
        info = NAMES.get(cur)
        if not info:
            break
        ppid, name = info
        chain.append(f"{name}({cur})")
        if not ppid or ppid == cur:
            break
        cur = ppid
    return " <- ".join(chain)


def window_info(hwnd):
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    pid = W.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    r = W.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    exstyle = user32.GetWindowLongW(hwnd, -20) & 0xFFFFFFFF
    if pid.value not in NAMES:
        NAMES.update(snapshot())
    return {
        "hwnd": hwnd, "cls": cls.value, "title": title.value, "pid": pid.value,
        "exe": exe_path(pid.value) or (NAMES.get(pid.value, (0, "?"))[1]),
        "lineage": lineage(pid.value), "w": r.right - r.left, "h": r.bottom - r.top,
        "toolwindow": bool(exstyle & 0x80), "topmost": bool(exstyle & 0x8),
    }


WinEventProc = ctypes.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)


def on_event(hook, event, hwnd, id_object, id_child, thread, ms):
    try:
        if not hwnd or id_object != 0 or id_child != 0:
            return
        if event == 0x8002:  # EVENT_OBJECT_SHOW
            if user32.GetAncestor(hwnd, 2) != hwnd or not user32.IsWindowVisible(hwnd):
                return
            rec = window_info(hwnd)
            rec["kind"] = "show"
        else:  # EVENT_SYSTEM_FOREGROUND
            rec = window_info(hwnd)
            rec["kind"] = "foreground"
        if rec["pid"] and rec["kind"] == "show":
            rec["cmdline"] = cmdline(rec["pid"])
        emit(rec)
    except Exception as e:  # never let the hook die
        emit({"kind": "hook_error", "err": repr(e)})


PROC = WinEventProc(on_event)


def poll_processes(stop):
    prev = snapshot()
    NAMES.update(prev)
    while not stop.is_set():
        time.sleep(0.15)
        cur = snapshot()
        NAMES.update(cur)
        for pid in cur.keys() - prev.keys():
            ppid, name = cur[pid]
            emit({"kind": "proc", "pid": pid, "name": name, "ppid": ppid,
                  "lineage": lineage(pid), "cmdline": cmdline(pid)})
        prev = cur


def main():
    video = os.path.join(OUT, "screen.mp4")
    ff = subprocess.Popen(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab", "-framerate", "4",
         "-draw_mouse", "1", "-i", "desktop", "-vf", "scale=1600:-2", "-c:v", "libx264",
         "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p", video],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=open(os.path.join(OUT, "ffmpeg.log"), "wb"),
        creationflags=0x08000000 | 0x00004000)  # CREATE_NO_WINDOW | BELOW_NORMAL
    emit({"kind": "start", "duration_s": DUR, "ffmpeg_pid": ff.pid, "self_pid": os.getpid()})

    h1 = user32.SetWinEventHook(0x0003, 0x0003, 0, PROC, 0, 0, 0x2)
    h2 = user32.SetWinEventHook(0x8002, 0x8002, 0, PROC, 0, 0, 0x2)
    stop = threading.Event()
    th = threading.Thread(target=poll_processes, args=(stop,), daemon=True)
    th.start()

    msg = W.MSG()
    end = time.time() + DUR
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    stop.set()
    user32.UnhookWinEvent(h1)
    user32.UnhookWinEvent(h2)
    try:
        ff.stdin.write(b"q")
        ff.stdin.flush()
        ff.wait(timeout=30)
    except Exception:
        ff.terminate()
    emit({"kind": "end", "ffmpeg_rc": ff.returncode})
    _log.close()

    # summary
    shows, fgs, procs = Counter(), Counter(), Counter()
    first = defaultdict(list)
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            k = r.get("kind")
            if k == "show":
                key = f"{os.path.basename(r.get('exe') or '?')} | {r.get('cls')} | {r.get('w')}x{r.get('h')}"
                shows[key] += 1
                first[key].append(r["clock"])
            elif k == "foreground":
                key = f"{os.path.basename(r.get('exe') or '?')} | {r.get('cls')} | {r.get('title')[:60]}"
                fgs[key] += 1
                first[key].append(r["clock"])
            elif k == "proc":
                procs[r.get("name")] += 1
    with open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("== TOP-LEVEL WINDOWS SHOWN (exe | class | size): count, first times ==\n")
        for key, c in shows.most_common():
            f.write(f"{c:4d}  {key}   {first[key][:6]}\n")
        f.write("\n== FOREGROUND CHANGES (exe | class | title) ==\n")
        for key, c in fgs.most_common():
            f.write(f"{c:4d}  {key}   {first[key][:6]}\n")
        f.write("\n== NEW PROCESSES by name ==\n")
        for key, c in procs.most_common():
            f.write(f"{c:4d}  {key}\n")


if __name__ == "__main__":
    main()
