"""engine_probe -- ask the ENGINE what it is really doing. Read-only, always.

Broken Windows Law: a window that says "ok" while nothing arrives is worse than
no window. Every fact in here is measured, never echoed from our own config:

  * read_engine_env(pid)  reads the LIVE engine process's own environment block
    out of its PEB. That is the URL the engine is actually posting audio to --
    not what RUN-KESHEV6.cmd set, not what os.environ says in THIS process.
    (2026-09-04: this distinction is the whole bug. RUN-KESHEV.cmd's inline
    `set` overrode Iddo's user-level setx for a day and nothing on screen could
    have told him.)

  * probe_health(url)     GETs the server's own /health with the real token.
    On the KESHEV-6 server /health answers 200 only when a real clip actually
    decoded (its canary), so a 200 is proof of a decode, not of a live socket.

Nothing here opens an audio device, writes a file, or changes a process.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request

TOKEN_FILE = r"D:/CLAUDE/mic-rebuild/state/stt-token"

# ── the engine's real environment, read out of its PEB ───────────────────────
# OpenProcess is asked for QUERY_INFORMATION|VM_READ only: we can look, we can
# never touch. If any step fails we return None and the window says "לא ידוע",
# which is the honest answer -- it must never guess a URL.

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

# x64 offsets (Win10/11). PEB->ProcessParameters, then
# RTL_USER_PROCESS_PARAMETERS->Environment / ->EnvironmentSize.
_PEB_PROCESS_PARAMETERS = 0x20
_RUPP_ENVIRONMENT = 0x80
_RUPP_ENVIRONMENT_SIZE = 0x3F0
_MAX_ENV_BYTES = 1 << 20


class _PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("ExitStatus", ctypes.c_long),
        ("_pad0", ctypes.c_long),
        ("PebBaseAddress", ctypes.c_void_p),
        ("AffinityMask", ctypes.c_size_t),
        ("BasePriority", ctypes.c_long),
        ("_pad1", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_size_t),
        ("InheritedFromUniqueProcessId", ctypes.c_size_t),
    ]


def _read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    ok = ctypes.windll.kernel32.ReadProcessMemory(
        h, ctypes.c_void_p(addr), buf, ctypes.c_size_t(size), ctypes.byref(got))
    if not ok or got.value == 0:
        return None
    return buf.raw[: got.value]


def _ptr(raw, off):
    return int.from_bytes(raw[off:off + 8], "little")


def read_engine_env(pid):
    """The live process's own environment as {NAME: value}, or None.

    Read-only: OpenProcess(QUERY_INFORMATION|VM_READ) + ReadProcessMemory.
    """
    if os.name != "nt" or not pid:
        return None
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, int(pid))
    if not h:
        return None
    try:
        pbi = _PROCESS_BASIC_INFORMATION()
        status = ctypes.windll.ntdll.NtQueryInformationProcess(
            h, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None)
        if status != 0 or not pbi.PebBaseAddress:
            return None
        peb = _read_mem(h, pbi.PebBaseAddress, 0x100)
        if not peb or len(peb) < _PEB_PROCESS_PARAMETERS + 8:
            return None
        rupp_addr = _ptr(peb, _PEB_PROCESS_PARAMETERS)
        if not rupp_addr:
            return None
        rupp = _read_mem(h, rupp_addr, _RUPP_ENVIRONMENT_SIZE + 8)
        if not rupp or len(rupp) < _RUPP_ENVIRONMENT + 8:
            return None
        env_addr = _ptr(rupp, _RUPP_ENVIRONMENT)
        if not env_addr:
            return None
        size = 0
        if len(rupp) >= _RUPP_ENVIRONMENT_SIZE + 8:
            size = _ptr(rupp, _RUPP_ENVIRONMENT_SIZE)
        if not (0 < size <= _MAX_ENV_BYTES):
            size = 64 * 1024          # honest fallback: read a block, stop at \0\0
        raw = _read_mem(h, env_addr, size)
        if not raw:
            return None
        try:
            text = raw.decode("utf-16-le", errors="ignore")
        except Exception:
            return None
        env = {}
        for entry in text.split("\x00"):
            if not entry:
                continue
            if "=" in entry[1:]:
                name, _, value = entry.partition("=")
                if name:
                    env[name.upper()] = value
        return env or None
    except Exception:
        return None
    finally:
        try:
            k32.CloseHandle(h)
        except Exception:
            pass


# ── the decoder's own health, measured ───────────────────────────────────────

_token_cache = [None]


def get_token():
    if _token_cache[0] is not None:
        return _token_cache[0]
    tok = os.environ.get("KESHEV_STT_TOKEN", "").strip()
    if not tok:
        try:
            with open(TOKEN_FILE, encoding="utf-8") as fh:
                tok = fh.read().strip()
        except OSError:
            tok = ""
    _token_cache[0] = tok
    return tok


def health_url(transcribe_url):
    """/health lives beside /v1/transcribe (same derivation as decoder.py)."""
    marker = "/v1/transcribe"
    if transcribe_url.endswith(marker):
        return transcribe_url[: -len(marker)] + "/health"
    return transcribe_url.rsplit("/", 1)[0] + "/health"


def probe_health(transcribe_url, timeout=3.0):
    """Measured health of the server the ENGINE is using.

    Returns {'state', 'http', 'canary_age_s', 'model', 'version', 'p50', 'error'}.
    'state' is UNREACHABLE when we could not ask -- never an optimistic guess.
    """
    out = {"state": "UNREACHABLE", "http": 0, "canary_age_s": None,
           "model": "", "version": "", "p50": None, "error": "", "at": time.time()}
    if not transcribe_url:
        out["error"] = "no url"
        return out
    req = urllib.request.Request(
        health_url(transcribe_url),
        headers={"Authorization": "Bearer " + get_token()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out["http"] = r.status
            body = r.read(65536)
    except urllib.error.HTTPError as exc:
        out["http"] = exc.code
        try:
            body = exc.read(65536)
        except Exception:
            body = b""
        if exc.code not in (200, 503):
            out["error"] = f"HTTP {exc.code}"
            return out
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        out["error"] = type(exc).__name__
        return out
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        out["state"] = "READY" if out["http"] == 200 else "LOADING"
        return out
    out["state"] = str(data.get("state") or ("READY" if out["http"] == 200 else "LOADING"))
    ca = data.get("canary_age_s")
    out["canary_age_s"] = float(ca) if isinstance(ca, (int, float)) else None
    models = data.get("models") or []
    out["model"] = str(models[0]) if models else ""
    out["version"] = str(data.get("version") or "")
    p50 = data.get("decode_p50_ms")
    out["p50"] = float(p50) if isinstance(p50, (int, float)) else None
    return out


# ── naming a server so a downgrade cannot hide ───────────────────────────────

def short_tag(url):
    """A tag Iddo can read at a glance: 8738 / PC-8737 / eran1 / host:port.

    2026-09-05: eran1 gained :8739, which runs the SAME good model :8738 runs
    (ivrit-ai/whisper-large-v3-turbo-ct2), on the DGX instead of his own GPU.
    It is named KESHEV 6 too, because the only thing that must never be confused
    here is WHICH MODEL is reading him -- the box is the small print.
    """
    if not url:
        return "?"
    m = re.search(r"//([^/:]+)(?::(\d+))?", url)
    if not m:
        return url[:18]
    host, port = m.group(1), m.group(2) or "80"
    if host in ("127.0.0.1", "localhost", "::1"):
        return "KESHEV 6 (8738)" if port == "8738" else f"PC {port}"
    if host == "<lan-ip>":
        return "KESHEV 6 (eran1)" if port == "8739" else f"eran1 {port}"
    if host == "<lan-ip>":   # 2026-09-15: eran2:8739 is the primary now
        return "KESHEV 6 (eran2)" if port == "8739" else f"eran2 {port}"
    return f"{host}:{port}"


# The two ports that serve the GOOD model (KESHEV 6, ivrit turbo):
#   8738 = this PC's GPU,  8739 = eran1's GB10.
# Same weights, same prompt, same repair map -- measured identical on 208 of his
# own segments, 2026-09-05. The badge shows "6" for either, because for Iddo the
# question the badge answers is "am I on the good model", not "which box".
KESHEV6_PORTS = ("8738", "8739")


def is_keshev6(url):
    return bool(url) and any(p in url for p in KESHEV6_PORTS)
