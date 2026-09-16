"""Offline unit tests for the ALMA-Govern fleet-health detectors.

Fully synthetic -- no SSH, no root, no GPU. Run with `pytest` or the plain
`python tests/test_fleet_health.py` fallback at the bottom.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alma_govern.fleet_health import (  # noqa: E402
    Severity, Thresholds, assess_node,
    detect_network_storm, detect_memory_pressure, detect_gpu_health,
)


# --------------------------- network storm ---------------------------------
def test_network_quiet_is_ok():
    snap = {"nics": {"eth0": {"bcast_pps": 500, "rx_pps": 20_000}},
            "ksoftirqd_pct": [4.0]}
    assert detect_network_storm(snap).severity == Severity.OK


def test_broadcast_storm_is_critical():
    snap = {"nics": {"fab0": {"bcast_pps": 900_000, "rx_pps": 2_000_000}},
            "ksoftirqd_pct": [99.0]}
    f = detect_network_storm(snap)
    assert f.severity == Severity.CRITICAL
    assert f.recommended_action and "advisory" in f.recommended_action
    assert f.metrics["worst_nic"] == "fab0"


def test_network_warn_band():
    snap = {"nics": {"eth0": {"bcast_pps": 70_000, "rx_pps": 100}}}
    assert detect_network_storm(snap).severity == Severity.WARN


def test_ksoftirqd_peg_alone_triggers():
    snap = {"ksoftirqd_pct": [95.0]}
    assert detect_network_storm(snap).severity == Severity.CRITICAL


# --------------------------- memory ----------------------------------------
def test_memory_nominal():
    snap = {"mem_total_mib": 100_000, "mem_available_mib": 60_000}
    assert detect_memory_pressure(snap).severity == Severity.OK


def test_oom_delta_is_always_critical():
    snap = {"mem_total_mib": 100_000, "mem_available_mib": 40_000,
            "oom_kill_delta": 1}
    assert detect_memory_pressure(snap).severity == Severity.CRITICAL


def test_low_available_floor_is_critical():
    # 99% used, only 1 GiB free on a big box -> critical by the MiB floor.
    snap = {"mem_total_mib": 1_000_000, "mem_available_mib": 1_000}
    assert detect_memory_pressure(snap).severity == Severity.CRITICAL


def test_memory_warn_band():
    snap = {"mem_total_mib": 100_000, "mem_available_mib": 12_000}  # 88% used
    assert detect_memory_pressure(snap).severity == Severity.WARN


def test_swap_thrash_warns():
    snap = {"mem_total_mib": 100_000, "mem_available_mib": 60_000,
            "swap_in_rate": 5_000}
    assert detect_memory_pressure(snap).severity >= Severity.WARN


# --------------------------- gpu -------------------------------------------
def test_gpu_nominal():
    snap = {"gpus": [{"index": 0, "temp_c": 60, "xids": []}]}
    assert detect_gpu_health(snap).severity == Severity.OK


def test_gpu_critical_xid():
    snap = {"gpus": [{"index": 2, "temp_c": 65, "xids": [119]}]}
    f = detect_gpu_health(snap)
    assert f.severity == Severity.CRITICAL
    assert 119 in f.metrics["critical_xids"]
    assert "reset" in (f.recommended_action or "")


def test_gpu_thermal_warn_and_crit():
    assert detect_gpu_health({"gpus": [{"index": 0, "temp_c": 88}]}).severity == Severity.WARN
    assert detect_gpu_health({"gpus": [{"index": 0, "temp_c": 95}]}).severity == Severity.CRITICAL


def test_benign_xid_is_ignored():
    # An Xid not in the critical set (e.g. 43, app error) must not go critical.
    snap = {"gpus": [{"index": 0, "temp_c": 60, "xids": [43]}]}
    assert detect_gpu_health(snap).severity == Severity.OK


# --------------------------- roll-up + robustness --------------------------
def test_empty_snapshot_is_ok():
    a = assess_node("n", {})
    assert a.severity == Severity.OK
    assert len(a.findings) == 3


def test_rollup_takes_worst():
    snap = {
        "nics": {"eth0": {"bcast_pps": 500, "rx_pps": 100}},   # ok
        "mem_total_mib": 100_000, "mem_available_mib": 60_000,  # ok
        "gpus": [{"index": 0, "temp_c": 95, "xids": []}],       # critical
    }
    assert assess_node("n", snap).severity == Severity.CRITICAL


def test_custom_thresholds_respected():
    th = Thresholds(bcast_pps_warn=10.0, bcast_pps_crit=20.0)
    snap = {"nics": {"eth0": {"bcast_pps": 25.0, "rx_pps": 0}}}
    assert detect_network_storm(snap, th).severity == Severity.CRITICAL
    # default thresholds would call the same 25 pps OK:
    assert detect_network_storm(snap).severity == Severity.OK


def test_to_dict_is_json_safe():
    import json
    a = assess_node("n", {"gpus": [{"index": 0, "temp_c": 95, "xids": []}]})
    json.dumps(a.to_dict())  # must not raise


# --------------------------- collectors (offline paths) --------------------
def test_xid_scraper_offline():
    from alma_govern.collectors import scrape_recent_xids
    sample = ("[Wed] NVRM: Xid (PCI:0000:01:00 GPU-0): 119, timeout\n"
              "[Wed] NVRM: Xid (PCI:0000:02:00 GPU 1): 79, off the bus\n")
    got = scrape_recent_xids(sample)
    assert got.get(0) == [119]
    assert got.get(1) == [79]


def test_collect_snapshot_runs_here():
    # Must not crash on this (Windows/dev) machine; sources just get omitted.
    from alma_govern.collectors import collect_snapshot
    snap = collect_snapshot(net_interval=0.05)
    assert isinstance(snap, dict) and "node" in snap


if __name__ == "__main__":
    # Plain-python fallback so this runs even without pytest installed.
    import types
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    sys.exit(0 if passed == len(fns) else 1)
