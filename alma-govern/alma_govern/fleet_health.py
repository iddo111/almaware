"""ALMA-Govern :: fleet_health

Fleet-health guard for the DGX fleet. Detects the class of failure that
OOM-killed trainings on the night of 2026-07-02: a network broadcast storm
that pegged softirq handling and exhausted RAM.

Design principles (per ALMA-Govern charter):
  * "mic always wins" / protect the hardware -- detection first, never harm.
  * Detectors are PURE functions over a *metric snapshot* dict. Real metrics
    come from the collectors in `collectors.py`, but tests inject synthetic
    snapshots so the whole thing runs OFFLINE with no SSH and no root.
  * "protect" actions are ADVISORY. They return a recommended command string
    and are DISABLED by default. Nothing here ever runs a destructive action
    on its own -- the operator must opt in and execute it themselves.

Three detector families:
  A. Network / softirq storm   -> detect_network_storm
  B. Memory exhaustion / OOM   -> detect_memory_pressure
  C. GPU thermal / Xid faults  -> detect_gpu_health

Each returns a `Finding`. A node-level roll-up is `assess_node`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any, Dict, List, Optional


class Severity(IntEnum):
    OK = 0
    INFO = 1
    WARN = 2
    CRITICAL = 3

    def label(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Thresholds -- conservative defaults, all overridable.
# ---------------------------------------------------------------------------
@dataclass
class Thresholds:
    # --- network / softirq storm ---
    # Broadcast/multicast packets-per-second on a single NIC. A healthy fabric
    # link sees maybe a few thousand pps of broadcast; a storm is orders more.
    bcast_pps_warn: float = 50_000.0
    bcast_pps_crit: float = 200_000.0
    # Total rx pps -- a NIC flooded well past line-rate-of-small-frames.
    rx_pps_warn: float = 500_000.0
    rx_pps_crit: float = 1_500_000.0
    # ksoftirqd CPU% (per-thread). Pegged softirq handling == kernel drowning
    # in interrupts, the signature of the storm night.
    ksoftirqd_pct_warn: float = 60.0
    ksoftirqd_pct_crit: float = 90.0

    # --- memory exhaustion ---
    mem_used_pct_warn: float = 85.0
    mem_used_pct_crit: float = 95.0
    # Available memory floor in MiB -- below this an OOM kill is imminent
    # regardless of percentage (matters on big-RAM DGX boxes).
    mem_avail_mib_crit: float = 2_048.0
    # Swap thrash: high swap-in rate means we are already paging to death.
    swap_in_rate_warn: float = 1_000.0   # pages/sec
    # A fresh oom_kill delta > 0 is always CRITICAL.

    # --- GPU health ---
    gpu_temp_c_warn: float = 84.0
    gpu_temp_c_crit: float = 92.0
    # Any Xid in this set is treated as hardware/driver fault -> CRITICAL.
    # 79 = GPU fell off the bus, 119/120 = GSP RPC timeout (the eran4 class),
    # 94/95 = uncontained ECC errors, 48 = double-bit ECC.
    xid_critical: frozenset = frozenset({48, 79, 94, 95, 119, 120})


DEFAULT_THRESHOLDS = Thresholds()


@dataclass
class Finding:
    detector: str
    severity: Severity
    summary: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    # Advisory only. Never executed by this library.
    recommended_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = int(self.severity)
        d["severity_label"] = self.severity.label()
        return d

    def __str__(self) -> str:
        act = f"  -> advise: {self.recommended_action}" if self.recommended_action else ""
        return f"[{self.severity.label():8}] {self.detector}: {self.summary}{act}"


# ---------------------------------------------------------------------------
# Detector A -- network / softirq broadcast storm
# ---------------------------------------------------------------------------
def detect_network_storm(snap: Dict[str, Any], th: Thresholds = DEFAULT_THRESHOLDS) -> Finding:
    """Detect a broadcast/multicast storm and/or pegged softirq handling.

    Expected snapshot keys (all optional; missing == unknown, treated benign):
      nics: {name: {"bcast_pps": float, "rx_pps": float}}
      ksoftirqd_pct: [float, ...]   # per-CPU ksoftirqd busy percent
    """
    nics: Dict[str, Dict[str, float]] = snap.get("nics", {}) or {}
    ksoft: List[float] = snap.get("ksoftirqd_pct", []) or []

    sev = Severity.OK
    reasons: List[str] = []
    worst_nic = None
    worst_bcast = 0.0
    worst_rx = 0.0

    for name, s in nics.items():
        bpps = float(s.get("bcast_pps", 0.0) or 0.0)
        rpps = float(s.get("rx_pps", 0.0) or 0.0)
        if bpps > worst_bcast:
            worst_bcast, worst_nic = bpps, name
        worst_rx = max(worst_rx, rpps)

        if bpps >= th.bcast_pps_crit or rpps >= th.rx_pps_crit:
            sev = max(sev, Severity.CRITICAL)
            reasons.append(f"{name}: {bpps:,.0f} bcast pps / {rpps:,.0f} rx pps")
        elif bpps >= th.bcast_pps_warn or rpps >= th.rx_pps_warn:
            sev = max(sev, Severity.WARN)
            reasons.append(f"{name}: {bpps:,.0f} bcast pps / {rpps:,.0f} rx pps")

    max_ksoft = max(ksoft) if ksoft else 0.0
    if max_ksoft >= th.ksoftirqd_pct_crit:
        sev = max(sev, Severity.CRITICAL)
        reasons.append(f"ksoftirqd pegged at {max_ksoft:.0f}%")
    elif max_ksoft >= th.ksoftirqd_pct_warn:
        sev = max(sev, Severity.WARN)
        reasons.append(f"ksoftirqd busy {max_ksoft:.0f}%")

    metrics = {
        "worst_nic": worst_nic,
        "worst_bcast_pps": worst_bcast,
        "worst_rx_pps": worst_rx,
        "max_ksoftirqd_pct": max_ksoft,
    }

    if sev == Severity.OK:
        return Finding("network_storm", sev, "network quiet; softirq nominal", metrics)

    action = None
    if sev >= Severity.WARN and worst_nic:
        # ADVISORY: recommend isolating the storming link. This matches the
        # "hidden loop -> don't bridge" fabric note. NEVER auto-run.
        action = (
            f"consider isolating storming link '{worst_nic}' "
            f"(advisory: `ip link set {worst_nic} down`) after confirming it is "
            f"not the only path; investigate for a bridged loop"
        )

    return Finding(
        "network_storm", sev,
        "possible broadcast/softirq storm: " + "; ".join(reasons),
        metrics, recommended_action=action,
    )


# ---------------------------------------------------------------------------
# Detector B -- memory exhaustion / imminent OOM
# ---------------------------------------------------------------------------
def detect_memory_pressure(snap: Dict[str, Any], th: Thresholds = DEFAULT_THRESHOLDS) -> Finding:
    """Detect memory exhaustion or an in-progress OOM cascade.

    Expected snapshot keys:
      mem_total_mib: float
      mem_available_mib: float
      swap_in_rate: float           # pages/sec swapped in (thrash indicator)
      oom_kill_delta: int           # new oom kills since last poll
    """
    total = float(snap.get("mem_total_mib", 0.0) or 0.0)
    avail = float(snap.get("mem_available_mib", 0.0) or 0.0)
    swap_in = float(snap.get("swap_in_rate", 0.0) or 0.0)
    oom_delta = int(snap.get("oom_kill_delta", 0) or 0)

    used_pct = 0.0 if total <= 0 else max(0.0, (total - avail) / total * 100.0)

    sev = Severity.OK
    reasons: List[str] = []

    if oom_delta > 0:
        sev = Severity.CRITICAL
        reasons.append(f"{oom_delta} OOM kill(s) since last poll")

    if total > 0:
        if avail <= th.mem_avail_mib_crit or used_pct >= th.mem_used_pct_crit:
            sev = max(sev, Severity.CRITICAL)
            reasons.append(f"memory critical: {used_pct:.1f}% used, {avail:,.0f} MiB free")
        elif used_pct >= th.mem_used_pct_warn:
            sev = max(sev, Severity.WARN)
            reasons.append(f"memory high: {used_pct:.1f}% used, {avail:,.0f} MiB free")

    if swap_in >= th.swap_in_rate_warn:
        sev = max(sev, Severity.WARN)
        reasons.append(f"swap thrash: {swap_in:,.0f} pages/s in")

    metrics = {
        "mem_total_mib": total,
        "mem_available_mib": avail,
        "mem_used_pct": round(used_pct, 2),
        "swap_in_rate": swap_in,
        "oom_kill_delta": oom_delta,
    }

    if sev == Severity.OK:
        return Finding("memory_pressure", sev,
                       f"memory nominal ({used_pct:.1f}% used)", metrics)

    action = None
    if sev >= Severity.WARN:
        # ADVISORY: protect running trainings by shedding non-essential load.
        # We name it but do not act -- operator decides what is sheddable.
        action = (
            "advisory: cap/pause non-essential jobs to protect running trainings; "
            "verify no runaway allocator; do NOT let the kernel OOM-pick the trainer"
        )

    return Finding("memory_pressure", sev,
                   "memory pressure: " + "; ".join(reasons),
                   metrics, recommended_action=action)


# ---------------------------------------------------------------------------
# Detector C -- GPU thermal / Xid
# ---------------------------------------------------------------------------
def detect_gpu_health(snap: Dict[str, Any], th: Thresholds = DEFAULT_THRESHOLDS) -> Finding:
    """Detect GPU thermal excursions and Xid hardware/driver faults.

    Expected snapshot keys:
      gpus: [{"index": int, "temp_c": float, "xids": [int, ...]}]
    """
    gpus: List[Dict[str, Any]] = snap.get("gpus", []) or []

    sev = Severity.OK
    reasons: List[str] = []
    hottest = 0.0
    hottest_idx = None
    crit_xids: List[int] = []
    xid_gpu = None

    for g in gpus:
        idx = g.get("index")
        temp = float(g.get("temp_c", 0.0) or 0.0)
        xids = [int(x) for x in (g.get("xids", []) or [])]

        if temp > hottest:
            hottest, hottest_idx = temp, idx

        if temp >= th.gpu_temp_c_crit:
            sev = max(sev, Severity.CRITICAL)
            reasons.append(f"GPU{idx} {temp:.0f}C (critical)")
        elif temp >= th.gpu_temp_c_warn:
            sev = max(sev, Severity.WARN)
            reasons.append(f"GPU{idx} {temp:.0f}C (warn)")

        bad = [x for x in xids if x in th.xid_critical]
        if bad:
            sev = max(sev, Severity.CRITICAL)
            crit_xids.extend(bad)
            xid_gpu = idx
            reasons.append(f"GPU{idx} Xid {','.join(map(str, bad))} (hw/driver fault)")

    metrics = {
        "hottest_gpu": hottest_idx,
        "hottest_temp_c": hottest,
        "critical_xids": sorted(set(crit_xids)),
    }

    if sev == Severity.OK:
        return Finding("gpu_health", sev,
                       f"GPUs nominal (hottest {hottest:.0f}C)" if gpus else "no GPUs reported",
                       metrics)

    action = None
    if crit_xids:
        action = (
            f"advisory: GPU{xid_gpu} reports critical Xid {sorted(set(crit_xids))}; "
            f"drain jobs off it and reset the GPU (e.g. `nvidia-smi -i {xid_gpu} -r` / "
            f"node reboot) -- matches the GSP-hang class"
        )
    elif sev >= Severity.WARN:
        action = "advisory: check airflow/cooling; throttle or pause jobs on the hot GPU"

    return Finding("gpu_health", sev,
                   "GPU issue: " + "; ".join(reasons),
                   metrics, recommended_action=action)


# ---------------------------------------------------------------------------
# Node roll-up
# ---------------------------------------------------------------------------
@dataclass
class NodeAssessment:
    node: str
    findings: List[Finding]

    @property
    def severity(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.OK)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "severity": int(self.severity),
            "severity_label": self.severity.label(),
            "findings": [f.to_dict() for f in self.findings],
        }


def assess_node(node: str, snapshot: Dict[str, Any],
                th: Thresholds = DEFAULT_THRESHOLDS) -> NodeAssessment:
    """Run all detectors against a single node's metric snapshot."""
    findings = [
        detect_network_storm(snapshot, th),
        detect_memory_pressure(snapshot, th),
        detect_gpu_health(snapshot, th),
    ]
    return NodeAssessment(node=node, findings=findings)
