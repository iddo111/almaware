"""Evening tribal fire: sound-only cultural exchange between independent ants.

Every ant synthesizes utterances from its own learned codebook and waveform
exemplars, and every other ant hears them as ordinary training audio through
its own quantizer. Nothing crosses the fire but sound: no weights, no
codebooks, no unit IDs. Real human audio always stays in every training mix,
and held-out error is always measured against real recordings only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from acoustic_units import (
    load_checkpoint, load_wav, reconstruct, train_ant, write_json_atomic,
    write_wav_atomic,
)
from colony import DEFAULT_ANTS, next_round, round_seeds, train_colony


FIRE_FORMAT = 1
DEFAULT_MAX_SYNTHETIC = 0.3
DEFAULT_UTTERANCES = 3
FORBIDDEN_FIRE_KEYS = {
    "centers", "baseline_center", "codebook", "codebooks", "weights",
    "exemplars_pcm16", "exemplar_source_hashes", "exemplar_source_frame_indexes",
    "unit_ids",
}


def fire_manifest_digest(manifest: dict) -> str:
    payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def speak(checkpoint: dict, train_folder: Path, out_folder: Path, utterances: int) -> list[dict]:
    """Synthesize utterances from one ant's own codebook and waveform exemplars."""
    if utterances < 1:
        raise ValueError("every ant must speak at least one utterance")
    sources = sorted(train_folder.glob("*.wav"))
    if not sources:
        raise ValueError(f"no real training audio in {train_folder}")
    spoken = []
    for index, source_path in enumerate(sources[:utterances]):
        source = load_wav(source_path)
        samples, _unit_ids = reconstruct(source, checkpoint)
        path = out_folder / f"utterance-{index:03d}.wav"
        write_wav_atomic(path, samples, checkpoint["exemplar_rate"])
        audio = load_wav(path)
        spoken.append({
            "path": path.name,
            "audio_sha256": audio.sha256,
            "pcm_sha256": audio.pcm_sha256,
            "sample_rate": audio.rate,
            "sample_count": int(len(audio.samples)),
            "duration_seconds": round(len(audio.samples) / audio.rate, 6),
        })
    return spoken


def build_training_mix(
    ant: str, recordings: Path, round_dir: Path, producers: dict, max_synthetic: float,
) -> dict:
    """Mix = the ant's own real audio plus OTHER ants' fire audio, capped."""
    if not 0.0 <= max_synthetic < 1.0:
        raise ValueError("max synthetic proportion must be in [0, 1)")
    train_folder = recordings / "train"
    real_paths = sorted(train_folder.glob("*.wav"))
    if not real_paths:
        raise ValueError("real human audio must stay in every training mix")
    mix_dir = round_dir / "mix" / ant
    mix_dir.mkdir(parents=True)
    real_seconds = 0.0
    for path in real_paths:
        audio = load_wav(path)
        real_seconds += len(audio.samples) / audio.rate
        shutil.copyfile(path, mix_dir / f"real-{path.name}")
    own_hashes = {entry["pcm_sha256"] for entry in producers[ant]["files"]}
    budget = real_seconds * max_synthetic / (1.0 - max_synthetic)
    synthetic_seconds = 0.0
    fire_files = []
    for producer in sorted(producers):
        if producer == ant:
            continue
        for entry in producers[producer]["files"]:
            if entry["pcm_sha256"] in own_hashes:
                continue
            duration = entry["duration_seconds"]
            if synthetic_seconds + duration > budget + 1e-9:
                continue
            name = f"fire-{producer}-{entry['path']}"
            shutil.copyfile(round_dir / producer / entry["path"], mix_dir / name)
            synthetic_seconds += duration
            fire_files.append({
                "producer": producer,
                "path": name,
                "pcm_sha256": entry["pcm_sha256"],
                "duration_seconds": duration,
            })
    proportion = synthetic_seconds / (real_seconds + synthetic_seconds)
    if proportion > max_synthetic + 1e-9:
        raise ValueError("synthetic proportion cap violated")
    return {
        "directory": f"mix/{ant}",
        "real_file_count": len(real_paths),
        "real_seconds": round(real_seconds, 6),
        "fire_files": fire_files,
        "fire_file_count": len(fire_files),
        "synthetic_seconds": round(synthetic_seconds, 6),
        "synthetic_proportion": round(proportion, 6),
        "max_synthetic": max_synthetic,
        "own_fire_excluded": True,
    }


