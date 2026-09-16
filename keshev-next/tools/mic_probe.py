r"""mic_probe -- one line that says whether Iddo's microphone chain is REALLY alive.

🪟 BROKEN WINDOWS LAW: test the REAL output, not a proxy. Every link below is
measured from the thing that enforces it (a live pid, a fresh mtime, an HTTP
/health with the real token, the engine's own log lines), never from a config
file that merely declares it.

READ-ONLY. It never opens an audio device, never starts, stops, pauses or
resumes anything, never writes inside keshev-next\. Stdlib only, so the thing
it probes cannot break it.

The chain it walks (one verdict per link):
  1 AUDIO     the engine's own "[mic] heartbeat: N blocks" line -- ~936/min is a
              live BRIO; 0-40 is a starved/dead device; none = no engine
  2 ENGINE    state\mic.pid alive, gui6 window alive, gui.heartbeat age
  3 DECODER   /health of the URL the launcher handed the engine (+ fallback),
              plus the PC's own :8737/:8738 so a dead rescue path is visible
  4 DELIVERY  the last decode=ok line, [typer] refusals, and whether the window
              that has the focus RIGHT NOW would silently eat SendInput (UIPI)
  5 PAUSE     state\PAUSED: signed (who/why/at) or orphan, and its age
  6 WATCHDOG  the delivery watchdog process and its last verdict line

Run:
    python tools\mic_probe.py            # one human line + a table
    python tools\mic_probe.py --json     # machine-readable
Exit code 0 = every link green, 1 = something is red, 2 = probe itself failed.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# 2026-09-12: the summary line carries Hebrew and this tool died on cp1252 mid-print
# (mistake ledger rule 3). Force UTF-8 on the console regardless of the code page.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
TRIAL = os.path.join(ROOT, "trial.log")
MIC_PID = os.path.join(STATE, "mic.pid")
GUI_PID = os.path.join(STATE, "gui6.pid")
HEARTBEAT = os.path.join(STATE, "gui.heartbeat")
PAUSED = os.path.join(STATE, "PAUSED")
ENV_CMD = os.path.join(STATE, "keshev6-env.cmd")
DECODER_JSON = os.path.join(STATE, "decoder.json")
TOKEN_FILE = r"D:\CLAUDE\mic-rebuild\state\stt-token"
WATCHDOG_JSON = r"D:\CLAUDE\tools\watchdogs\keshev-delivery.json"


def configure(root=None, state=None, trial=None):
    r"""Point the probe at a DECOY tree instead of the live microphone.

    2026-09-11, for tools\keshev_guard.py. A supervisor that restarts things has
    to be exercised against fabricated deaths BEFORE it is allowed near the real
    engine -- "never test a safety gate on a living system" (the law, and the
    reason this takes a decoy dir at all rather than a --pretend flag).
    """
    global ROOT, STATE, TRIAL, MIC_PID, GUI_PID, HEARTBEAT, PAUSED, ENV_CMD, DECODER_JSON
    if root:
        ROOT = os.path.abspath(root)
        STATE = os.path.join(ROOT, "state")
        TRIAL = os.path.join(ROOT, "trial.log")
    if state:
        STATE = os.path.abspath(state)
    if trial:
        TRIAL = os.path.abspath(trial)
    MIC_PID = os.path.join(STATE, "mic.pid")
    GUI_PID = os.path.join(STATE, "gui6.pid")
    HEARTBEAT = os.path.join(STATE, "gui.heartbeat")
    PAUSED = os.path.join(STATE, "PAUSED")
    ENV_CMD = os.path.join(STATE, "keshev6-env.cmd")
    DECODER_JSON = os.path.join(STATE, "decoder.json")

TAIL_BYTES = 400_000
HTTP_TIMEOUT = 3.0

_k32 = ctypes.windll.kernel32
_u32 = ctypes.windll.user32
_adv = ctypes.windll.advapi32

# argtypes/restype on every Win32 call we make: a 64-bit HANDLE truncated to a
# C int is the exact "int too long to convert" / silent-no-op class of bug that
# bit SetPriorityClass on 2026-09-07 (feedback_sign_the_pause_20260907).
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.WaitForSingleObject.restype = wintypes.DWORD
_adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
_adv.OpenProcessToken.restype = wintypes.BOOL
_adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
_adv.GetTokenInformation.restype = wintypes.BOOL
_adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
_adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
_adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
_adv.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
_u32.GetForegroundWindow.argtypes = []
_u32.GetForegroundWindow.restype = wintypes.HWND
_u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u32.GetWindowThreadProcessId.restype = wintypes.DWORD
_u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_u32.GetWindowTextLengthW.restype = ctypes.c_int
_u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u32.GetWindowTextW.restype = ctypes.c_int


# ------------------------------------------------------------------ helpers
def _read(path, n=4000):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(n)
    except OSError:
        return ""


def _age_min(path):
    try:
        return (time.time() - os.path.getmtime(path)) / 60.0
    except OSError:
        return None


def _pid_alive(pid):
    if not pid:
        return False
    SYNCHRONIZE = 0x00100000
    h = _k32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not h:
        return False
    try:
        return _k32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT = alive
    finally:
        _k32.CloseHandle(h)


def _pid_from(path):
    try:
        return int(_read(path, 32).strip() or 0)
    except ValueError:
        return 0


# 2026-09-11: the engine now stamps every line with HH:MM:SS (app/logstamp.py).
# Strip it before the startswith() tests below -- and KEEP it, because "when did
# the last word arrive" is the question this whole night was about.
_TS_RE = re.compile(r"^(\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s")


def _unstamp(line):
    m = _TS_RE.match(line)
    return (m.group(1), line[m.end():]) if m else ("", line)


def _tail_lines(path):
    """[(HH:MM:SS or '', line-without-stamp), ...] from the end of the file."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - TAIL_BYTES))
            data = fh.read()
        return [_unstamp(ln) for ln in data.decode("utf-8", "replace").splitlines()]
    except OSError:
        return []


