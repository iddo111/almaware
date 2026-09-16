"""Session-aware, waveform-only corpus manifest for the Hebrew Voice Ant Farm."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from acoustic_units import load_wav, write_json_atomic


MANIFEST_FORMAT = 1
SPLITS = ("train", "heldout", "evaluation")
FORBIDDEN_LEARNING_FIELDS = {"text", "transcript", "tokens", "letters", "words"}


def manifest_digest(manifest: dict) -> str:
    payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(root: Path, speaker: str, sessions: dict[str, str]) -> dict:
    missing = set(SPLITS) - set(sessions)
    if missing:
        raise ValueError(f"missing session IDs for: {', '.join(sorted(missing))}")
    if len(set(sessions.values())) != len(SPLITS):
        raise ValueError("train, held-out, and evaluation must use different recording sessions")
    entries = []
    for split in SPLITS:
        folder = root / split
        paths = sorted(folder.glob("*.wav"))
        if not paths:
            raise ValueError(f"no WAV recordings in {folder}")
        for path in paths:
            audio = load_wav(path)
            entries.append({
                "path": path.relative_to(root).as_posix(),
                "split": split,
                "speaker_id": speaker,
                "session_id": sessions[split],
                "audio_sha256": audio.sha256,
                "pcm_sha256": audio.pcm_sha256,
                "sample_rate": audio.rate,
                "sample_count": int(len(audio.samples)),
            })
    manifest = {
        "format_version": MANIFEST_FORMAT,
        "architecture": "private-waveform-only-corpus",
        "learning_tokens": "waveform-features-only",
        "private": True,
        "entries": entries,
        "sample_rates": sorted({entry["sample_rate"] for entry in entries}),
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    return manifest


def validate_manifest(path: Path, root: Path | None = None) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != MANIFEST_FORMAT:
        raise ValueError("unsupported corpus manifest format")
    if manifest.get("manifest_sha256") != manifest_digest(manifest):
        raise ValueError("corpus manifest hash mismatch")
    if manifest.get("learning_tokens") != "waveform-features-only":
        raise ValueError("corpus manifest is not waveform-only")
    if FORBIDDEN_LEARNING_FIELDS & set(manifest):
        raise ValueError("text-derived learning fields are forbidden")
    root = (root or path.parent).resolve()
    seen_paths: set[str] = set()
    seen_hashes: dict[str, str] = {}
    seen_pcm_hashes: dict[str, str] = {}
    session_splits: dict[tuple[str, str], str] = {}
    split_counts = {split: 0 for split in SPLITS}
    for entry in manifest.get("entries", []):
        if FORBIDDEN_LEARNING_FIELDS & set(entry):
            raise ValueError("text-derived learning fields are forbidden")
        split = entry.get("split")
        if split not in SPLITS:
            raise ValueError(f"invalid corpus split: {split}")
        relative = entry.get("path", "")
        if relative in seen_paths:
            raise ValueError(f"duplicate corpus path: {relative}")
        seen_paths.add(relative)
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"corpus path escapes root: {relative}") from exc
        audio = load_wav(candidate)
        if audio.sha256 != entry.get("audio_sha256"):
            raise ValueError(f"audio hash mismatch: {relative}")
        if audio.pcm_sha256 != entry.get("pcm_sha256"):
            raise ValueError(f"decoded PCM hash mismatch: {relative}")
        if audio.rate != entry.get("sample_rate") or len(audio.samples) != entry.get("sample_count"):
            raise ValueError(f"audio format mismatch: {relative}")
        prior_split = seen_hashes.setdefault(audio.sha256, split)
        if prior_split != split:
            raise ValueError("the same audio appears in more than one corpus split")
        prior_pcm_split = seen_pcm_hashes.setdefault(audio.pcm_sha256, split)
        if prior_pcm_split != split:
            raise ValueError("the same decoded PCM appears in more than one corpus split")
        session_key = (entry.get("speaker_id", ""), entry.get("session_id", ""))
        prior_session_split = session_splits.setdefault(session_key, split)
        if prior_session_split != split:
            raise ValueError("one speaker/session appears in more than one corpus split")
        split_counts[split] += 1
    if any(count == 0 for count in split_counts.values()):
        raise ValueError("every corpus split must contain audio")
    actual_paths = {
        wav.relative_to(root).as_posix()
        for split in SPLITS
        for wav in (root / split).glob("*.wav")
    }
    if actual_paths != seen_paths:
        missing = sorted(actual_paths - seen_paths)
        stale = sorted(seen_paths - actual_paths)
        raise ValueError(f"manifest/file-set mismatch; unindexed={missing}, missing={stale}")
    return manifest


def index_command(args) -> None:
    sessions = {
        "train": args.train_session,
        "heldout": args.heldout_session,
        "evaluation": args.evaluation_session,
    }
    manifest = build_manifest(Path(args.root), args.speaker, sessions)
    output = Path(args.output)
    write_json_atomic(output, manifest)
    validate_manifest(output, Path(args.root))
    print(json.dumps({
        "manifest": str(output),
        "manifest_sha256": manifest["manifest_sha256"],
        "recording_count": len(manifest["entries"]),
        "sessions": sessions,
        "learning_tokens": manifest["learning_tokens"],
    }))


def validate_command(args) -> None:
    manifest = validate_manifest(Path(args.manifest), Path(args.root))
    print(json.dumps({
        "manifest_sha256": manifest["manifest_sha256"],
        "recording_count": len(manifest["entries"]),
        "valid": True,
    }))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    index = commands.add_parser("index")
    index.add_argument("--root", required=True)
    index.add_argument("--speaker", required=True)
    index.add_argument("--train-session", required=True)
    index.add_argument("--heldout-session", required=True)
    index.add_argument("--evaluation-session", required=True)
    index.add_argument("--output", required=True)
    index.set_defaults(fn=index_command)
    validate = commands.add_parser("validate")
    validate.add_argument("--root", required=True)
    validate.add_argument("--manifest", required=True)
    validate.set_defaults(fn=validate_command)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
