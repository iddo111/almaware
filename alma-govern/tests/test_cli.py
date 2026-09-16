"""In-process tests for the ALMA-Govern CLI monitoring contract.

These drive ``alma_govern.cli.main([...])`` directly -- no subprocess, no SSH,
no host metrics -- against temporary JSON snapshot files fed through the
``check --from FILE`` offline path. They lock the documented contract:

  * exit code == worst severity (0 OK .. 3 CRITICAL) so it plugs into monitoring
  * ``--json`` emits a JSON object whose top-level ``severity`` == the exit code
  * ``--protect`` prints the (advisory-only) recommended action; the default
    run never prints it.

Run with ``pytest`` or the plain-python fallback at the bottom.
"""
import io
import json
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alma_govern.cli import main  # noqa: E402


# --------------------------- snapshot fixtures -----------------------------
# An OK node: quiet NIC, plenty of RAM, cool GPU, no faults -> severity 0.
OK_SNAPSHOT = {
    "node": "ok-node",
    "nics": {"eth0": {"bcast_pps": 500, "rx_pps": 20_000}},
    "ksoftirqd_pct": [4.0],
    "mem_total_mib": 100_000,
    "mem_available_mib": 60_000,
    "gpus": [{"index": 0, "temp_c": 60, "xids": []}],
}

# A CRITICAL node: a GPU pegged at 95C (>= gpu_temp_c_crit 92) -> severity 3.
CRITICAL_SNAPSHOT = {
    "node": "crit-node",
    "gpus": [{"index": 0, "temp_c": 95, "xids": []}],
}


def _write_snapshot(tmp_path, name, payload):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w") as fh:
        json.dump(payload, fh)
    return path


def _run(argv):
    """Run the CLI in-process; return (exit_code, captured_stdout)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


# --------------------------- (1) OK -> exit 0 ------------------------------
def test_ok_snapshot_returns_zero(tmp_path):
    snap = _write_snapshot(tmp_path, "ok.json", OK_SNAPSHOT)
    code, _ = _run(["check", "--from", snap])
    assert code == 0


# --------------------------- (2) CRITICAL -> exit 3 ------------------------
def test_critical_snapshot_returns_three(tmp_path):
    snap = _write_snapshot(tmp_path, "crit.json", CRITICAL_SNAPSHOT)
    code, _ = _run(["check", "--from", snap])
    assert code == 3


# --------------- (3) --json stdout parses; severity == exit code -----------
def test_json_severity_matches_exit_code_ok(tmp_path):
    snap = _write_snapshot(tmp_path, "ok.json", OK_SNAPSHOT)
    code, out = _run(["check", "--from", snap, "--json"])
    doc = json.loads(out)  # must be valid JSON
    assert doc["severity"] == code == 0


def test_json_severity_matches_exit_code_critical(tmp_path):
    snap = _write_snapshot(tmp_path, "crit.json", CRITICAL_SNAPSHOT)
    code, out = _run(["check", "--from", snap, "--json"])
    doc = json.loads(out)
    assert doc["severity"] == code == 3


# --------------- (4) --protect prints advisory; default does not -----------
_ADVISORY_MARK = "ADVISORY (not executed):"


def test_protect_prints_advisory(tmp_path):
    snap = _write_snapshot(tmp_path, "crit.json", CRITICAL_SNAPSHOT)
    code, out = _run(["check", "--from", snap, "--protect"])
    assert code == 3
    assert _ADVISORY_MARK in out


def test_without_protect_advisory_is_absent(tmp_path):
    snap = _write_snapshot(tmp_path, "crit.json", CRITICAL_SNAPSHOT)
    code, out = _run(["check", "--from", snap])
    assert code == 3
    assert _ADVISORY_MARK not in out


if __name__ == "__main__":
    # Plain-python fallback so this runs even without pytest installed.
    import tempfile
    import types

    class _Tmp:
        """Minimal stand-in for the pytest tmp_path fixture."""

        def __init__(self, d):
            self._d = d

        def __str__(self):
            return self._d

    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    passed = 0
    for fn in fns:
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(_Tmp(d))
                print(f"[PASS] {fn.__name__}")
                passed += 1
            except Exception as e:  # noqa: BLE001
                print(f"[FAIL] {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    sys.exit(0 if passed == len(fns) else 1)
