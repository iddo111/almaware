"""Truth-gated boundary and repeatability metrics for acoustic-unit candidates.

The evaluator is deliberately annotation-driven.  It never accepts text,
transcripts, letters, words, or text-derived tokens.  It measures only whether
checkpoint-namespaced acoustic-unit transitions agree with human-supplied
waveform boundaries and whether opaque repetition groups are more repeatable
across independent recording sessions than unrelated groups.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from acoustic_units import (
    CHECKPOINT_FORMAT,
    FEATURE_SPEC,
    encode,
    features,
    load_checkpoint,
    load_wav,
    write_json_atomic,
)
from corpus import validate_manifest


ANNOTATION_FORMAT = 1
REPORT_FORMAT = 1
ANNOTATION_ARCHITECTURE = "waveform-boundary-repeatability-annotations"
REPORT_ARCHITECTURE = "checkpoint-namespaced-acoustic-candidate-evaluation"
BOUNDARY_TOLERANCE_SECONDS = 0.020
GROUP_ID_PATTERN = re.compile(r"rg-[0-9a-f]{32}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
CLAIM_LIMIT = (
    "acoustic-unit candidate metrics only; not syllable, word, meaning, "
    "speech, or conversation acceptance"
)

_TOP_LEVEL_KEYS = {
    "format_version",
    "architecture",
    "corpus_manifest_sha256",
    "checkpoint_sha256",
    "entries",
    "annotations_sha256",
}
_ENTRY_BASE_KEYS = {
    "path",
    "split",
    "speaker_id",
    "session_id",
    "audio_sha256",
    "pcm_sha256",
    "repetition_group_id",
}
_BOUNDARY_KEYS = {"boundaries_samples", "boundaries_seconds"}


def _canonical_json_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def annotation_digest(annotations: dict) -> str:
    """Return the SHA-256 seal over an annotation document's signed fields."""
    return _canonical_json_digest({
        key: value for key, value in annotations.items()
        if key != "annotations_sha256"
    })


def report_digest(report: dict) -> str:
    """Return the SHA-256 seal over a metrics report's signed fields."""
    return _canonical_json_digest({
        key: value for key, value in report.items()
        if key != "report_sha256"
    })


