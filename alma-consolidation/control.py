#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
CONTROL page of Iddo's private master dashboard (private_hub.py, :8896).
Iddo's order 2026-09-08 10:40: "שליטה מלאה בהכל מרחוק" -- full control of everything, remotely.

100% stdlib. Reads state files; never touches keshev-next\app (the live mic code).

What it can do -- and the whole list, by construction (ACTIONS below):
  keshev.pause   write the SIGNED state\PAUSED (who/why/at/expires/restore/disables) atomically,
                 the exact shape app\gui.py toggle_pause() writes, so the delivery watchdog's
                 looks_like_receipt guard treats it as a HUMAN pause and leaves it alone.
  keshev.listen  lift it: receipt written BESIDE the file, then PAUSED removed.
  start.keshev   the KESHEV window via RUN-KESHEV.cmd -- refused if a window/engine is alive (ONE-MIC).
  start.cockpit  START-COCKPIT-HEADLESS.cmd -- refused if :8790 already answers.
  start.portal   alma-vr\portal\portal.py (:8899) -- refused if :8899 already answers.

What it can NOT do, on purpose: there is no endpoint that starts, stops or restarts ERAN
(eran1 eranb-life), DARWISH (eran4 dmidi-life) or any fleet service. Not "blocked" -- absent.

Every action appends one line to control-audit.jsonl (ts, who, action, result, detail).

Decoy mode: STATE_DIR is overridable (env MASTER_DASH_KESHEV_STATE, or private_hub.py
--demo-decoy <dir>) so the gate is demonstrated on a temp directory, never on the live mic
(feedback_never_test_safety_on_a_living_system).
"""
from __future__ import annotations

import ctypes
import html
import io
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import fleet_models          # 2026-09-09: the MODEL LEDGER + the two FLEET MODES (Iddo 23:44-23:49)
import one_place             # 2026-09-11 (WAVE B3): devices + models + chat + work queue

# Per-process CSRF token, the pattern remote_claude_gateway.py :8941 uses. The page
# embeds it; a POST to /control/api/ask or /control/api/queue without the matching
# X-CSRF-Token header is refused even if the cookie and the key are both right.
CSRF = secrets.token_urlsafe(32)

BASE = r"D:\CLAUDE\alma-consolidation"
AUDIT = os.path.join(BASE, "control-audit.jsonl")
KESHEV_ROOT = r"D:\CLAUDE\keshev-next"
LIVE_STATE_DIR = os.path.join(KESHEV_ROOT, "state")
STATE_DIR = os.environ.get("MASTER_DASH_KESHEV_STATE") or LIVE_STATE_DIR
TRIAL_LOG = os.path.join(KESHEV_ROOT, "trial.log")
RUN_KESHEV = os.path.join(KESHEV_ROOT, "RUN-KESHEV.cmd")
COCKPIT_CMD = r"D:\CLAUDE\almaware-cockpit\START-COCKPIT-HEADLESS.cmd"
PORTAL_PY = r"D:\CLAUDE\alma-vr\portal\portal.py"
PYW312 = r"C:\Program Files\Python312\pythonw.exe"
STATUS_JSON = r"D:\CLAUDE\almaware-hud\status.json"
COLLECTOR_PID = r"D:\CLAUDE\almaware-hud\collector.pid"
RAMCHAT_SESSION = r"D:\CLAUDE\RAMCHAT\ramchat_session.json"
# --------------------------------------------------------------------------
# ADDRESSES COME FROM ONE PLACE (2026-09-11, WAVE A2 address sweep).
# D:\CLAUDE\fleet_inventory.json is measured, dated and re-measurable
# (`python D:\CLAUDE\fleet_inventory.py --refresh`). Constants below are the
# offline fallback, not the source of truth.
# --------------------------------------------------------------------------
sys.path.insert(0, r"D:\CLAUDE")
try:
    import fleet_inventory as _fi
except Exception:                                             # noqa: BLE001
    _fi = None


def _door(name: str, fallback: str) -> str:
    if _fi is None:
        return fallback
    try:
        return _fi.door(name)
    except Exception:                                         # noqa: BLE001
        return fallback


TAILNET_HOST = (_fi.load()["tailnet"]["domain"] if _fi else None) and \
    _fi.load()["tailnet"]["root"].replace("https://", "") or "<tailnet-host>"
PC_TAILNET_IP = (_fi.ip("pc", "tailnet") if _fi else None) or "<tailnet-ip>"

WHO = "iddo (master dashboard)"
_NOWIN = 0x08000000          # CREATE_NO_WINDOW -- a windowless parent must never pop a console
BELOW_NORMAL = 0x00004000    # BELOW_NORMAL_PRIORITY_CLASS -- the PC is the mic's machine
HEARTBEAT_FRESH_S = 30       # gui writes every 8 s; the engine's dead-man fires at 30 s
STILL_ACTIVE = 259

# ---------------------------------------------------------------------------- doors
# (id, icon, name, probe_url, local_url, tailnet_url or None, what)
# green/red comes from the PROBE at page time, never from this list.
DOORS = [
    ("cockpit", "🖥️", "ALMAWARE COCKPIT", "http://127.0.0.1:8790/", "http://127.0.0.1:8790/", None, "fleet HUD · status.json"),
    ("phonemic", "📱", "PHONE MIC", "http://127.0.0.1:8893/", "http://127.0.0.1:8893/", f"https://{TAILNET_HOST}:8893/", "the phone as the microphone"),
    ("galeria", "🎨", "GALERIA", "http://127.0.0.1:8861/", "http://127.0.0.1:8861/", None, "every model's real outputs"),
    ("makom", "🏠", "MAKOM", "http://127.0.0.1:8858/", "http://127.0.0.1:8858/", None, "מקום · one place"),
    ("portal", "🥽", "QUEST PORTAL", "http://127.0.0.1:8899/", "http://127.0.0.1:8899/", f"http://{PC_TAILNET_IP}:8899/", "the wall of tiles in the headset"),
    # RETIRED 2026-09-11 (holy harness law): the three eran4 coder tiles -- QWEN CODER :8447,
    # ALMA TWIN :8448, GLM CODER :8449 -- were archived to F:/ALMAWARE-ARCHIVE/HARNESSES-20260911
    # (eran4-qwen-coder-ui-8447, eran4-twin-window-8448, eran4-glm-coder-8449; restore lines in
    # MANIFEST.md there). The one harness is ALMAWARE Coder, tailnet twin :8875.
    # RETIRED 2026-09-11: council.py :8910 has no listener, no launcher and no
    # caller anywhere in the tree. It was a permanently-red tile pretending to be
    # a door. The RAMCHAT transcript is rendered below this panel regardless.
    # See D:/CLAUDE/_deliverables/ecosystem/RETIRED-20260911.md to revive it.
    # 2026-09-11 (WAVE A2): all three URLs here were wrong. eranb-serve's window
    # is published by `tailscale serve` on eran1, so :8820 is bound on eran1's
    # TAILSCALE address only -- the LAN URL could never have answered, and the
    # bare-IP tailnet URL is refused by tailscaled (it wants the ts.net name).
    # Correct door from D:/CLAUDE/fleet_inventory.json. It reads 502 today:
    # eranb-serve crash-loops on "Address already in use" because serve.py binds
    # the tailnet IP that tailscale serve already holds. ERAN's box is read-only
    # to this sweep -- the one-line bind fix needs Iddo.
    ("eran-window", "🧬", "ERAN · window (read-only)", _door("eran_window", "https://<tailnet-host>:8820/"), _door("eran_window", "https://<tailnet-host>:8820/"), _door("eran_window", "https://<tailnet-host>:8820/"), "eran1 :8820 · observation only"),
    ("recall", "🔎", "ALMA-RECALL", "http://127.0.0.1:8794/", "http://127.0.0.1:8794/", None, "one search over all memory"),
    # RESTORED 2026-09-11 (WAVE A2): FLEET MODE was built 09-05/06, extended 09-08
    # with the TRAIN<->CODER switch, and then simply had no launcher -- it was not
    # running at all. Now autostarted by the task ALMA-FleetMode-8872. It binds
    # 127.0.0.1 AND the PC tailnet address itself (no `tailscale serve` in front).
    ("fleetmode", "🎛️", "FLEET MODE", "http://127.0.0.1:8872/", "http://127.0.0.1:8872/", "http://%s:8872/" % PC_TAILNET_IP, "switch what each DGX is running"),
]

_lock = threading.Lock()
_door_cache = {"at": 0.0, "rows": None}
_serve_cache = {"at": 0.0, "map": {}}


# ---------------------------------------------------------------------------- helpers
def set_below_normal():
    try:
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p          # pseudo-handle -1 must stay 64-bit
        k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        return bool(k.SetPriorityClass(k.GetCurrentProcess(), BELOW_NORMAL))
    except Exception:
        return False


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = ctypes.c_void_p
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    except Exception:
        return False


def _read(path, limit=4000):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return None


def _age(path):
    try:
        return round(time.time() - os.path.getmtime(path), 1)
    except OSError:
        return None


def port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(url, timeout=2.5):
    """One GET; returns (status_code_or_None, ms, error). 4xx counts as 'answers'."""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "master-dashboard-probe/1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, int((time.time() - t0) * 1000), None
    except urllib.error.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000), None
    except Exception as e:
        return None, int((time.time() - t0) * 1000), str(e)[:120]


def audit(action, result, detail=None, who=WHO, ip=None):
    row = {"ts": datetime.now().isoformat(timespec="seconds"), "who": who, "action": action,
           "result": result, "detail": detail, "ip": ip}
    try:
        with _lock, io.open(AUDIT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return row


one_place.wire(audit)     # one audit file, one lock -- one_place writes through ours


def tailscale_serve_map():
    """{local_port: https_url} from `tailscale serve status`, cached 60 s, no console."""
    now = time.time()
    if now - _serve_cache["at"] < 60 and _serve_cache["map"]:
        return _serve_cache["map"]
    m = {}
    try:
        out = subprocess.run(["tailscale", "serve", "status"], capture_output=True, text=True,
                             timeout=8, creationflags=_NOWIN).stdout
        cur = None
        for line in out.splitlines():
            h = re.match(r"^(https://\S+?)(?::(\d+))?\s", line)
            if h:
                cur = h.group(1) + (":" + h.group(2) if h.group(2) else "")
                continue
            p = re.search(r"proxy http://127\.0\.0\.1:(\d+)", line)
            if p and cur and re.search(r"\|--\s+/\s", line):
                m[int(p.group(1))] = cur + "/"
    except Exception:
        pass
    _serve_cache.update(at=now, map=m)
    return m


# ---------------------------------------------------------------------------- KESHEV state
def keshev_state():
    pause_file = os.path.join(STATE_DIR, "PAUSED")
    hb = os.path.join(STATE_DIR, "gui.heartbeat")
    micpid = os.path.join(STATE_DIR, "mic.pid")
    paused = os.path.exists(pause_file)
    pause_body = _read(pause_file) if paused else None
    pause_json = None
    if pause_body:
        try:
            pause_json = json.loads(pause_body)
        except ValueError:
            pause_json = None
    hb_age = _age(hb)
    window = hb_age is not None and hb_age <= HEARTBEAT_FRESH_S
    pid = (_read(micpid) or "").strip()
    engine = pid_alive(pid)
    log_age = _age(TRIAL_LOG)
    if paused:
        state = "paused"
    elif window and engine:
        state = "listening"
    elif window or engine:
        state = "half"
    else:
        state = "dead"
    return {
        "state": state, "paused": paused, "pause": pause_json, "pause_raw": pause_body,
        "pause_signed": bool(pause_body) and (all(k in pause_body for k in ("who", "why")) or "restore" in pause_body),
        "window": window, "heartbeat_age_s": hb_age, "engine": engine, "mic_pid": pid or None,
        "log_age_s": log_age, "state_dir": STATE_DIR, "decoy": STATE_DIR != LIVE_STATE_DIR,
    }


def keshev_pause(why=None, who=WHO):
    """Exactly app\\gui.py toggle_pause()'s shape, signed, atomic tmp+replace."""
    pause_file = os.path.join(STATE_DIR, "PAUSED")
    if os.path.exists(pause_file):
        return "already-paused", {"file": pause_file}
    os.makedirs(STATE_DIR, exist_ok=True)
    doc = {
        "who": who,
        "why": (why or "").strip() or "he pressed pause on the master dashboard -- the mic stays off until he presses listen",
        "at": datetime.now().isoformat(),
        "expires": None,
        "restore": "press listen on the master dashboard or in the KESHEV window, or delete state\\PAUSED",
        "disables": True,
    }
    tmp = pause_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, pause_file)      # never a half-written pause
    return "paused", {"file": pause_file, "json": doc}


