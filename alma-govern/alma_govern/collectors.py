"""ALMA-Govern :: collectors

Turn a live node into the metric-snapshot dict that `fleet_health` detectors
consume. Kept strictly separate from detection so detectors stay pure and the
test-suite never needs a real host.

Everything here degrades gracefully: on a platform that lacks a source, the
corresponding snapshot key is simply omitted (detectors treat missing == benign).

Sources used when available:
  * /proc/net/dev + /proc/net/snmp  -> rx pps, broadcast pps (Linux)
  * ksoftirqd/* threads via psutil   -> per-CPU softirq busy percent
  * psutil.virtual_memory / swap     -> memory + swap
  * /proc/vmstat oom_kill            -> OOM kill counter
  * nvidia-smi (subprocess)          -> GPU temp + Xid (best-effort)

No SSH here -- a collector runs *on the node*. Fleet-wide collection is left to
the caller (they SSH out and call the CLI / this module remotely).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


IS_LINUX = platform.system() == "Linux"


def _read_proc_net_dev() -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    try:
        with open("/proc/net/dev") as fh:
            lines = fh.readlines()[2:]
        for ln in lines:
            name, _, rest = ln.partition(":")
            name = name.strip()
            cols = rest.split()
            if len(cols) >= 16:
                out[name] = {
                    "rx_bytes": int(cols[0]),
                    "rx_packets": int(cols[1]),
                    "rx_multicast": int(cols[7]),
                    "tx_packets": int(cols[9]),
                }
    except Exception:
        pass
    return out


def sample_network(interval: float = 0.5) -> Dict[str, Dict[str, float]]:
    """Return {nic: {"rx_pps", "bcast_pps"}} by diffing /proc/net/dev.

    Note: /proc/net/dev exposes multicast (which includes broadcast in the
    kernel counter) but not a clean broadcast-only counter, so we treat the
    rx_multicast delta as the broadcast/multicast pps proxy -- exactly the
    storm signal we care about.
    """
    if not IS_LINUX:
        return {}
    a = _read_proc_net_dev()
    if not a:
        return {}
    time.sleep(max(0.05, interval))
    b = _read_proc_net_dev()
    result: Dict[str, Dict[str, float]] = {}
    for nic, bv in b.items():
        av = a.get(nic)
        if not av:
            continue
        dt = interval
        rx_pps = max(0.0, (bv["rx_packets"] - av["rx_packets"]) / dt)
        bcast_pps = max(0.0, (bv["rx_multicast"] - av["rx_multicast"]) / dt)
        result[nic] = {"rx_pps": rx_pps, "bcast_pps": bcast_pps}
    return result


def sample_ksoftirqd(interval: float = 0.5) -> List[float]:
    """Per-thread ksoftirqd CPU busy percent."""
    if psutil is None:
        return []
    procs = []
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info.get("name") or "").startswith("ksoftirqd"):
                procs.append(p)
                p.cpu_percent(None)  # prime
        except Exception:
            continue
    if not procs:
        return []
    time.sleep(max(0.05, interval))
    pcts = []
    for p in procs:
        try:
            pcts.append(p.cpu_percent(None))
        except Exception:
            continue
    return pcts


def _read_oom_kill_total() -> Optional[int]:
    try:
        with open("/proc/vmstat") as fh:
            for ln in fh:
                if ln.startswith("oom_kill "):
                    return int(ln.split()[1])
    except Exception:
        pass
    return None


def sample_memory(prev_oom_total: Optional[int] = None) -> Dict[str, Any]:
    """Memory + swap + OOM-delta. Pass the previous oom total to get a delta."""
    out: Dict[str, Any] = {}
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            out["mem_total_mib"] = vm.total / (1024 * 1024)
            out["mem_available_mib"] = vm.available / (1024 * 1024)
        except Exception:
            pass
        try:
            sw = psutil.swap_memory()
            # sin is cumulative bytes; caller diffs for a rate. We expose a
            # coarse instantaneous proxy only when a rate isn't available.
            out["swap_in_bytes_total"] = getattr(sw, "sin", 0)
        except Exception:
            pass
    cur = _read_oom_kill_total()
    if cur is not None:
        out["oom_kill_total"] = cur
        if prev_oom_total is not None:
            out["oom_kill_delta"] = max(0, cur - prev_oom_total)
    return out


def sample_gpu() -> List[Dict[str, Any]]:
    """Best-effort GPU temp via nvidia-smi. Xid parsing is left to a log
    scraper (dmesg) which is node-specific; here we return temps and an empty
    xids list so the detector still runs.
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        r = subprocess.run(
            [exe, "--query-gpu=index,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8,
        )
    except Exception:
        return []
    gpus: List[Dict[str, Any]] = []
    for ln in r.stdout.strip().splitlines():
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) >= 2:
            try:
                gpus.append({"index": int(parts[0]),
                             "temp_c": float(parts[1]),
                             "xids": []})
            except ValueError:
                continue
    return gpus


def scrape_recent_xids(dmesg_text: Optional[str] = None) -> Dict[int, List[int]]:
    """Parse `dmesg` (or provided text) for `NVRM: Xid (... GPU N ...): CODE`.

    Returns {gpu_index: [xid, ...]}. Provided text keeps this testable offline.
    """
    import re
    if dmesg_text is None:
        if not shutil.which("dmesg"):
            return {}
        try:
            dmesg_text = subprocess.run(
                ["dmesg", "--ctime"], capture_output=True, text=True, timeout=8
            ).stdout
        except Exception:
            return {}
    out: Dict[int, List[int]] = {}
    pat = re.compile(r"NVRM:\s*Xid.*?GPU[- ]?(\d+).*?:\s*(\d+)", re.IGNORECASE)
    for m in pat.finditer(dmesg_text or ""):
        gpu, xid = int(m.group(1)), int(m.group(2))
        out.setdefault(gpu, []).append(xid)
    return out


def collect_snapshot(net_interval: float = 0.5) -> Dict[str, Any]:
    """Assemble a full snapshot for the local node. Safe to call anywhere;
    unavailable sources are simply omitted.
    """
    snap: Dict[str, Any] = {
        "node": platform.node(),
        "ts": time.time(),
    }
    nics = sample_network(net_interval)
    if nics:
        snap["nics"] = nics
    ksoft = sample_ksoftirqd(net_interval)
    if ksoft:
        snap["ksoftirqd_pct"] = ksoft
    snap.update(sample_memory())
    gpus = sample_gpu()
    if gpus:
        # fold in scraped xids
        xids = scrape_recent_xids()
        for g in gpus:
            g["xids"] = xids.get(g["index"], [])
        snap["gpus"] = gpus
    return snap
