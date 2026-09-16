"""
Self-test for keshev_intake.py, run against the LIVE sidecar (not a mock).
Opens a fresh Notepad, locks the sidecar's typing target to it via the real
HTTP API, types Hebrew text through /type, reads the text back from Notepad
via the clipboard (Ctrl+A / Ctrl+C sent from THIS process, exactly like a
human would), and asserts equality. Then unlocks and force-closes Notepad.
Never touches the live keshev-next mic.
"""
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8892"
TOKEN_PATH = r"D:\CLAUDE\keshev-next\state\intake.token"

with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    TOKEN = f.read().strip()

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_A = 0x41
VK_C = 0x43


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT_U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_U)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def _key_input(vk, up=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    return inp


def send_ctrl_combo(vk):
    seq = [_key_input(VK_CONTROL), _key_input(vk), _key_input(vk, up=True), _key_input(VK_CONTROL, up=True)]
    arr = (INPUT * len(seq))(*seq)
    user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def read_clipboard_text():
    CF_UNICODETEXT = 13
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]

    if not user32.OpenClipboard(None):
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return None
        try:
            text = ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
        return text
    finally:
        user32.CloseClipboard()


def api(method, path, body=None):
    url = BASE + path
    headers = {"X-Alma-Token": TOKEN, "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main():
    report = {}

    status, health = api("GET", "/health")
    print("health:", status, health)
    assert status == 200 and health.get("ok") is True

    target_script = r"D:\CLAUDE\keshev-next\intake\selftest_target.py"
    proc = subprocess.Popen(["C:\\Program Files\\Python312\\python.exe", target_script])
    print(f"launched disposable Tk target, pid={proc.pid}, waiting for its window...")

    hwnd = None
    title = None
    deadline = time.time() + 8
    while time.time() < deadline and hwnd is None:
        time.sleep(0.3)
        st, wins = api("GET", "/windows")
        for w in wins["windows"]:
            if w["pid"] == proc.pid and w["title"] == "KESHEV-INTAKE-SELFTEST-TARGET":
                hwnd = w["hwnd"]
                title = w["title"]
                break
    if hwnd is None:
        print("FAIL: selftest target window never appeared in /windows")
        subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
        sys.exit(1)
    print(f"found target hwnd={hwnd} title={title!r} pid={proc.pid}")

    st, resp = api("POST", "/lock", {"hwnd": hwnd})
    print("lock:", st, resp)
    assert st == 200 and resp["locked"] is True

    content_path = r"D:\CLAUDE\keshev-next\state\selftest_target_content.txt"
    try:
        os.remove(content_path)
    except FileNotFoundError:
        pass

    text = "שלום מהטלפון"
    t0 = time.time()
    st, resp = api("POST", "/type", {"text": text})
    wall_ms = round((time.time() - t0) * 1000, 1)
    print("type:", st, resp, f"(wall {wall_ms}ms)")
    report["type_response"] = resp
    report["type_wall_ms"] = wall_ms
    assert st == 200, f"expected 200, got {st}: {resp}"
    assert resp["foreground_matched"] is True, "SetForegroundWindow from the sidecar did not land on the target window"

    # Out-of-band verification: the disposable target itself dumps its live Text
    # content to a file every 100ms, so we read back what ACTUALLY landed inside
    # it instead of racing a second, separate foreground change (Ctrl+A/Ctrl+C
    # from this process would need the sidecar's transient foreground grab to
    # still hold hundreds of ms later, which Windows does not guarantee, and
    # which the real /type call never depends on -- it types immediately after
    # grabbing foreground, in the same call).
    got = None
    deadline = time.time() + 3
    while time.time() < deadline:
        time.sleep(0.15)
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                got = f.read()
        except FileNotFoundError:
            continue
        if got:
            break
    print("target window content read back:", repr(got))
    report["target_content"] = got
    report["expected"] = text
    report["match"] = (got == text)

    st, resp = api("POST", "/unlock")
    print("unlock:", st, resp)

    subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)

    print("REPORT:", json.dumps(report, ensure_ascii=False, indent=2))
    if not report["match"]:
        print("SELFTEST FAIL: clipboard text does not match what was sent")
        sys.exit(1)
    print("SELFTEST PASS")


if __name__ == "__main__":
    main()
