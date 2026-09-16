#!/usr/bin/env python
"""ERAN Dashboard — floating, always-on-top, TABBED fleet widget.

Tabs:
  FLEET — PC + eran1..eran4: temp/util/mem, online+ping, live up/down throughput,
          training indicator, and the 200G fabric (brfab on eran1) status.
  AI    — Claude usage today (transcripts/tokens, parsed from ~/.claude) + Grok route status.
  PC    — CPU%, RAM, disk, GPU temp/util, live net up/down, internet reachability.

Frameless, draggable by title bar. Custom Minimize (collapse) + Close. Bright theme.
Flicker-free: built once, labels updated in place. Three background pollers
(fast PC ~1s, nodes ~15s, AI ~60s). Real data only — no fabricated numbers.

Launch:  pythonw eran_dashboard.py
"""
import tkinter as tk
from tkinter import ttk
import subprocess, threading, json, time, datetime, os, socket, glob, re
import http.server
from typing import Any

try:
    import psutil
except Exception:
    psutil = None

# Real usage snapshots (vendored stdlib clients): Claude OAuth usage (weekly/5h
# windows + reset) and Grok billing (monthly used/limit + reset). Graceful if absent.
try:
    from claude_usage_client import fetch_claude_usage_snapshot as _fetch_claude_snap
    from grok_usage_client import fetch_usage_snapshot as _fetch_grok_snap
except Exception:
    def _fetch_claude_snap():
        return {"ok": False, "error": "client missing"}
    def _fetch_grok_snap():
        return {"ok": False, "error": "client missing"}

# System-tray support (minimize to tray). Falls back to collapse if unavailable.
try:
    import pystray
    from PIL import Image as _PILImage, ImageDraw as _PILDraw
    _HAVE_TRAY = True
except Exception:
    _HAVE_TRAY = False

NODES    = ["eran1", "eran2", "eran3", "eran4"]
# Authoritative fleet map — current IPs (2026-07-03). The dashboard connects with
# EXPLICIT -i <key> + user@ip so it does NOT depend on the ambient ~/.ssh config
# (which has drifted: two included configs disagree). eran1 is the wired head node
# and needs the NVIDIA-Sync key; eran2/3/4 use the default id_ed25519 key.
# 2026-09-11 WAVE A2: all four were stale (eran3 .20 and eran4 .12 never existed).
# Tailnet addresses from D:/CLAUDE/fleet_inventory.json -- they survive router swaps.
NODE_IP  = {"eran1": "<tailnet-ip>", "eran2": "<tailnet-ip>", "eran3": "<tailnet-ip>", "eran4": "<tailnet-ip>"}
NODE_USER = {"eran1": "eran1", "eran2": "eran2", "eran3": "eran3", "eran4": "eran4"}
_NVSYNC_KEY = r"C:\Users\<user>\AppData\Local\NVIDIA Corporation\Sync\config\nvsync.key"
_DEFAULT_KEY = os.path.expanduser(r"~\.ssh\id_ed25519")
NODE_KEY = {"eran1": _NVSYNC_KEY, "eran2": _DEFAULT_KEY, "eran3": _DEFAULT_KEY, "eran4": _DEFAULT_KEY}
STATUS_FILE = r"D:\CLAUDE\eran-status\status.json"
METRICS_FILE = r"D:\CLAUDE\eran-live\logs\metrics.jsonl"   # Eran-LIVE training stats
CLAUDE_PROJ = r"C:\Users\<user>\.claude\projects"
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

BG="#ffffff"; BAR="#0f4c81"; BAR_TXT="#ffffff"; TXT="#1f2937"; SUB="#6b7280"
OK="#16a34a"; WARN="#f59e0b"; HOT="#dc2626"; OFF="#9ca3af"; LINE="#e5e7eb"; HDR="#0f4c81"; ACC="#2563eb"

_state: dict[str, Any] = {"pc": {}, "nodes": {}, "fabric": {}, "ai": {},
                          "eran": {}, "projects": {}, "last": "—"}
_lock  = threading.Lock()
_loss_hist: list[float] = []   # recent Eran-LIVE loss values for the sparkline


# ---------- helpers --------------------------------------------------------
def _temp_color(t: Any) -> str:
    """Return the display color for a temperature-like numeric value."""
    try: t = float(t)
    except Exception: return SUB
    return OK if t < 50 else (WARN if t < 72 else HOT)

def _pct_color(p: Any) -> str:
    """Color for a 0-100 usage percentage (green/amber/red)."""
    try: p = float(p)
    except Exception: return SUB
    return OK if p < 60 else (WARN if p < 85 else HOT)

def _sev_color(sev: Any) -> str:
    """Color for an ALMA-Govern severity (0 OK,1 INFO,2 WARN,3 CRITICAL)."""
    s = _safe_int(sev)
    if s is None: return SUB
    return {0: OK, 1: ACC, 2: WARN, 3: HOT}.get(s, SUB)

def _fmt_bw(b: Any) -> str:
    """Format a bytes-per-second value for the compact dashboard labels."""
    if b is None: return "—"
    try:
        b = float(b)
        if b >= 1e6: return f"{b/1e6:.0f}M"
        if b >= 1e3: return f"{b/1e3:.0f}K"
        return f"{b:.0f}"
    except Exception:
        return "—"

def _fmt_n(n: Any) -> str:
    """Format large integer counters for narrow UI rows."""
    try: n = int(n)
    except Exception: return "—"
    if n >= 1e9: return f"{n/1e9:.2f}B"
    if n >= 1e6: return f"{n/1e6:.1f}M"
    if n >= 1e3: return f"{n/1e3:.1f}K"
    return str(n)

def _safe_int(v: Any) -> int | None:
    """Parse an int without letting malformed command output escape."""
    try:
        return int(str(v).strip())
    except Exception:
        return None

