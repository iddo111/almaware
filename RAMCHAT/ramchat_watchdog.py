"""One-shot RAMCHAT watchdog with bounded, GUI-only recovery.

It never starts or stops Alma/model services. Run repeatedly from Task Scheduler
if desired; each run performs at most one RAMCHAT GUI start and writes status.
"""
from __future__ import annotations

import ctypes
import json
import mmap
import os
import struct
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / "ramchat_watchdog_status.json"
MAPS = (
    ("RAMCHAT_COUNCIL_V1", 16 * 1024 * 1024, b"RAMCHAT1"),
    ("RAMCHAT_QUEUE_V1", 8 * 1024 * 1024, b"RAMQUEU1"),
)
HARNESS = os.environ.get(
    "ALMA_HARNESS_URL", "http://127.0.0.1:8095"
).rstrip("/")


def gui_pids() -> tuple[list[int], str | None]:
    cmd = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -match '^pythonw?\\.exe$' -and $_.CommandLine -match "
        "'RAMCHAT.*ramchat\\.pyw' } | Select-Object -ExpandProperty ProcessId"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True, capture_output=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        return [], str(exc)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        return [], detail[-1000:]
    return [int(x) for x in result.stdout.split() if x.isdigit()], None


def gui_window_ok(pids: list[int]) -> bool:
    """A live pythonw PID is not enough — the Tk window can die while the
    process lingers (seen 2026-08-08). Verify a titled top-level window."""
    if not pids:
        return False
    ids = ",".join(str(p) for p in pids)
    cmd = (
        f"(Get-Process -Id {ids} -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowTitle }) | Measure-Object | "
        "Select-Object -ExpandProperty Count"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True, capture_output=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return int((result.stdout or "0").strip() or 0) > 0
    except Exception:
        return True  # diagnostic failure must not trigger a kill


def check_map(name: str, size: int, magic: bytes) -> dict:
    try:
        with mmap.mmap(-1, size, tagname=name, access=mmap.ACCESS_READ) as shared:
            if shared[:8] != magic:
                return {"ok": False, "error": "bad magic"}
            length = struct.unpack("<Q", shared[8:16])[0]
            if length > size - 16:
                return {"ok": False, "error": "payload out of bounds"}
            payload = json.loads(shared[16:16 + length].decode("utf-8"))
            return {"ok": isinstance(payload, dict), "schema": payload.get("schema"), "bytes": length}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_alma() -> dict:
    try:
        with urllib.request.urlopen(HARNESS + "/api/models", timeout=15) as response:
            models = json.loads(response.read().decode("utf-8")).get("models", [])
        wanted = {m.get("key"): m for m in models if m.get("key") in {"nemotron", "gptoss120b"}}
        nem = wanted.get("nemotron", {})
        try:
            topology_mismatch = (
                int(nem.get("replicas", 0)) != 1
                or int(nem.get("ready_replicas", 0)) != 1
            )
        except (TypeError, ValueError):
            topology_mismatch = True
        return {
            "ok": len(wanted) == 2,
            "gptoss120b_ready": bool(wanted.get("gptoss120b", {}).get("ready")),
            "nemotron_ready": bool(nem.get("ready")) and not topology_mismatch,
            "nemotron_node": nem.get("node"),
            "topology_mismatch": topology_mismatch,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main() -> int:
    pids, discovery_error = gui_pids()
    maps = {name: check_map(name, size, magic) for name, size, magic in MAPS}
    recovery = "none"
    zombie_killed = False
    if pids and not discovery_error and not gui_window_ok(pids):
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        time.sleep(1)
        pids, discovery_error = gui_pids()
        maps = {name: check_map(name, size, magic) for name, size, magic in MAPS}
        zombie_killed = True
        recovery = "killed_zombie_window"
    # Never launch blindly when process discovery itself failed. A previous
    # version treated that diagnostic failure as proof the GUI was absent and
    # could create duplicate RAMCHAT windows.
    if not pids and discovery_error:
        recovery = "skipped_process_discovery_error"
    elif not pids and not zombie_killed and all(item["ok"] for item in maps.values()):
        recovery = "skipped_shared_memory_alive"
    elif not pids:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        subprocess.Popen(
            [str(pythonw), str(ROOT / "ramchat.pyw")], cwd=ROOT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        recovery = "started_gui_once"
        time.sleep(1)
        pids, discovery_error = gui_pids()
        maps = {name: check_map(name, size, magic) for name, size, magic in MAPS}
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "gui": {
            "ok": bool(pids) or all(item["ok"] for item in maps.values()),
            "pids": pids,
            "recovery": recovery,
            "process_discovery_error": discovery_error,
        },
        "shared_memory": maps,
        "alma": check_alma(),
    }
    temporary = STATUS.with_name(STATUS.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATUS)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["gui"]["ok"] and all(x["ok"] for x in report["shared_memory"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
