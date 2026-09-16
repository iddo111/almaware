"""
keshev-next INTAKE SIDECAR - phone-mic-to-PC-typing helper.

Standalone, stdlib-only HTTP service. It NEVER edits, imports-and-restarts,
or shares a process with the live keshev-next mic (app/main.py) -- it only
imports pure functions from app/typer.py so its typing behaviour (elevated
-window block, password-manager skip) is byte-identical to the live mic's.

Built 2026-09-06 per Iddo's 11:47 order (phone mic -> Tailscale -> PC typed
text, into a window HE locks). Claimed in RAMCHAT as claude-cli-PHONEMIC-PCLOCK,
port 8892. Binds ONLY 127.0.0.1 and the PC's own Tailscale IPv4 -- never
0.0.0.0. Run via RUN-INTAKE.cmd (start /belownormal /min) -- see the
BELOW_NORMAL PC rule in CLAUDE.md.

Endpoints:
  GET  /health            -- no auth, liveness only
  GET  /windows            -- top-level visible windows, z-order, elevated flag
  GET  /status              -- current lock state
  POST /lock   {"hwnd": N}   -- lock typing to that window (persists across restarts)
  POST /unlock                -- clear the lock
  POST /type   {"text": "...", "auto_enter": bool}
       -- if locked: brings the locked window forward (best-effort -- Windows'
          foreground-lock-timeout can refuse this from a background process,
          which the response reports honestly via foreground_matched) then
          types via app/typer.py's type_string(); if not locked, types into
          whatever window currently has focus, exactly like the live mic.
       -- 409 (not a silent drop) if the target is an elevated (Administrator)
          window -- Windows (UIPI) would eat the keystrokes and report success.

All endpoints except /health require header:  X-Alma-Token: <token>
Token lives at keshev-next/state/intake.token (32 hex, generated on first run).
CORS is allowed only for https://<tailnet-host> (the phone PWA's origin).
"""
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import secrets
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))            # ...\keshev-next\intake
KESHEV_ROOT = os.path.dirname(BASE_DIR)                            # ...\keshev-next
APP_DIR = os.path.join(KESHEV_ROOT, "app")
STATE_DIR = os.path.join(KESHEV_ROOT, "state")

sys.path.insert(0, APP_DIR)
import typer as keshev_typer  # noqa: E402  -- THE SAME module the live mic uses

TOKEN_PATH = os.path.join(STATE_DIR, "intake.token")
LOCK_PATH = os.path.join(STATE_DIR, "intake_lock.json")
LOG_PATH = os.path.join(STATE_DIR, "intake.log")

PORT = 8892
BIND_LOOPBACK = "127.0.0.1"
def _tailscale_ipv4():
    """Ask Tailscale for our address instead of trusting a hard-coded one.

    2026-09-06: this was pinned to the measured literal "<tailnet-ip>". Correct that
    day, and a silent death the day Tailscale hands out a different address: the bind
    fails, the phone leg stops, and nothing supervises this process to notice. A
    watcher may only act on a state it can name -- so name it at startup, every time.
    Falls back to the old literal only if the tailscale CLI cannot answer."""
    import subprocess
    for argv in (["tailscale", "ip", "-4"],
                 [r"C:\Program Files\Tailscale	ailscale.exe", "ip", "-4"]):
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            for line in (out.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("100."):
                    return line
        except Exception:
            continue
    return "<tailnet-ip>"


BIND_TAILSCALE = _tailscale_ipv4()
ALLOWED_ORIGIN = "https://<tailnet-host>"

SW_RESTORE = 9
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000

_lock_guard = threading.Lock()
_locked_hwnd = None  # int or None

user32 = keshev_typer.user32
kernel32 = keshev_typer.kernel32

# ---- extra Win32 declarations the live typer.py has no need of ----
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentProcess.argtypes = []
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.SetPriorityClass.restype = wintypes.BOOL


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def set_priority_below_normal():
    """PC rule: nothing above BELOW_NORMAL. RUN-INTAKE.cmd already launches us
    via 'start /belownormal', but set it again here so a direct debug run
    ('python keshev_intake.py') still complies."""
    try:
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
    except Exception as e:
        log(f"could not set BELOW_NORMAL priority: {e}")


def load_or_create_token():
    os.makedirs(STATE_DIR, exist_ok=True)
    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, "r", encoding="utf-8") as f:
                tok = f.read().strip()
            if tok:
                return tok
        except Exception:
            pass
    tok = secrets.token_hex(16)  # 32 hex chars
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(tok)
    log(f"generated new token at {TOKEN_PATH}")
    return tok


