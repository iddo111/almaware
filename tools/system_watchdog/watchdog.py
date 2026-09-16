"""
Smart-System-Watchdog
=====================

Permanent, lightweight system health daemon for Iddo's Win11 PC.

* Runs under pythonw.exe — no console popup (per feedback_no_popup_holocaust).
* Singleton via msvcrt.locking on a lockfile.
* Snapshot every 15 min: RAM %, disk %, top-5 RSS, listening ports
  of interest, count of "must-be-running" services.
* Maintenance every 6 hours: temp cleanup, DNS flush, log pruning.
* Self-heal: if a service in RESTART_COMMANDS is dead, fire its command.
  RESTART_COMMANDS starts empty — Iddo fills it in later.

Drop-in safe defaults: never touches firewall, Defender, network,
power plan, or Windows Updates. Never restarts user services unless
explicitly configured here.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# ----------------------------- config -----------------------------

HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "watchdog.log"
LOCK_PATH = HERE / "watchdog.lock"
STATE_PATH = HERE / "watchdog_state.json"
LOG_ROTATE_MB = 50

SNAPSHOT_INTERVAL_SEC = 15 * 60          # 15 min
MAINTENANCE_INTERVAL_SEC = 6 * 60 * 60   # 6 hours

PORTS_OF_INTEREST = [1883, 3765, 11434]

# names matched against process command line / image. Case-insensitive substring match.
# These patterns are conservative — better a false-negative than restarting something twice.
SERVICE_PATTERNS = {
    "wazzup_node":  ["wazzup", "/wazzup/index.js", "\\wazzup\\index.js"],
    "bridge_js":    ["bridge.js", "whatsapp-bridge"],
    "perez_mesh":   ["perez_mesh", "perez-mesh"],
    "alma_trainer": ["alma-memorial", "trainer_loop", "face_rec_gui"],
    "ollama":       ["ollama serve", "ollama_llama_server", "ollama.exe"],
}

# {service_key: shell_command_to_run_to_restart}.
# Leave empty by default — Iddo fills this in once he decides what to auto-restart.
RESTART_COMMANDS: dict[str, str] = {}

TEMP_OLDER_THAN_DAYS = 7
DEATH_LOG_OLDER_THAN_DAYS = 7

# ------------------------- singleton lock -------------------------

def acquire_singleton_lock() -> object | None:
    """Return open file handle holding an exclusive lock, or None if already running."""
    import msvcrt
    try:
        f = open(LOCK_PATH, "a+b")
    except OSError:
        return None
    try:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    try:
        f.seek(0)
        f.truncate(0)
        f.write(str(os.getpid()).encode("ascii"))
        f.flush()
    except OSError:
        pass
    return f

# --------------------------- logging ------------------------------

def _rotate_if_needed() -> None:
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_ROTATE_MB * 1024 * 1024:
            backup = LOG_PATH.with_suffix(".log.1")
            if backup.exists():
                backup.unlink(missing_ok=True)
            LOG_PATH.rename(backup)
    except OSError:
        pass

def log_event(kind: str, payload: dict) -> None:
    _rotate_if_needed()
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        **payload,
    }
    line = json.dumps(rec, ensure_ascii=False, default=str)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass

# ------------------------- powershell helper ----------------------

CREATE_NO_WINDOW = 0x08000000

def run_ps(script: str, timeout: int = 60) -> str:
    """Run a PowerShell snippet hidden, return stdout (stripped)."""
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return out.decode("utf-8", errors="replace").strip()
    except subprocess.CalledProcessError as e:
        return (e.output or b"").decode("utf-8", errors="replace").strip()
    except subprocess.TimeoutExpired:
        return ""
    except OSError:
        return ""

# --------------------------- snapshot -----------------------------

def get_ram() -> dict:
    script = (
        "$os = Get-CimInstance Win32_OperatingSystem;"
        "$total=[math]::Round($os.TotalVisibleMemorySize/1MB,2);"
        "$free=[math]::Round($os.FreePhysicalMemory/1MB,2);"
        "$used=[math]::Round($total-$free,2);"
        "$pct=[math]::Round(($used/$total)*100,1);"
        "[pscustomobject]@{total_gb=$total; used_gb=$used; free_gb=$free; pct=$pct} | ConvertTo-Json -Compress"
    )
    raw = run_ps(script)
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"raw": raw}

def get_disks() -> list[dict]:
    script = (
        "Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null } |"
        " ForEach-Object {"
        "  $tot=$_.Used+$_.Free;"
        "  if ($tot -gt 0) {"
        "    [pscustomobject]@{"
        "      name=$_.Name;"
        "      used_gb=[math]::Round($_.Used/1GB,2);"
        "      free_gb=[math]::Round($_.Free/1GB,2);"
        "      free_pct=[math]::Round(($_.Free/$tot)*100,1)"
        "    }"
        "  }"
        "} | ConvertTo-Json -Compress"
    )
    raw = run_ps(script)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return []

def get_top_rss(n: int = 5) -> list[dict]:
    script = (
        f"Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First {n}"
        " ProcessName, Id, @{N='ram_mb';E={[math]::Round($_.WorkingSet64/1MB)}} |"
        " ConvertTo-Json -Compress"
    )
    raw = run_ps(script)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return []

def get_listening_ports(ports: list[int]) -> dict:
    """Return {port: True/False} — alive iff something is listening."""
    out: dict[int, bool] = {}
    for p in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                # If we can connect, the port is in use (= listening).
                rc = s.connect_ex(("127.0.0.1", p))
                out[p] = (rc == 0)
        except OSError:
            out[p] = False
    return out

def count_services() -> dict:
    """Use wmic-style query on processes to count services by pattern."""
    script = (
        "Get-CimInstance Win32_Process |"
        " Select-Object ProcessId, Name, CommandLine |"
        " ConvertTo-Json -Compress"
    )
    raw = run_ps(script, timeout=30)
    if not raw:
        return {k: 0 for k in SERVICE_PATTERNS}
    try:
        procs = json.loads(raw)
        if isinstance(procs, dict):
            procs = [procs]
    except json.JSONDecodeError:
        return {k: 0 for k in SERVICE_PATTERNS}

    counts: dict[str, int] = {k: 0 for k in SERVICE_PATTERNS}
    for p in procs:
        cl = (p.get("CommandLine") or "").lower()
        nm = (p.get("Name") or "").lower()
        for key, patterns in SERVICE_PATTERNS.items():
            if any(pat.lower() in cl or pat.lower() in nm for pat in patterns):
                counts[key] += 1
    return counts

def take_snapshot() -> dict:
    snap = {
        "ram": get_ram(),
        "disks": get_disks(),
        "top_rss": get_top_rss(5),
        "ports": get_listening_ports(PORTS_OF_INTEREST),
        "services": count_services(),
    }
    return snap

# ------------------------ self-heal ------------------------------

def self_heal(services: dict) -> list[dict]:
    """Restart services that are configured AND missing."""
    actions: list[dict] = []
    for key, count in services.items():
        if count > 0:
            continue
        cmd = RESTART_COMMANDS.get(key)
        if not cmd:
            continue
        try:
            subprocess.Popen(
                cmd,
                shell=True,
                creationflags=CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                close_fds=True,
            )
            actions.append({"service": key, "action": "restart_fired", "cmd": cmd})
        except OSError as e:
            actions.append({"service": key, "action": "restart_failed", "error": str(e)})
    return actions

# -------------------- maintenance routines -----------------------

def prune_temp(root: str, older_than_days: int) -> tuple[int, int]:
    """Delete files older than N days. Returns (count, bytes)."""
    if not root or not os.path.isdir(root):
        return (0, 0)
    cutoff = time.time() - (older_than_days * 86400)
    count = 0
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
                if st.st_mtime < cutoff:
                    sz = st.st_size
                    os.remove(p)
                    count += 1
                    total += sz
            except OSError:
                continue
    return (count, total)

def flush_dns() -> bool:
    try:
        subprocess.run(
            ["ipconfig", "/flushdns"],
            check=False,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False

def prune_death_logs() -> tuple[int, int]:
    folder = Path("D:/CLAUDE/whatsapp-bridge/logs")
    if not folder.is_dir():
        return (0, 0)
    cutoff = time.time() - (DEATH_LOG_OLDER_THAN_DAYS * 86400)
    count = 0
    total = 0
    for p in folder.glob("bridgejs_death_*.log"):
        try:
            st = p.stat()
            if st.st_mtime < cutoff:
                sz = st.st_size
                p.unlink()
                count += 1
                total += sz
        except OSError:
            continue
    return (count, total)

def run_maintenance() -> dict:
    summary: dict = {"actions": []}
    user_temp = os.environ.get("TEMP") or os.environ.get("TMP")
    local_temp = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp")
    win_temp = "C:\\Windows\\Temp"

    targets = []
    seen = set()
    for t in (user_temp, local_temp, win_temp):
        if t and t.lower() not in seen:
            seen.add(t.lower())
            targets.append(t)

    for t in targets:
        c, b = prune_temp(t, TEMP_OLDER_THAN_DAYS)
        summary["actions"].append({"target": t, "deleted": c, "bytes": b})

    summary["dns_flushed"] = flush_dns()

    dlc, dlb = prune_death_logs()
    summary["actions"].append({"target": "bridgejs_death_*.log", "deleted": dlc, "bytes": dlb})

    summary["total_bytes_reclaimed"] = sum(a.get("bytes", 0) for a in summary["actions"])
    return summary

# --------------------------- state -------------------------------

def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

def save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass

# -------------------------- main loop ----------------------------

def cycle_once() -> None:
    """One pass: snapshot + maybe maintenance + self-heal."""
    snap = take_snapshot()
    log_event("snapshot", snap)

    actions = self_heal(snap.get("services", {}))
    if actions:
        log_event("self_heal", {"actions": actions})

    state = load_state()
    last_maint = state.get("last_maintenance_ts")
    do_maint = False
    if not last_maint:
        do_maint = True
    else:
        try:
            last_dt = datetime.fromisoformat(last_maint)
            if datetime.now() - last_dt > timedelta(seconds=MAINTENANCE_INTERVAL_SEC):
                do_maint = True
        except ValueError:
            do_maint = True

    if do_maint:
        m = run_maintenance()
        log_event("maintenance", m)
        state["last_maintenance_ts"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)

def main_loop() -> None:
    log_event("startup", {"pid": os.getpid(), "py": sys.version.split()[0]})
    while True:
        try:
            cycle_once()
        except (OSError, RuntimeError) as e:
            log_event("error", {"err": str(e), "tb": traceback.format_exc(limit=4)})
        time.sleep(SNAPSHOT_INTERVAL_SEC)

def run_once_foreground() -> None:
    """For smoke-test: do exactly one cycle and exit."""
    log_event("startup_oneshot", {"pid": os.getpid(), "py": sys.version.split()[0]})
    cycle_once()
    log_event("shutdown_oneshot", {})

# --------------------------- entry -------------------------------

if __name__ == "__main__":
    if "--once" in sys.argv:
        # smoke-test: don't acquire long-lived lock, just do one pass.
        run_once_foreground()
        sys.exit(0)

    handle = acquire_singleton_lock()
    if handle is None:
        # Another instance is already running. Quietly exit.
        sys.exit(0)
    try:
        main_loop()
    finally:
        try:
            handle.close()
        except OSError:
            pass
