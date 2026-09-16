#!/usr/bin/env python3
"""Read-only watchdog for the four-DGX swarm.

It records reachability, GPU temperature/load, and SSH latency.  DGX3 is
checked through DGX1's private fabric because it is currently absent from the
LAN.  This program deliberately never restarts hosts or services.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATUS = HERE / "dgx_watchdog_status.json"
ERROR_LOG = HERE / "dgx_watchdog_error.log"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NODES = {
    "dgx1": ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "eran1@<lan-ip>"],
    "dgx2": ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "eran2@<tailnet-ip>"],
    "dgx4": ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "eran4@<tailnet-ip>"],
}
REMOTE_CHECK = (
    "hostname; nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,"
    "memory.used,memory.total --format=csv,noheader,nounits; cut -d' ' -f1-3 /proc/loadavg"
)


def check(name: str) -> dict:
    if name == "dgx3":
        command = NODES["dgx1"] + [
            "ssh -o BatchMode=yes -o ConnectTimeout=6 eran3@<tailnet-host> "
            + repr(REMOTE_CHECK)
        ]
    else:
        command = NODES[name] + [REMOTE_CHECK]
    started = time.monotonic()
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=15,
        creationflags=NO_WINDOW,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {
        "node": name,
        "ok": result.returncode == 0 and len(lines) >= 3,
        "latency_ms": elapsed_ms,
        "hostname": lines[0] if lines else None,
        "gpu": lines[1] if len(lines) > 1 else None,
        "load": lines[2] if len(lines) > 2 else None,
        "error": result.stderr.strip() or None,
        "route": "via_dgx1_fabric" if name == "dgx3" else "direct_lan",
    }


def snapshot() -> dict:
    nodes = [check(name) for name in ("dgx1", "dgx2", "dgx3", "dgx4")]
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "watchdog": "read_only",
        "healthy": sum(node["ok"] for node in nodes),
        "total": len(nodes),
        "nodes": nodes,
    }


def write_status(data: dict) -> None:
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATUS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="repeat every 60 seconds")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress stdout for console-free scheduled execution",
    )
    args = parser.parse_args()
    while True:
        data = snapshot()
        write_status(data)
        if not args.quiet:
            print(json.dumps(data, indent=2))
        if not args.watch:
            return 0 if data["healthy"] == data["total"] else 1
        time.sleep(60)


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        ERROR_LOG.write_text(
            datetime.now(timezone.utc).isoformat() + "\n" + traceback.format_exc(),
            encoding="utf-8",
        )
        raise
    raise SystemExit(exit_code)
