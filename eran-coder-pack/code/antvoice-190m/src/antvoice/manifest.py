"""Strict real-audio manifest validation for provenance and split isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_FIELDS = frozenset(
    {
        "audio_path",
        "split",
        "speaker_id",
        "session_id",
        "corpus_id",
        "rights_id",
        "consent_id",
        "rights_status",
        "sha256",
        "sample_rate",
        "num_samples",
    }
)
OPTIONAL_FIELDS = frozenset({"language_audit_status"})
FORBIDDEN_FIELDS = frozenset(
    {
        "text",
        "transcript",
        "transcription",
        "words",
        "characters",
        "phonemes",
        "translation",
        "prompt",
        "response",
    }
)
VERIFIED_RIGHTS_STATUS = "VERIFIED"
VERIFIED_HEBREW_STATUS = "VERIFIED_HEBREW"


@dataclass(frozen=True)
class AudioRecord:
    audio_path: str
    split: str
    speaker_id: str
    session_id: str
    corpus_id: str
    rights_id: str
    consent_id: str
    rights_status: str
    sha256: str
    sample_rate: int
    num_samples: int
    language_audit_status: str | None

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "audio_path": self.audio_path,
            "split": self.split,
            "speaker_id": self.speaker_id,
            "session_id": self.session_id,
            "corpus_id": self.corpus_id,
            "rights_id": self.rights_id,
            "consent_id": self.consent_id,
            "rights_status": self.rights_status,
            "sha256": self.sha256,
            "sample_rate": self.sample_rate,
            "num_samples": self.num_samples,
            "language_audit_status": self.language_audit_status,
        }


@dataclass(frozen=True)
class ManifestSummary:
    records: int
    train_records: int
    eval_records: int
    train_speakers: int
    eval_speakers: int
    train_sessions: int
    eval_sessions: int
    audio_bytes: int
    manifest_sha256: str

    def to_dict(self) -> dict[str, int | str]:
        return {
            "records": self.records,
            "train_records": self.train_records,
            "eval_records": self.eval_records,
            "train_speakers": self.train_speakers,
            "eval_speakers": self.eval_speakers,
            "train_sessions": self.train_sessions,
            "eval_sessions": self.eval_sessions,
            "audio_bytes": self.audio_bytes,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class ValidatedManifest:
    summary: ManifestSummary
    records: tuple[AudioRecord, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_audio_path(audio_root: Path, relative: str, line_number: int) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError(f"line {line_number}: audio_path must be relative")
    root = audio_root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"line {line_number}: audio_path escapes audio_root") from exc
    if resolved.suffix.lower() != ".wav":
        raise ValueError(f"line {line_number}: only .wav audio is accepted")
    if not resolved.is_file():
        raise ValueError(f"line {line_number}: missing audio file {relative!r}")
    return resolved


def _records(path: Path) -> Iterable[tuple[int, dict[str, object]]]:
    if not path.is_file():
        raise ValueError(f"manifest does not exist: {path}")
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"line {line_number}: record must be an object")
        yield line_number, record


def _looks_like_ambient_voice_history(record: dict[str, object]) -> bool:
    corpus_id = str(record["corpus_id"]).strip().lower().replace("-", "_")
    audio_path = str(record["audio_path"]).replace("\\", "/").lower()
    return "voice_history" in corpus_id or "/voice_history/" in f"/{audio_path}"


def load_validated_manifest(
    manifest_path: str | Path,
    audio_root: str | Path,
    *,
    required_sample_rate: int = 16_000,
    require_verified_hebrew: bool = False,
    allow_ambient_voice_history: bool = False,
) -> ValidatedManifest:
    manifest = Path(manifest_path)
    root = Path(audio_root)
    splits: dict[str, list[AudioRecord]] = {"train": [], "eval": []}
    validated_records: list[AudioRecord] = []
    seen_audio_hashes: set[str] = set()
    total_bytes = 0

    for line_number, record in _records(manifest):
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(
                f"line {line_number}: missing fields {sorted(missing)!r}"
            )
        forbidden = FORBIDDEN_FIELDS & record.keys()
        if forbidden:
            raise ValueError(
                f"line {line_number}: text-derived fields are forbidden: "
                f"{sorted(forbidden)!r}"
            )
        unexpected = record.keys() - REQUIRED_FIELDS - OPTIONAL_FIELDS
        if unexpected:
            raise ValueError(
                f"line {line_number}: unexpected fields are forbidden: "
                f"{sorted(unexpected)!r}"
            )
        split = record["split"]
        if split not in splits:
            raise ValueError(f"line {line_number}: split must be 'train' or 'eval'")
        if not isinstance(record["audio_path"], str) or not record[
            "audio_path"
        ].strip():
            raise ValueError(f"line {line_number}: audio_path must be nonempty text")
        for identity in (
            "speaker_id",
            "session_id",
            "corpus_id",
            "rights_id",
            "consent_id",
        ):
            value = record[identity]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"line {line_number}: {identity} must be nonempty")
        if record["rights_status"] != VERIFIED_RIGHTS_STATUS:
            raise ValueError(
                f"line {line_number}: rights_status must be "
                f"{VERIFIED_RIGHTS_STATUS!r}"
            )
        language_status = record.get("language_audit_status")
        if language_status is not None and (
            not isinstance(language_status, str) or not language_status.strip()
        ):
            raise ValueError(
                f"line {line_number}: language_audit_status must be nonempty when set"
            )
        if require_verified_hebrew and language_status != VERIFIED_HEBREW_STATUS:
            raise ValueError(
                f"line {line_number}: language_audit_status must be "
                f"{VERIFIED_HEBREW_STATUS!r} for this training run"
            )
        if not allow_ambient_voice_history and _looks_like_ambient_voice_history(
            record
        ):
            raise ValueError(
                f"line {line_number}: ambient voice_history is blocked by default"
            )
        expected_hash = record["sha256"]
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(
            expected_hash
        ):
            raise ValueError(f"line {line_number}: sha256 must be lowercase hex")
        if expected_hash in seen_audio_hashes:
            raise ValueError(
                f"line {line_number}: duplicate audio content hash {expected_hash}"
            )

        audio_path = _safe_audio_path(root, str(record["audio_path"]), line_number)
        actual_hash = _sha256(audio_path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"line {line_number}: SHA256 mismatch for {record['audio_path']!r}"
            )
        try:
            with wave.open(str(audio_path), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                num_samples = wav.getnframes()
                compression = wav.getcomptype()
        except (wave.Error, EOFError) as exc:
            raise ValueError(f"line {line_number}: invalid WAV container") from exc
        if channels != 1 or sample_width != 2 or compression != "NONE":
            raise ValueError(
                f"line {line_number}: WAV must be mono, 16-bit, uncompressed PCM"
            )
        if sample_rate != required_sample_rate:
            raise ValueError(
                f"line {line_number}: WAV rate {sample_rate}, "
                f"required {required_sample_rate}"
            )
        if record["sample_rate"] != sample_rate:
            raise ValueError(f"line {line_number}: declared sample_rate mismatch")
        if record["num_samples"] != num_samples:
            raise ValueError(f"line {line_number}: declared num_samples mismatch")
        if num_samples < required_sample_rate // 4:
            raise ValueError(f"line {line_number}: recording is shorter than 250 ms")

        validated = AudioRecord(
            audio_path=str(record["audio_path"]),
            split=str(split),
            speaker_id=str(record["speaker_id"]),
            session_id=str(record["session_id"]),
            corpus_id=str(record["corpus_id"]),
            rights_id=str(record["rights_id"]),
            consent_id=str(record["consent_id"]),
            rights_status=str(record["rights_status"]),
            sha256=expected_hash,
            sample_rate=sample_rate,
            num_samples=num_samples,
            language_audit_status=(
                str(language_status) if language_status is not None else None
            ),
        )
        seen_audio_hashes.add(expected_hash)
        total_bytes += audio_path.stat().st_size
        splits[str(split)].append(validated)
        validated_records.append(validated)

    if not splits["train"] or not splits["eval"]:
        raise ValueError("manifest must contain at least one train and one eval record")

    train_speakers = {item.speaker_id for item in splits["train"]}
    eval_speakers = {item.speaker_id for item in splits["eval"]}
    speaker_overlap = train_speakers & eval_speakers
    if speaker_overlap:
        raise ValueError(
            f"train/eval speaker overlap is forbidden: {sorted(speaker_overlap)!r}"
        )

    train_sessions = {item.session_id for item in splits["train"]}
    eval_sessions = {item.session_id for item in splits["eval"]}
    session_overlap = train_sessions & eval_sessions
    if session_overlap:
        raise ValueError(
            f"train/eval session overlap is forbidden: {sorted(session_overlap)!r}"
        )

    return ValidatedManifest(
        summary=ManifestSummary(
            records=len(splits["train"]) + len(splits["eval"]),
            train_records=len(splits["train"]),
            eval_records=len(splits["eval"]),
            train_speakers=len(train_speakers),
            eval_speakers=len(eval_speakers),
            train_sessions=len(train_sessions),
            eval_sessions=len(eval_sessions),
            audio_bytes=total_bytes,
            manifest_sha256=_sha256(manifest),
        ),
        records=tuple(validated_records),
    )


def validate_manifest(
    manifest_path: str | Path,
    audio_root: str | Path,
    *,
    required_sample_rate: int = 16_000,
    require_verified_hebrew: bool = False,
    allow_ambient_voice_history: bool = False,
) -> ManifestSummary:
    return load_validated_manifest(
        manifest_path,
        audio_root,
        required_sample_rate=required_sample_rate,
        require_verified_hebrew=require_verified_hebrew,
        allow_ambient_voice_history=allow_ambient_voice_history,
    ).summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--audio-root", required=True)
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--require-verified-hebrew", action="store_true")
    args = parser.parse_args()
    summary = validate_manifest(
        args.manifest,
        args.audio_root,
        required_sample_rate=args.sample_rate,
        require_verified_hebrew=args.require_verified_hebrew,
    )
    print(json.dumps(summary.to_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
