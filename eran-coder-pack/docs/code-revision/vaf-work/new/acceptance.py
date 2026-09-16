"""Deterministic Stage-1 truth report for the Hebrew Voice Ant Farm."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from acoustic_units import (
    CHECKPOINT_FORMAT, collapse_runs, encode, evaluate_checkpoint, features,
    load_checkpoint, load_wav, write_json_atomic,
)
from colony import DEFAULT_ANTS, colony_digest
from corpus import SPLITS, validate_manifest


def digest_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def report_digest(report: dict) -> str:
    return digest_json({k: v for k, v in report.items() if k != "report_sha256"})


def build_report(project: Path) -> dict:
    project = project.resolve()
    recordings = project / "recordings"
    state = project / "state"
    manifest_path = recordings / "manifest.json"
    manifest = validate_manifest(manifest_path, recordings)
    entries = manifest["entries"]

    audio = {
        "manifest": str(manifest_path),
        "manifest_sha256": manifest["manifest_sha256"],
        "recording_count": len(entries),
        "split_counts": {
            split: sum(entry["split"] == split for entry in entries)
            for split in SPLITS
        },
        "durations_seconds": {
            split: round(sum(
                entry["sample_count"] / entry["sample_rate"]
                for entry in entries if entry["split"] == split
            ), 3)
            for split in SPLITS
        },
        "sample_rates": manifest["sample_rates"],
        "unique_file_hashes": len({entry["audio_sha256"] for entry in entries}),
        "unique_decoded_pcm_hashes": len({entry["pcm_sha256"] for entry in entries}),
        "learning_tokens": manifest["learning_tokens"],
    }

    ants = []
    codebook_hashes = set()
    for ant in DEFAULT_ANTS:
        checkpoint_path = state / ant / "current.json"
        checkpoint = load_checkpoint(checkpoint_path)
        if checkpoint["format_version"] != CHECKPOINT_FORMAT:
            raise ValueError(f"{ant}: current checkpoint is not format {CHECKPOINT_FORMAT}")
        provenance = checkpoint.get("corpus_provenance") or {}
        if provenance.get("manifest_sha256") != manifest["manifest_sha256"]:
            raise ValueError(f"{ant}: checkpoint corpus provenance does not match manifest")
        evaluation = evaluate_checkpoint(checkpoint, recordings / "evaluation")
        codebook_sha256 = digest_json(checkpoint["centers"])
        codebook_hashes.add(codebook_sha256)
        incumbent = checkpoint.get("incumbent_checkpoint_sha256")
        incumbent_exists = bool(
            incumbent and (state / ant / f"candidate-{incumbent[:12]}.json").exists()
        )
        artifact_change_verified = bool(
            checkpoint.get("promotion_eligible")
            and (
                checkpoint.get("promotion_basis") == "first-checkpoint-vs-baseline"
                or (incumbent and incumbent != checkpoint["checkpoint_sha256"] and incumbent_exists)
            )
        )
        ants.append({
            "ant": ant,
            "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "incumbent_checkpoint_sha256": incumbent,
            "incumbent_artifact_exists": incumbent_exists,
            "artifact_change_verified": artifact_change_verified,
            "format_version": checkpoint["format_version"],
            "architecture": checkpoint["architecture"],
            "seed": checkpoint["seed"],
            "units": checkpoint["units"],
            "codebook_sha256": codebook_sha256,
            "promotion_basis": checkpoint.get("promotion_basis"),
            "promotion_eligible": checkpoint.get("promotion_eligible"),
            "train_frame_count": checkpoint["train_frame_count"],
            "heldout_frame_count": checkpoint["heldout_frame_count"],
            "heldout_error_before": checkpoint["heldout_error_before"],
            "heldout_error_after": checkpoint["heldout_error_after"],
            "evaluation": evaluation,
        })
    if len(codebook_hashes) != len(DEFAULT_ANTS):
        raise ValueError("independent ants do not have four distinct codebooks")

    queen_path = state / "queen" / "current.json"
    queen = json.loads(queen_path.read_text(encoding="utf-8"))
    if queen.get("colony_sha256") != colony_digest(queen):
        raise ValueError("Queen manifest hash mismatch")
    if queen.get("corpus_manifest_sha256") != manifest["manifest_sha256"]:
        raise ValueError("Queen corpus provenance does not match manifest")
    expected_winner = min(ants, key=lambda item: item["heldout_error_after"])
    selection = queen.get("queen_selection") or {}
    if selection.get("selected_ant") != expected_winner["ant"]:
        raise ValueError("Queen selection does not match minimum held-out error")
    if selection.get("selected_checkpoint_sha256") != expected_winner["checkpoint_sha256"]:
        raise ValueError("Queen selected checkpoint does not match current ant checkpoint")
    if queen.get("codebooks_merged") is not False:
        raise ValueError("Queen manifest does not preserve independent codebooks")

    source_path = sorted((recordings / "evaluation").glob("*.wav"))[0]
    source = load_wav(source_path)
    selected = load_checkpoint(state / expected_winner["ant"] / "current.json")
    source_features, hop = features(source)
    unit_ids = encode(source_features, np.asarray(selected["centers"], dtype=np.float32))
    segments = collapse_runs(unit_ids, hop)

    layer3_verified = all(ant["artifact_change_verified"] for ant in ants)
    layer4_verified = all(
        ant["heldout_error_after"] < ant["heldout_error_before"]
        and ant["evaluation"]["improved"]
        for ant in ants
    )
    overall = "PARTIAL" if layer3_verified and layer4_verified else "BLOCKED"
    report = {
        "format_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "overall": overall,
        "claim_limit": "waveform acoustic-unit candidates only; not syllables or conversation",
        "layers": {
            "1_audio_capture": {
                "status": "VERIFIED",
                "evidence": "sealed nonempty PCM WAV corpus with known format and split hashes",
            },
            "2_acoustic_learner": {
                "status": "PARTIAL",
                "evidence": "waveform features produced a learned vector codebook and integer unit sequence",
                "missing": "learned boundary and cross-session repeatability evidence sufficient to call units syllable-like",
            },
            "3_learning": {
                "status": "VERIFIED" if layer3_verified else "BLOCKED",
                "evidence": "four sealed promoted checkpoint artifacts created or changed from verified incumbents",
            },
            "4_evaluation": {
                "status": "VERIFIED" if layer4_verified else "BLOCKED",
                "evidence": "held-out promotion metrics and untouched evaluation metrics were recomputed",
            },
            "5_conversation": {
                "status": "BLOCKED",
                "missing": "grounded meaning, approved memory, real reasoning model, learned response units, and spoken Hebrew closed loop",
            },
        },
        "audio": audio,
        "ants": ants,
        "queen": {
            "manifest": str(queen_path),
            "colony_sha256": queen["colony_sha256"],
            "selected_ant": selection["selected_ant"],
            "selected_checkpoint_sha256": selection["selected_checkpoint_sha256"],
            "selection_criterion": selection["criterion"],
            "evaluation_was_not_used_for_selection": selection[
                "evaluation_was_not_used_for_selection"
            ],
            "codebooks_merged": queen["codebooks_merged"],
        },
        "fresh_encode_probe": {
            "source": str(source_path),
            "source_audio_sha256": source.sha256,
            "unit_namespace": f"{selected['checkpoint_sha256']}:unit_id",
            "frame_count": int(len(unit_ids)),
            "segment_count": len(segments),
            "distinct_unit_ids": len(set(int(unit) for unit in unit_ids)),
            "first_20_unit_ids": [int(unit) for unit in unit_ids[:20]],
        },
        "runtime": {
            "mode": "completed-bounded-stage-1-training-and-evaluation",
            "persistent_service_started": False,
            "reason": "no genuine semantic/reasoning/spoken-response service exists to start",
        },
    }
    report["report_sha256"] = report_digest(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--output", default="state/acceptance-current.json")
    args = parser.parse_args()
    project = Path(args.project)
    report = build_report(project)
    output = Path(args.output)
    if not output.is_absolute():
        output = project / output
    write_json_atomic(output, report)
    print(json.dumps({
        "overall": report["overall"],
        "report": str(output.resolve()),
        "report_sha256": report["report_sha256"],
        "layers": {
            name: value["status"] for name, value in report["layers"].items()
        },
    }, sort_keys=True))


if __name__ == "__main__":
    main()