def _token():
    t = os.environ.get("KESHEV_STT_TOKEN", "").strip()
    return t or _read(TOKEN_FILE, 200).strip()


def _health(url_transcribe):
    """(state, http, detail) for a /v1/transcribe URL's sibling /health."""
    marker = "/v1/transcribe"
    base = url_transcribe[: -len(marker)] if url_transcribe.endswith(marker) else url_transcribe.rsplit("/", 1)[0]
    req = urllib.request.Request(base + "/health", headers={"Authorization": "Bearer " + _token()})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            body = r.read(2000).decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        code, body = e.code, ""
    except Exception as e:  # unreachable, refused, timeout
        return "UNREACHABLE", 0, type(e).__name__
    ms = int((time.monotonic() - t0) * 1000)
    try:
        j = json.loads(body) if body else {}
    except ValueError:
        j = {}
    state = str(j.get("state", "READY" if code == 200 else ("LOADING" if code == 503 else "HTTP%d" % code)))
    extra = ""
    if j.get("canary_stale") is True:
        extra = " canary_STALE"
    return state, code, "%d ms%s" % (ms, extra)


def _env_urls():
    r"""(primary, fallback, last_resort) -- the doors the engine would use NOW.

    2026-09-11: state\decoder.json is the runtime truth (app/decoder.py re-reads
    it per segment); state\keshev6-env.cmd is only what the launcher decided.
    Ask the file the engine actually obeys, and fall back to the launcher's
    fragment when it is not there.
    """
    try:
        j = json.loads(_read(DECODER_JSON, 8000) or "{}")
        if j.get("primary"):
            return (j.get("primary", ""), j.get("fallback", ""), j.get("last_resort", ""))
    except ValueError:
        pass
    txt = _read(ENV_CMD)
    prim = re.search(r"KESHEV_STT_URL=(\S+)", txt)
    fb = re.search(r"KESHEV_STT_FALLBACK_URL=(\S+)", txt)
    return (prim.group(1) if prim else "", fb.group(1) if fb else "", "")


