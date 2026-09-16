import os
# Pin the search lane so the suite is deterministic on every machine.
# Without this, colony.node_lane() falls back to a hostname hash and each
# node trains a different seed schedule, which made these tests flaky.
os.environ.setdefault("VAF_NODE_LANE", "0")

import tempfile
import unittest
from pathlib import Path

from acoustic_units import load_checkpoint, load_wav, write_json_atomic
from colony import DEFAULT_ANTS, train_colony
from corpus import build_manifest
from fire import run_cycle, run_fire_round, validate_fire_round
from test_colony import build_recordings


def train_baseline(root: Path) -> tuple[Path, Path, Path]:
    recordings = build_recordings(root)
    manifest = build_manifest(
        recordings, "speaker-a",
        {"train": "s1", "heldout": "s2", "evaluation": "s3"},
    )
    manifest_path = recordings / "manifest.json"
    write_json_atomic(manifest_path, manifest)
    state = root / "state"
    train_colony(recordings, manifest_path, state, units=4)
    return recordings, manifest_path, state


class TribalFireTest(unittest.TestCase):
    def test_only_sound_and_manifest_cross_the_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings, _, state = train_baseline(root)
            manifest = run_fire_round(
                state, recordings, root / "fire", utterances=2, round_id="round-1",
            )
            round_dir = root / "fire" / "round-1"
            non_wav = [
                path for path in round_dir.rglob("*")
                if path.is_file() and path.suffix != ".wav"
            ]
            self.assertEqual([path.name for path in non_wav], ["manifest.json"])
            text = (round_dir / "manifest.json").read_text(encoding="utf-8")
            for leaked in (
                "centers", "baseline_center", "exemplars_pcm16",
                "exemplar_source_hashes", "unit_ids",
            ):
                self.assertNotIn(f'"{leaked}"', text)
            for ant in DEFAULT_ANTS:
                self.assertEqual(manifest["producers"][ant]["utterance_count"], 2)
                for entry in manifest["producers"][ant]["files"]:
                    audio = load_wav(round_dir / ant / entry["path"])
                    self.assertEqual(audio.pcm_sha256, entry["pcm_sha256"])
            self.assertEqual(
                validate_fire_round(round_dir)["manifest_sha256"],
                manifest["manifest_sha256"],
            )

    def test_ant_never_ingests_its_own_fire_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings, _, state = train_baseline(root)
            manifest = run_fire_round(
                state, recordings, root / "fire", utterances=2, round_id="round-1",
            )
            round_dir = root / "fire" / "round-1"
            for ant in DEFAULT_ANTS:
                own_hashes = {
                    entry["pcm_sha256"] for entry in manifest["producers"][ant]["files"]
                }
                for entry in manifest["mixes"][ant]["fire_files"]:
                    self.assertNotEqual(entry["producer"], ant)
                mix_hashes = {
                    load_wav(path).pcm_sha256
                    for path in (round_dir / "mix" / ant).glob("*.wav")
                }
                self.assertFalse(own_hashes & mix_hashes)

    def test_synthetic_proportion_cap_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings, _, state = train_baseline(root)
            manifest = run_fire_round(
                state, recordings, root / "fire",
                utterances=3, max_synthetic=0.25, round_id="round-1",
            )
            round_dir = root / "fire" / "round-1"
            available_from_others = 3 * 3
            for ant in DEFAULT_ANTS:
                mix_dir = round_dir / "mix" / ant
                real_seconds = sum(
                    len(load_wav(path).samples) / load_wav(path).rate
                    for path in mix_dir.glob("real-*.wav")
                )
                fire_seconds = sum(
                    len(load_wav(path).samples) / load_wav(path).rate
                    for path in mix_dir.glob("fire-*.wav")
                )
                self.assertLessEqual(
                    fire_seconds / (real_seconds + fire_seconds), 0.25 + 1e-9
                )
                mix = manifest["mixes"][ant]
                self.assertLessEqual(mix["synthetic_proportion"], 0.25 + 1e-9)
                self.assertLess(mix["fire_file_count"], available_from_others)
                self.assertGreater(mix["fire_file_count"], 0)
            with self.assertRaisesRegex(ValueError, r"\[0, 1\)"):
                run_fire_round(
                    state, recordings, root / "fire",
                    max_synthetic=1.0, round_id="round-2",
                )

    def test_real_audio_always_stays_in_every_training_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings, _, state = train_baseline(root)
            real_hashes = {
                load_wav(path).pcm_sha256
                for path in (recordings / "train").glob("*.wav")
            }
            manifest = run_fire_round(
                state, recordings, root / "fire",
                utterances=2, max_synthetic=0.0, round_id="round-1",
            )
            round_dir = root / "fire" / "round-1"
            for ant in DEFAULT_ANTS:
                mix_hashes = {
                    load_wav(path).pcm_sha256
                    for path in (round_dir / "mix" / ant).glob("*.wav")
                }
                self.assertTrue(real_hashes <= mix_hashes)
                self.assertEqual(manifest["mixes"][ant]["fire_file_count"], 0)
                self.assertEqual(
                    manifest["mixes"][ant]["real_file_count"], len(real_hashes)
                )

    def test_cycle_measures_heldout_error_on_real_recordings_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings, manifest_path, state = train_baseline(root)
            cycle = run_cycle(
                recordings, manifest_path, state, root / "fire",
                units=4, utterances=2, round_id="cycle-1",
            )
            self.assertEqual(cycle["heldout_measured_against"], "real-recordings-only")
            self.assertEqual(len(cycle["ants"]), 4)
            for result in cycle["ants"]:
                self.assertEqual(
                    result["improved_after_fire"],
                    result["heldout_error_after_fire"]
                    < result["heldout_error_before_fire"] - 1e-9,
                )
                if not result["fire_candidate_promoted"]:
                    self.assertEqual(
                        result["heldout_error_after_fire"],
                        result["heldout_error_before_fire"],
                    )
            self.assertEqual(
                cycle["fire_improved_any_ant"],
                any(result["improved_after_fire"] for result in cycle["ants"]),
            )
            for ant in DEFAULT_ANTS:
                checkpoint = load_checkpoint(state / ant / "current.json")
                self.assertEqual(checkpoint["ant"], ant)
            validate_fire_round(root / "fire" / "cycle-1")


if __name__ == "__main__":
    unittest.main()