def keshev_listen(who=WHO):
    """Lift the pause: receipt BESIDE the file (never on it), then remove PAUSED."""
    pause_file = os.path.join(STATE_DIR, "PAUSED")
    if not os.path.exists(pause_file):
        return "not-paused", {"file": pause_file}
    body = _read(pause_file) or ""
    try:
        doc = json.loads(body)
        if not isinstance(doc, dict):
            doc = {"raw": body}
    except ValueError:
        doc = {"raw": body}
    doc["lifted_at"] = datetime.now().isoformat()
    doc["lifted_by"] = who
    receipt = pause_file + ".receipt-lifted-by-dashboard-" + time.strftime("%Y%m%d-%H%M")
    tmp = receipt + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, receipt)
    os.remove(pause_file)
    return "listening", {"receipt": receipt, "removed": pause_file}


# ---------------------------------------------------------------------------- starts (safe only)
def start_keshev():
    st = keshev_state()
    if st["window"] or st["engine"]:
        return "refused", {"reason": "ONE-MIC: a KESHEV window/engine is already alive",
                           "heartbeat_age_s": st["heartbeat_age_s"], "mic_pid": st["mic_pid"]}
    if not os.path.isfile(RUN_KESHEV):
        return "error", {"reason": "RUN-KESHEV.cmd missing"}
    # the .cmd itself gets no console; its `start ""` opens the window exactly as a double-click does.
    # NOT below-normal: the microphone outranks everything on this PC.
    subprocess.Popen(["cmd.exe", "/c", RUN_KESHEV], cwd=KESHEV_ROOT, creationflags=_NOWIN,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "started", {"cmd": RUN_KESHEV}


def start_cockpit():
    if port_open("127.0.0.1", 8790):
        return "refused", {"reason": ":8790 already answers"}
    if not os.path.isfile(COCKPIT_CMD):
        return "error", {"reason": "START-COCKPIT-HEADLESS.cmd missing"}
    subprocess.Popen(["cmd.exe", "/c", COCKPIT_CMD], cwd=os.path.dirname(COCKPIT_CMD),
                     creationflags=_NOWIN | BELOW_NORMAL,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "started", {"cmd": COCKPIT_CMD}


def start_portal():
    if port_open("127.0.0.1", 8899):
        return "refused", {"reason": ":8899 already answers"}
    if not os.path.isfile(PORTAL_PY):
        return "error", {"reason": "portal.py missing"}
    py = PYW312 if os.path.isfile(PYW312) else sys.executable
    subprocess.Popen([py, PORTAL_PY], cwd=os.path.dirname(PORTAL_PY),
                     creationflags=_NOWIN | BELOW_NORMAL,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "started", {"py": py, "script": PORTAL_PY}


# ============================================================================ FLEET (2026-09-08)
# Iddo's order 18:18: "תסדר לי את הדשבורד שאני יכול בלחיצת כפתור להחליט מה קורה עם הצי"
# -- one-button fleet control for eran2/eran3/eran4 ONLY.
#
# eran1 (ERAN, eranb-life.service) and DARWISH (eran4 dmidi-life.service + dmidi-tap.service)
# are Ark-protected (project_handoff_20260905.md "THE ARK / תיבת נוח": permanently-living,
# measured well under 1 GB resident, never stopped). THEY GET NO BUTTON, NO ACTION, NO
# ENDPOINT HERE. By construction: every SSH target below is one of the three literal strings
# in FLEET_ALIASES, matched with `assert alias in FLEET_ALIASES` before any subprocess call --
# eran1 is not a member of that tuple and does not appear as a string anywhere in this
# module's actionable (SSH/subprocess) path. There is no function here that takes a hostname
# from the request body; every ACTIONS entry below calls a zero-argument wrapper with its
# target baked into the Python source.
FLEET_ALIASES = ("eran2", "eran3", "eran4")           # PC ~/.ssh/config aliases -- verified working directly 2026-09-08 18:2x
Q480_HEALTH_URL = "https://<tailnet-host>:8443/health"
Q480_COMPLETIONS_URL = "https://<tailnet-host>:8443/v1/completions"
# eran2, unmodified proven scripts -- this module NEVER rewrites or replaces them.
# 2026-09-08 18:2x: verified live serve.sh in the container was patched v3(Bearer)->v4(no-auth)
# by hand after Iddo's 18:13 order. 18:3x, mid-build of THIS panel: a second, concurrent
# session (claude-cli-FABLE-480b, RAMCHAT 18:29/18:3x) shipped qwen480-pp-up-v5.sh -- an
# unmodified copy of up-v3.sh whose only diff (`diff` run 18:3x) is the docker-cp line: it
# installs qwen480-serve-v5.sh (adds --enable-auto-tool-choice --tool-call-parser qwen3_coder
# for ALMIDO; header confirms "No password (Iddo's order 18:13)") DIRECTLY, no swap-after
# needed. Re-verified live in the running container 18:3x. Using v5 here, not v3+manual-swap:
# it is simpler, it is what the fleet is actually running right now, and it was proven by
# someone else's real launch minutes before this line was written -- the definition of
# "the exact script that is live", per this task's own instruction.
Q480_UP_SCRIPT = "~/qwen480-pp-up-v6-stable.sh"        # 2026-09-08 21:4x: v5's tool-calling flags broke ("500 cannot import
                                                        # name normalize_tool_choice from xgrammar", matches the 08-21 xgrammar
                                                        # scar in project_qwen480_pipeline.md). v6 = the up-v3.sh clean-rebuild
                                                        # recipe + no-auth serve WITHOUT tool-calling flags -- proven stable.
Q480_DOWN_SCRIPT = "~/qwen480-pp-down-v2.sh"           # verified 2026-09-08: "qwen480-pp-down.sh" (no -v2) does NOT exist on eran2; this is the current down script -- docker rm -f qwen480-pp on eran2+eran3+eran4
_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=2"]

_fleet3_cache = {a: {"at": 0.0, "data": None} for a in FLEET_ALIASES}
_q480_cache = {"at": 0.0, "data": None}
_bg_lock = threading.Lock()
_bg_state = {"480b_start": None}   # None, or {"at","phase","log"} while/after a background bring-up


def _ssh_fleet(alias, remote_cmd, timeout=20):
    """One SSH call to a HARDCODED fleet alias -- never accept `alias` from a request body."""
    assert alias in FLEET_ALIASES, "refusing: %r is not an allowed fleet alias" % (alias,)
    cmd = ["ssh"] + _SSH_OPTS + [alias, remote_cmd]
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, creationflags=_NOWIN, text=True, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "ssh timeout after %ss" % timeout
    except Exception as e:
        return 1, "", str(e)[:200]


_PROBE_CMD = (
    "free -g; echo ---GPU---; "
    "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>&1; "
    "echo ---DOCKER---; docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}' 2>&1"
)


def _parse_fleet3(rc, out, err):
    if rc != 0 and not out.strip():
        return {"reachable": False, "error": (err or ("ssh rc=%d" % rc))[:200]}
    mem, gpu, docker, section = {}, [], [], "mem"
    for line in out.splitlines():
        s = line.strip()
        if s == "---GPU---":
            section = "gpu"; continue
        if s == "---DOCKER---":
            section = "docker"; continue
        if section == "mem" and line.startswith("Mem:"):
            p = line.split()
            if len(p) >= 7:
                mem = {"total_gb": int(p[1]), "used_gb": int(p[2]), "free_gb": int(p[3]),
                      "buffcache_gb": int(p[5]), "avail_gb": int(p[6])}
        elif section == "gpu" and s and "," in s:
            f = [x.strip() for x in s.split(",")]
            if len(f) >= 3:
                gpu.append({"pid": f[0], "process": f[1], "used": f[2]})
        elif section == "docker" and s and "|" in s:
            f = s.split("|")
            if len(f) >= 3:
                docker.append({"name": f[0], "status": f[1], "image": f[2]})
    return {"reachable": True, "mem": mem, "gpu_apps": gpu, "docker": docker}


def fleet3_probe(alias, force=False):
    assert alias in FLEET_ALIASES
    now = time.time()
    c = _fleet3_cache[alias]
    if not force and c["data"] and now - c["at"] < 25:
        return c["data"]
    rc, out, err = _ssh_fleet(alias, _PROBE_CMD, timeout=12)
    data = _parse_fleet3(rc, out, err)
    data["probed_at"] = datetime.now().isoformat(timespec="seconds")
    c.update(at=now, data=data)
    return data


def probe_eran2(force=False): return fleet3_probe("eran2", force)
def probe_eran3(force=False): return fleet3_probe("eran3", force)
def probe_eran4(force=False): return fleet3_probe("eran4", force)


def fleet3_state(force=False):
    with ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(lambda a: (a, fleet3_probe(a, force)), FLEET_ALIASES))
    return {a: d for a, d in res}


def q480_health():
    """GET /health -- no Bearer header, by design: Iddo removed the auth requirement 18:13
    and this dashboard must not reintroduce it. Returns (code_or_None, ms, body_or_err)."""
    t0 = time.time()
    try:
        req = urllib.request.Request(Q480_HEALTH_URL, headers={"User-Agent": "master-dashboard-probe/1"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status, int((time.time() - t0) * 1000), r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000), str(e)[:200]
    except Exception as e:
        return None, int((time.time() - t0) * 1000), str(e)[:200]


def q480_completion_probe():
    """One tiny REAL /v1/completions call -- proof of life beyond /health. Wired to a
    dedicated button, never auto-fired on refresh: the model is shared production capacity."""
    body = json.dumps({"model": "qwen3-coder-480b", "prompt": "2+2=", "max_tokens": 4, "temperature": 0}).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(Q480_COMPLETIONS_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "master-dashboard-probe/1"})
        with urllib.request.urlopen(req, timeout=25) as r:
            out = json.loads(r.read().decode("utf-8", "replace"))
            text = ((out.get("choices") or [{}])[0]).get("text", "")
            return "answered", {"ms": int((time.time() - t0) * 1000), "text": text[:120]}
    except Exception as e:
        return "no-answer", {"ms": int((time.time() - t0) * 1000), "error": str(e)[:200]}


def q480_status(force=False):
    now = time.time()
    if not force and _q480_cache["data"] and now - _q480_cache["at"] < 20:
        return _q480_cache["data"]
    code, ms, body = q480_health()
    rc, out, err = _ssh_fleet("eran2",
        "docker ps --format '{{.Names}}|{{.Status}}' 2>&1; echo ---PROC---; "
        "docker exec qwen480-pp bash -c \"ps aux | grep -E 'vllm serve|VLLM::' | grep -v grep\" 2>&1; "
        "echo ---LOG---; tail -n 15 /tmp/vllm-v5.log 2>/dev/null || tail -n 15 /tmp/vllm-v4.log 2>/dev/null || tail -n 15 /tmp/vllm-v3.log 2>/dev/null",
        timeout=12)
    container_up = "qwen480-pp|Up" in out
    proc_alive = ("vllm serve" in out) or ("VLLM::" in out)
    log_tail = out.split("---LOG---", 1)[-1].strip()[-1500:] if "---LOG---" in out else None
    if code == 200:
        state = "up"
    elif container_up and proc_alive:
        state = "loading"
    elif container_up:
        state = "starting"
    else:
        state = "down"
    data = {"state": state, "health_code": code, "health_ms": ms, "health_body": body,
            "container_up": container_up, "process_alive": proc_alive, "log_tail": log_tail,
            "url": Q480_HEALTH_URL, "checked_at": datetime.now().isoformat(timespec="seconds")}
    _q480_cache.update(at=now, data=data)
    return data


def q480_stop():
    st = q480_status(force=True)
    if st["state"] == "down":
        return "refused", {"reason": "already down", "status": st}
    rc, out, err = _ssh_fleet("eran2", "bash %s 2>&1" % Q480_DOWN_SCRIPT, timeout=90)
    return ("stopped" if rc == 0 else "error"), {"rc": rc, "out": out[-2000:], "err": err[:500], "script": Q480_DOWN_SCRIPT}


def _q480_start_worker(who):
    with _bg_lock:
        _bg_state["480b_start"] = {"at": datetime.now().isoformat(timespec="seconds"), "phase": "bringup", "log": ""}
    # Q480_UP_SCRIPT (up-v5.sh) installs the no-auth, tool-calling serve script DIRECTLY as
    # part of its own proven docker-cp step -- no manual swap-after needed (see the constant's
    # header comment for how that was verified 2026-09-08).
    rc, out, err = _ssh_fleet("eran2", "bash %s 2>&1" % Q480_UP_SCRIPT, timeout=240)
    with _bg_lock:
        _bg_state["480b_start"]["phase"] = "loading" if rc == 0 else "error"
        _bg_state["480b_start"]["log"] = (out or "")[-4000:] + (("\n" + err) if err else "")
    audit("fleet.480b.start", "bringup-finished" if rc == 0 else "bringup-error", {"rc": rc}, who=who)


def q480_start(who=WHO):
    st = q480_status(force=True)
    if st["state"] in ("up", "loading", "starting"):
        return "refused", {"reason": "already " + st["state"], "status": st}
    with _bg_lock:
        bg = _bg_state.get("480b_start")
        if bg and bg.get("phase") not in (None, "loading", "error"):
            return "refused", {"reason": "a start is already in progress", "state": bg}
    t = threading.Thread(target=_q480_start_worker, args=(who,), daemon=True)
    t.start()
    return "starting", {"note": "bring-up launched in background (docker+ray+pip ~1-4 min, model load ~10-25 min); poll fleet.480b.status",
                        "script": Q480_UP_SCRIPT}


# THE WHOLE ACTION SPACE. Nothing about ERAN, DARWISH or any fleet unit but eran2/eran3/eran4 exists here.
ACTIONS = {
    "keshev.pause": lambda body: keshev_pause(body.get("why")),
    "keshev.listen": lambda body: keshev_listen(),
    "start.keshev": lambda body: start_keshev(),
    "start.cockpit": lambda body: start_cockpit(),
    "start.portal": lambda body: start_portal(),
    "fleet.probe.eran2": lambda body: ("probed", probe_eran2(force=True)),
    "fleet.probe.eran3": lambda body: ("probed", probe_eran3(force=True)),
    "fleet.probe.eran4": lambda body: ("probed", probe_eran4(force=True)),
    "fleet.480b.status": lambda body: ("read", q480_status(force=True)),
    "fleet.480b.testcompletion": lambda body: q480_completion_probe(),
    "fleet.480b.stop": lambda body: q480_stop(),
    "fleet.480b.start": lambda body: q480_start(),
    # ---- MODEL LEDGER / FLEET MODES (fleet_models.py). Every one is behind a confirm.
    "models.status": lambda body: ("read", fleet_models.fleet_model_state(force=True)),
    "models.colibri.up": lambda body: fleet_models.colibri_up(),
    "models.colibri.down": lambda body: fleet_models.colibri_down(),
    "models.colibri.probe": lambda body: fleet_models.colibri_probe(),
    "models.codertrain.stop": lambda body: fleet_models.coder_train_stop(),
    "models.codertrain.start": lambda body: fleet_models.coder_train_start(),
}

_OK_RESULTS = {"paused", "listening", "started", "probed", "read", "answered", "stopped", "starting"}


def run_action(name, body, ip=None):
    fn = ACTIONS.get(name)
    if fn is None:
        audit(name, "no-such-action", ip=ip)
        return 404, {"ok": False, "result": "no-such-action", "detail": "this dashboard has no such endpoint, by construction"}
    try:
        result, detail = fn(body or {})
    except Exception as e:
        result, detail = "error", {"exc": repr(e)[:300]}
    audit(name, result, detail, ip=ip)
    return 200, {"ok": result in _OK_RESULTS, "result": result, "detail": detail}


# ------------------------------------------------- ask / queue (2026-09-11, B3)
# Both are reached only after private_hub.py has checked: the HttpOnly cookie,
# the token in the body, AND the per-process X-CSRF-Token header. one_place does
# its own rate limit (20/min) and size cap (4 KB) and writes the audit row.
def run_ask(body, ip=None):
    result, detail = one_place.ask(str(body.get("model") or ""),
                                   str(body.get("text") or ""), ip=ip)
    return 200, {"ok": result == "answered", "result": result, "detail": detail}


def run_queue(body, ip=None):
    result, detail = one_place.queue_op(str(body.get("op") or ""),
                                        str(body.get("id") or ""),
                                        body.get("result"), ip=ip)
    return 200, {"ok": result in ("claimed", "done"), "result": result, "detail": detail}


# ---------------------------------------------------------------------------- read-only state
def fleet_state():
    out = {"collector": {}, "boxes": {}, "eran": None, "services": {}, "system": None}
    pid = (_read(COLLECTOR_PID) or "").strip()
    age = _age(STATUS_JSON)
    out["collector"] = {"pid": pid or None, "alive": pid_alive(pid), "status_age_s": age,
                        "fresh": age is not None and age < 60}
    try:
        s = json.load(io.open(STATUS_JSON, encoding="utf-8"))
    except Exception as e:
        out["collector"]["error"] = str(e)[:120]
        return out
    meta = s.get("meta") or {}
    out["collector"]["ts_iso"] = meta.get("ts_iso")
    out["collector"]["stale"] = meta.get("stale")
    for name, b in (s.get("fleet") or {}).items():
        if name.startswith("_") or not isinstance(b, dict):
            continue
        gpu = (b.get("gpu") or [{}])[0] if b.get("gpu") else {}
        out["boxes"][name] = {
            "reachable": b.get("reachable"), "hostname": b.get("hostname"), "load": b.get("load"),
            "mem_pct": (b.get("mem") or {}).get("pct"), "gpu_util": gpu.get("util_pct"),
            "gpu_temp": gpu.get("temp_c"), "gpu_w": gpu.get("power_w"), "error": b.get("error"),
            "age_s": round(time.time() - b["cached_at"], 0) if b.get("cached_at") else None,
        }
    live = (s.get("eran") or {}).get("live") or {}
    out["eran"] = {k: live.get(k) for k in ("up", "state", "beat", "beats_per_s", "unit", "prototypes", "url", "error", "retired")}
    for k, v in (s.get("services") or {}).items():
        if isinstance(v, dict):
            out["services"][k] = {"up": v.get("up"), "target": v.get("target"), "ms": v.get("latency_ms")}
    # 2026-09-15 (W6): probes the collector no longer runs, with the reason. Never red.
    out["services_retired"] = {k: (v.get("retired") if isinstance(v, dict) else str(v))
                               for k, v in (s.get("services_retired") or {}).items()}
    sysd = s.get("system") or {}
    out["system"] = {"cpu_pct": (sysd.get("cpu") or {}).get("pct"), "mem_pct": (sysd.get("mem") or {}).get("pct"),
                     "disks": {d: v.get("free_gb") for d, v in (sysd.get("disks") or {}).items()}}
    return out


def doors_state(force=False):
    now = time.time()
    if not force and _door_cache["rows"] and now - _door_cache["at"] < 20:
        return _door_cache["rows"]
    serve = tailscale_serve_map()
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda d: probe(d[3]), DOORS))
    rows = []
    for d, (code, ms, err) in zip(DOORS, res):
        did, icon, name, purl, local, tail, what = d
        port = None
        m = re.search(r"127\.0\.0\.1:(\d+)", local)
        if m:
            port = int(m.group(1))
        if code is None and port and err and "timed out" in err and port_open("127.0.0.1", port):
            # GALERIA renders its index in ~7 s: the port answers, the page is slow. Honest, not red.
            code, err = "open/slow", None
        if tail is None and port in serve:
            tail = serve[port]
        # 2026-09-11 (WAVE A2): "up" used to mean "something answered", so a 502 from
        # a dead backend behind a live `tailscale serve` painted the tile GREEN.
        # ERAN's window was drawn alive for days while eranb-serve crash-looped.
        # A 5xx is the proxy telling us the thing behind it is gone -- that is DOWN.
        up = code is not None and not (isinstance(code, int) and code >= 500)
        rows.append({"id": did, "icon": icon, "name": name, "what": what, "local": local, "tailnet": tail,
                     "up": up, "code": code, "ms": ms, "error": err})
    hub_tail = serve.get(8896)
    rows.insert(0, {"id": "hub", "icon": "🔒", "name": "THIS DASHBOARD", "what": "private_hub.py :8896",
                    "local": "http://127.0.0.1:8896/control", "tailnet": (hub_tail + "control") if hub_tail else None,
                    "up": True, "code": 200, "ms": 0, "error": None})
    _door_cache.update(at=now, rows=rows)
    return rows


