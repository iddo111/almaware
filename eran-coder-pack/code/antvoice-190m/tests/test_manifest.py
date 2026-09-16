import hashlib
import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from antvoice.manifest import (
    VERIFIED_HEBREW_STATUS,
    load_validated_manifest,
    validate_manifest,
)


SAMPLE_RATE = 16_000
NUM_SAMPLES = 4_000


def _write_wav(path: Path, frequency: float) -> str:
    frames = bytearray()
    for index in range(NUM_SAMPLES):
        value = round(
            8_000 * math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE)
        )
        frames.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(
    *,
    audio_path: str,
    split: str,
    speaker: str,
    session: str,
    sha256: str,
) -> dict[str, object]:
    return {
        "audio_path": audio_path,
        "split": split,
        "speaker_id": speaker,
        "session_id": session,
        "corpus_id": "consented-hebrew-pilot",
        "rights_id": f"rights-{speaker}",
        "consent_id": f"consent-{speaker}",
        "rights_status": "VERIFIED",
        "language_audit_status": VERIFIED_HEBREW_STATUS,
        "sha256": sha256,
        "sample_rate": SAMPLE_RATE,
        "num_samples": NUM_SAMPLES,
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, list[dict[str, object]]]:
    audio = tmp_path / "audio"
    audio.mkdir()
    train_hash = _write_wav(audio / "train.wav", 220.0)
    eval_hash = _write_wav(audio / "eval.wav", 331.0)
    records = [
        _record(
            audio_path="train.wav",
            split="train",
            speaker="speaker-train",
            session="session-train",
            sha256=train_hash,
        ),
        _record(
            audio_path="eval.wav",
            split="eval",
            speaker="speaker-eval",
            session="session-eval",
            sha256=eval_hash,
        ),
    ]
    manifest = tmp_path / "manifest.jsonl"
    return audio, manifest, records


def _write_manifest(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_validates_hashes_and_disjoint_speakers_and_sessions(self) -> None:
        audio, manifest, records = _fixture(self.root)
        _write_manifest(manifest, records)
        summary = validate_manifest(manifest, audio)
        self.assertEqual(summary.records, 2)
        self.assertEqual(summary.train_records, 1)
        self.assertEqual(summary.eval_records, 1)
        self.assertEqual(summary.train_speakers, 1)
        self.assertEqual(summary.eval_speakers, 1)
        self.assertEqual(len(summary.manifest_sha256), 64)

    def test_returns_only_validated_typed_records(self) -> None:
        audio, manifest, records = _fixture(self.root)
        _write_manifest(manifest, records)
        validated = load_validated_manifest(
            manifest,
            audio,
            require_verified_hebrew=True,
        )
        self.assertEqual(len(validated.records), 2)
        self.assertEqual(validated.records[0].rights_status, "VERIFIED")
        self.assertEqual(
            validated.records[0].language_audit_status,
            VERIFIED_HEBREW_STATUS,
        )

    def test_rejects_speaker_overlap(self) -> None:
        audio, manifest, records = _fixture(self.root)
        records[1]["speaker_id"] = records[0]["speaker_id"]
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "speaker overlap"):
            validate_manifest(manifest, audio)

    def test_rejects_session_overlap(self) -> None:
        audio, manifest, records = _fixture(self.root)
        records[1]["session_id"] = records[0]["session_id"]
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "session overlap"):
            validate_manifest(manifest, audio)

    def test_rejects_sha256_mismatch(self) -> None:
        audio, manifest, records = _fixture(self.root)
        records[0]["sha256"] = "0" * 64
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            validate_manifest(manifest, audio)

    def test_rejects_text_derived_fields(self) -> None:
        audio, manifest, records = _fixture(self.root)
        records[0]["transcript"] = "forbidden"
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "text-derived fields"):
            validate_manifest(manifest, audio)

    def test_rejects_missing_rights_identifier(self) -> None:
        audio, manifest, records = _fixture(self.root)
        del records[0]["rights_id"]
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "missing fields"):
            validate_manifest(manifest, audio)

    def test_rejects_unverified_rights(self) -> None:
        audio, manifest, records = _fixture(self.root)
        records[0]["rights_status"] = "UNVERIFIED"
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "rights_status"):
            validate_manifest(manifest, audio)

    def test_training_mode_requires_verified_hebrew_audit(self) -> None:
        audio, manifest, records = _fixture(self.root)
        del records[0]["language_audit_status"]
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "VERIFIED_HEBREW"):
            validate_manifest(
                manifest,
                audio,
                require_verified_hebrew=True,
            )

    def test_language_audit_is_optional_for_validation_only(self) -> None:
        audio, manifest, records = _fixture(self.root)
        del records[0]["language_audit_status"]
        del records[1]["language_audit_status"]
        _write_manifest(manifest, records)
        summary = validate_manifest(manifest, audio)
        self.assertEqual(summary.records, 2)

    def test_blocks_ambient_voice_history_by_default(self) -> None:
        audio, manifest, records = _fixture(self.root)
        records[0]["corpus_id"] = "ambient_voice_history_17_44h"
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "voice_history"):
            validate_manifest(manifest, audio)

    def test_rejects_unrecognized_metadata_fields(self) -> None:
        audio, manifest, records = _fixture(self.root)
        records[0]["caption"] = "forbidden metadata"
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            validate_manifest(manifest, audio)

    def test_rejects_duplicate_audio_content(self) -> None:
        audio, manifest, records = _fixture(self.root)
        duplicate = audio / "duplicate.wav"
        duplicate.write_bytes((audio / "train.wav").read_bytes())
        records[1]["audio_path"] = "duplicate.wav"
        records[1]["sha256"] = records[0]["sha256"]
        _write_manifest(manifest, records)
        with self.assertRaisesRegex(ValueError, "duplicate audio content hash"):
            validate_manifest(manifest, audio)


if __name__ == "__main__":
    unittest.main()