def _run_text(cmd: list[str], timeout: float) -> str:
    """Run a command and return stdout, swallowing subprocess failures."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              creationflags=CNW).stdout
    except Exception:
        return ""

def _set_state(key: str, value: Any) -> None:
    """Replace one top-level shared state bucket under the lock."""
    with _lock:
        _state[key] = value

def _set_node_state(node: str, value: dict[str, Any]) -> None:
    """Update a single node entry under the shared state lock."""
    with _lock:
        nodes = dict(_state.get("nodes", {}))
        nodes[node] = dict(value)
        _state["nodes"] = nodes

def _set_pc_state(value: dict[str, Any]) -> None:
    """Update PC state and the last-refresh marker atomically."""
    with _lock:
        _state["pc"] = dict(value)
        _state["last"] = datetime.datetime.now().strftime("%H:%M:%S")

def _snapshot_state() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """Return a UI-safe snapshot of all shared state."""
    with _lock:
        pc = dict(_state.get("pc", {}))
        nodes = {k: dict(v) for k, v in dict(_state.get("nodes", {})).items()}
        fabric = dict(_state.get("fabric", {}))
        ai = dict(_state.get("ai", {}))
        last = str(_state.get("last", "—"))
    return pc, nodes, fabric, ai, last

def _add_rates(d: dict[str, Any], prev: tuple[float, int, int] | None, now: float) -> tuple[float, int, int] | None:
    """Add down/up rates to a byte-counter dict and return the next baseline."""
    rx, tx = d.get("rx"), d.get("tx")
    if rx is None or tx is None:
        return None
    if prev:
        pt, prx, ptx = prev; dt = max(0.5, now - pt)
        d["down"] = (rx - prx) / dt
        d["up"] = (tx - ptx) / dt
    return now, rx, tx

def _internet_ok() -> bool:
    """Check basic internet reachability without raising into pollers."""
    try:
        s = socket.create_connection(("8.8.8.8", 53), 1.0); s.close(); return True
    except Exception:
        return False

def _port_up(p: int) -> bool:
    """Check whether a local TCP port accepts connections."""
    try:
        s = socket.create_connection(("127.0.0.1", p), 0.3); s.close(); return True
    except Exception:
        return False

def _ping_ms(ip: str) -> int | None:
    """Return one Windows ping latency in ms, or None for any failure."""
    out = _run_text(["ping", "-n", "1", "-w", "800", ip], 3)
    try:
        m = re.search(r"[=<]\s*(\d+)\s*ms", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None

def _local_gpu() -> tuple[str | None, str | None]:
    """Read local GPU temperature/utilization from nvidia-smi."""
    out = _run_text(["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu",
                     "--format=csv,noheader,nounits"], 5)
    try:
        rows = [r for r in out.strip().splitlines() if r.strip()]
        p = [x.strip() for x in rows[0].split(",")]
        return (p[0] or None), (p[1] or None)
    except Exception:
        return None, None


_REMOTE = (
    "nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total "
    "--format=csv,noheader,nounits 2>/dev/null; echo '==='; "
    "ps -eo args= 2>/dev/null | grep -Ei 'train|revital|gist|finetune|torchrun|deepspeed' "
    "| grep -v grep | head -1; echo '==='; "
    "IF=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'dev \\K\\S+'); echo IF=$IF; "
    "cat /sys/class/net/$IF/statistics/rx_bytes /sys/class/net/$IF/statistics/tx_bytes 2>/dev/null; echo '==='; "
    "if [ -e /sys/class/net/brfab ]; then echo FAB=$(cat /sys/class/net/brfab/operstate) "
    "$(cat /sys/class/net/brfab/speed 2>/dev/null); "
    "cat /sys/class/net/brfab/statistics/rx_bytes /sys/class/net/brfab/statistics/tx_bytes 2>/dev/null; "
    "for ip in <fabric-ip> <fabric-ip>; do ping -c1 -W1 $ip >/dev/null 2>&1 && echo \"$ip up\" || echo \"$ip down\"; done; fi; "
    # Storm-guard: ask ALMA-Govern for this node's worst severity (read-only, advisory,
    # never acts). Emits one line GOV=<sev> <label>. Absent SDK -> silently skipped.
    "echo '==='; if [ -d ~/alma-govern ]; then "
    "cd ~/alma-govern && python3 -m alma_govern.cli check --json 2>/dev/null "
    "| python3 -c \"import sys,json;"
    "d=json.load(sys.stdin);print('GOV=%d %s'%(d['severity'],d['severity_label']))\" 2>/dev/null; fi"
)

def _parse_node(out: str) -> dict[str, Any]:
    """Parse the compact remote SSH payload for one fleet node."""
    info = {"online": True, "temp": "—", "util": "—", "mem": "—", "train": None,
            "rx": None, "tx": None, "fab": None, "gov_sev": None, "gov_label": None}
    try:
        parts = out.split("===")
        if parts:
            rows = [r.strip() for r in parts[0].strip().splitlines() if r.strip()]
            if rows:
                p = [x.strip() for x in rows[0].split(",")]
                if len(p) >= 4:
                    info["temp"], info["util"] = p[0], p[1]
                    used, total = _safe_int(p[2]), _safe_int(p[3])
                    info["mem"] = f"{used/1024:.0f}/{total/1024:.0f}G" if used is not None and total is not None else f"{p[2]}/{p[3]}"
        if len(parts) > 1:
            t = parts[1].strip().splitlines()
            if t and t[0].strip(): info["train"] = t[0].strip()[:28]
        if len(parts) > 2:
            ln = [r.strip() for r in parts[2].strip().splitlines() if r.strip()]
            nums = [_safe_int(x) for x in ln if x.isdigit()]
            nums = [x for x in nums if x is not None]
            if len(nums) >= 2:
                info["rx"], info["tx"] = nums[0], nums[1]
        if len(parts) > 3 and "FAB=" in parts[3]:
            fb = {"state": "—", "speed": "—", "rx": None, "tx": None, "peers_up": 0, "peers_total": 0}
            for ln in parts[3].strip().splitlines():
                ln = ln.strip()
                if ln.startswith("FAB="):
                    seg = ln[4:].split()
                    if seg: fb["state"] = seg[0]
                    if len(seg) > 1: fb["speed"] = seg[1]
                elif ln.isdigit():
                    val = _safe_int(ln)
                    if val is None:
                        continue
                    if fb["rx"] is None: fb["rx"] = val
                    elif fb["tx"] is None: fb["tx"] = val
                elif " up" in ln or " down" in ln:
                    fb["peers_total"] += 1
                    if ln.endswith(" up"): fb["peers_up"] += 1
            info["fab"] = fb
        # Storm-guard severity — scan the whole payload for the GOV= line so it
        # doesn't matter which trailing segment it landed in.
        m = re.search(r"GOV=(\d+)\s+(\S+)", out)
        if m:
            info["gov_sev"] = _safe_int(m.group(1))
            info["gov_label"] = m.group(2)
    except Exception:
        pass
    return info

def _node_ssh_cmd(n: str) -> list[str]:
    """Build the read-only SSH command for one node from the authoritative fleet
    map — explicit -i <key> + user@ip so it never depends on the ambient ~/.ssh
    config (which has drifted). Falls back to a bare hostname if no IP is known."""
    ip = NODE_IP.get(n)
    user = NODE_USER.get(n, n)
    target = f"{user}@{ip}" if ip else n
    cmd = ["ssh", "-o", "ConnectTimeout=6", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new"]
    key = NODE_KEY.get(n)
    if key and os.path.exists(key):
        cmd += ["-i", key]
    cmd += [target, _REMOTE]
    return cmd

def _poll_node(n: str) -> dict[str, Any]:
    """Poll one node over SSH and return an offline marker on any failure."""
    out = _run_text(_node_ssh_cmd(n), 16)
    if "===" not in out:
        return {"online": False}
    try:
        return _parse_node(out)
    except Exception:
        return {"online": False}


def _claude_usage() -> dict[str, Any]:
    """Summarize today's Claude transcript token usage."""
    today = datetime.date.today()
    tin = tout = tcache = 0; mb = 0.0; nfiles = 0
    try:
        files = glob.glob(os.path.join(CLAUDE_PROJ, "**", "*.jsonl"), recursive=True)
    except Exception:
        files = []
    for f in files:
        try:
            if datetime.date.fromtimestamp(os.path.getmtime(f)) != today: continue
        except Exception:
            continue
        nfiles += 1
        try: mb += os.path.getsize(f) / 1e6
        except Exception: pass
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"usage"' not in line: continue
                    try: ev = json.loads(line)
                    except Exception: continue
                    msg = ev.get("message")
                    u = msg.get("usage") if isinstance(msg, dict) else None
                    if not u and isinstance(ev.get("usage"), dict): u = ev["usage"]
                    if isinstance(u, dict):
                        tin   += _safe_int(u.get("input_tokens", 0)) or 0
                        tout  += _safe_int(u.get("output_tokens", 0)) or 0
                        tcache += (_safe_int(u.get("cache_read_input_tokens", 0)) or 0) + (_safe_int(u.get("cache_creation_input_tokens", 0)) or 0)
        except Exception:
            pass
    return {"files": nfiles, "mb": round(mb, 1), "in": tin, "out": tout, "cache": tcache}