def ramchat_tail(n=8):
    try:
        d = json.load(io.open(RAMCHAT_SESSION, encoding="utf-8"))
        rows = d[-n:] if isinstance(d, list) else []
        return [{"who": r.get("who"), "text": (r.get("text") or "")[:220], "ts": r.get("ts") or r.get("time")} for r in rows]
    except Exception as e:
        return [{"who": "?", "text": "ramchat_session.json unreadable: %s" % e, "ts": None}]


# ============================================================ BACKGROUND PROBER
# 2026-09-11 (WAVE B3). Before this, /control was 5-7 s on every cold open: the
# request itself did 11 HTTP door probes + 3 SSH round trips to eran2/3/4 + the
# 480B health check, and the internal caches (20-25 s) expired between phone
# visits, so the phone paid the full cost EVERY time.
#
# Now a daemon thread owns freshness and the request owns nothing. The page is
# assembled from cache and states its own age. Two tiers, because they cost
# very different things:
#   FAST  pure HTTP -- door tiles, the 33 inventory doors, the model list,
#         `tailscale status`. Cheap, local, safe to repeat.
#   SLOW  SSH into eran2/eran3/eran4 + the 480B health + the model ledger.
#         Real load on living boxes, so it runs on a longer cadence and NOT AT
#         ALL while nobody is looking at the page.
# "Nobody is looking" = no /control and no /control/api/state for 3 minutes.
PROBE_TICK_S = 5
FAST_TTL_ACTIVE, FAST_TTL_IDLE = 25, 300
SLOW_TTL_ACTIVE, SLOW_TTL_IDLE = 60, 0        # 0 == never while idle
ACTIVE_WINDOW_S = 180

