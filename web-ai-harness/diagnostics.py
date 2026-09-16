"""Read-only diagnostics a local model may call.

Deliberately NOT a shell. Each tool is fixed and parameterless (or takes a
value from a closed enum), so a model — or a prompt injected into one — cannot
compose an arbitrary command. This is the same shape as the old
perplexity-pc-harness `run_diagnostic` enum, and it is the reason this file
exists instead of an `exec(cmd)` helper: the QUORUM gateway on this machine
shelled out to agent CLIs from an unauthenticated endpoint, and that is exactly
the mistake not to repeat.

Everything here is observation only. Nothing writes, installs, kills or
configures.
"""
from __future__ import annotations

import json
import platform
import shutil
import socket
import subprocess

TIMEOUT = 20


def _run(args: list[str]) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT)
        return (p.stdout or p.stderr or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return f"(unavailable: {exc})"


def where_am_i() -> dict:
    """Which machine runs the MODEL, and which runs these TOOLS. They differ.

    The model is served from a DGX node over the tailnet; these tools execute on
    the Windows workstation that hosts the chat UI. Asking system_report() 'what
    machine are you on' therefore returns the PC, which reads as though the model
    lives there. It does not. This tool exists to say so explicitly.
    """
    return {
        "model_runs_on": {
            "gpt-oss-120b": "eran4 (DGX GB10) — <tailnet-ip>:8000, llama.cpp, MXFP4",
            "glm-5.2": "eran1/2/3/4 (DGX GB10) — :8800, colibri, 4 replicas",
        },
        "tools_run_on": f"{socket.gethostname()} — the Windows workstation hosting this chat UI",
        "note": ("The model itself has no filesystem or shell. These read-only "
                 "diagnostics execute on the PC and their results are handed to the "
                 "model. So system_report() describes the PC, not the DGX. For DGX "
                 "figures use fleet_health()."),
    }


def system_report() -> dict:
    """The WORKSTATION this tool runs on — NOT the machine serving the model.

    For the DGX nodes that actually run the models, use fleet_health().
    """
    disks = {}
    for d in ("C:\\", "D:\\"):
        try:
            u = shutil.disk_usage(d)
            disks[d] = {
                "total_gb": round(u.total / 2**30, 1),
                "free_gb": round(u.free / 2**30, 1),
                "percent_used": round(100 * (u.total - u.free) / u.total, 1),
            }
        except OSError:
            pass
    return {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": __import__("os").cpu_count(),
        "disks": disks,
    }


def gpu_report() -> dict:
    out = _run(["nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader"])
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4:
            gpus.append({"name": parts[0], "memory_total": parts[1],
                         "memory_used": parts[2], "utilization": parts[3]})
    return {"gpus": gpus} if gpus else {"gpus": [], "note": out[:200]}


def lan_report() -> dict:
    """Local addresses and the Tailscale peer list. No scanning of others."""
    addrs = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       family=socket.AF_INET):
            a = info[4][0]
            if a not in addrs:
                addrs.append(a)
    except socket.gaierror:
        pass

    peers = []
    ts = _run(["tailscale", "status"])
    for line in ts.splitlines():
        f = line.split()
        if len(f) >= 4 and f[0].startswith("100."):
            peers.append({"ip": f[0], "host": f[1], "os": f[3],
                          "state": "online" if "offline" not in line else "offline"})
    return {"local_ipv4": addrs, "tailscale_peers": peers,
            "tailscale_available": not ts.startswith("(unavailable")}


def fleet_health() -> dict:
    """Reachability of the four DGX nodes over Tailscale/SSH. Read-only."""
    nodes = {}
    for host in ("eran1", "eran2", "eran3", "eran4"):
        out = _run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
                    host, "hostname; free -g | sed -n 2p; uptime -p"])
        nodes[host] = {"reachable": not out.startswith("(unavailable")
                       and "Permission denied" not in out
                       and "Could not resolve" not in out,
                       "detail": out[:300]}
    return {"nodes": nodes}


REGISTRY = {
    "where_am_i": (where_am_i, "Which machine runs the MODEL vs which runs these TOOLS — they are different machines."),
    "system_report": (system_report, "Host, OS, CPU, memory and disk usage of this PC."),
    "gpu_report": (gpu_report, "Local NVIDIA GPU name, memory and utilization."),
    "lan_report": (lan_report, "This machine's IPv4 addresses and its Tailscale peers."),
    "fleet_health": (fleet_health, "Reachability, memory and uptime of DGX nodes eran1-4."),
}


def tool_schemas() -> list[dict]:
    """OpenAI tool definitions. All parameterless — nothing to inject into."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {"type": "object", "properties": {},
                               "additionalProperties": False},
            },
        }
        for name, (_fn, desc) in REGISTRY.items()
    ]


def call(name: str) -> str:
    if name not in REGISTRY:
        return json.dumps({"error": f"unknown tool {name!r}",
                           "available": sorted(REGISTRY)})
    try:
        return json.dumps(REGISTRY[name][0](), ensure_ascii=False)
    except Exception as exc:  # a broken diagnostic must not kill the loop
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