# ------------------------------------------------------------- integrity
def _process_integrity(pid):
    """MEDIUM / HIGH / SYSTEM / LOW / DENIED / UNKNOWN -- read-only token query."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TOKEN_QUERY = 0x0008
    TokenIntegrityLevel = 25
    h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return "DENIED"
    tok = wintypes.HANDLE()
    try:
        if not _adv.OpenProcessToken(h, TOKEN_QUERY, ctypes.byref(tok)):
            return "DENIED"
        need = wintypes.DWORD()
        _adv.GetTokenInformation(tok, TokenIntegrityLevel, None, 0, ctypes.byref(need))
        buf = ctypes.create_string_buffer(need.value)
        if not _adv.GetTokenInformation(tok, TokenIntegrityLevel, buf, need, ctypes.byref(need)):
            return "UNKNOWN"
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_MANDATORY_LABEL.Label.Sid
        cnt = _adv.GetSidSubAuthorityCount(sid)[0]
        rid = _adv.GetSidSubAuthority(sid, cnt - 1)[0]
        if rid >= 0x4000:
            return "SYSTEM"
        if rid >= 0x3000:
            return "HIGH"
        if rid >= 0x2000:
            return "MEDIUM"
        return "LOW"
    finally:
        if tok:
            _k32.CloseHandle(tok)
        _k32.CloseHandle(h)


def _foreground():
    hwnd = _u32.GetForegroundWindow()
    if not hwnd:
        return {"hwnd": 0, "pid": 0, "title": "", "integrity": "NONE"}
    pid = wintypes.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    n = _u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    _u32.GetWindowTextW(hwnd, buf, n + 1)
    return {"hwnd": int(hwnd), "pid": int(pid.value), "title": buf.value[:60],
            "integrity": _process_integrity(pid.value) if pid.value else "UNKNOWN"}


def _outbox_pending():
    """How many sentences the typer could not deliver are still being retried."""
    n = 0
    try:
        with io.open(os.path.join(STATE, "outbox.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    n += 1
    except OSError:
        return 0
    return n


# The CIM query below costs ~1 s and spawns a PowerShell. keshev_guard calls
# probe() every 30 s forever, so remember the pid: a live pid is confirmed with
# one OpenProcess, and PowerShell is only paid for when the watchdog is gone.
_watchdog_pid_hint = 0


def _watchdog_process():
    """Is keshev_delivery_watchdog.py running? (CIM query, ~1 s, read-only)."""
    global _watchdog_pid_hint
    if _watchdog_pid_hint and _pid_alive(_watchdog_pid_hint):
        return _watchdog_pid_hint
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'keshev_delivery_watchdog' } | "
             "Select-Object -First 1 -ExpandProperty ProcessId)"],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pid = out.stdout.strip()
        _watchdog_pid_hint = int(pid) if pid.isdigit() else 0
        return _watchdog_pid_hint
    except Exception:
        return -1


# ---------------------------------------------------------------- the walk
def probe():
    r = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "links": {}}
    L = r["links"]

    # 2 ENGINE ------------------------------------------------------------
    mic_pid, gui_pid = _pid_from(MIC_PID), _pid_from(GUI_PID)
    hb_age = _age_min(HEARTBEAT)
    eng = {"mic_pid": mic_pid, "mic_alive": _pid_alive(mic_pid),
           "gui_pid": gui_pid, "gui_alive": _pid_alive(gui_pid),
           # gui6.on_close() REMOVES gui6.pid and mic.pid. So a missing pid file
           # means "Iddo closed the window", and a pid file holding a dead pid
           # means "it died on its own". Those are opposite facts and the guard
           # must never confuse them: restarting the first one fights him.
           "gui_pid_file_present": os.path.exists(GUI_PID),
           "mic_pid_file_present": os.path.exists(MIC_PID),
           "heartbeat_age_min": None if hb_age is None else round(hb_age, 1),
           "trial_log_age_min": None if _age_min(TRIAL) is None else round(_age_min(TRIAL), 1)}
    eng["ok"] = eng["mic_alive"] and eng["gui_alive"] and hb_age is not None and hb_age < 1.0
    L["engine"] = eng

    # 1 AUDIO (from the engine's own heartbeat line) ------------------------
    stamped = _tail_lines(TRIAL)
    lines = [ln for _at, ln in stamped]
    hb = [ln for ln in lines if ln.startswith("[mic] heartbeat:")]
    deaf = [ln for ln in lines if ln.startswith("[mic] DEAF")]
    dev = [ln for ln in lines if ln.startswith("[mic] device=")]
    au = {"blocks_per_min": None, "peak_rms": None, "device": "", "deaf_lines_in_tail": len(deaf)}
    if hb:
        m = re.search(r"heartbeat: (\d+) blocks, peak RMS (\d+)", hb[-1])
        if m:
            au["blocks_per_min"], au["peak_rms"] = int(m.group(1)), int(m.group(2))
    if dev:
        m = re.search(r"device='([^']+)' \[([^\]]+)\]", dev[-1])
        au["device"] = ("%s [%s]" % (m.group(1), m.group(2))) if m else dev[-1][:80]
    b = au["blocks_per_min"]
    au["ok"] = eng["mic_alive"] and b is not None and b >= 600
    au["clipping"] = (au["peak_rms"] or 0) > 10000
    L["audio"] = au

    # 3 DECODER -----------------------------------------------------------
    prim, fb, last = _env_urls()
    dec = {"primary_url": prim, "fallback_url": fb, "last_resort_url": last}
    for key, url in (("primary", prim), ("fallback", fb),
                     ("pc_8737", "http://127.0.0.1:8737/v1/transcribe"),
                     ("pc_8738", "http://127.0.0.1:8738/v1/transcribe")):
        if url:
            st, code, det = _health(url)
            dec[key] = {"state": st, "http": code, "detail": det}
    dec["ok"] = bool(prim) and dec.get("primary", {}).get("state") == "READY"
    dec["any_ready"] = any(dec.get(k, {}).get("state") == "READY" for k in ("primary", "fallback", "pc_8737", "pc_8738"))
    L["decoder"] = dec

    # 4 DELIVERY ----------------------------------------------------------
    ok_lines = [(at, ln) for at, ln in stamped if " decode=ok " in ln]
    refused = [ln for ln in lines if ln.startswith("[typer] refused") or "BLOCKED admin-window" in ln]
    # 2026-09-11: the outbox is the honest end of the delivery story -- a refusal
    # that was later retried into a window that took it, or DROPPED out loud.
    outbox_q = [ln for ln in lines if ln.startswith("[outbox] queued")]
    outbox_d = [ln for ln in lines if ln.startswith("[outbox] delivered")]
    outbox_x = [ln for ln in lines if ln.startswith("[outbox] DROPPED")]
    fg = _foreground()
    dl = {"last_decode_ok": ok_lines[-1][1][-90:] if ok_lines else "",
          # THE question trial.log could not answer before tonight.
          "last_word_at": ok_lines[-1][0] if ok_lines else "",
          "decode_ok_in_tail": len(ok_lines), "typer_refusals_in_tail": len(refused),
          "outbox_queued": len(outbox_q), "outbox_delivered": len(outbox_d),
          "outbox_dropped": len(outbox_x),
          "outbox_pending": _outbox_pending(),
          "foreground": fg}
    dl["focus_would_eat_keys"] = fg["integrity"] in ("HIGH", "SYSTEM", "DENIED")
    dl["ok"] = not dl["focus_would_eat_keys"]
    L["delivery"] = dl

    # 5 PAUSE -------------------------------------------------------------
    pz = {"paused": os.path.exists(PAUSED)}
    if pz["paused"]:
        body = _read(PAUSED)
        try:
            j = json.loads(body)
        except ValueError:
            j = {}
        pz.update({"who": j.get("who", ""), "at": j.get("at", ""),
                   "signed": bool(j.get("who")) and bool(j.get("why")),
                   "age_min": round(_age_min(PAUSED) or 0, 1)})
        pz["by_iddo"] = "iddo" in str(pz.get("who", "")).lower()
    pz["ok"] = (not pz["paused"]) or pz.get("signed", False)
    L["pause"] = pz

    # 6 WATCHDOG ----------------------------------------------------------
    wd_pid = _watchdog_process()
    wj = {}
    try:
        wj = json.loads(_read(WATCHDOG_JSON, 20000) or "{}")
    except ValueError:
        pass
    wd = {"pid": wd_pid, "alive": wd_pid > 0, "last_verdict": wj.get("verdict", ""),
          "last_iso": wj.get("iso", ""), "alarms": wj.get("alarms", []),
          "last_typed_text": wj.get("last_typed_text", "")}
    wd["ok"] = wd["alive"]
    L["watchdog"] = wd

    # verdict -------------------------------------------------------------
    red = [k for k, v in L.items() if not v.get("ok")]
    if pz["paused"] and pz.get("by_iddo"):
        # his own pause is not a fault; audio/delivery are expected quiet
        red = [k for k in red if k not in ("delivery",)]
    r["red"] = red
    r["verdict"] = "GREEN" if not red else "RED"
    return r


def one_line(r):
    L = r["links"]
    au, eng, dec, dl, pz, wd = (L[k] for k in ("audio", "engine", "decoder", "delivery", "pause", "watchdog"))
    parts = [
        "MIC %s" % r["verdict"],
        "audio=%s/min rms=%s%s" % (au["blocks_per_min"], au["peak_rms"], " CLIP" if au["clipping"] else ""),
        "engine=%s hb=%smin" % ("up" if eng["mic_alive"] else "DOWN", eng["heartbeat_age_min"]),
        "stt=%s(%s) fb=%s pc8738=%s" % (
            dec.get("primary", {}).get("state", "-"), (dec.get("primary_url") or "-").split("//")[-1].split("/")[0],
            dec.get("fallback", {}).get("state", "-"), dec.get("pc_8738", {}).get("state", "-")),
        "focus=%s/%s" % (dl["foreground"]["integrity"], (dl["foreground"]["title"] or "?")[:24]),
        "lastword=%s" % (dl.get("last_word_at") or "-"),
        "outbox=%d" % dl.get("outbox_pending", 0),
        "pause=%s" % ("no" if not pz["paused"] else ("iddo %smin" % pz.get("age_min") if pz.get("by_iddo")
                                                     else ("signed:%s" % pz.get("who", "?")[:18] if pz.get("signed") else "ORPHAN"))),
        "watchdog=%s/%s" % ("up" if wd["alive"] else "DOWN", wd["last_verdict"] or "-"),
    ]
    if r["red"]:
        parts.append("RED:" + ",".join(r["red"]))
    return "  ".join(parts)


def main(argv):
    try:
        r = probe()
    except Exception as exc:
        print("mic_probe FAILED: %s: %s" % (type(exc).__name__, exc))
        return 2
    if "--json" in argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(one_line(r))
        if "--quiet" not in argv:
            for k, v in r["links"].items():
                print("  %-9s %s  %s" % (k, "ok " if v.get("ok") else "RED",
                                         json.dumps({a: b for a, b in v.items() if a != "ok"}, ensure_ascii=False)[:300]))
    return 0 if r["verdict"] == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