_groups = {"fast": {"at": 0.0, "ms": None, "data": None, "err": None},
           "slow": {"at": 0.0, "ms": None, "data": None, "err": None}}
_view = {"at": 0.0}
_prober = {"thread": None, "wake": threading.Event(), "due": set(), "running": set()}


def _honor_inventory_flags(dev):
    """2026-09-15 (W6): one_place.devices_state() probes EVERY door in the inventory,
    so the 11 doors fleet_inventory.json marks `retired` (and wabot, which has no
    socket at all -- `socketless`, url null) were painted BROKEN in the devices panel.
    Relabel them here from the same inventory file: RETIRED doors are listed last,
    grey, and do not count; a socketless door is SSH-ONLY, grey, never red.
    (one_place.py is outside this fix's file list; it still spends one probe on each.)"""
    try:
        inv_doors = one_place._inventory().get("doors") or {}
    except Exception:                                         # noqa: BLE001
        return dev
    if not isinstance(dev, dict) or not dev.get("hosts"):
        return dev
    gone_ok = gone_total = 0
    for h in dev["hosts"]:
        live, retired = [], []
        for r in h.get("doors") or []:
            rec = inv_doors.get(r.get("name")) or {}
            if rec.get("retired"):
                gone_total += 1
                gone_ok += 1 if r.get("state") == "VERIFIED" else 0
                retired.append(dict(r, state="RETIRED", retired=str(rec["retired"])[:240]))
            elif not r.get("url") and rec.get("socketless"):
                if r.get("state") == "VERIFIED":
                    gone_ok += 1
                live.append(dict(r, state="SSH-ONLY", note=str(rec.get("probe_note") or "")[:240]))
            else:
                live.append(r)
        h["doors"] = live + retired
        h["doors_ok"] = sum(1 for r in live if r.get("state") == "VERIFIED")
        h["doors_total"] = len(live)
        h["doors_retired"] = len(retired)
    if isinstance(dev.get("doors_total"), int):
        dev["doors_total"] = dev["doors_total"] - gone_total
    if isinstance(dev.get("doors_ok"), int):
        dev["doors_ok"] = dev["doors_ok"] - gone_ok
    dev["doors_retired"] = gone_total
    return dev


def _build_fast():
    return {"doors": doors_state(True),
            "devices": _honor_inventory_flags(one_place.devices_state()),
            "models_live": one_place.models_state(True)}


def _build_slow():
    try:
        models = fleet_models.fleet_model_state(True)
    except Exception as e:                                    # noqa: BLE001
        models = {"error": repr(e)[:300], "mode": "?", "boxes": {}, "router": {}}
    try:
        switch = fleet_models.switch_progress()
    except Exception:                                         # noqa: BLE001
        switch = None
    return {"fleet3": fleet3_state(True), "q480": q480_status(True),
            "models": models, "switch": switch}


_BUILDERS = {"fast": _build_fast, "slow": _build_slow}


def _refresh_group(name):
    g = _groups[name]
    t0 = time.time()
    try:
        g["data"] = _BUILDERS[name]()
        g["err"] = None
    except Exception as e:                                    # noqa: BLE001
        g["err"] = repr(e)[:300]
    g["ms"] = int((time.time() - t0) * 1000)
    g["at"] = time.time()
    _prober["due"].discard(name)


def _run_group_bg(name):
    try:
        _refresh_group(name)
    finally:
        _prober["running"].discard(name)


def _prober_loop():
    # 2026-09-15 (W6): the two groups used to run IN SERIES on this one thread. The
    # fast group measured 53-100 s (39 inventory doors + 27 model seats), so after an
    # idle spell the SLOW group -- the model ledger and the 480B -- waited behind it
    # and the page kept showing a snapshot from the last time anyone looked (29 h on
    # 09-15). Now each group runs in its own single-flight worker, so a view gets a
    # fresh ledger within one tick (5 s) + its own probe time, whatever fast is doing.
    # The idle rule is unchanged: SLOW (SSH) still never runs while nobody is looking.
    while True:
        now = time.time()
        active = (now - _view["at"]) < ACTIVE_WINDOW_S
        for name, (ttl_a, ttl_i) in (("fast", (FAST_TTL_ACTIVE, FAST_TTL_IDLE)),
                                     ("slow", (SLOW_TTL_ACTIVE, SLOW_TTL_IDLE))):
            g = _groups[name]
            ttl = ttl_a if active else ttl_i
            due = (g["data"] is None and g["err"] is None) or (name in _prober["due"]) \
                or (ttl > 0 and (now - g["at"]) >= ttl)
            if due and name not in _prober["running"]:
                _prober["running"].add(name)
                threading.Thread(target=_run_group_bg, args=(name,),
                                 name="control-prober-" + name, daemon=True).start()
        _prober["wake"].clear()
        _prober["wake"].wait(PROBE_TICK_S)


