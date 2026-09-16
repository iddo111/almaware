"""Independent acoustic ants with held-out Queen selection and no codebook merge."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from acoustic_units import evaluate_checkpoint, load_checkpoint, train_ant, write_json_atomic
from corpus import validate_manifest


COLONY_FORMAT = 1
DEFAULT_ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")
DEFAULT_SEEDS = (7007, 7019, 7039, 7057)


def colony_digest(manifest: dict) -> str:
    payload = {k: v for k, v in manifest.items() if k != "colony_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def train_colony(
    recordings: Path, corpus_manifest: Path, state: Path,
    ants: tuple[str, ...] = DEFAULT_ANTS, seeds: tuple[int, ...] = DEFAULT_SEEDS,
    units: int = 64,
) -> dict:
    if len(ants) != len(seeds) or len(set(ants)) != len(ants):
        raise ValueError("ants and unique seeds must have the same length")
    if len(set(seeds)) != len(seeds):
        raise ValueError("every ant requires an independent random seed")
    corpus = validate_manifest(corpus_manifest, recordings)
    sessions = {
        split: sorted({
            entry["session_id"] for entry in corpus["entries"] if entry["split"] == split
        })
        for split in ("train", "heldout", "evaluation")
    }
    corpus_provenance = {
        "manifest_sha256": corpus["manifest_sha256"],
        "sample_rates": corpus["sample_rates"],
        "speaker_ids": sorted({entry["speaker_id"] for entry in corpus["entries"]}),
        "sessions": sessions,
    }
    train_folder = recordings / "train"
    heldout_folder = recordings / "heldout"
    evaluation_folder = recordings / "evaluation"
    results = []
    for ant, seed in zip(ants, seeds):
        _, _candidate = train_ant(
            train_folder, heldout_folder, state, ant, units, seed, corpus_provenance
        )
        current_path = state / ant / "current.json"
        if not current_path.exists():
            continue
        checkpoint = load_checkpoint(current_path)
        evaluation = evaluate_checkpoint(checkpoint, evaluation_folder)
        results.append({
            "ant": ant,
            "seed": checkpoint["seed"],
            "checkpoint": str(
                (state / ant / f"candidate-{checkpoint['checkpoint_sha256'][:12]}.json")
                .relative_to(state).as_posix()
            ),
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "heldout_error_before": checkpoint["heldout_error_before"],
            "heldout_error_after": checkpoint["heldout_error_after"],
            "improved_over_baseline": checkpoint["improved_over_baseline"],
            "evaluation": evaluation,
        })
    if not results:
        raise ValueError("no ant has a promoted current checkpoint")
    experiment_namespaces = {
        load_checkpoint(state / result["checkpoint"])["experiment_namespace"]
        for result in results
    }
    if len(experiment_namespaces) != 1:
        raise ValueError("Queen cannot compare ants from different feature/unit experiments")
    winner = min(results, key=lambda result: result["heldout_error_after"])
    queen = {
        "format_version": COLONY_FORMAT,
        "architecture": "independent-waveform-acoustic-colony",
        "corpus_manifest_sha256": corpus["manifest_sha256"],
        "experiment_namespace": next(iter(experiment_namespaces)),
        "ants": results,
        "queen_selection": {
            "selected_ant": winner["ant"],
            "selected_checkpoint_sha256": winner["checkpoint_sha256"],
            "criterion": "minimum-heldout-quantization-error",
            "evaluation_was_not_used_for_selection": True,
        },
        "codebooks_merged": False,
        "unit_namespace": "checkpoint_sha256:unit_id",
        "claim_limit": "acoustic candidates and learned-exemplar reconstruction only",
    }
    queen["colony_sha256"] = colony_digest(queen)
    queen_state = state / "queen"
    queen_state.mkdir(parents=True, exist_ok=True)
    candidate = queen_state / f"candidate-{queen['colony_sha256'][:12]}.json"
    write_json_atomic(candidate, queen)
    current = queen_state / "current.json"
    existing = json.loads(current.read_text(encoding="utf-8")) if current.exists() else None
    if not existing or existing.get("colony_sha256") != queen["colony_sha256"]:
        write_json_atomic(current, queen)
    return queen


def train_command(args) -> None:
    queen = train_colony(
        Path(args.recordings), Path(args.manifest), Path(args.state),
        units=args.units,
    )
    print(json.dumps({
        "colony_sha256": queen["colony_sha256"],
        "selected_ant": queen["queen_selection"]["selected_ant"],
        "selected_checkpoint_sha256": queen["queen_selection"]["selected_checkpoint_sha256"],
        "codebooks_merged": queen["codebooks_merged"],
        "claim_limit": queen["claim_limit"],
    }))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    train = commands.add_parser("train")
    train.add_argument("--recordings", required=True)
    train.add_argument("--manifest", required=True)
    train.add_argument("--state", default="state")
    train.add_argument("--units", type=int, default=64)
    train.set_defaults(fn=train_command)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
