import json
import tempfile
import unittest
from pathlib import Path

from acoustic_units import load_checkpoint, write_json_atomic
from colony import colony_digest, train_colony
from corpus import build_manifest, manifest_digest, validate_manifest
from test_acoustic_units import write_tone


def build_recordings(root: Path) -> Path:
    recordings = root / "recordings"
    frequencies = {
        "train": (280, 390, 510),
        "heldout": (300, 410, 530),
        "evaluation": (320, 430, 550),
    }
    for split, values in frequencies.items():
        folder = recordings / split
        folder.mkdir(parents=True)
        for index, hz in enumerate(values):
            write_tone(folder / f"{index}.wav", hz)
    return recordings


class CorpusAndColonyTest(unittest.TestCase):
    def test_manifest_enforces_waveforms_and_session_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings = build_recordings(root)
            sessions = {"train": "s1", "heldout": "s2", "evaluation": "s3"}
            manifest = build_manifest(recordings, "speaker-a", sessions)
            path = recordings / "manifest.json"
            write_json_atomic(path, manifest)
            self.assertEqual(validate_manifest(path, recordings)["manifest_sha256"], manifest["manifest_sha256"])

            with self.assertRaisesRegex(ValueError, "different recording sessions"):
                build_manifest(
                    recordings, "speaker-a",
                    {"train": "same", "heldout": "same", "evaluation": "s3"},
                )

            poisoned = json.loads(path.read_text(encoding="utf-8"))
            poisoned["entries"][0]["transcript"] = "forbidden"
            poisoned["manifest_sha256"] = manifest_digest(poisoned)
            write_json_atomic(path, poisoned)
            with self.assertRaisesRegex(ValueError, "text-derived"):
                validate_manifest(path, recordings)

    def test_four_ants_remain_independent_and_queen_uses_heldout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings = build_recordings(root)
            manifest = build_manifest(
                recordings, "speaker-a",
                {"train": "s1", "heldout": "s2", "evaluation": "s3"},
            )
            manifest_path = recordings / "manifest.json"
            write_json_atomic(manifest_path, manifest)
            state = root / "state"
            queen = train_colony(recordings, manifest_path, state, units=4)

            self.assertEqual(len(queen["ants"]), 4)
            self.assertFalse(queen["codebooks_merged"])
            self.assertEqual(queen["unit_namespace"], "checkpoint_sha256:unit_id")
            self.assertTrue(queen["queen_selection"]["evaluation_was_not_used_for_selection"])
            expected = min(queen["ants"], key=lambda ant: ant["heldout_error_after"])["ant"]
            self.assertEqual(queen["queen_selection"]["selected_ant"], expected)
            hashes = {ant["checkpoint_sha256"] for ant in queen["ants"]}
            self.assertEqual(len(hashes), 4)
            for ant in queen["ants"]:
                checkpoint = load_checkpoint(state / ant["ant"] / "current.json")
                self.assertEqual(checkpoint["ant"], ant["ant"])
                self.assertEqual(checkpoint["seed"], ant["seed"])
            self.assertEqual(queen["colony_sha256"], colony_digest(queen))
            self.assertTrue((state / "queen" / "current.json").exists())

            queen_current = state / "queen" / "current.json"
            first_bytes = queen_current.read_bytes()
            first_mtime = queen_current.stat().st_mtime_ns
            second = train_colony(recordings, manifest_path, state, units=4)
            current_hashes = {
                load_checkpoint(state / ant / "current.json")["checkpoint_sha256"]
                for ant in ("ant-a", "ant-b", "ant-c", "ant-d")
            }
            self.assertIn(second["queen_selection"]["selected_checkpoint_sha256"], current_hashes)
            self.assertEqual(second["colony_sha256"], queen["colony_sha256"])
            self.assertEqual(queen_current.read_bytes(), first_bytes)
            self.assertEqual(queen_current.stat().st_mtime_ns, first_mtime)


if __name__ == "__main__":
    unittest.main()