def validate_fire_round(round_dir: Path) -> dict:
    """Only sound and a provenance manifest may exist inside a fire round."""
    manifest_path = round_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != FIRE_FORMAT:
        raise ValueError("unsupported fire manifest format")
    if manifest.get("manifest_sha256") != fire_manifest_digest(manifest):
        raise ValueError("fire manifest hash mismatch")
    for path in round_dir.rglob("*"):
        if path.is_dir() or path == manifest_path:
            continue
        if path.suffix != ".wav":
            raise ValueError(f"only sound crosses the fire: {path}")

    def scan(value: object) -> None:
        if isinstance(value, dict):
            leaked = FORBIDDEN_FIRE_KEYS & set(value)
            if leaked:
                raise ValueError(f"fire manifest leaks model internals: {sorted(leaked)}")
            for inner in value.values():
                scan(inner)
        elif isinstance(value, list):
            for inner in value:
                scan(inner)

    scan(manifest)
    for ant, mix in manifest.get("mixes", {}).items():
        if any(entry["producer"] == ant for entry in mix.get("fire_files", [])):
            raise ValueError(f"{ant} must never ingest its own fire audio")
    return manifest


def run_fire_round(
    state: Path, recordings: Path, fire_root: Path,
    ants: tuple[str, ...] = DEFAULT_ANTS,
    utterances: int = DEFAULT_UTTERANCES,
    max_synthetic: float = DEFAULT_MAX_SYNTHETIC,
    round_id: str | None = None,
) -> dict:
    if not 0.0 <= max_synthetic < 1.0:
        raise ValueError("max synthetic proportion must be in [0, 1)")
    round_id = round_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    round_dir = fire_root / round_id
    if round_dir.exists():
        raise ValueError(f"fire round already exists: {round_dir}")
    producers = {}
    for ant in ants:
        checkpoint = load_checkpoint(state / ant / "current.json")
        out_folder = round_dir / ant
        out_folder.mkdir(parents=True)
        files = speak(checkpoint, recordings / "train", out_folder, utterances)
        producers[ant] = {
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "utterance_count": len(files),
            "files": files,
        }
    mixes = {
        ant: build_training_mix(ant, recordings, round_dir, producers, max_synthetic)
        for ant in ants
    }
    manifest = {
        "format_version": FIRE_FORMAT,
        "architecture": "tribal-fire-sound-only-exchange",
        "round_id": round_id,
        "crossed_the_fire": "synthesized-waveforms-only",
        "never_shared": "weights-codebooks-unit-identifiers",
        "max_synthetic": max_synthetic,
        "producers": producers,
        "mixes": mixes,
    }
    manifest["manifest_sha256"] = fire_manifest_digest(manifest)
    write_json_atomic(round_dir / "manifest.json", manifest)
    validate_fire_round(round_dir)
    return manifest