def _strict_json_object(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"annotation file is required: {path}")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key is forbidden: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number is forbidden: {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid annotation JSON: {path}") from exc
    if type(value) is not dict:
        raise ValueError("annotation document must be a JSON object")
    return value


def _require_sha256(value: object, field: str) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 hex string")
    return value


def _validate_current_checkpoint(checkpoint_path: Path, manifest: dict) -> dict:
    checkpoint_path = checkpoint_path.resolve()
    if checkpoint_path.name != "current.json":
        raise ValueError("checkpoint must be a sealed current.json artifact")
    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint.get("format_version") != CHECKPOINT_FORMAT:
        raise ValueError("checkpoint is not the current acoustic checkpoint format")
    if checkpoint.get("architecture") != (
        "waveform-acoustic-vector-quantizer-with-exemplars"
    ):
        raise ValueError("checkpoint is not the waveform acoustic learner")
    if checkpoint.get("feature_spec") != FEATURE_SPEC:
        raise ValueError("checkpoint feature specification mismatch")
    if checkpoint_path.parent.name != checkpoint.get("ant"):
        raise ValueError("checkpoint path does not match its ant identity")

    entries = manifest["entries"]
    expected_provenance = {
        "manifest_sha256": manifest["manifest_sha256"],
        "sample_rates": manifest["sample_rates"],
        "speaker_ids": sorted({entry["speaker_id"] for entry in entries}),
        "sessions": {
            split: sorted({
                entry["session_id"] for entry in entries
                if entry["split"] == split
            })
            for split in ("train", "heldout", "evaluation")
        },
    }
    if checkpoint.get("corpus_provenance") != expected_provenance:
        raise ValueError("checkpoint corpus provenance does not exactly match manifest")
    expected_train = sorted(
        entry["pcm_sha256"] for entry in entries if entry["split"] == "train"
    )
    expected_heldout = sorted(
        entry["pcm_sha256"] for entry in entries if entry["split"] == "heldout"
    )
    if checkpoint.get("train_audio_hashes") != expected_train:
        raise ValueError("checkpoint training-audio provenance does not match manifest")
    if checkpoint.get("heldout_audio_hashes") != expected_heldout:
        raise ValueError("checkpoint held-out provenance does not match manifest")
    return checkpoint


def _boundaries_seconds(entry: dict, manifest_entry: dict) -> tuple[str, list[float]]:
    present = _BOUNDARY_KEYS & set(entry)
    if len(present) != 1:
        raise ValueError(
            f"{entry.get('path', '<unknown>')}: provide exactly one of "
            "boundaries_samples or boundaries_seconds"
        )
    key = next(iter(present))
    values = entry[key]
    if type(values) is not list or not values:
        raise ValueError(f"{entry['path']}: boundary list must be nonempty")
    if len(values) > manifest_entry["sample_count"]:
        raise ValueError(f"{entry['path']}: implausibly many boundaries")

    sample_rate = manifest_entry["sample_rate"]
    duration = manifest_entry["sample_count"] / sample_rate
    converted = []
    previous = -math.inf
    for value in values:
        if key == "boundaries_samples":
            if type(value) is not int:
                raise ValueError(f"{entry['path']}: sample boundaries must be integers")
            if not 0 < value < manifest_entry["sample_count"]:
                raise ValueError(f"{entry['path']}: sample boundary outside audio")
            seconds = value / sample_rate
        else:
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise ValueError(f"{entry['path']}: time boundaries must be finite numbers")
            seconds = float(value)
            if not 0.0 < seconds < duration:
                raise ValueError(f"{entry['path']}: time boundary outside audio")
        if seconds <= previous:
            raise ValueError(f"{entry['path']}: boundaries must be strictly increasing")
        converted.append(seconds)
        previous = seconds
    return key, converted


def _validate_annotations(
    annotation_path: Path, manifest: dict, checkpoint: dict
) -> tuple[list[dict], str]:
    annotations = _strict_json_object(annotation_path)
    if set(annotations) != _TOP_LEVEL_KEYS:
        raise ValueError("annotation document has missing or forbidden top-level fields")
    if (
        type(annotations.get("format_version")) is not int
        or annotations["format_version"] != ANNOTATION_FORMAT
    ):
        raise ValueError("unsupported annotation format")
    if annotations.get("architecture") != ANNOTATION_ARCHITECTURE:
        raise ValueError("annotation architecture mismatch")
    _require_sha256(annotations.get("corpus_manifest_sha256"), "corpus_manifest_sha256")
    _require_sha256(annotations.get("checkpoint_sha256"), "checkpoint_sha256")
    _require_sha256(annotations.get("annotations_sha256"), "annotations_sha256")
    if annotations["annotations_sha256"] != annotation_digest(annotations):
        raise ValueError("annotation document hash mismatch")
    if annotations["corpus_manifest_sha256"] != manifest["manifest_sha256"]:
        raise ValueError("annotation corpus provenance does not match manifest")
    if annotations["checkpoint_sha256"] != checkpoint["checkpoint_sha256"]:
        raise ValueError("annotation checkpoint provenance does not match current checkpoint")
    if type(annotations["entries"]) is not list or not annotations["entries"]:
        raise ValueError("annotation entries must be a nonempty list")

    eligible = {
        entry["path"]: entry for entry in manifest["entries"]
        if entry["split"] in {"heldout", "evaluation"}
    }
    validated = []
    seen_paths: set[str] = set()
    seen_audio_hashes: set[str] = set()
    seen_pcm_hashes: set[str] = set()
    for annotation in annotations["entries"]:
        if type(annotation) is not dict:
            raise ValueError("every annotation entry must be a JSON object")
        present_boundaries = _BOUNDARY_KEYS & set(annotation)
        if set(annotation) != _ENTRY_BASE_KEYS | present_boundaries:
            raise ValueError("annotation entry has missing or forbidden fields")
        if len(present_boundaries) != 1:
            raise ValueError("annotation entry requires exactly one boundary coordinate field")
        path = annotation.get("path")
        if type(path) is not str or path not in eligible:
            raise ValueError("annotations may contain only heldout/evaluation manifest paths")
        if path in seen_paths:
            raise ValueError(f"duplicate annotation path: {path}")
        seen_paths.add(path)
        manifest_entry = eligible[path]
        for field in (
            "split", "speaker_id", "session_id", "audio_sha256", "pcm_sha256"
        ):
            if type(annotation.get(field)) is not str:
                raise ValueError(f"{path}: {field} must be a string")
            if field in {"speaker_id", "session_id"} and not annotation[field]:
                raise ValueError(f"{path}: {field} must be nonempty")
            if annotation[field] != manifest_entry[field]:
                raise ValueError(f"{path}: {field} does not match corpus manifest")
        _require_sha256(annotation["audio_sha256"], f"{path}: audio_sha256")
        _require_sha256(annotation["pcm_sha256"], f"{path}: pcm_sha256")
        group = annotation.get("repetition_group_id")
        if type(group) is not str or GROUP_ID_PATTERN.fullmatch(group) is None:
            raise ValueError(
                f"{path}: repetition_group_id must be opaque rg- plus 32 lowercase hex digits"
            )
        if annotation["audio_sha256"] in seen_audio_hashes:
            raise ValueError("annotated recordings must have unique container hashes")
        if annotation["pcm_sha256"] in seen_pcm_hashes:
            raise ValueError("annotated recordings must have unique decoded-PCM hashes")
        seen_audio_hashes.add(annotation["audio_sha256"])
        seen_pcm_hashes.add(annotation["pcm_sha256"])
        coordinate_kind, seconds = _boundaries_seconds(annotation, manifest_entry)
        validated.append({
            **annotation,
            "boundary_coordinate_kind": coordinate_kind,
            "boundary_seconds": seconds,
            "sample_rate": manifest_entry["sample_rate"],
            "sample_count": manifest_entry["sample_count"],
        })

    if seen_paths != set(eligible):
        missing = sorted(set(eligible) - seen_paths)
        extra = sorted(seen_paths - set(eligible))
        raise ValueError(
            f"annotations are incomplete for the sealed non-train corpus; "
            f"missing={missing}, extra={extra}"
        )

    sessions_by_group: dict[str, set[str]] = defaultdict(set)
    splits_by_group: dict[str, set[str]] = defaultdict(set)
    for entry in validated:
        group = entry["repetition_group_id"]
        sessions_by_group[group].add(entry["session_id"])
        splits_by_group[group].add(entry["split"])
    if len(sessions_by_group) < 2:
        raise ValueError("at least two independent opaque repetition groups are required")
    for group in sorted(sessions_by_group):
        if len(sessions_by_group[group]) < 2:
            raise ValueError(f"{group}: repetition group needs at least two sessions")
        if splits_by_group[group] != {"heldout", "evaluation"}:
            raise ValueError(
                f"{group}: repetition group must cover heldout and evaluation independently"
            )
    return (
        sorted(validated, key=lambda entry: entry["path"]),
        annotations["annotations_sha256"],
    )


def match_boundaries(
    predicted: list[float], reference: list[float],
    tolerance_seconds: float = BOUNDARY_TOLERANCE_SECONDS,
) -> tuple[int, int, int, list[float]]:
    """Deterministically match sorted transition/reference times within tolerance."""
    if tolerance_seconds != BOUNDARY_TOLERANCE_SECONDS:
        raise ValueError("boundary tolerance is fixed at 20 milliseconds")
    predicted = sorted(predicted)
    reference = sorted(reference)
    i = j = 0
    errors = []
    epsilon = 1e-12
    while i < len(predicted) and j < len(reference):
        delta = predicted[i] - reference[j]
        if abs(delta) <= tolerance_seconds + epsilon:
            errors.append(abs(delta))
            i += 1
            j += 1
        elif delta < -tolerance_seconds - epsilon:
            i += 1
        else:
            j += 1
    true_positive = len(errors)
    return (
        true_positive,
        len(predicted) - true_positive,
        len(reference) - true_positive,
        errors,
    )


def _scores(true_positive: int, false_positive: int, false_negative: int) -> dict:
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = true_positive / precision_denominator if precision_denominator else 0.0
    recall = true_positive / recall_denominator if recall_denominator else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 9),
        "recall": round(recall, 9),
        "f1": round(f1, 9),
    }