def start_prober():
    """Called once by private_hub.py before serve_forever()."""
    if _prober["thread"] is not None:
        return _prober["thread"]
    t = threading.Thread(target=_prober_loop, name="control-prober", daemon=True)
    _prober["thread"] = t
    t.start()
    return t


def _kick():
    """Mark both groups due and wake the prober. Never blocks the request."""
    _prober["due"].update(("fast", "slow"))
    _prober["wake"].set()


def full_state(force=False):
    """Assembled from cache -- this function does NO network and NO SSH.

    The cheap half (KESHEV's state files, the HUD's status.json, the RAMCHAT
    tail, the work queue) is read per request because they are local files and
    measure well under 20 ms together, and because the PAUSE/LISTEN buttons must
    show their effect the moment they are pressed. `force` wakes the prober and
    returns immediately; the 15 s auto-refresh picks the fresh numbers up.
    """
    _view["at"] = time.time()
    if _prober["thread"] is None:            # never started (import-time use, tests)
        for name in ("fast", "slow"):
            if _groups[name]["data"] is None:
                _refresh_group(name)
    if force:
        _kick()
    fast = _groups["fast"]
    slow = _groups["slow"]
    fd = fast["data"] or {}
    sd = slow["data"] or {}
    now = time.time()
    st = {"now": datetime.now().isoformat(timespec="seconds"),
          "keshev": keshev_state(),
          "fleet": fleet_state(),
          "ramchat": ramchat_tail(12),
          "queue": one_place.queue_state(),
          "doors": fd.get("doors") or [],
          "devices": fd.get("devices") or {"hosts": [], "probing": True},
          "models_live": fd.get("models_live") or {"models": [], "probing": True},
          "fleet3": sd.get("fleet3") or {},
          "q480": sd.get("q480") or {"state": "?", "health_code": None, "health_ms": 0,
                                     "container_up": None, "process_alive": None,
                                     "checked_at": None, "log_tail": None},
          "models": sd.get("models") or {"mode": "?", "boxes": {}, "router": {}},
          "switch": sd.get("switch"),
          "actions": sorted(ACTIONS)}
    st["cache"] = {
        "fast_age_s": round(now - fast["at"], 1) if fast["at"] else None,
        "slow_age_s": round(now - slow["at"], 1) if slow["at"] else None,
        "fast_ms": fast["ms"], "slow_ms": slow["ms"],
        "fast_err": fast["err"], "slow_err": slow["err"],
        "active": True, "tick_s": PROBE_TICK_S,
        "prober": _prober["thread"] is not None,
    }
    return st


# ---------------------------------------------------------------------------- the page
def control_page(token):
    st = full_state()
    j = json.dumps(st, ensure_ascii=False).replace("</", "<\\/")
    return (PAGE_HTML.replace("__STATE__", j)
            .replace("__KEY__", html.escape(token))
            .replace("__CSRF__", html.escape(CSRF)))