def run_cycle(
    recordings: Path, corpus_manifest: Path, state: Path, fire_root: Path,
    units: int = 64,
    ants: tuple[str, ...] = DEFAULT_ANTS,
    utterances: int = DEFAULT_UTTERANCES,
    max_synthetic: float = DEFAULT_MAX_SYNTHETIC,
    round_id: str | None = None,
) -> dict:
    """Train on real audio, hold a fire, retrain on the mixes, then remeasure.

    Held-out error is always measured against real recordings only; a fire
    round that does not improve it is reported as not improving it.
    """
    train_colony(recordings, corpus_manifest, state, units=units)
    incumbents = {ant: load_checkpoint(state / ant / "current.json") for ant in ants}
    fire = run_fire_round(
        state, recordings, fire_root,
        ants=ants, utterances=utterances,
        max_synthetic=max_synthetic, round_id=round_id,
    )
    round_dir = fire_root / fire["round_id"]
    results = []
    # Fresh restart seeds for the post-fire retrain too: reusing incumbent["seed"]
    # made the retrain a pure function of a mix that never changed, so the fire
    # could never promote anything.
    fire_seeds = round_seeds(next_round(state))
    for index, ant in enumerate(ants):
        incumbent = incumbents[ant]
        provenance = dict(incumbent.get("corpus_provenance") or {})
        provenance["tribal_fire"] = {
            "round_id": fire["round_id"],
            "fire_manifest_sha256": fire["manifest_sha256"],
            "synthetic_proportion": fire["mixes"][ant]["synthetic_proportion"],
            "heard_from": sorted({
                entry["producer"] for entry in fire["mixes"][ant]["fire_files"]
            }),
        }
        candidate, _ = train_ant(
            round_dir / "mix" / ant, recordings / "heldout", state, ant,
            incumbent["units"], fire_seeds[index], provenance,
        )
        current = load_checkpoint(state / ant / "current.json")
        results.append({
            "ant": ant,
            "heldout_error_before_fire": incumbent["heldout_error_after"],
            "fire_candidate_heldout_error": candidate["heldout_error_after"],
            "fire_candidate_promoted": bool(candidate["promotion_eligible"]),
            "heldout_error_after_fire": current["heldout_error_after"],
            "improved_after_fire": (
                current["heldout_error_after"]
                < incumbent["heldout_error_after"] - 1e-9
            ),
        })
    queen = train_colony(recordings, corpus_manifest, state, units=units)
    return {
        "format_version": FIRE_FORMAT,
        "round_id": fire["round_id"],
        "fire_manifest_sha256": fire["manifest_sha256"],
        "heldout_measured_against": "real-recordings-only",
        "ants": results,
        "fire_improved_any_ant": any(result["improved_after_fire"] for result in results),
        # State of each ant at the END of the cycle. `ants[].heldout_error_after_fire`
        # above is captured before the closing train_colony, so on its own it hides
        # any improvement that the closing colony round promotes.
        "heldout_error_after_cycle": {
            entry["ant"]: entry["heldout_error_after"] for entry in queen["ants"]
        },
        "queen_selection_after": queen["queen_selection"],
        "colony_sha256_after": queen["colony_sha256"],
        "claim_limit": "sound-only cultural transmission; no weights or codebooks shared",
    }


def round_command(args) -> None:
    manifest = run_fire_round(
        Path(args.state), Path(args.recordings), Path(args.out),
        utterances=args.utterances, max_synthetic=args.max_synthetic,
        round_id=args.round_id,
    )
    print(json.dumps({
        "round_id": manifest["round_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "utterances": {
            ant: producer["utterance_count"]
            for ant, producer in manifest["producers"].items()
        },
        "synthetic_proportions": {
            ant: mix["synthetic_proportion"] for ant, mix in manifest["mixes"].items()
        },
        "never_shared": manifest["never_shared"],
    }))


def cycle_command(args) -> None:
    cycle = run_cycle(
        Path(args.recordings), Path(args.manifest), Path(args.state), Path(args.out),
        units=args.units, utterances=args.utterances,
        max_synthetic=args.max_synthetic, round_id=args.round_id,
    )
    print(json.dumps(cycle))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    fire_round = commands.add_parser("round")
    fire_round.add_argument("--state", default="state")
    fire_round.add_argument("--recordings", required=True)
    fire_round.add_argument("--out", default="fire")
    fire_round.add_argument("--max-synthetic", type=float, default=DEFAULT_MAX_SYNTHETIC)
    fire_round.add_argument("--utterances", type=int, default=DEFAULT_UTTERANCES)
    fire_round.add_argument("--round-id", default=None)
    fire_round.set_defaults(fn=round_command)
    cycle = commands.add_parser("cycle")
    cycle.add_argument("--state", default="state")
    cycle.add_argument("--recordings", required=True)
    cycle.add_argument("--manifest", required=True)
    cycle.add_argument("--out", default="fire")
    cycle.add_argument("--units", type=int, default=64)
    cycle.add_argument("--max-synthetic", type=float, default=DEFAULT_MAX_SYNTHETIC)
    cycle.add_argument("--utterances", type=int, default=DEFAULT_UTTERANCES)
    cycle.add_argument("--round-id", default=None)
    cycle.set_defaults(fn=cycle_command)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
