import os
# Pin the search lane so the suite is deterministic on every machine.
# Without this, colony.node_lane() falls back to a hostname hash and each
# node trains a different seed schedule, which made these tests flaky.
os.environ.setdefault("VAF_NODE_LANE", "0")

import json
import tempfile
import unittest
from pathlib import Path

from acoustic_units import load_checkpoint, write_json_atomic
from colony import (
    SEARCH_LANES, colony_digest, next_round, round_seeds, train_colony,
)
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
            before = {ant["ant"]: ant["heldout_error_after"] for ant in queen["ants"]}
            second = train_colony(recordings, manifest_path, state, units=4)
            current_hashes = {
                load_checkpoint(state / ant / "current.json")["checkpoint_sha256"]
                for ant in ("ant-a", "ant-b", "ant-c", "ant-d")
            }
            self.assertIn(second["queen_selection"]["selected_checkpoint_sha256"], current_hashes)

            # Each round is a fresh random restart, so the second round may or may
            # not beat the incumbent. The invariant is NOT "the colony never
            # changes" -- asserting that is what let the farm run frozen for four
            # days -- but "the queen file is rewritten exactly when the colony
            # changes, and no ant ever gets worse".
            after = {ant["ant"]: ant["heldout_error_after"] for ant in second["ants"]}
            for ant, value in after.items():
                self.assertLessEqual(value, before[ant] + 1e-9)
            if second["colony_sha256"] == queen["colony_sha256"]:
                self.assertEqual(queen_current.read_bytes(), first_bytes)
                self.assertEqual(queen_current.stat().st_mtime_ns, first_mtime)
            else:
                self.assertNotEqual(queen_current.read_bytes(), first_bytes)
                self.assertTrue(any(after[a] < before[a] - 1e-9 for a in after))

    def test_seeds_advance_every_round_and_never_collide_across_nodes(self):
        """Regression: fit_codebook is pure, so a constant seed means no search.

        The farm recomputed one identical colony every 15 minutes for four days
        because DEFAULT_SEEDS never advanced. Seeds must be unique within a
        round (each ant is independent) and never reused across rounds or nodes
        (otherwise a node re-explores a basin someone already tried).
        """
        seen = {}
        for round_n in range(25):
            for lane in range(SEARCH_LANES):
                seeds = round_seeds(round_n, lane)
                self.assertEqual(len(set(seeds)), len(seeds), "ants share a seed")
                for seed in seeds:
                    self.assertNotIn(seed, seen, "seed %d reused" % seed)
                    seen[seed] = (round_n, lane)
        self.assertNotEqual(round_seeds(0, 0), round_seeds(1, 0))
        self.assertNotEqual(round_seeds(0, 0), round_seeds(0, 1))

    def test_round_counter_persists_and_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            self.assertEqual([next_round(state) for _ in range(3)], [0, 1, 2])
            self.assertEqual(json.loads((state / "round.json").read_text())["round"], 2)


if __name__ == "__main__":
    unittest.main()