TOKEN = load_or_create_token()


def load_lock():
    global _locked_hwnd
    try:
        with open(LOCK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        hwnd = data.get("hwnd")
        if hwnd and user32.IsWindow(hwnd):
            _locked_hwnd = hwnd
            log(f"restored lock on hwnd={hwnd} from {LOCK_PATH}")
        else:
            _locked_hwnd = None
    except FileNotFoundError:
        _locked_hwnd = None
    except Exception as e:
        log(f"load_lock failed: {e}")
        _locked_hwnd = None


def save_lock():
    try:
        with open(LOCK_PATH, "w", encoding="utf-8") as f:
            json.dump({"hwnd": _locked_hwnd}, f)
    except Exception as e:
        log(f"save_lock failed: {e}")


def get_window_title(hwnd):
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def list_windows():
    """Top-level visible titled windows in EnumWindows' (z-order, top to bottom) order."""
    results = []

    def _cb(hwnd, lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            title = get_window_title(hwnd)
            if not title:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = ""
            try:
                import psutil
                proc_name = psutil.Process(pid.value).name()
            except Exception:
                proc_name = ""
            integrity = keshev_typer.process_integrity(pid.value)
            elevated = keshev_typer.integrity_is_elevated(integrity)
            results.append({
                "hwnd": int(hwnd),
                "title": title,
                "pid": int(pid.value),
                "process_name": proc_name,
                "integrity": integrity,
                "elevated": elevated,
            })
        except Exception as e:
            log(f"enum callback error: {e}")
        return True

    cb = WNDENUMPROC(_cb)
    user32.EnumWindows(cb, 0)
    return results


def force_foreground(hwnd):
    """Best-effort bring hwnd to the foreground from this background process.
    Windows' foreground-lock-timeout heuristic can legitimately refuse a
    SetForegroundWindow call from a process that is not already the active
    app -- this is NOT guaranteed to work, hence the caller-visible
    foreground_matched flag instead of trusting the return code alone.
    Returns (set_foreground_return_ok, actually_foreground_after)."""
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        cur_thread = kernel32.GetCurrentThreadId()
        fg = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        attached = []
        for t in (fg_thread, target_thread):
            if t and t != cur_thread and t not in attached:
                if user32.AttachThreadInput(cur_thread, t, True):
                    attached.append(t)
        user32.BringWindowToTop(hwnd)
        ok = bool(user32.SetForegroundWindow(hwnd))
        for t in attached:
            user32.AttachThreadInput(cur_thread, t, False)
        time.sleep(0.05)
        now_fg = user32.GetForegroundWindow()
        return ok, (now_fg == hwnd)
    except Exception as e:
        log(f"force_foreground error: {e}")
        return False, False


class Handler(BaseHTTPRequestHandler):
    server_version = "KeshevIntake/1.0"

    def log_message(self, fmt, *args):
        log(f"{self.address_string()} - {fmt % args}")

    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Alma-Token, Content-Type")

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _authed(self):
        return self.headers.get("X-Alma-Token", "") == TOKEN

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        try:
            if self.path == "/health":
                self._send_json(200, {"ok": True, "service": "keshev-intake", "pid": os.getpid()})
                return
            if not self._authed():
                self._send_json(401, {"error": "unauthorized", "hint": "X-Alma-Token header required"})
                return
            if self.path == "/windows":
                wins = list_windows()
                self._send_json(200, {"windows": wins, "count": len(wins)})
                return
            if self.path == "/status":
                with _lock_guard:
                    hwnd = _locked_hwnd
                valid = bool(hwnd and user32.IsWindow(hwnd))
                title = get_window_title(hwnd) if valid else ""
                self._send_json(200, {"locked": valid, "hwnd": hwnd if valid else None, "title": title})
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            log(f"GET {self.path} error: {e}\n{traceback.format_exc()}")
            self._send_json(500, {"error": str(e)})

    def do_POST(self):
        global _locked_hwnd
        try:
            if not self._authed():
                self._send_json(401, {"error": "unauthorized", "hint": "X-Alma-Token header required"})
                return
            if self.path == "/lock":
                body = self._read_json_body()
                try:
                    hwnd = int(body.get("hwnd"))
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "hwnd (int) required"})
                    return
                if not user32.IsWindow(hwnd):
                    self._send_json(404, {"error": "no such window", "hwnd": hwnd})
                    return
                with _lock_guard:
                    _locked_hwnd = hwnd
                    save_lock()
                title = get_window_title(hwnd)
                log(f"LOCK hwnd={hwnd} title={title!r}")
                self._send_json(200, {"locked": True, "hwnd": hwnd, "title": title})
                return
            if self.path == "/unlock":
                with _lock_guard:
                    old = _locked_hwnd
                    _locked_hwnd = None
                    save_lock()
                log(f"UNLOCK (was hwnd={old})")
                self._send_json(200, {"locked": False})
                return
            if self.path == "/type":
                body = self._read_json_body()
                text = body.get("text", "")
                auto_enter = bool(body.get("auto_enter", False))
                if not isinstance(text, str) or not text:
                    self._send_json(400, {"error": "text (non-empty string) required"})
                    return
                self._handle_type(text, auto_enter)
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            log(f"POST {self.path} error: {e}\n{traceback.format_exc()}")
            self._send_json(500, {"error": str(e)})

    def _handle_type(self, text, auto_enter):
        global _locked_hwnd
        t0 = time.time()
        with _lock_guard:
            hwnd = _locked_hwnd
        target_title = ""
        foreground_matched = None

        if hwnd:
            if not user32.IsWindow(hwnd):
                with _lock_guard:
                    _locked_hwnd = None
                    save_lock()
                self._send_json(410, {"error": "locked window no longer exists", "hwnd": hwnd})
                return
            integrity = keshev_typer.window_integrity(hwnd)
            if keshev_typer.integrity_is_elevated(integrity):
                self._send_json(409, {
                    "error": "target window is elevated (Administrator) - Windows (UIPI) "
                             "silently drops keystrokes into it; relaunch it without "
                             "'Run as administrator'.",
                    "error_he": "החלון הנעול רץ כמנהל מערכת - Windows חוסם הקלדה אליו "
                                "בשקט; פתח אותו מחדש בלי 'הפעל כמנהל'.",
                    "hwnd": hwnd, "integrity": integrity,
                })
                return
            _ok, matched = force_foreground(hwnd)
            foreground_matched = matched
            target_title = get_window_title(hwnd)
            if not matched:
                log(f"WARN: SetForegroundWindow did not land on hwnd={hwnd} "
                    f"({target_title!r}) - Windows foreground-lock-timeout may have refused it")
        else:
            # 2026-09-06 21:59 -- REFUSE, do not guess. Until now an unlocked intake typed
            # into whatever happened to be in the foreground, and tonight that meant a
            # silence-hallucination ("אדוני") landed in his YouTube tab at 21:56:38 and in
            # his Claude conversation at 21:58:47. The lock had quietly gone; nothing said so.
            # Typing into an unnamed target is the same fault as a watcher acting on a state
            # it cannot name. No lock, no keystrokes.
            self._send_json(409, {
                "error": "no window is locked - refusing to type into whatever is in front",
                "error_he": "אין חלון נעול - לא מקליד למשהו אקראי",
                "typed": 0, "locked": False,
            })
            log("REFUSED /type: nothing locked (would have typed %d chars into %r)"
                % (len(text), get_window_title(user32.GetForegroundWindow()) or "?"))
            return

        ok = keshev_typer.type_string(text, auto_enter=auto_enter)
        latency_ms = round((time.time() - t0) * 1000, 1)
        if not ok:
            self._send_json(409, {
                "error": "typing blocked (elevated foreground window or password manager) - see server log",
                "typed": 0, "target_title": target_title, "latency_ms": latency_ms,
            })
            return
        log(f"TYPE {len(text)} chars into {target_title!r} "
            f"(locked={bool(hwnd)}, foreground_matched={foreground_matched}) in {latency_ms}ms")
        self._send_json(200, {
            "typed": len(text), "target_title": target_title,
            "locked": bool(hwnd), "foreground_matched": foreground_matched,
            "latency_ms": latency_ms,
        })


def main():
    set_priority_below_normal()
    load_lock()
    log(f"keshev-intake starting, pid={os.getpid()}, token file={TOKEN_PATH}")

    servers = []
    for host in (BIND_LOOPBACK, BIND_TAILSCALE):
        try:
            httpd = ThreadingHTTPServer((host, PORT), Handler)
            servers.append((host, httpd))
            log(f"bound {host}:{PORT}")
        except Exception as e:
            log(f"FAILED to bind {host}:{PORT}: {e}")

    if not servers:
        log("FATAL: no listeners bound, exiting")
        sys.exit(1)

    threads = []
    for host, httpd in servers:
        th = threading.Thread(target=httpd.serve_forever, daemon=True, name=f"http-{host}")
        th.start()
        threads.append(th)

    for th in threads:
        th.join()


if __name__ == "__main__":
    main()