PAGE_HTML = r"""<!doctype html><html lang="he" dir="rtl"><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>
<title>MASTER DASHBOARD · שליטה</title><style>
body{background:#faf9f7;color:#1a1a1a;font-family:system-ui,Segoe UI,Arial;margin:0;padding:14px;max-width:900px;margin:auto}
h1{font-size:20px;margin:0 0 2px} .sub{color:#777;font-size:12px;margin:0 0 12px}
h2{font-size:15px;margin:18px 0 6px;border-bottom:2px solid #eadfce;padding-bottom:3px;color:#8a5a2b}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.tile{border:1px solid #e6e3de;border-radius:10px;padding:10px;background:#fff;box-shadow:0 1px 2px #0000000a;font-size:13px}
.tile b{display:block;font-size:14px} .tile .m{color:#666;font-size:12px;margin-top:3px}
.up{border-inline-start:6px solid #2ecc40} .down{border-inline-start:6px solid #e0433a} .grey{border-inline-start:6px solid #bbb}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-inline-end:6px;vertical-align:middle}
.g{background:#2ecc40}.r{background:#e0433a}.y{background:#f5a623}.b{background:#bbb}
.big{font-size:26px;font-weight:700;margin:4px 0}
button{font-size:16px;padding:12px 16px;border-radius:10px;border:0;cursor:pointer;margin:4px 6px 4px 0;color:#fff;background:#8a5a2b;min-height:46px}
button.pause{background:#c0392b} button.listen{background:#2ecc40;color:#111} button.start{background:#2c6fbb} button:disabled{background:#ccc;color:#666}
button.sm{font-size:13px;padding:8px 12px;min-height:38px}
.door a{text-decoration:none;color:#8a5a2b;font-weight:600} .door .l{font-size:11px;color:#999;direction:ltr;text-align:left;word-break:break-all}
.ram{font-size:12px;background:#fff;border:1px solid #e6e3de;border-radius:8px;padding:8px} .ram div{padding:3px 0;border-bottom:1px dashed #eee}
.ram span{color:#8a5a2b;font-weight:600} #msg{position:sticky;top:0;background:#fff8e6;border:1px solid #f0d090;padding:8px;border-radius:8px;display:none;font-size:13px;z-index:9}
.law{font-size:11px;color:#999;margin:14px 0}
input,select,textarea{font-size:16px;padding:10px;border:1px solid #ddd;border-radius:8px;width:100%;box-sizing:border-box;margin:6px 0;font-family:inherit;background:#fff;color:#1a1a1a}
select{min-height:46px} textarea{min-height:84px;resize:vertical}
a.back{font-size:12px;color:#8a5a2b}
/* ---- 2026-09-11 WAVE B3: phone-first. 6" screen, one thumb, bright. ---- */
details{border:1px solid #e6e3de;border-radius:10px;background:#fff;margin:0 0 8px;overflow:hidden}
details>summary{cursor:pointer;padding:13px 12px;font-weight:600;font-size:15px;color:#8a5a2b;list-style:none;min-height:22px}
details>summary::-webkit-details-marker{display:none}
details>summary::after{content:"▾";float:left;color:#bbb} details[open]>summary::after{content:"▴"}
details>.body{padding:0 10px 10px}
.pill{display:inline-block;font-size:11px;padding:3px 8px;border-radius:999px;margin:2px 2px 2px 0;direction:ltr;white-space:nowrap}
.pill.ok{background:#e7f8e7;color:#176b17;border:1px solid #bfe8bf}
.pill.bad{background:#fdeceb;color:#a02219;border:1px solid #f3c3bf}
.pill.slow{background:#fff6e3;color:#8a5a1b;border:1px solid #f0dcaf}
.pill.pc{background:#f1f1f1;color:#999;border:1px solid #e2e2e2}
.stale{color:#a0762b} .off{opacity:.55}
.answer{background:#fff;border:1px solid #e6e3de;border-radius:10px;padding:12px;margin-top:8px;font-size:15px;line-height:1.55;white-space:pre-wrap;word-break:break-word;unicode-bidi:plaintext;min-height:10px}
.qrow{border-bottom:1px dashed #eee;padding:8px 0;font-size:13px}
.qrow .id{font-size:10px;color:#aaa;direction:ltr;text-align:left}
.hostrow{border-bottom:1px solid #f0efec;padding:9px 0}
.hostrow .n{font-weight:600;font-size:15px} .hostrow .m{color:#666;font-size:12px}
.addr{direction:ltr;text-align:left;font-size:11px;color:#999;word-break:break-all}
@media(max-width:520px){
 body{padding:10px} h1{font-size:18px} .grid{grid-template-columns:1fr 1fr;gap:6px}
 button{width:100%;margin:4px 0} button.sm{width:auto;margin:3px 4px 3px 0}
 .tile{font-size:12.5px}
}
</style>
<h1>&#128274; MASTER DASHBOARD &middot; שליטה מרחוק</h1>
<p class=sub><a class=back href="/">&larr; catalogue / הקטלוג</a> &middot; <span id=now></span> &middot; auto-refresh 15 s &middot; <span id=cache></span></p>
<div id=msg></div>

<h2>🎙️ KESHEV &middot; המיקרופון</h2>
<div class=tile id=kbox>
  <div class=big id=kstate>…</div>
  <div class=m id=kdetail></div>
  <div id=kpause class=m></div>
  <div style="margin-top:8px">
    <input id=why placeholder="למה? / why (optional) — goes into the signed PAUSED file">
    <button class=pause onclick="act('keshev.pause',{why:document.getElementById('why').value})">השהה 🔴 PAUSE</button>
    <button class=listen onclick="act('keshev.listen')">האזן 🟢 LISTEN</button>
    <button class=start onclick="act('start.keshev')">▶ open KESHEV window</button>
  </div>
</div>

<h2>🤖 שאל מודל &middot; ASK ANY MODEL <span style="font-weight:400;font-size:12px;color:#777"><span id=mcount></span></span></h2>
<div class=tile id=askbox>
  <select id=model onchange="rememberModel()"></select>
  <textarea id=asktext placeholder="כתוב כאן שאלה — בעברית או באנגלית. Enter שולח."></textarea>
  <div>
    <button class=start id=asksend onclick="ask()">שלח ✉️ ASK</button>
    <button class=sm onclick="document.getElementById('asktext').value='';document.getElementById('answer').textContent=''">נקה</button>
    <span class=m id=askmeta style="color:#999;font-size:12px"></span>
  </div>
  <div class=answer id=answer></div>
  <div class=m style="color:#999;margin-top:6px">השאלה נשלחת מהמחשב הזה אל הדלת שבחרת. מפתחות API אף פעם לא מגיעים לדפדפן. עד 4KB, 20 שאלות לדקה, כל שאלה נרשמת ביומן (המודל והאורך — לא הטקסט).</div>
</div>

<details id=devbox>
  <summary>📱 המכשירים &middot; DEVICES <span id=devsum style="font-weight:400;font-size:12px;color:#777"></span></summary>
  <div class=body id=devices></div>
</details>

<details id=workbox>
  <summary>📋 העבודה &middot; THE WORK <span id=worksum style="font-weight:400;font-size:12px;color:#777"></span></summary>
  <div class=body>
    <div class=m style="color:#999;font-size:12px;margin:4px 0">תור העבודה של RAMCHAT. לחיצה על "קח" תופסת את המשימה בשם <b>iddo (control page)</b> — אטומי, אם מישהו כבר תפס אותה תיענה סירוב.</div>
    <div id=qmine></div>
    <div id=queue></div>
    <div style="margin-top:10px;font-weight:600;color:#8a5a2b">🧠 RAMCHAT &middot; המועצה</div>
    <div class=ram id=ram style="margin-top:6px"></div>
  </div>
</details>

<details id=fleetctl>
<summary>🖧🎛️ FLEET CONTROL &middot; שליטה בצי</summary>
<div class=body>
<div class=m style="font-size:12px;color:#777;margin:2px 0 8px">eran2 / eran3 / eran4 only &mdash; eran1 (ERAN) &amp; DARWISH have NO button anywhere on this page</div>
<div class=grid id=fleet3></div>

<div class=tile id=q480box style="margin-top:8px">
  <b>🐉 Qwen3-Coder-480B &middot; vLLM PP&times;3 (eran2+eran3+eran4)</b>
  <div class=big id=q480state>…</div>
  <div class=m id=q480detail></div>
  <div id=q480log class=m style="direction:ltr;text-align:left;white-space:pre-wrap;max-height:130px;overflow:auto;background:#faf9f5;border:1px solid #eee;border-radius:6px;padding:6px;margin-top:6px;display:none;font-family:monospace;font-size:11px"></div>
  <div style="margin-top:8px">
    <button class=start onclick="act('fleet.480b.start')">▶ START the cluster</button>
    <button class=pause onclick="act('fleet.480b.stop')">■ STOP the cluster</button>
    <button onclick="act('fleet.480b.testcompletion')">🧪 live completion probe</button>
    <button onclick="act('fleet.480b.status')">⟳ refresh</button>
  </div>
  <div class=m style="margin-top:6px;color:#999">No Bearer key by Iddo's 18:13 order (tailnet-only via tailscale serve on eran2) &mdash; this panel never adds one back.</div>
</div>

</div></details>

<details id=giantsbox>
<summary>🧠🎛️ מודלים ענקיים &middot; THE GIANTS</summary>
<div class=body>
<div class=m style="font-size:12px;color:#777;margin:2px 0 8px">one button decides what the fleet IS &mdash; they cannot coexist</div>
<div class=tile id=modebox>
  <b id=modelabel>…</b>
  <div class=m id=modewhy></div>
  <div class=m id=routerline style="margin-top:6px"></div>
  <div class=grid id=giants style="margin-top:8px"></div>
  <div style="margin-top:8px">
    <button onclick="act('models.status')">⟳ refresh</button>
  </div>
  <!-- 2026-09-15 (W6): the COLIBRI raise/lower/probe buttons and the coder-train
       stop/resume buttons were removed from the page -- both units are DISABLED
       (measured 09-15). The action endpoints still exist in ACTIONS; to restore the
       buttons, copy this block back from control.py.bak-bw-20260915. -->
  <div class="m off" style="margin-top:8px;border-top:1px solid #eee;padding-top:8px">
    <b>retired · לא פעילים</b><br>
    COLIBRI GLM-5.2 744B &mdash; unit disabled on eran1 + eran4, keepalive timer disabled<br>
    coder-train &middot; eran1 &mdash; stopped 2026-09-10 (scored worse than its base), unit disabled
  </div>
</div>

</div></details>

<details id=overviewbox>
<summary>🖧 FLEET OVERVIEW &middot; תמונת מצב</summary>
<div class=body>
<div id=coll class=m style="font-size:12px;color:#777;margin:2px 0 8px"></div>
<div class=grid id=fleet></div>
<div class=grid id=eran style="margin-top:8px"></div>
</div></details>

<details id=doorsbox open>
<summary>🚪 DOORS &middot; דלתות</summary>
<div class=body>
<div class=grid id=doors></div>
<div style="margin-top:8px">
  <button class=start onclick="act('start.cockpit')">▶ start COCKPIT</button>
  <button class=start onclick="act('start.portal')">▶ start QUEST PORTAL</button>
  <button onclick="refresh(true)">⟳ re-probe</button>
</div>
</div></details>

<p class=law>By construction this page has no start/stop/restart for ERAN (eran1) or DARWISH (eran4 dmidi-life/dmidi-tap) &mdash; not hidden, ABSENT: no function in control.py accepts a hostname from a request, every SSH target is a literal in FLEET_ALIASES=(eran2,eran3,eran4). Every fleet button targets one of those three boxes only, from a fixed action list.
Every action is logged to control-audit.jsonl. Pause writes the SIGNED PAUSED file (who/why/at/expires/restore/disables), exactly like the KESHEV window.</p>

<!-- A SEPARATE script block, on purpose. 2026-09-11: the whole page script below
     had been ONE SyntaxError since 2026-09-09 (a raw newline inside a JS string in
     the coder-train confirm text), so every tile on this page rendered its static
     placeholder and no button worked -- silently, for two days. This block cannot
     be taken down by a syntax error in that one, so from now on the page SAYS SO. -->
<script>
window.addEventListener('error',function(e){
  var m=document.getElementById('msg'); if(!m)return;
  m.style.display='block'; m.style.background='#fde9e9';
  m.textContent='⚠ JS ERROR — הדף מת ולא מתעדכן: '+(e.message||e.error)+' @'+(e.lineno||'?')+':'+(e.colno||'?');
});
</script>
<script>
const KEY="__KEY__"; const CSRF="__CSRF__"; let S=__STATE__;
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function age(s){if(s==null)return'—';if(s<90)return Math.round(s)+' שנ\'';if(s<5400)return Math.round(s/60)+' דק\'';return Math.round(s/3600)+' שע\''}
/* ---------------- WAVE B3: models + chat ---------------- */
let MODEL_SIG="";
function getCookie(n){const m=document.cookie.match('(^|;)\\s*'+n+'\\s*=\\s*([^;]+)');return m?decodeURIComponent(m.pop()):''}
function rememberModel(){document.cookie='ctlmodel='+encodeURIComponent(document.getElementById('model').value)+';Path=/;Max-Age=31536000;SameSite=Lax'}
function renderModels(){
  const M=S.models_live||{}, sel=document.getElementById('model'), rows=M.models||[];
  document.getElementById('mcount').textContent=M.probing?'בודק…':((M.up||0)+' חיים מתוך '+(M.total||0));
  const sig=rows.map(r=>r.id+(r.up?'1':'0')).join('|');
  if(sig===MODEL_SIG)return; MODEL_SIG=sig;
  const want=sel.value||getCookie('ctlmodel');
  const groups={};
  for(const r of rows)(groups[r.where||'?']=groups[r.where||'?']||[]).push(r);
  let h='';
  for(const g of Object.keys(groups)){
    h+='<optgroup label="'+esc(g)+'">';
    for(const r of groups[g])h+='<option value="'+esc(r.id)+'"'+(r.up?'':' disabled')+'>'+(r.up?'🟢':'🔴')+' '+esc(r.label)+(r.tag?' — '+esc(r.tag):'')+'</option>';
    h+='</optgroup>';
  }
  sel.innerHTML=h||'<option disabled>אין מודלים</option>';
  if(want&&rows.some(r=>r.id===want&&r.up))sel.value=want;
  else{const first=rows.find(r=>r.up);if(first)sel.value=first.id}
}
async function ask(){
  const sel=document.getElementById('model'),ta=document.getElementById('asktext');
  const b=document.getElementById('asksend'),ans=document.getElementById('answer'),meta=document.getElementById('askmeta');
  const text=(ta.value||'').trim(); if(!text){ta.focus();return}
  if(!sel.value){msg('בחר מודל קודם',false);return}
  b.disabled=true;const label=sel.options[sel.selectedIndex].textContent;
  ans.textContent='…';meta.textContent=label+' חושב';const t0=Date.now();
  try{
    const r=await fetch('/control/api/ask',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':CSRF},
      body:JSON.stringify({key:KEY,model:sel.value,text:text})});
    const j=await r.json();
    if(j.ok){ans.textContent=(j.detail&&j.detail.answer)||'';meta.textContent=label+' · '+Math.round((Date.now()-t0)/100)/10+' שנ\'';}
    else{ans.textContent='';meta.textContent='';msg('לא ענה: '+j.result+' — '+esc((j.detail&&(j.detail.reason||j.detail.error))||''),false)}
  }catch(e){ans.textContent='';msg('שליחה נכשלה: '+e,false)}
  b.disabled=false;
}
/* ---------------- WAVE B3: devices ---------------- */
function renderDevices(){
  const D=S.devices||{},hs=D.hosts||[];
  document.getElementById('devsum').textContent=D.probing?'בודק…':(hs.filter(h=>h.online).length+'/'+hs.length+' מחוברים · '+(D.doors_ok||0)+'/'+(D.doors_total||0)+' דלתות'+(D.doors_retired?(' · '+D.doors_retired+' retired'):''));
  let h='';
  for(const d of hs){
    const pills=(d.doors||[]).map(p=>{
      if(p.state==='RETIRED')return '<span class="pill pc" title="'+esc(p.retired||'')+'">'+esc(p.name)+' · retired</span>';
      if(p.state==='SSH-ONLY')return '<span class="pill pc" title="'+esc(p.note||'')+'">'+esc(p.name)+' · ssh-only</span>';
      if(p.loopback&&d.key==='pc')return '<span class="pill pc" title="'+esc(p.url)+'">'+esc(p.name)+' · PC only</span>';
      const c=p.state==='VERIFIED'?'ok':(p.state==='SLOW'?'slow':'bad');
      return '<a class="pill '+c+'" style="text-decoration:none" target=_blank href="'+esc(p.url)+'" title="'+esc(p.purpose||'')+'">'+esc(p.name)+' '+esc(p.code==null?'—':p.code)+'</a>';
    }).join('');
    h+='<div class="hostrow'+(d.online?'':' off')+'"><div class=n><span class="dot '+(d.online?'g':'b')+'"></span>'+esc(d.key)+
       ' <span style="font-weight:400;font-size:12px;color:#888">'+esc(d.last_seen||'')+'</span></div>'+
       '<div class=m>'+esc(d.role||'')+'</div>'+
       '<div class=addr>'+(d.tailnet_ip?('tailnet '+esc(d.tailnet_ip)+(d.magicdns?' · '+esc(d.magicdns):'')):'no tailnet')+(d.lan_ip?(' · LAN '+esc(d.lan_ip)):'')+'</div>'+
       (pills?('<div style="margin-top:4px">'+pills+'</div>'):'')+'</div>';
  }
  document.getElementById('devices').innerHTML=h||'<div class=m>אין נתוני מכשירים</div>';
}
/* ---------------- WAVE B3: the work queue ---------------- */
function renderQueue(){
  const Q=S.queue||{};
  document.getElementById('worksum').textContent=(Q.open_total||0)+' פתוחות'+((Q.mine||[]).length?(' · '+Q.mine.length+' שלך'):'');
  const row=(t,mine)=>'<div class=qrow><div>'+esc(t.prompt)+'</div><div class=id>'+esc(t.id)+' · '+esc(t.status)+(t.held?(' · '+esc(t.held)):'')+'</div>'+
    (mine?('<button class=sm onclick="queueOp(\'done\',\''+esc(t.id)+'\')">✔ סיימתי</button>')
         :('<button class="sm start" onclick="queueOp(\'claim\',\''+esc(t.id)+'\')">✋ קח</button>'))+'</div>';
  document.getElementById('qmine').innerHTML=(Q.mine||[]).length?('<div style="font-weight:600;color:#8a5a2b;margin:4px 0">שלך עכשיו</div>'+Q.mine.map(t=>row(t,true)).join('')):'';
  const op=Q.open||[];
  document.getElementById('queue').innerHTML=op.length?('<div style="font-weight:600;color:#8a5a2b;margin:8px 0 4px">פתוחות ('+op.length+' מתוך '+(Q.open_total||0)+')</div>'+op.map(t=>row(t,false)).join('')):'<div class=m>אין משימות פתוחות</div>';
}
async function queueOp(op,id){
  if(!confirm(op==='claim'?('לתפוס את המשימה?\n'+id):('לסמן כבוצעה?\n'+id)))return;
  try{const r=await fetch('/control/api/queue',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':CSRF},
      body:JSON.stringify({key:KEY,op:op,id:id})});
    const j=await r.json(); msg(op+' → '+j.result+' '+((j.detail&&j.detail.out)||''),j.ok); setTimeout(()=>refresh(false),800);
  }catch(e){msg('queue failed: '+e,false)}
}
function msg(t,ok){const m=document.getElementById('msg');m.style.display='block';m.style.background=ok?'#e9fbe9':'#fde9e9';m.textContent=t;setTimeout(()=>m.style.display='none',9000)}
function render(){
  document.getElementById('now').textContent=S.now;
  const k=S.keshev, ks=document.getElementById('kstate'), kb=document.getElementById('kbox');
  const map={listening:['🟢 LISTENING · מאזין','g','up'],paused:['🔴 PAUSED · מושהה','r','down'],half:['🟡 HALF · חצי חי','y','grey'],dead:['⚫ DEAD · מת','b','down']};
  const [lab,dot,cls]=map[k.state]||['?','b','grey'];
  ks.innerHTML='<span class="dot '+dot+'"></span>'+lab+(k.decoy?' <small style="color:#c0392b">[DECOY state dir: '+esc(k.state_dir)+']</small>':'');
  kb.className='tile '+cls;
  document.getElementById('kdetail').textContent='window heartbeat '+(k.heartbeat_age_s==null?'none':k.heartbeat_age_s+' s')+' · engine pid '+(k.mic_pid||'-')+(k.engine?' alive':' NOT alive')+' · last log write '+(k.log_age_s==null?'?':Math.round(k.log_age_s)+' s ago');
  const kp=document.getElementById('kpause');
  kp.innerHTML=k.paused?('PAUSED by <b>'+esc(k.pause&&k.pause.who)+'</b> at '+esc(k.pause&&k.pause.at)+' — '+esc(k.pause&&k.pause.why)+(k.pause_signed?' <span style="color:#2ecc40">signed ✓ (the watchdog leaves it alone)</span>':' <span style="color:#c0392b">UNSIGNED — the watchdog clears this shape after 15 min</span>')):'';
  let f3h='';
  for(const a of ['eran2','eran3','eran4']){
    const b=(S.fleet3||{})[a]||{}; const ok=b.reachable===true; const mem=b.mem||{};
    const gpuLine=(b.gpu_apps||[]).length?b.gpu_apps.map(g=>esc(g.process)+' &middot; '+esc(g.used)).join('<br>'):'(no GPU processes)';
    const dockLine=(b.docker||[]).length?b.docker.map(d=>esc(d.name)+' — '+esc(d.status)).join('<br>'):'(no containers)';
    const pending=b.reachable===undefined;
    f3h+='<div class="tile '+(pending?'grey':(ok?'up':'down'))+'"><b>'+a+'</b><div class=m>'+(ok?
        ('RAM '+mem.used_gb+'/'+mem.total_gb+' G used ('+mem.free_gb+' G free)<br><u>GPU procs</u><br>'+gpuLine+'<br><u>docker</u><br>'+dockLine):
        (pending?'בודק ברקע…':('unreachable: '+esc(b.error))))+'</div>'+
        '<button style="margin-top:6px;padding:6px 10px;font-size:12px" onclick="act(\'fleet.probe.'+a+'\')">⟳ refresh '+a+'</button></div>';
  }
  document.getElementById('fleet3').innerHTML=f3h;
  const q=S.q480||{};
  const qmap={up:['🟢 UP · חי','g','up'],loading:['🟡 LOADING · בטעינה','y','grey'],starting:['🟡 STARTING · מתחיל','y','grey'],down:['⚫ DOWN · כבוי','b','down']};
  const [qlab,qdot,qcls]=qmap[q.state]||['?','b','grey'];
  document.getElementById('q480state').innerHTML='<span class="dot '+qdot+'"></span>'+qlab;
  document.getElementById('q480box').className='tile '+qcls;
  document.getElementById('q480detail').textContent=q.checked_at?('health '+(q.health_code==null?'no answer':q.health_code)+' ('+(q.health_ms||0)+' ms) · container '+(q.container_up?'up':'down')+' · vllm process '+(q.process_alive?'alive':'not found')+' · checked '+q.checked_at):'בודק ברקע…';
  const qlog=document.getElementById('q480log');
  if(q.log_tail){qlog.style.display='block';qlog.textContent=q.log_tail}else{qlog.style.display='none'}
  const f=S.fleet, c=f.collector;
  document.getElementById('coll').textContent=c.alive&&c.fresh?('collector pid '+c.pid+' · status.json '+c.status_age_s+' s old'):('⚠ COLLECTOR '+(c.alive?'alive but status.json '+c.status_age_s+' s old':'DOWN')+' — tiles are stale');
  let h='';
  for(const [n,b] of Object.entries(f.boxes||{})){const ok=b.reachable===true;h+='<div class="tile '+(ok?'up':'down')+'"><b>'+esc(n)+'</b><div class=m>'+(ok?('load '+(b.load||[]).map(x=>x.toFixed?x.toFixed(1):x).join(' / ')+'<br>mem '+b.mem_pct+'% · GPU '+esc(b.gpu_util)+'% '+esc(b.gpu_temp)+'°C '+(b.gpu_w!=null?Math.round(b.gpu_w)+'W':'')):('unreachable: '+esc(b.error)))+'</div></div>'}
  if(!Object.keys(f.boxes||{}).length)h='<div class="tile grey">no fleet data (collector down?)</div>';
  document.getElementById('fleet').innerHTML=h;
  const e=f.eran||{}; const sy=f.system||{};
  document.getElementById('eran').innerHTML=(e.state==='retired'?('<div class="tile grey"><b>🧬 ERAN · eran1</b><div class=m>disabled + archived by Iddo\'s order · not probed<br>'+esc(e.retired||'')+'</div></div>'):('<div class="tile '+(e.up?'up':'down')+'"><b>🧬 ERAN · eran1</b><div class=m>'+(e.up?('beat '+esc(e.beat)+' · '+esc(e.beats_per_s)+'/s · unit '+esc(e.unit)+' · protos '+esc(e.prototypes)):'window not answering: '+esc(e.error))+'</div></div>'))
    +'<div class="tile grey"><b>💻 this PC</b><div class=m>CPU '+esc(sy.cpu_pct)+'% · RAM '+esc(sy.mem_pct)+'%'+(sy.disks?'<br>'+Object.entries(sy.disks).map(([d,g])=>d+' '+Math.round(g)+'G').join(' · '):'')+'</div></div>';
  let dh='';
  for(const d of S.doors){const href=d.tailnet||d.local; dh+='<div class="tile door '+(d.up?'up':'down')+'"><b>'+d.icon+' <a href="'+esc(href)+'" target=_blank>'+esc(d.name)+'</a></b><div class=m>'+esc(d.what)+'</div><div class=l>'+(d.up?('HTTP '+d.code+' · '+d.ms+' ms'):('DOWN · '+esc(d.error)))+'</div><div class=l>'+(d.tailnet?esc(d.tailnet):('PC only: '+esc(d.local)))+'</div></div>'}
  document.getElementById('doors').innerHTML=dh;
  const M=S.models||{};
  const gb=M.gptoss_boxes||[];
  const modeMap={'MONOLITH':['⚙️ MONOLITH · מונולית — one 480B over eran2+3+4','up'],'COUNCIL':['⚖️ COUNCIL · מועצה — four boxes, four giants','up'],'GPTOSS':['🟢 GPT-OSS 120B on '+gb.length+' boxes ('+gb.join(', ')+') · 480B down, pending Iddo','up']};
  let mm=modeMap[M.mode]||[(M.mode||'?'),'grey'];
  // 2026-09-15 (W6): MONOLITH is computed from "qwen480-pp container Up" -- right for the
  // COLIBRI resource gate (the container holds eran4's memory), wrong as a green light:
  // it painted green while /health answered 502. Green only when the 480B really serves.
  const q480serving=(q.health_code===200);
  if(M.mode==='MONOLITH'&&!q480serving)mm=['⚠️ MONOLITH container up · 480B NOT serving (/health '+(q.health_code==null?'no answer':q.health_code)+', '+(q.state||'?')+') · pending Iddo','down'];
  document.getElementById('modelabel').textContent='MODE: '+mm[0];
  document.getElementById('modebox').className='tile '+mm[1];
  const RR=M.retired_running||[];
  document.getElementById('modewhy').textContent='480B '+(M.q480_up?(q480serving?'UP':'container up, NOT serving'):'down')+' · gpt-oss-120b on '+gb.length+' · Colibri '+(M.colibri_up?'UP':'retired')+' · coder-train '+(M.coder_train_up?'RUNNING (83.7 GB)':'retired')+(RR.length?(' · ⚠ RETIRED BUT RUNNING: '+RR.join(', ')):'')+' · checked '+esc(M.checked_at||'?');
  const R=M.router||{};
  document.getElementById('routerline').innerHTML=R.code==200
    ? ('🔌 harness alma-router '+esc(R.url)+' — HTTP 200 in '+R.ms+' ms, serving: '+(R.models&&R.models.length?R.models.map(esc).join(', '):'<b style="color:#c0392b">NOTHING — data:[] · ההרנס חי, אבל ריק</b>'))
    : ('🔌 harness alma-router '+esc(R.url)+' — <b style="color:#c0392b">no answer</b> '+esc(R.code||''));
  let gh='';
  for(const [k,b] of Object.entries(M.boxes||{})){
    const ok=b.reachable===true, mem=b.mem||{};
    const us=Object.entries(b.units||{}).map(([u,st])=>u.replace('.service','')+': '+st).join('<br>')||'(none of the tracked units)';
    gh+='<div class="tile '+(ok?'up':'down')+'"><b>'+esc(k)+'</b><div class=m>'+(ok?
       ('RAM '+mem.used_gb+'/'+mem.total_gb+' G · '+mem.avail_gb+' G available<br>'+us):('unreachable: '+esc(b.error)))+'</div></div>';
  }
  document.getElementById('giants').innerHTML=gh||'<div class="tile grey">no model data</div>';
  document.getElementById('ram').innerHTML=(S.ramchat||[]).map(r=>'<div><span>'+esc(r.who)+'</span> '+esc(r.text)+'</div>').join('');
  renderModels(); renderDevices(); renderQueue();
  const C=S.cache||{};
  document.getElementById('cache').innerHTML='מדידות: רשת לפני '+age(C.fast_age_s)+
    ' · צי (SSH) לפני '+age(C.slow_age_s)+(C.prober?'':' <b style="color:#c0392b">(אין רקע)</b>')+
    ((C.fast_age_s!=null&&C.fast_age_s>120)?' <span class=stale>— ישן</span>':'');
}
async function refresh(force){try{const r=await fetch('/control/api/state'+(force?'?force=1':''),{cache:'no-store'});S=await r.json();render()}catch(e){msg('state fetch failed: '+e,false)}}
async function act(name,extra){
  const labels={'keshev.pause':'PAUSE the microphone? / להשהות את המיקרופון?','keshev.listen':'LISTEN — lift the pause? / להרים את ההשהיה?','start.keshev':'Open the KESHEV window? (refused if one is alive)','start.cockpit':'Start the COCKPIT? (refused if :8790 answers)','start.portal':'Start the QUEST PORTAL :8899?',
    'fleet.480b.start':'START the Qwen3-Coder-480B cluster on eran2+eran3+eran4? Takes minutes; refused if already up/loading. / להתחיל את מקבץ 480B?',
    'fleet.480b.stop':'STOP the Qwen3-Coder-480B cluster — docker rm -f on eran2+eran3+eran4? This kills it for anyone using it right now. / לעצור את מקבץ 480B — יפגע בכל מי שמשתמש בו כרגע?',
    'models.colibri.up':'Raise COLIBRI GLM-5.2 744B on eran4? Refused while the 480B holds that box. Loading 358 GB takes many minutes. / להעלות את קוליברי?',
    'models.colibri.down':'Lower COLIBRI on eran4? / להוריד את קוליברי?',
    'models.codertrain.stop':'STOP the coder training on eran1 and give back 83.7 GB?\n\nIt finishes the current step, writes its 47 GB checkpoint (~8 min) and exits cleanly. --resume auto picks up exactly here. ERAN is NOT touched.\n\nלעצור את אימון הקודר ולשחרר 83.7 גיגה? שום דבר לא יאבד.',
    'models.codertrain.start':'Resume the coder training on eran1 (it will take 83.7 GB again)?'};
  const SAFE=new Set(['fleet.probe.eran2','fleet.probe.eran3','fleet.probe.eran4','fleet.480b.status','fleet.480b.testcompletion','models.status','models.colibri.probe']);
  if(!SAFE.has(name) && !confirm(labels[name]||name))return;
  try{const r=await fetch('/control/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({key:KEY,action:name},extra||{}))});
    const j=await r.json(); msg(name+' → '+j.result+(j.detail&&j.detail.reason?(' — '+j.detail.reason):''),j.ok); setTimeout(()=>refresh(true),1500)}catch(e){msg('action failed: '+e,false)}
}
document.getElementById('asktext').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});
render(); setInterval(()=>refresh(false),15000);
</script></html>"""