def _grok_status() -> dict[str, str]:
    """Report Grok local route status and newest known log date."""
    route = any(_port_up(p) for p in (8787, 8055, 8767, 8080))
    last = "—"
    try:
        logs = glob.glob(r"D:\grok\logs\*")
        if logs:
            newest = max(logs, key=os.path.getmtime)
            last = datetime.datetime.fromtimestamp(os.path.getmtime(newest)).strftime("%m-%d")
    except Exception:
        pass
    return {"route": "UP" if route else "DOWN", "last": last}


def _eran_metrics() -> dict[str, Any]:
    """Latest Eran-LIVE training stats — read only the LAST line of metrics.jsonl
    (seek to the file tail so it stays cheap even as the log grows to millions of steps)."""
    try:
        with open(METRICS_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", "ignore").strip().splitlines()
        for line in reversed(tail):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                d = json.loads(line)
                return {"step": d.get("step"), "loss": d.get("loss"),
                        "ema": d.get("ema_loss"), "sps": d.get("steps_per_s"),
                        "lr": d.get("lr")}
    except Exception:
        pass
    return {}

def _active_projects() -> dict[str, Any]:
    """REAL active projects — ground truth from RUNNING processes, not the stale
    hand-curated status.json. Maps each live process command line to its
    D:\\CLAUDE\\<project> folder and counts processes per project. Live every poll."""
    seen: dict[str, int] = {}
    try:
        if psutil:
            for pr in psutil.process_iter(["name", "cmdline"]):
                try:
                    cl = " ".join(pr.info.get("cmdline") or [])
                    if not cl:
                        continue
                    # capture the project folder right under .../CLAUDE/
                    m = re.search(r"[A-Za-z]:[\\/]CLAUDE[\\/]([^\\/\s\"']+)", cl)
                    if not m:
                        continue
                    proj = m.group(1)
                    # skip infra/build noise and worktree wrapper dir
                    if proj.startswith(".") or proj.lower() in ("dist", "build", "dist_alma", "build_alma"):
                        continue
                    seen[proj] = seen.get(proj, 0) + 1
                except Exception:
                    continue
    except Exception:
        pass
    items = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
    lst = [f"● {name}  ×{n}" for name, n in items]
    return {"updated": datetime.datetime.now().strftime("%H:%M:%S"),
            "list": lst, "procs": sum(seen.values())}

def _snapshot_eran() -> tuple[dict[str, Any], dict[str, Any], list[float]]:
    """UI-safe snapshot of Eran metrics, active projects, and the loss history."""
    with _lock:
        eran = dict(_state.get("eran", {}))
        proj = dict(_state.get("projects", {})) if isinstance(_state.get("projects"), dict) else {}
        hist = list(_loss_hist)
    return eran, proj, hist


# ---------- pollers --------------------------------------------------------
def _pc_poller() -> None:
    """Poll local PC metrics forever, never letting failures kill the thread."""
    try:
        prev = psutil.net_io_counters() if psutil else None
    except Exception:
        prev = None
    pt = time.time()
    while True:
        try:
            if psutil:
                cpu = psutil.cpu_percent(interval=1.0)
                vm = psutil.virtual_memory()
                now = time.time(); nio = psutil.net_io_counters(); dt = max(0.2, now - pt)
                up = (nio.bytes_sent - prev.bytes_sent) / dt if prev else 0
                down = (nio.bytes_recv - prev.bytes_recv) / dt if prev else 0
                prev = nio; pt = now
                try: disk = psutil.disk_usage("D:\\").percent
                except Exception: disk = psutil.disk_usage("C:\\").percent
                gt, gu = _local_gpu()
                pc = {"cpu": cpu, "ram": vm.percent,
                      "ram_gb": f"{vm.used/1e9:.0f}/{vm.total/1e9:.0f}G",
                      "disk": disk, "gpu_temp": gt, "gpu_util": gu,
                      "up": up, "down": down, "inet": _internet_ok()}
            else:
                pc = {"cpu": None}
                time.sleep(1)
            _set_pc_state(pc)
        except Exception:
            time.sleep(1)

def _node_poller() -> None:
    """Poll remote nodes forever, isolating each node and cycle failure."""
    prev: dict[str, tuple[float, int, int]] = {}
    fab_prev: tuple[float, int, int] | None = None
    while True:
        try:
            for n in NODES:
                try:
                    r = _poll_node(n)
                    now = time.time()
                    if r.get("online"):
                        next_prev = _add_rates(r, prev.get(n), now)
                        if next_prev:
                            prev[n] = next_prev
                    if r.get("online"):
                        r["ping"] = _ping_ms(NODE_IP.get(n, ""))
                    if r.get("fab"):
                        fb = r["fab"]
                        next_fab_prev = _add_rates(fb, fab_prev, now)
                        if next_fab_prev:
                            fab_prev = next_fab_prev
                        _set_state("fabric", dict(fb))
                    _set_node_state(n, r)
                except Exception:
                    _set_node_state(n, {"online": False})
        except Exception:
            pass
        time.sleep(15)

def _ai_poller() -> None:
    """Poll AI usage/status forever without allowing file/network errors to escape.
    Adds the REAL Claude (weekly) + Grok (monthly) usage snapshots, with resets."""
    while True:
        try:
            ai = {"claude": _claude_usage(), "grok": _grok_status()}
            try:
                ai["claude_snap"] = _fetch_claude_snap()
            except Exception as e:
                ai["claude_snap"] = {"ok": False, "error": repr(e)[:40]}
            try:
                ai["grok_snap"] = _fetch_grok_snap()
            except Exception as e:
                ai["grok_snap"] = {"ok": False, "error": repr(e)[:40]}
            _set_state("ai", ai)
        except Exception:
            pass
        time.sleep(60)

def _eran_poller() -> None:
    """Poll Eran-LIVE training (fast ~2s) and active projects (slow ~30s) forever."""
    last_proj = 0.0
    while True:
        try:
            m = _eran_metrics()
            _set_state("eran", m)
            lv = m.get("loss")
            if isinstance(lv, (int, float)):
                with _lock:
                    _loss_hist.append(float(lv))
                    if len(_loss_hist) > 120:
                        del _loss_hist[:-120]
            now = time.time()
            if now - last_proj > 30:
                _set_state("projects", _active_projects())
                last_proj = now
        except Exception:
            pass
        time.sleep(2)


# ---------- GUI ------------------------------------------------------------
class Dash:
    W = 400
    H = 680

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.collapsed = False
        self._drag = {"x": 0, "y": 0}
        self.r = {}              # label registry
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        try: root.attributes("-alpha", 0.97)
        except Exception: pass
        sw = root.winfo_screenwidth()
        root.geometry(f"{self.W}x{self.H}+{sw - self.W - 24}+52")
        self._bar()
        self.body = tk.Frame(root, bg=BG); self.body.pack(fill="both", expand=True)
        self._tabs()
        self._tick()
        self._keep_top()
        self._setup_tray()

    # ---------------------------------------------------------------- system tray
    def _tray_image(self):
        img = _PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = _PILDraw.Draw(img)
        d.ellipse((3, 3, 61, 61), fill="#0f4c81")
        d.ellipse((25, 23, 39, 37), fill="#16a34a")   # green = Eran live
        return img

    def _setup_tray(self) -> None:
        self.tray = None
        if not _HAVE_TRAY:
            return
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.MenuItem("Quit", self._tray_quit),
            )
            self.tray = pystray.Icon("almaware_eran", self._tray_image(),
                                     "ALMAWARE · ERAN", menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception:
            self.tray = None

    def _to_tray(self) -> None:
        if self.tray is None:
            self._toggle()            # no tray backend → fall back to collapse
            return
        self.root.withdraw()          # hide window; tray icon restores it

    def _tray_show(self, *_a) -> None:
        self.root.after(0, self._restore)

    def _restore(self) -> None:
        self.root.deiconify()
        try: self.root.attributes("-topmost", True)
        except Exception: pass

    def _tray_quit(self, *_a) -> None:
        if self.tray is not None:
            try: self.tray.stop()
            except Exception: pass
        self.root.after(0, self.root.destroy)

    def _keep_top(self) -> None:
        # Re-assert always-on-top so other apps don't bury the widget.
        # Raises z-order only (SetWindowPos HWND_TOPMOST) — does NOT steal keyboard
        # focus and never calls SetForegroundWindow, per the no-screen-hijack rule.
        try: self.root.attributes("-topmost", True)
        except Exception: pass
        self.root.after(3000, self._keep_top)

    def _bar(self) -> None:
        bar = tk.Frame(self.root, bg=BAR, height=32); bar.pack(fill="x"); bar.pack_propagate(False)
        ttl = tk.Label(bar, text="●  ALMAWARE · ERAN", bg=BAR, fg=BAR_TXT, font=("Segoe UI", 11, "bold"))
        ttl.pack(side="left", padx=10)
        cl = tk.Label(bar, text="✕", bg=BAR, fg=BAR_TXT, font=("Segoe UI", 11, "bold"), cursor="hand2", padx=8)
        cl.pack(side="right"); cl.bind("<Button-1>", lambda e: self._tray_quit())
        mn = tk.Label(bar, text="⤓", bg=BAR, fg=BAR_TXT, font=("Segoe UI", 11, "bold"), cursor="hand2", padx=8)
        mn.pack(side="right"); mn.bind("<Button-1>", lambda e: self._to_tray())   # minimize to tray
        cb = tk.Label(bar, text="—", bg=BAR, fg=BAR_TXT, font=("Segoe UI", 11, "bold"), cursor="hand2", padx=8)
        cb.pack(side="right"); cb.bind("<Button-1>", lambda e: self._toggle())     # collapse to bar
        for w in (bar, ttl):
            w.bind("<Button-1>", lambda e: self._grab(e)); w.bind("<B1-Motion>", lambda e: self._move(e))

    def _grab(self, e: tk.Event) -> None: self._drag = {"x": e.x, "y": e.y}
    def _move(self, e: tk.Event) -> None:
        self.root.geometry(f"+{self.root.winfo_x()+e.x-self._drag['x']}+{self.root.winfo_y()+e.y-self._drag['y']}")
    def _toggle(self) -> None:
        if self.collapsed:
            self.body.pack(fill="both", expand=True); self.root.geometry(f"{self.W}x{self.H}")
        else:
            self.body.pack_forget(); self.root.geometry(f"{self.W}x32")
        self.collapsed = not self.collapsed

    # ---- builders ----
    def _kv(self, parent: tk.Widget, key: str, init: str = "—", color: str = TXT, bold: bool = False) -> tk.Label:
        row = tk.Frame(parent, bg=BG); row.pack(fill="x", padx=14, pady=1)
        tk.Label(row, text=key, bg=BG, fg=SUB, font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        v = tk.Label(row, text=init, bg=BG, fg=color, font=("Consolas", 10, "bold" if bold else "normal"), anchor="w")
        v.pack(side="left")
        return v

    def _mkbar(self, parent: tk.Widget, w: int = 90, h: int = 11) -> dict:
        c = tk.Canvas(parent, width=w, height=h, bg="#e9edf2", highlightthickness=0, bd=0)
        fill = c.create_rectangle(0, 0, 0, h, fill=OK, width=0)
        c.pack(side="left", padx=(4, 0))
        return {"c": c, "fill": fill, "w": w, "h": h}

    def _setbar(self, bar: dict, pct: Any, color: str) -> None:
        try: p = max(0.0, min(100.0, float(pct)))
        except Exception: p = 0.0
        bar["c"].coords(bar["fill"], 0, 0, bar["w"] * p / 100.0, bar["h"])
        bar["c"].itemconfig(bar["fill"], fill=color)

    def _kvbar(self, parent: tk.Widget, key: str) -> tuple:
        row = tk.Frame(parent, bg=BG); row.pack(fill="x", padx=14, pady=2)
        tk.Label(row, text=key, bg=BG, fg=SUB, font=("Segoe UI", 9), width=9, anchor="w").pack(side="left")
        v = tk.Label(row, text="—", bg=BG, fg=TXT, font=("Consolas", 10, "bold"), width=11, anchor="w")
        v.pack(side="left")
        bar = self._mkbar(row)
        return v, bar

    def _hdr(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text, bg=BG, fg=HDR, font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(8, 1))
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x", padx=12)

    def _tabs(self) -> None:
        style = ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#e8eef5", foreground=TXT,
                        font=("Segoe UI", 9, "bold"), padding=(14, 5))
        style.map("TNotebook.Tab", background=[("selected", BAR)], foreground=[("selected", "#ffffff")])
        nb = ttk.Notebook(self.body); nb.pack(fill="both", expand=True)
        f_eran = tk.Frame(nb, bg=BG); f_fleet = tk.Frame(nb, bg=BG); f_ai = tk.Frame(nb, bg=BG); f_pc = tk.Frame(nb, bg=BG)
        nb.add(f_eran, text="ERAN"); nb.add(f_fleet, text="FLEET"); nb.add(f_ai, text="AI"); nb.add(f_pc, text="PC")
        self._build_eran(f_eran); self._build_fleet(f_fleet); self._build_ai(f_ai); self._build_pc(f_pc)
        self.footer = tk.Label(self.body, text="—", bg=BG, fg=SUB, font=("Segoe UI", 8))
        self.footer.pack(side="bottom", pady=3)

    def _build_eran(self, p: tk.Widget) -> None:
        self._hdr(p, "ERAN  ·  LIVE TRAINING  (learning from עידו's voice)")
        self.er_step = self._kv(p, "step", "—", color=ACC, bold=True)
        self.er_loss = self._kv(p, "loss", "—", color=OK, bold=True)
        self.er_ema  = self._kv(p, "ema loss", "—")
        self.er_sps  = self._kv(p, "steps/sec", "—")
        sl = tk.Frame(p, bg=BG); sl.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(sl, text="loss trend", bg=BG, fg=SUB, font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.er_spark = tk.Canvas(sl, width=240, height=34, bg="#f3f6fa", highlightthickness=0, bd=0)
        self.er_spark.pack(side="left")
        self._hdr(p, "HEAT  /  LOAD")
        self.er_gpu = self._kv(p, "GPU", "—", bold=True)
        self.er_cpu = self._kv(p, "CPU", "—")
        self.er_ram = self._kv(p, "RAM", "—")
        self._hdr(p, "ACTIVE PROJECTS")
        self.er_proj = tk.Label(p, text="—", bg=BG, fg=TXT, font=("Segoe UI", 9),
                                anchor="w", justify="left", wraplength=self.W - 30)
        self.er_proj.pack(fill="x", padx=14, pady=(2, 4))

    def _draw_spark(self, hist: list[float]) -> None:
        c = self.er_spark; c.delete("all")
        w, h = 240, 34
        if len(hist) < 2:
            return
        lo, hi = min(hist), max(hist); rng = (hi - lo) or 1e-6
        n = len(hist); pts = []
        for i, v in enumerate(hist):
            x = 1 + i * (w - 2) / (n - 1)
            y = h - 2 - (v - lo) / rng * (h - 4)
            pts += [x, y]
        c.create_line(*pts, fill=ACC, width=2)

    def _u_eran(self, eran: dict[str, Any], projects: dict[str, Any],
                hist: list[float], pc: dict[str, Any]) -> None:
        eran = eran or {}; projects = projects or {}; pc = pc or {}   # defensive (swarm review)
        step = eran.get("step"); self.er_step.config(text=_fmt_n(step) if step is not None else "—")
        loss = eran.get("loss"); self.er_loss.config(text=(f"{loss:.4f}" if isinstance(loss, (int, float)) else "—"))
        ema  = eran.get("ema");  self.er_ema.config(text=(f"{ema:.4f}" if isinstance(ema, (int, float)) else "—"))
        sps  = eran.get("sps");  self.er_sps.config(text=(f"{sps:.1f}/s" if isinstance(sps, (int, float)) else "—"))
        self._draw_spark(hist)
        gt = pc.get("gpu_temp"); gu = pc.get("gpu_util")
        self.er_gpu.config(text=(f"{gt}°  {gu}%" if gt else "—"), fg=_temp_color(gt))
        cpu = pc.get("cpu"); self.er_cpu.config(text=(f"{cpu}%" if cpu is not None else "—"), fg=_pct_color(cpu))
        ram = pc.get("ram"); rg = pc.get("ram_gb", "")
        self.er_ram.config(text=(f"{ram}%  {rg}" if ram is not None else "—"))
        lst = projects.get("list", []) if projects else []
        procs = projects.get("procs", 0) if projects else 0
        txt = "\n".join(lst[:7]) if lst else "—"
        if procs:
            txt += f"\n● {procs} live python procs under D:\\CLAUDE"
        self.er_proj.config(text=txt)

    def _build_fleet(self, p: tk.Widget) -> None:
        self._hdr(p, "NODES  ·  temp util  ping  ↓dl ↑ul")
        self.node_rows = {}
        for key in ["PC"] + NODES:
            row = tk.Frame(p, bg=BG); row.pack(fill="x", padx=12, pady=1)
            dot = tk.Label(row, text="●", bg=BG, fg=OFF, font=("Segoe UI", 9)); dot.pack(side="left")
            nm  = tk.Label(row, text=f" {key}", bg=BG, fg=TXT, font=("Consolas", 10, "bold"), width=6, anchor="w"); nm.pack(side="left")
            tp  = tk.Label(row, text="—", bg=BG, fg=SUB, font=("Consolas", 9), width=5, anchor="w"); tp.pack(side="left")
            ut  = tk.Label(row, text="", bg=BG, fg=SUB, font=("Consolas", 9), width=4, anchor="w"); ut.pack(side="left")
            pg  = tk.Label(row, text="", bg=BG, fg=SUB, font=("Consolas", 9), width=5, anchor="w"); pg.pack(side="left")
            net = tk.Label(row, text="", bg=BG, fg=ACC, font=("Consolas", 9), width=9, anchor="w"); net.pack(side="left")
            trn = tk.Label(row, text="", bg=BG, fg=OK, font=("Segoe UI", 8)); trn.pack(side="left")
            ubar = self._mkbar(row, w=34, h=7)
            self.node_rows[key] = {"dot": dot, "tp": tp, "ut": ut, "pg": pg, "net": net, "trn": trn, "ubar": ubar}
        self._hdr(p, "200G FABRIC  ·  brfab @ eran1")
        self.fab_state = self._kv(p, "link", "—", bold=True)
        self.fab_thr   = self._kv(p, "throughput", "—", color=ACC)
        self.fab_peers = self._kv(p, "fabric peers", "—")
        self._hdr(p, "STORM-GUARD  ·  ALMA-Govern  (advisory)")
        self.gov_summary = self._kv(p, "fleet health", "—", bold=True)

    def _build_ai(self, p: tk.Widget) -> None:
        self._hdr(p, "CLAUDE  ·  usage  (weekly reset)")
        self.cl_week,  self.bar_cl_week  = self._kvbar(p, "weekly")
        self.cl_burst, self.bar_cl_burst = self._kvbar(p, "5h burst")
        self.cl_reset = self._kv(p, "resets", "—", color=SUB)
        self.cl_tok   = self._kv(p, "today tok", "—", color=SUB)
        self._hdr(p, "GROK  ·  usage  (monthly reset)")
        self.gk_month, self.bar_gk_month = self._kvbar(p, "monthly")
        self.gk_used  = self._kv(p, "used", "—")
        self.gk_reset = self._kv(p, "resets", "—", color=SUB)
        self.gk_route = self._kv(p, "route", "—", bold=True)

    def _build_pc(self, p: tk.Widget) -> None:
        self._hdr(p, "THIS PC  ·  usage")
        self.pc_cpu,  self.bar_cpu  = self._kvbar(p, "CPU")
        self.pc_ram,  self.bar_ram  = self._kvbar(p, "RAM")
        self.pc_disk, self.bar_disk = self._kvbar(p, "Disk D:")
        self.pc_gpu,  self.bar_gpu  = self._kvbar(p, "GPU")
        self._hdr(p, "WEB CONNECTION")
        self.pc_down = self._kv(p, "download", "—", color=ACC, bold=True)
        self.pc_up   = self._kv(p, "upload", "—", color=OK, bold=True)
        self.pc_inet = self._kv(p, "internet", "—", bold=True)

    # ---- updates ----
    def _u_fleet(self, pc: dict[str, Any], nodes: dict[str, Any], fabric: dict[str, Any]) -> None:
        for key, w in self.node_rows.items():
            info = nodes.get(key, {}) if key != "PC" else self._pc_as_node(pc)
            if not info or not info.get("online", key == "PC"):
                if key != "PC":
                    w["dot"].config(fg=OFF); w["tp"].config(text="offline", fg=OFF)
                    w["ut"].config(text=""); w["pg"].config(text=""); w["net"].config(text=""); w["trn"].config(text="")
                    if "ubar" in w: self._setbar(w["ubar"], 0, OFF)
                    continue
            training = bool(info.get("train"))
            w["dot"].config(fg=(OK if training else (SUB if info.get("online", True) else OFF)))
            t = info.get("temp", "—"); w["tp"].config(text=(f"{t}°" if t not in (None, "—") else "—"), fg=_temp_color(t))
            util = info.get("util")
            w["ut"].config(text=(f"{util}%" if util not in (None, "—", "") else ""))
            if "ubar" in w: self._setbar(w["ubar"], util if util not in (None, "—", "") else 0, _pct_color(util))
            pg = info.get("ping"); w["pg"].config(text=(f"{pg}ms" if pg is not None else ""))
            dn, up = info.get("down"), info.get("up")
            w["net"].config(text=(f"↓{_fmt_bw(dn)} ↑{_fmt_bw(up)}" if dn is not None else ""))
            gsev = info.get("gov_sev")
            trn_txt = " ▶" if training else ""
            # Surface a storm-guard warning glyph next to the training marker on WARN+.
            if _safe_int(gsev) is not None and (_safe_int(gsev) or 0) >= 2:
                trn_txt += " ⚠"
                w["trn"].config(fg=_sev_color(gsev))
            else:
                w["trn"].config(fg=OK)
            w["trn"].config(text=trn_txt)
        # Fleet-wide storm-guard rollup: worst severity across nodes that reported.
        sevs = [(_safe_int(nd.get("gov_sev")), nd.get("gov_label"))
                for nd in nodes.values()
                if nd and _safe_int(nd.get("gov_sev")) is not None]
        if sevs:
            worst = max(sevs, key=lambda x: (x[0] or 0))
            n_rep = len(sevs)
            lbl = worst[1] or {0: "OK", 1: "INFO", 2: "WARN", 3: "CRITICAL"}.get(worst[0] or 0, "?")
            self.gov_summary.config(text=f"{lbl}  ({n_rep}/{len(NODES)} nodes report)",
                                    fg=_sev_color(worst[0]))
        else:
            self.gov_summary.config(text="— no report", fg=SUB)
        if fabric:
            st = fabric.get("state", "—"); sp = fabric.get("speed", "—")
            try: spt = f"{int(sp)/1000:.0f}G" if str(sp).isdigit() else sp
            except Exception: spt = sp
            self.fab_state.config(text=f"{st}  {spt}", fg=(OK if st == "up" else HOT))
            dn, up = fabric.get("down"), fabric.get("up")
            self.fab_thr.config(text=(f"↓{_fmt_bw(dn)} ↑{_fmt_bw(up)} /s" if dn is not None else "—"))
            self.fab_peers.config(text=f"{fabric.get('peers_up',0)}/{fabric.get('peers_total',0)} reachable")

    def _pc_as_node(self, pc: dict[str, Any]) -> dict[str, Any]:
        return {"online": True, "temp": pc.get("gpu_temp", "—"), "util": pc.get("gpu_util", ""),
                "ping": 0, "down": pc.get("down"), "up": pc.get("up"), "train": None}

    def _u_ai(self, ai: dict[str, Any]) -> None:
        cl = ai.get("claude", {}); gk = ai.get("grok", {})
        cs = ai.get("claude_snap", {}); gs = ai.get("grok_snap", {})
        # ---- Claude (weekly utilization + 5h burst, real OAuth usage) ----
        if cs.get("ok"):
            sv = cs.get("seven_day", {}); fv = cs.get("five_hour", {})
            wk = float(sv.get("utilization") or 0); bu = float(fv.get("utilization") or 0)
            self.cl_week.config(text=f"{wk:.0f}%", fg=_pct_color(wk)); self._setbar(self.bar_cl_week, wk, _pct_color(wk))
            self.cl_burst.config(text=f"{bu:.0f}%", fg=_pct_color(bu)); self._setbar(self.bar_cl_burst, bu, _pct_color(bu))
            self.cl_reset.config(text=f"{sv.get('reset_label','?')} ({sv.get('days_to_reset',0)}d {sv.get('hours_to_reset',0)}h) · {cs.get('subscription_type','?')}")
        else:
            self.cl_week.config(text="—"); self._setbar(self.bar_cl_week, 0, OFF)
            self.cl_burst.config(text="—"); self._setbar(self.bar_cl_burst, 0, OFF)
            self.cl_reset.config(text=str(cs.get("error", "…")))
        self.cl_tok.config(text=f"in {_fmt_n(cl.get('in'))} · out {_fmt_n(cl.get('out'))} · {cl.get('files','—')} files")
        # ---- Grok (monthly used/limit + reset, real billing) ----
        if gs.get("ok"):
            mu = float(gs.get("percent_used") or 0)
            self.gk_month.config(text=f"{mu:.0f}%", fg=_pct_color(mu)); self._setbar(self.bar_gk_month, mu, _pct_color(mu))
            self.gk_used.config(text=f"{int(gs.get('used',0)):,} / {int(gs.get('limit',0)):,}")
            self.gk_reset.config(text=f"{gs.get('reset_label','?')} ({gs.get('days_to_reset',0)}d)")
        else:
            self.gk_month.config(text="—"); self._setbar(self.bar_gk_month, 0, OFF)
            self.gk_used.config(text=str(gs.get("error", "…")))
        self.gk_route.config(text=gk.get("route", "—"), fg=(OK if gk.get("route") == "UP" else HOT))

    def _u_pc(self, pc: dict[str, Any]) -> None:
        if not pc: return
        cpu = pc.get("cpu")
        self.pc_cpu.config(text=(f"{cpu}%" if cpu is not None else "—"), fg=_pct_color(cpu))
        self._setbar(self.bar_cpu, cpu if cpu is not None else 0, _pct_color(cpu))
        ram = pc.get("ram")
        self.pc_ram.config(text=(f"{ram}%" if ram is not None else "—"))
        self._setbar(self.bar_ram, ram if ram is not None else 0, _pct_color(ram))
        disk = pc.get("disk")
        self.pc_disk.config(text=(f"{disk}%" if disk is not None else "—"))
        self._setbar(self.bar_disk, disk if disk is not None else 0, _pct_color(disk))
        gt = pc.get("gpu_temp"); gu = pc.get("gpu_util")
        self.pc_gpu.config(text=(f"{gt}° {gu}%" if gt else "—"))
        self._setbar(self.bar_gpu, gu if gu not in (None, "") else 0, _pct_color(gu))
        self.pc_down.config(text=f"{_fmt_bw(pc.get('down'))}B/s")
        self.pc_up.config(text=f"{_fmt_bw(pc.get('up'))}B/s")
        ok = pc.get("inet"); self.pc_inet.config(text=("online" if ok else "OFFLINE"), fg=(OK if ok else HOT))

    def _tick(self) -> None:
        try:
            pc, nodes, fabric, ai, last = _snapshot_state()
            eran, projects, hist = _snapshot_eran()
            self._u_eran(eran, projects, hist, pc)
            self._u_fleet(pc, nodes, fabric); self._u_ai(ai); self._u_pc(pc)
            self.footer.config(text=f"updated {last}  ·  עידו פרץ · ALMAWARE")
        except Exception:
            pass
        self.root.after(1000, self._tick)


# ---------- status / health HTTP endpoint ----------------------------------
# A tiny embedded server so the fleet router can monitor the dashboard
# (/health) and the public Eran portal can read a sanitized fleet snapshot
# (/status.json). Output is PUBLIC-SAFE: logical node names (eran1..4) only —
# no hostnames, IPs, file paths, or any personal data. Bound to localhost.
HEALTH_PORT = int(os.environ.get("ERAN_DASHBOARD_PORT", "8788"))


def _public_status() -> dict[str, Any]:
    """Build a privacy-safe fleet snapshot from in-memory state."""
    _pc, nodes, _fabric, _ai, _last = _snapshot_state()
    out_nodes: list[dict[str, Any]] = []
    online = training = 0
    utils: list[int] = []
    temps: list[int] = []
    sevs: list[int] = []
    for name in NODES:
        nd = nodes.get(name, {})
        is_on = bool(nd.get("online"))
        gtemp = _safe_int(nd.get("temp"))
        gutil = _safe_int(nd.get("util"))
        gsev = _safe_int(nd.get("gov_sev"))
        tr = 1 if nd.get("train") else 0
        if is_on:
            online += 1
            if tr:
                training += 1
            if gutil is not None:
                utils.append(gutil)
            if gtemp is not None:
                temps.append(gtemp)
            if gsev is not None:
                sevs.append(gsev)
        out_nodes.append({"name": name, "online": is_on,
                          "gtemp": gtemp, "gutil": gutil, "train": tr,
                          "gov_sev": gsev})
    return {
        "ts": int(time.time()),
        "nodes": out_nodes,
        "summary": {
            "online": online,
            "total": len(NODES),
            "training": training,
            "gutil_avg": round(sum(utils) / len(utils)) if utils else None,
            "gtemp_max": max(temps) if temps else None,
            "gov_worst": max(sevs) if sevs else None,
        },
    }


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    """Serve /health and /status.json. Read-only, sanitized, CORS-open."""
    def log_message(self, *a):   # keep the console quiet
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            st = _public_status(); s = st["summary"]
            self._send(200, {"ok": True, "service": "eran-dashboard",
                             "ts": st["ts"], "nodes_online": s["online"],
                             "nodes_total": s["total"],
                             "training": s["training"] > 0})
            return
        if path in ("/status.json", "/status"):
            self._send(200, _public_status())
            return
        self._send(404, {"error": "not found"})


def _start_status_server() -> None:
    """Start the /health + /status.json server in a daemon thread (best-effort)."""
    def run():
        httpd = None
        for p in range(HEALTH_PORT, HEALTH_PORT + 10):
            try:
                httpd = http.server.ThreadingHTTPServer(("127.0.0.1", p), _StatusHandler)
                break
            except OSError:
                continue
        if httpd is None:
            return
        try:
            httpd.serve_forever()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def main() -> None:
    _start_status_server()
    for fn in (_pc_poller, _node_poller, _ai_poller, _eran_poller):
        threading.Thread(target=fn, daemon=True).start()
    root = tk.Tk(); root.title("ERAN Dashboard")
    Dash(root); root.mainloop()


if __name__ == "__main__":
    main()
