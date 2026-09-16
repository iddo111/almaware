"""Permanent fixer agent — scans all of Iddo's apps and repairs them.

Runs every 5 minutes via Windows Task Scheduler (registered as Interactive
user, so GUI apps can actually draw).

Each app is a (name, check_fn, repair_fn) entry. check_fn returns True if
healthy. repair_fn brings it back. Both are designed to be idempotent and
fast (<10s typical).

Logs:
  - human: D:\\CLAUDE\\tools\\fixer_agent.log (ring at 1MB)
  - structured: D:\\CLAUDE\\tools\\fixer_agent_status.json (last status per app)

To pause: create file D:\\CLAUDE\\tools\\FIXER_PAUSE.
To skip a single app: add its name to D:\\CLAUDE\\tools\\fixer_skip.txt (one per line).
"""
from __future__ import annotations
import json, os, socket, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT      = Path(r"D:\CLAUDE\tools")
LOG       = ROOT / "fixer_agent.log"
STATUS    = ROOT / "fixer_agent_status.json"
PAUSE     = ROOT / "FIXER_PAUSE"
SKIP_FILE = ROOT / "fixer_skip.txt"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > 1_000_000:
        backup = LOG.with_suffix(".log.1")
        if backup.exists(): backup.unlink()
        LOG.rename(backup)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{ts}  {msg}\n")
    print(msg)


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect((host, port)); return True
    except OSError:
        return False
    finally:
        s.close()


def proc_running(name_glob: str, cmdline_substr: str = "") -> bool:
    """True if any process matching name has cmdline_substr in its command line.
    Uses Win32_Process commandline (catches script paths, not just exe paths)."""
    if not cmdline_substr:
        cmd = ["powershell", "-NoProfile", "-Command",
               f"(Get-Process -Name '{name_glob}' -ErrorAction SilentlyContinue | Measure-Object).Count"]
    else:
        cmd = ["powershell", "-NoProfile", "-Command",
               f"(Get-CimInstance Win32_Process -Filter \"Name like '{name_glob}%'\" "
               f"-ErrorAction SilentlyContinue | "
               f"Where-Object {{ $_.CommandLine -like '*{cmdline_substr}*' }} | "
               f"Measure-Object).Count"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                       text=True, timeout=10).strip()
        return int(out or "0") > 0
    except Exception:
        return False


def service_state(name: str) -> str:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Service '{name}' -ErrorAction SilentlyContinue).Status"],
            stderr=subprocess.DEVNULL, text=True, timeout=10).strip()
        return out or "missing"
    except Exception as e:
        return f"err:{e}"


def url_alive(url: str, timeout: int = 8) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fixer-agent/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def spawn(args: list[str], cwd: str | None = None) -> int | None:
    try:
        p = subprocess.Popen(
            args, cwd=cwd,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
        )
        return p.pid
    except Exception as e:
        log(f"  spawn failed for {args[0]}: {e}")
        return None


# ─── App registry ──────────────────────────────────────────────────────────

PYTHONW_ALMA = r"D:\CLAUDE\alma-memorial\.venv-train\Scripts\pythonw.exe"
PYTHONW_AMC  = r"D:\CLAUDE\ai-media-center\.venv-amc\Scripts\pythonw.exe"
NODE         = "node"


SYS_PY      = r"C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe"
SYS_PYW     = r"C:\Users\<user>\AppData\Local\Programs\Python\Python312\pythonw.exe"


def app_alma_facerec():
    name = "alma_facerec_gui"
    def check():
        return proc_running("pythonw", "face_rec_gui.py")
    def repair():
        spawn([PYTHONW_ALMA, r"D:\CLAUDE\alma-memorial\tools\face_rec_gui.py"],
              cwd=r"D:\CLAUDE\alma-memorial")
    return name, check, repair


def app_alma_trainer():
    name = "alma_trainer_loop"
    def check():
        # trainer is fine if its watchdog pid file points to a live process
        pidfile = Path(r"D:\CLAUDE\alma-memorial\tools\_watchdog.pid")
        if not pidfile.exists(): return False
        try:
            pid = int(pidfile.read_text().strip() or "0")
            if pid == 0: return False
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue | Measure-Object).Count"],
                stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
            return int(out or "0") > 0
        except Exception:
            return False
    def repair():
        spawn([PYTHONW_ALMA, r"D:\CLAUDE\alma-memorial\tools\alma_trainer_watchdog.py"],
              cwd=r"D:\CLAUDE\alma-memorial")
    return name, check, repair


