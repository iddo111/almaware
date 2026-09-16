from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from holobrain.provenance import SourceKind, SourceRecord, validate_training_source


class ProvenanceTests(unittest.TestCase):
    def test_street_view_is_always_rejected(self) -> None:
        record = SourceRecord(
            "street",
            SourceKind.GOOGLE_STREET_VIEW,
            None,
            "API account exists",
            written_permission=True,
        )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_training_source(record)

    def test_youtube_requires_local_file_and_rights(self) -> None:
        record = SourceRecord(
            "podcast",
            SourceKind.YOUTUBE_OR_PODCAST,
            None,
            "public URL only",
        )
        with self.assertRaisesRegex(ValueError, "local file"):
            validate_training_source(record)

    def test_owned_voice_file_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.wav"
            path.write_bytes(b"RIFF")
            record = SourceRecord(
                "iddo-session-1",
                SourceKind.OPERATOR_OWNED_VOICE,
                path,
                "Recorded and owned by operator",
            )
            validate_training_source(record)


if __name__ == "__main__":
    unittest.main()
