#!/usr/bin/env python3
"""ALMA-Govern fleet-health -- offline demo.

Runs the three detectors against synthetic metric snapshots (no SSH, no root,
no GPU). It replays the failure that OOM-killed trainings on 2026-07-02:
a network broadcast storm that pegged softirq handling and exhausted RAM.

Run:  python demo.py
Exit code is 0 iff every detector fired as expected.
"""
from __future__ import annotations

import sys

from alma_govern.fleet_health import (
    Severity, assess_node,
    detect_network_storm, detect_memory_pressure, detect_gpu_health,
)

PASS, FAIL = "PASS", "FAIL"
_ok = True


def check(name: str, got: Severity, want_min: Severity) -> None:
    global _ok
    good = got >= want_min
    _ok = _ok and good
    print(f"  [{PASS if good else FAIL}] {name}: got {got.label()} "
          f"(expected >= {want_min.label()})")


def hr(t: str) -> None:
    print("\n" + t)
    print("-" * len(t))


# ---------------------------------------------------------------------------
# 1. Healthy node -- everything must read OK.
# ---------------------------------------------------------------------------
hr("1. Healthy node baseline")
healthy = {
    "node": "eran2",
    "nics": {"enp1s0f0": {"bcast_pps": 800, "rx_pps": 40_000}},
    "ksoftirqd_pct": [3.0, 5.0, 2.0],
    "mem_total_mib": 1_024_000, "mem_available_mib": 700_000,
    "swap_in_rate": 0, "oom_kill_delta": 0,
    "gpus": [{"index": 0, "temp_c": 61, "xids": []},
             {"index": 1, "temp_c": 63, "xids": []}],
}
a = assess_node("eran2", healthy)
for f in a.findings:
    print("   ", f)
check("network", detect_network_storm(healthy).severity, Severity.OK)
check("memory", detect_memory_pressure(healthy).severity, Severity.OK)
check("gpu", detect_gpu_health(healthy).severity, Severity.OK)
# On a healthy node the roll-up must be exactly OK (not just >= OK).
_ok = _ok and (a.severity == Severity.OK)
print(f"  [{PASS if a.severity == Severity.OK else FAIL}] roll-up == OK")


# ---------------------------------------------------------------------------
# 2. THE STORM NIGHT -- broadcast storm + softirq peg + OOM cascade.
# ---------------------------------------------------------------------------
hr("2. Broadcast storm + OOM cascade (2026-07-02 replay)")
storm = {
    "node": "eran3",
    # ConnectX-7 fabric leg flooded by a bridged loop:
    "nics": {"enp1s0f1np1": {"bcast_pps": 950_000, "rx_pps": 2_400_000}},
    "ksoftirqd_pct": [98.0, 96.0, 99.0],          # softirq drowning
    "mem_total_mib": 1_024_000, "mem_available_mib": 900,  # ~all RAM gone
    "swap_in_rate": 12_000, "oom_kill_delta": 3,  # trainings getting killed
    "gpus": [{"index": 0, "temp_c": 70, "xids": []}],
}
a = assess_node("eran3", storm)
for f in a.findings:
    print("   ", f)
    if f.recommended_action:
        print("       advisory:", f.recommended_action)
check("network storm -> CRITICAL", detect_network_storm(storm).severity, Severity.CRITICAL)
check("memory/OOM -> CRITICAL", detect_memory_pressure(storm).severity, Severity.CRITICAL)
_ok = _ok and (a.severity == Severity.CRITICAL)
print(f"  [{PASS if a.severity == Severity.CRITICAL else FAIL}] roll-up == CRITICAL")
# Prove the advisory action is present but is a *recommendation* only.
net = detect_network_storm(storm)
has_advice = bool(net.recommended_action) and "advisory" in net.recommended_action
_ok = _ok and has_advice
print(f"  [{PASS if has_advice else FAIL}] protect action present & advisory-only")


# ---------------------------------------------------------------------------
# 3. Early WARN -- catch it BEFORE the cascade.
# ---------------------------------------------------------------------------
hr("3. Early-warning thresholds (WARN before CRITICAL)")
early = {
    "node": "eran1",
    "nics": {"eth0": {"bcast_pps": 70_000, "rx_pps": 600_000}},  # above warn
    "ksoftirqd_pct": [65.0],                                     # busy, not pegged
    "mem_total_mib": 512_000, "mem_available_mib": 60_000,       # ~88% used
    "swap_in_rate": 0, "oom_kill_delta": 0,
}
for f in assess_node("eran1", early).findings:
    print("   ", f)
check("network -> WARN", detect_network_storm(early).severity, Severity.WARN)
check("memory -> WARN", detect_memory_pressure(early).severity, Severity.WARN)
# And must NOT be critical yet:
n_sev = detect_network_storm(early).severity
m_sev = detect_memory_pressure(early).severity
not_crit = n_sev < Severity.CRITICAL and m_sev < Severity.CRITICAL
_ok = _ok and not_crit
print(f"  [{PASS if not_crit else FAIL}] neither is CRITICAL yet (early catch)")


# ---------------------------------------------------------------------------
# 4. GPU Xid fault (eran4 GSP-hang class).
# ---------------------------------------------------------------------------
hr("4. GPU Xid hardware/driver fault (GSP-hang class)")
gpu_fault = {
    "node": "eran4",
    "gpus": [{"index": 0, "temp_c": 66, "xids": [119]}],  # GSP RPC timeout
}
gf = detect_gpu_health(gpu_fault)
print("   ", gf)
if gf.recommended_action:
    print("       advisory:", gf.recommended_action)
check("Xid 119 -> CRITICAL", gf.severity, Severity.CRITICAL)
xid_advice = bool(gf.recommended_action) and "reset" in gf.recommended_action
_ok = _ok and xid_advice
print(f"  [{PASS if xid_advice else FAIL}] recommends GPU reset (advisory)")


# ---------------------------------------------------------------------------
# 5. GPU thermal-only WARN.
# ---------------------------------------------------------------------------
hr("5. GPU thermal excursion")
hot = {"node": "eran2", "gpus": [{"index": 3, "temp_c": 88, "xids": []}]}
h = detect_gpu_health(hot)
print("   ", h)
check("88C -> WARN", h.severity, Severity.WARN)


# ---------------------------------------------------------------------------
# 6. Missing data must be treated as benign (no false alarms).
# ---------------------------------------------------------------------------
hr("6. Sparse/empty snapshot -> no false positives")
empty = {"node": "unknown"}
a = assess_node("unknown", empty)
for f in a.findings:
    print("   ", f)
_ok = _ok and (a.severity == Severity.OK)
print(f"  [{PASS if a.severity == Severity.OK else FAIL}] empty snapshot == OK")


# ---------------------------------------------------------------------------
hr("RESULT")
print("  ALL DETECTORS FIRED AS EXPECTED" if _ok else "  *** SOME CHECKS FAILED ***")
sys.exit(0 if _ok else 1)