def app_amc_gui():
    name = "ai_media_center_gui"
    def check(): return proc_running("pythonw", r"ai-media-center\amc\gui.py")
    def repair():
        spawn([PYTHONW_AMC, r"D:\CLAUDE\ai-media-center\amc\gui.py"],
              cwd=r"D:\CLAUDE\ai-media-center")
    return name, check, repair


def app_wa_bridge():
    name = "wa_bridge"
    def check(): return proc_running("node", "bridge.js")
    def repair():
        spawn([NODE, "bridge.js"], cwd=r"D:\CLAUDE\whatsapp-bridge")
    return name, check, repair


def app_wa_responder():
    name = "wa_responder"
    def check(): return proc_running("python", "responder.py")
    def repair():
        spawn([SYS_PY, r"D:\CLAUDE\whatsapp-bridge\responder.py"],
              cwd=r"D:\CLAUDE\whatsapp-bridge")
    return name, check, repair


def app_wa_watchdog():
    name = "wa_watchdog"
    def check(): return proc_running("pythonw", r"whatsapp-bridge\watchdog.py")
    def repair():
        spawn([SYS_PYW, r"D:\CLAUDE\whatsapp-bridge\watchdog.py"],
              cwd=r"D:\CLAUDE\whatsapp-bridge")
    return name, check, repair


def app_mosquitto():
    name = "mosquitto"
    def check(): return service_state("mosquitto") == "Running" or port_listening(1883)
    def repair():
        # try service first; fall back to direct exe spawn (no admin needed for spawn)
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Start-Service mosquitto -ErrorAction SilentlyContinue"],
                       check=False, timeout=15)
        if port_listening(1883): return
        for exe in (r"C:\Program Files\mosquitto\mosquitto.exe",
                    r"C:\Program Files (x86)\mosquitto\mosquitto.exe"):
            if Path(exe).exists():
                spawn([exe, "-v"])
                return
    return name, check, repair


def app_iddoperez_site():
    name = "iddoperez_ai_site"
    def check(): return port_listening(8080) and url_alive("https://iddoperez.ai")
    def repair():
        # Delegate to the dedicated watchdog — it knows how
        subprocess.run([PYTHONW_ALMA, r"D:\CLAUDE\projects\iddoperez-ai\_watchdog.py"],
                       check=False, timeout=60)
    return name, check, repair


APPS: list[Callable] = [
    app_alma_facerec,
    app_alma_trainer,
    app_amc_gui,
    app_wa_bridge,
    app_wa_responder,
    app_wa_watchdog,
    app_mosquitto,
    app_iddoperez_site,
]


# ─── Main loop ─────────────────────────────────────────────────────────────

def load_skip() -> set[str]:
    if not SKIP_FILE.exists():
        return set()
    return {ln.strip() for ln in SKIP_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def main() -> int:
    if PAUSE.exists():
        log("[paused] FIXER_PAUSE present — exiting clean")
        return 0

    skip = load_skip()
    status = {"updated": datetime.now().isoformat(), "apps": {}}

    for app_ctor in APPS:
        name, check, repair = app_ctor()
        if name in skip:
            log(f"[{name}] skipped (in fixer_skip.txt)")
            status["apps"][name] = {"state": "skipped"}
            continue
        try:
            healthy = check()
        except Exception as e:
            log(f"[{name}] check threw: {e}")
            status["apps"][name] = {"state": "check_error", "error": str(e)}
            continue
        if healthy:
            status["apps"][name] = {"state": "ok"}
            continue
        log(f"[{name}] DOWN — repairing")
        try:
            repair()
        except Exception as e:
            log(f"[{name}] repair threw: {e}")
            status["apps"][name] = {"state": "repair_error", "error": str(e)}
            continue
        time.sleep(3)
        try:
            healthy_after = check()
        except Exception:
            healthy_after = False
        log(f"[{name}] post-repair: {'OK' if healthy_after else 'STILL DOWN'}")
        status["apps"][name] = {
            "state": "repaired" if healthy_after else "repair_failed",
        }

    STATUS.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