# ------------------------------------------------------- the page's own syntax check
def check_page_js():
    """Parse the page's <script> blocks with node --check.

    Added 2026-09-11 after finding that the entire CONTROL script had been a
    SyntaxError for two days (a raw newline inside a JS string literal), which
    is invisible from the server side: the HTML still renders, still returns
    200, still looks right in curl -- and every tile is frozen on its static
    placeholder. Returns (ok, detail). node absent -> ("skipped", why).
    """
    import shutil
    import tempfile
    blocks = re.findall(r"<script>(.*?)</script>", PAGE_HTML, re.S)
    if not blocks:
        return False, "no <script> block in PAGE_HTML"
    node = shutil.which("node")
    if not node:
        return "skipped", "node not on PATH"
    src = "\n;\n".join(b.replace("__STATE__", "{}").replace("__KEY__", "K")
                       .replace("__CSRF__", "C") for b in blocks)
    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(src)
        p = subprocess.run([node, "--check", path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           creationflags=_NOWIN)
        if p.returncode == 0:
            return True, "%d script block(s), %d chars, node parses them" % (len(blocks), len(src))
        return False, (p.stderr or p.stdout or "")[:600]
    except Exception as e:                                    # noqa: BLE001
        return "skipped", repr(e)[:200]
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------- decoy demo
def demo_decoy(tmpdir):
    """Run pause/listen against a TEMP state dir and apply the real watchdog guard to it."""
    global STATE_DIR
    tmpdir = os.path.abspath(tmpdir)
    assert os.path.normcase(tmpdir) != os.path.normcase(LIVE_STATE_DIR), "refusing: that is the LIVE state dir"
    assert "keshev-next" not in tmpdir.lower(), "refusing: decoy must live outside keshev-next"
    os.makedirs(tmpdir, exist_ok=True)
    STATE_DIR = tmpdir
    print("DECOY state dir:", tmpdir)
    print("live state dir :", LIVE_STATE_DIR, "(untouched)")
    # the real guard, imported from the real watchdog, pointed at the decoy path
    sys.path.insert(0, r"D:\CLAUDE\tools\watchdogs")
    import keshev_delivery_watchdog as wd
    decoy = os.path.join(tmpdir, "PAUSED")
    wd.PAUSED = decoy
    facts = {"paused": True, "paused_for_min": 999.0}      # "sat for 999 minutes"

    print("\n[1] keshev.pause on the decoy ->", keshev_pause("decoy demo, Iddo's 10:40 order")[0])
    body = _read(decoy)
    print(body)
    print("looks_like_receipt =", all(k in body for k in ("who", "why")) or "restore" in body)
    r = wd.clear_stale_pause(facts)
    print("watchdog.clear_stale_pause(999 min) ->", repr(r), "| file still exists:", os.path.exists(decoy))
    print("=> the real guard LEAVES a dashboard pause alone however old it is" if r is None and os.path.exists(decoy)
          else "=> UNEXPECTED: the guard did not spare it")

    print("\n[2] keshev.listen on the decoy ->", keshev_listen()[0])
    print("PAUSED exists:", os.path.exists(decoy), "| receipts beside it:",
          [f for f in os.listdir(tmpdir) if f.startswith("PAUSED.receipt")])

    print("\n[3] negative control: a BARE timestamp (the 2026-09-03 / 09-07 orphan shape)")
    with open(decoy, "w", encoding="utf-8") as f:
        f.write(datetime.now().isoformat())
    r = wd.clear_stale_pause(facts)
    print("watchdog.clear_stale_pause(999 min) ->", repr(r)[:160])
    print("PAUSED exists:", os.path.exists(decoy), "| dir:", sorted(os.listdir(tmpdir)))
    print("=> the same guard CLEARS the unsigned shape: the gate discriminates, it has refused something")
    audit("demo.decoy", "ran", {"dir": tmpdir}, who="claude-cli-FABLE-dashboard")