def _collapsed_units(unit_ids: np.ndarray) -> tuple[int, ...]:
    if len(unit_ids) == 0:
        return ()
    changes = np.concatenate((np.array([True]), unit_ids[1:] != unit_ids[:-1]))
    return tuple(int(value) for value in unit_ids[changes])


def _sequence_digest(namespace: str, sequence: tuple[int, ...]) -> str:
    values = np.asarray(sequence, dtype="<i4")
    return hashlib.sha256(namespace.encode() + b"\0" + values.tobytes()).hexdigest()


def alignment_similarity(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    """Return deterministic normalized Levenshtein similarity for unit sequences."""
    if not left and not right:
        return 1.0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_value in enumerate(left, start=1):
        current = [i]
        for j, right_value in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left_value != right_value),
            ))
        previous = current
    distance = previous[-1]
    return 1.0 - distance / max(len(left), len(right))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_annotations(
    checkpoint_path: Path, manifest_path: Path, recordings_root: Path,
    annotation_path: Path,
) -> dict:
    """Validate all provenance and compute deterministic candidate-only metrics."""
    recordings_root = recordings_root.resolve()
    manifest_path = manifest_path.resolve()
    try:
        manifest_path.relative_to(recordings_root)
    except ValueError as exc:
        raise ValueError("corpus manifest must be inside the recordings root") from exc
    manifest = validate_manifest(manifest_path, recordings_root)
    checkpoint = _validate_current_checkpoint(checkpoint_path, manifest)
    annotated, annotations_sha256 = _validate_annotations(
        annotation_path, manifest, checkpoint
    )
    centers = np.asarray(checkpoint["centers"], dtype=np.float32)
    namespace = f"{checkpoint['checkpoint_sha256']}:unit_id"

    rows = []
    total_tp = total_fp = total_fn = 0
    all_errors: list[float] = []
    sequences: dict[str, tuple[int, ...]] = {}
    for annotation in annotated:
        wav_path = (recordings_root / annotation["path"]).resolve()
        try:
            wav_path.relative_to(recordings_root)
        except ValueError as exc:
            raise ValueError(f"audio path escapes recordings root: {annotation['path']}") from exc
        audio = load_wav(wav_path)
        if audio.sha256 != annotation["audio_sha256"]:
            raise ValueError(f"audio changed after annotation: {annotation['path']}")
        if audio.pcm_sha256 != annotation["pcm_sha256"]:
            raise ValueError(f"decoded PCM changed after annotation: {annotation['path']}")
        acoustic_features, hop_seconds = features(audio)
        unit_ids = encode(acoustic_features, centers)
        transition_indexes = np.flatnonzero(unit_ids[1:] != unit_ids[:-1]) + 1
        predicted = [float(index) * hop_seconds for index in transition_indexes]
        tp, fp, fn, errors = match_boundaries(predicted, annotation["boundary_seconds"])
        total_tp += tp
        total_fp += fp
        total_fn += fn
        all_errors.extend(errors)
        sequence = _collapsed_units(unit_ids)
        sequences[annotation["path"]] = sequence
        rows.append({
            "path": annotation["path"],
            "split": annotation["split"],
            "speaker_id": annotation["speaker_id"],
            "session_id": annotation["session_id"],
            "repetition_group_id": annotation["repetition_group_id"],
            "boundary_coordinate_kind": annotation["boundary_coordinate_kind"],
            "reference_boundary_count": len(annotation["boundary_seconds"]),
            "predicted_boundary_count": len(predicted),
            "boundary_metrics": _scores(tp, fp, fn),
            "frame_count": int(len(unit_ids)),
            "collapsed_unit_count": len(sequence),
            "unit_sequence_sha256": _sequence_digest(namespace, sequence),
        })

    within_pairs = []
    between_pairs = []
    for left_index, left in enumerate(annotated):
        for right in annotated[left_index + 1:]:
            left_session = left["session_id"]
            right_session = right["session_id"]
            if left_session == right_session:
                continue
            similarity = alignment_similarity(
                sequences[left["path"]], sequences[right["path"]]
            )
            pair = {
                "left_path": left["path"],
                "right_path": right["path"],
                "similarity": round(similarity, 9),
            }
            if left["repetition_group_id"] == right["repetition_group_id"]:
                within_pairs.append({
                    **pair,
                    "repetition_group_id": left["repetition_group_id"],
                })
            else:
                between_pairs.append({
                    **pair,
                    "left_repetition_group_id": left["repetition_group_id"],
                    "right_repetition_group_id": right["repetition_group_id"],
                })
    if not within_pairs:
        raise ValueError("no cross-session within-group comparisons were produced")
    if not between_pairs:
        raise ValueError("no independent cross-session between-group evidence was produced")

    per_group = []
    for group in sorted({entry["repetition_group_id"] for entry in annotated}):
        group_paths = {entry["path"] for entry in annotated if entry["repetition_group_id"] == group}
        similarities = [
            pair["similarity"] for pair in within_pairs
            if pair["left_path"] in group_paths and pair["right_path"] in group_paths
        ]
        if not similarities:
            raise ValueError(f"{group}: no independent within-group comparison")
        per_group.append({
            "repetition_group_id": group,
            "recording_count": len(group_paths),
            "session_count": len({
                entry["session_id"]
                for entry in annotated if entry["path"] in group_paths
            }),
            "cross_session_pair_count": len(similarities),
            "mean_alignment_similarity": round(_mean(similarities), 9),
        })

    within_values = [pair["similarity"] for pair in within_pairs]
    between_values = [pair["similarity"] for pair in between_pairs]
    within_mean = _mean(within_values)
    between_mean = _mean(between_values)
    boundary = _scores(total_tp, total_fp, total_fn)
    boundary.update({
        "tolerance_seconds": BOUNDARY_TOLERANCE_SECONDS,
        "matched_mean_absolute_error_seconds": (
            round(_mean(all_errors), 9) if all_errors else None
        ),
    })
    report = {
        "format_version": REPORT_FORMAT,
        "architecture": REPORT_ARCHITECTURE,
        "status": "METRICS_COMPUTED",
        "acceptance_status": "UNVERIFIED",
        "claim_limit": CLAIM_LIMIT,
        "synthetic_test_limit": "synthetic fixtures prove evaluator mechanics only",
        "checkpoint": {
            "ant": checkpoint["ant"],
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "unit_namespace": namespace,
        },
        "corpus_manifest_sha256": manifest["manifest_sha256"],
        "annotations_sha256": annotations_sha256,
        "coverage": {
            "annotated_recording_count": len(annotated),
            "eligible_recording_count": len([
                entry for entry in manifest["entries"]
                if entry["split"] in {"heldout", "evaluation"}
            ]),
            "splits": sorted({entry["split"] for entry in annotated}),
            "independent_repetition_group_count": len(per_group),
            "all_groups_cross_session": True,
        },
        "boundary_metrics": boundary,
        "repeatability_metrics": {
            "alignment": "collapsed-unit normalized Levenshtein similarity",
            "within_group_cross_session_pair_count": len(within_pairs),
            "between_group_cross_session_pair_count": len(between_pairs),
            "within_group_mean_similarity": round(within_mean, 9),
            "between_group_mean_similarity": round(between_mean, 9),
            "within_minus_between_margin": round(within_mean - between_mean, 9),
            "within_exceeds_between": within_mean > between_mean,
            "groups": per_group,
            "within_group_pairs": within_pairs,
            "between_group_pairs": between_pairs,
        },
        "recordings": rows,
    }
    report["report_sha256"] = report_digest(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--checkpoint", required=True)
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--recordings", required=True)
    evaluate.add_argument("--annotations", required=True)
    evaluate.add_argument("--output")
    args = parser.parse_args()
    report = evaluate_annotations(
        Path(args.checkpoint), Path(args.manifest), Path(args.recordings),
        Path(args.annotations),
    )
    if args.output:
        write_json_atomic(Path(args.output), report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
