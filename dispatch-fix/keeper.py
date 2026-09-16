"""
Dispatch keeper — meta-watchdog for pc-listener.py.

Runs every 5 minutes via Scheduled Task `Dispatch-Keeper`. Checks:

  (a) pc-listener.py process alive AND port 18180 listening
  (b) state/pc-listener.log mtime within 5 min OR (a) is true (because the
      log only writes when there's traffic, so an idle listener is fine
      provided the process+port are good)

If (a) fails, respawns pc-listener.bat.

Per Iddo's no-popup-Holocaust rule: launched as pythonw, no console.

Author: triple-fix agent, 2026-05-04.
"""
from __future__ import annotations

import datetime as _dt
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\CLAUDE\dispatch-fix")
BIN = ROOT / "bin"
LISTENER_PY = BIN / "pc-listener.py"
LISTENER_BAT = BIN / "pc-listener.bat"
LOG = ROOT / "keeper.log"
STATE_LOG = ROOT / "state" / "pc-listener.log"
PORT = 18180
PYTHONW = Path(r"C:\Users\<user>\AppData\Local\Programs\Python\Python312\pythonw.exe")

CREATE_NO_WINDOW = 0x08000000

LOG.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ts = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except OSError:
        pass


def port_listening(port: int = PORT) -> bool:
    """Quick TCP probe to localhost — confirms the listener is bound."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def listener_pid() -> int | None:
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" "
        "| Where-Object { $_.CommandLine -like '*pc-listener.py*' } "
        "| Select-Object -First 1 -ExpandProperty ProcessId"
    )
    try:
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace",
            timeout=12, creationflags=CREATE_NO_WINDOW,
        ).strip()
        return int(out) if out.isdigit() else None
    except Exception as e:
        log(f"WARN listener_pid failed: {e}")
        return None


def ping_ok() -> bool:
    """HTTP /ping check. Uses Connection: close so the server flushes immediately."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(("127.0.0.1", PORT))
            s.send(b"GET /ping HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            data = b""
            while True:
                try:
                    chunk = s.recv(1024)
                except OSError:
                    break
                if not chunk:
                    break
                data += chunk
                if len(data) > 4096:
                    break
            return b"pong" in data
    except OSError:
        return False


def reap_all() -> None:
    """Kill EVERY pc-listener process.

    respawn() only runs when the listener is unhealthy (not listening, or
    listening but not answering /ping — a wedged socket). In that state no
    surviving process is worth keeping, and a wedged owner would otherwise hold
    the LISTEN socket and make the fresh spawn's bind fail (exit 0) forever. So
    reap them all, then spawn one clean listener. With allow_reuse_address now
    False in pc-listener, only that single fresh process can own the port.
    """
    # Two-step kill, fast path first. Get-CimInstance with a CommandLine -like
    # filter is intermittently >15s on this box, so do NOT rely on it alone:
    #  (1) kill whoever owns :18180 via Get-NetTCPConnection (instant, no CIM) —
    #      this clears a wedged owner so the LISTEN socket frees up;
    #  (2) best-effort CIM sweep for non-owning stragglers (longer timeout, and
    #      a timeout here is harmless because the owner is already gone).
    ps = (
        "$killed = New-Object System.Collections.ArrayList; "
        "$owner = (Get-NetTCPConnection -LocalPort 18180 -State Listen "
        "-ErrorAction SilentlyContinue | Select-Object -First 1 "
        "-ExpandProperty OwningProcess); "
        "if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue; "
        "[void]$killed.Add($owner) } "
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" "
        "-ErrorAction SilentlyContinue "
        "| Where-Object { $_.CommandLine -like '*pc-listener.py*' } "
        "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction "
        "SilentlyContinue; [void]$killed.Add($_.ProcessId) }; "
        "$killed | Sort-Object -Unique"
    )
    try:
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace",
            timeout=25, creationflags=CREATE_NO_WINDOW,
        ).strip()
        if out:
            log(f"ACTION reaped pc-listener PIDs before respawn: {out.split()}")
    except Exception as e:
        log(f"WARN reap_all sweep slow/failed (port owner already killed first): {e}")


def respawn() -> None:
    reap_all()
    # Stop-Process is async; wait for the LISTEN socket to actually free up so the
    # fresh spawn's (now strict) bind doesn't lose a race and exit 0, leaving us
    # dead until the next tick. Poll up to ~5s.
    for _ in range(10):
        if not port_listening():
            break
        time.sleep(0.5)
    log("ACTION respawning pc-listener via pythonw")
    try:
        subprocess.Popen(
            [str(PYTHONW), str(LISTENER_PY)],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x00000008 | 0x00000200,  # DETACHED + NEW_PROCESS_GROUP
            close_fds=True,
        )
        log("ACTION respawn submitted")
    except Exception as e:
        log(f"ERROR respawn failed: {e}")


def main() -> int:
    pid = listener_pid()
    listening = port_listening()
    pong = ping_ok() if listening else False
    log_age_min = -1.0
    if STATE_LOG.exists():
        log_age_min = (time.time() - STATE_LOG.stat().st_mtime) / 60

    log(f"CHECK pid={pid} listening={listening} pong={pong} log_age_min={log_age_min:.1f}")

    # Healthy criterion: a working HTTP listener is the source of truth.
    # PID lookup via PowerShell is flaky (Win32_Process CommandLine truncated for
    # some launches), so don't fail just because we couldn't find the PID — if
    # the port is bound AND /ping returns pong, the listener is doing its job.
    healthy = listening and pong
    if not healthy:
        log(f"NOTICE unhealthy (listening={listening} pong={pong}) — respawning")
        respawn()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL {e}")
        sys.exit(1)
