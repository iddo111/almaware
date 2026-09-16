"""Tests for the one-place portfolio catalog contract."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alma_govern.portfolio_catalog import validate_catalog  # noqa: E402
from alma_govern.portfolio_catalog_cli import main  # noqa: E402


def entry(**overrides):
    result = {
        "id": "garden-sentinel",
        "name": "Garden Memory Sentinel",
        "family": "hardware",
        "path": "arduino-neuron-builds/07-garden-memory-sentinel",
        "purpose": "advisory plant-stress measurement",
        "owner": "ALMA",
        "status": "VERIFIED",
        "status_at": "2026-07-22T04:03:15+03:00",
        "acceptance_gate": "three target compiles and no flash",
        "next_action": "identify a physical board and sensors",
        "safety_boundary": "LED and serial only",
        "public_benefit_domains": ["ecology", "education"],
        "duplicate_of": None,
        "evidence": [{
            "kind": "compile",
            "value": "Uno, Nano ESP32 and RP2040 passed",
            "observed_at": "2026-07-22T04:03:15+03:00",
            "strength": "direct",
        }],
    }
    result.update(overrides)
    return result


def catalog(entries=None):
    return {
        "schema_version": 1,
        "generated_at": "2026-07-22T04:10:00+03:00",
        "entries": entries or [entry()],
    }


def fields(issues):
    return {issue.field for issue in issues}


def test_valid_catalog_passes(tmp_path):
    target = tmp_path / "arduino-neuron-builds" / "07-garden-memory-sentinel"
    target.mkdir(parents=True)
    assert validate_catalog(catalog(), workspace_root=tmp_path) == []


def test_verified_requires_direct_evidence():
    evidence = [{
        "kind": "README",
        "value": "claims it worked",
        "observed_at": "2026-07-22T04:03:15+03:00",
        "strength": "historical",
    }]
    assert "evidence" in fields(validate_catalog(catalog([entry(evidence=evidence)])))


def test_missing_path_is_rejected(tmp_path):
    assert "path" in fields(validate_catalog(catalog(), workspace_root=tmp_path))


def test_unsafe_relative_path_is_rejected():
    assert "path" in fields(validate_catalog(catalog([entry(path="../secret")])))


def test_duplicate_ids_are_rejected():
    assert "id" in fields(validate_catalog(catalog([entry(), entry()])))


def test_superseded_requires_existing_target():
    old = entry(id="old-ui", status="SUPERSEDED", duplicate_of="new-ui")
    assert "duplicate_of" in fields(validate_catalog(catalog([old])))


def test_duplicate_cycle_is_rejected():
    one = entry(id="one-ui", duplicate_of="two-ui")
    two = entry(id="two-ui", duplicate_of="one-ui")
    assert any(issue.message == "duplicate cycle"
               for issue in validate_catalog(catalog([one, two])))


def test_cli_outputs_machine_readable_result(tmp_path, capsys):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
