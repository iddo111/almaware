"""Separate, dry-run-by-default promotion of evaluated shadow artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .io_utils import atomic_write_json, file_sha256
from .labels import PARTIAL_NOT_ANT_FARM_ACCEPTANCE, TRUTH_VERIFIED


def _inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must remain inside {root}") from exc
    return resolved


def promote(
    *,
    run_root: Path,
    evaluation_report: Path,
    execute: bool,
) -> dict[str, object]:
    root = run_root.resolve()
    shadow_root = root / "shadow"
    report_path = _inside(
        evaluation_report,
        shadow_root / "reports",
        "evaluation report",
    )
    if report_path.suffix != ".json":
        raise ValueError("evaluation report must end in .json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("evaluation report root must be an object")
    required = {
        "artifact_type": "REAL_AUDIO_HELDOUT_EVALUATION_REPORT",
        "evaluation_status": TRUTH_VERIFIED,
        "acceptance": PARTIAL_NOT_ANT_FARM_ACCEPTANCE,
        "promotion_eligible": True,
        "automatic_promotion_performed": False,
    }
    for key, value in required.items():
        if report.get(key) != value:
            raise ValueError(
                f"evaluation report is not promotion-eligible: "
                f"{key}={report.get(key)!r}"
            )
    checkpoint_value = report.get("checkpoint")
    checkpoint_sha256 = report.get("checkpoint_sha256")
    if not isinstance(checkpoint_value, str) or not isinstance(
        checkpoint_sha256, str
    ):
        raise ValueError("evaluation report checkpoint fields are invalid")
    checkpoint = _inside(
        root / checkpoint_value,
        shadow_root / "checkpoints",
        "checkpoint",
    )
    if checkpoint.suffix != ".pt":
        raise ValueError("evaluated checkpoint must end in .pt")
    if not checkpoint.is_file():
        raise ValueError("evaluated shadow checkpoint is missing")
    if file_sha256(checkpoint) != checkpoint_sha256:
        raise ValueError("evaluated shadow checkpoint hash mismatch")

    active_root = root / "active"
    release = active_root / "releases" / f"{checkpoint_sha256}.pt"
    plan: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "ANTVOICE_PROMOTION_PLAN",
        "execution": "EXECUTED" if execute else "DRY_RUN",
        "source_shadow_checkpoint": str(checkpoint),
        "source_sha256": checkpoint_sha256,
        "evaluation_report": str(report_path),
        "destination_immutable_release": str(release),
        "product_acceptance": PARTIAL_NOT_ANT_FARM_ACCEPTANCE,
        "trainer_writes_active": False,
    }
    if not execute:
        return plan

    release.parent.mkdir(parents=True, exist_ok=True)
    if release.exists():
        if file_sha256(release) != checkpoint_sha256:
            raise ValueError("existing active release hash mismatch")
    else:
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=release.parent,
                prefix=f".{release.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
            shutil.copyfile(checkpoint, temporary_name)
            if file_sha256(temporary_name) != checkpoint_sha256:
                raise ValueError("copied active release hash mismatch")
            with open(temporary_name, "rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary_name, release)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
    atomic_write_json(
        active_root / "CURRENT.json",
        {
            "schema_version": 1,
            "artifact_type": "ANTVOICE_ACTIVE_RELEASE_POINTER",
            "immutable_release": str(release.relative_to(active_root)),
            "sha256": checkpoint_sha256,
            "evaluation_report_sha256": file_sha256(report_path),
            "promoted_utc": datetime.now(timezone.utc).isoformat(),
            "product_acceptance": PARTIAL_NOT_ANT_FARM_ACCEPTANCE,
        },
    )
    return plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--evaluation-report", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = promote(
        run_root=Path(args.run_root),
        evaluation_report=Path(args.evaluation_report),
        execute=args.execute,
    )
    print(json.dumps(plan, sort_keys=True))


if __name__ == "__main__":
    main()
