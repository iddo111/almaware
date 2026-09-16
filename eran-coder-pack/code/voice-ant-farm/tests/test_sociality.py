import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acoustic_units import load_wav, write_json_atomic
from corpus import build_manifest
from experiments.sociality.run_experiment import (
    CONDITIONS, MATCHED_CONDITIONS, assert_heldout_is_real, colony_seeds,
    folder_pcm_hashes, run_condition,
)
from test_colony import build_recordings


def build_corpus(root: Path) -> tuple[Path, Path]:
    recordings = build_recordings(root)
    manifest = build_manifest(
        recordings, "speaker-a",
        {"train": "s1", "heldout": "s2", "evaluation": "s3"},
    )
    manifest_path = recordings / "manifest.json"
    write_json_atomic(manifest_path, manifest)
    return recordings, manifest_path


def run(root: Path, condition: str, **overrides) -> dict:
    recordings, manifest_path = overrides.pop("corpus", (None, None))
    if recordings is None:
        recordings, manifest_path = build_corpus(root)
    options = {
        "colony_size": 4, "replicate": 0, "rounds": 1, "units": 4,
        "synthetic_proportion": 0.3,
    }
    options.update(overrides)
    return run_condition(
        condition, recordings,
        work_root=root / "work", results_root=root / "results",
        manifest_path=manifest_path, **options,
    )


class SocialityVolumeMatchingTest(unittest.TestCase):
    def test_added_volume_is_matched_across_conditions_and_ants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = build_corpus(root)
            results = {
                condition: run(root, condition, corpus=corpus)
                for condition in CONDITIONS
            }
            matched = set()
            for condition, result in results.items():
                treatment = result["per_round"][1]
                added = treatment["added_samples_per_ant"]
                self.assertEqual(
                    set(result["per_round"][0]["added_samples_per_ant"].values()), {0},
                    "round 0 must be a real-audio-only bootstrap",
                )
                if condition == "SOLO":
                    self.assertEqual(set(added.values()), {0})
                    continue
                self.assertEqual(len(set(added.values())), 1)
                self.assertGreater(min(added.values()), 0)
                matched.add(min(added.values()))
                self.assertEqual(
                    result["volume_matching"]["matched_added_samples_per_ant"],
                    min(added.values()),
                )
            self.assertEqual(len(matched), 1, "SELF_ECHO, SOCIAL and NOISE must match")
            reference = results["SOCIAL"]["volume_matching"]["segment_plan"]
            for condition in MATCHED_CONDITIONS:
                self.assertEqual(
                    results[condition]["volume_matching"]["segment_plan"], reference,
                    "every condition must synthesize from the same real segments",
                )
                for entries in results[condition]["per_round"][1][
                    "added_audio_per_ant"
                ].values():
                    self.assertEqual(
                        [entry["sample_count"] for entry in entries],
                        [item["synthetic_samples"] for item in reference],
                    )
            round0 = {result["per_round"][0]["mean_heldout_error"] for result in results.values()}
            self.assertEqual(len(round0), 1, "round 0 is identical across conditions")

    def test_matched_files_are_distinct_so_the_mix_cannot_deduplicate_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run(root, "SELF_ECHO", keep_work=True)
            for entries in result["per_round"][1]["added_audio_per_ant"].values():
                hashes = {entry["pcm_sha256"] for entry in entries}
                self.assertEqual(len(hashes), len(entries))
            mix_root = root / "work" / "self_echo-4-r0" / "round-01" / "mix"
            for ant_dir in sorted(mix_root.iterdir()):
                added = sorted(ant_dir.glob("added-*.wav"))
                real = sorted(ant_dir.glob("real-*.wav"))
                self.assertEqual(len(added), 3)
                self.assertEqual(len(real), 3)
                pcm = {load_wav(path).pcm_sha256 for path in added + real}
                self.assertEqual(len(pcm), len(added) + len(real))


class SocialityIsolationTest(unittest.TestCase):
    def test_a_social_ant_never_ingests_its_own_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run(root, "SOCIAL", keep_work=True)
            ants = result["ants"]
            added = result["per_round"][1]["added_audio_per_ant"]
            spoken_by = {ant: set() for ant in ants}
            for entries in added.values():
                for entry in entries:
                    spoken_by[entry["producer"]].add(entry["pcm_sha256"])
            for ant in ants:
                producers = [entry["producer"] for entry in added[ant]]
                self.assertNotIn(ant, producers)
                self.assertEqual(sorted(producers), sorted(set(ants) - {ant}))
                own = {entry["pcm_sha256"] for entry in added[ant]}
                self.assertFalse(own & spoken_by[ant])
                ingested = {
                    load_wav(path).pcm_sha256
                    for path in (
                        root / "work" / "social-4-r0" / "round-01" / "mix" / ant
                    ).glob("added-*.wav")
                }
                self.assertEqual(ingested, own)
                self.assertFalse(ingested & spoken_by[ant])

    def test_self_echo_ingests_only_its_own_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run(root, "SELF_ECHO")
            for ant, entries in result["per_round"][1]["added_audio_per_ant"].items():
                self.assertEqual({entry["producer"] for entry in entries}, {ant})


class SocialityHeldOutPurityTest(unittest.TestCase):
    def test_synthesized_audio_never_enters_the_heldout_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings, manifest_path = build_corpus(root)
            heldout = recordings / "heldout"
            evaluation = recordings / "evaluation"
            before = folder_pcm_hashes(heldout)
            before_files = sorted(path.name for path in heldout.glob("*.wav"))
            protected = before | folder_pcm_hashes(evaluation)
            for condition in CONDITIONS:
                result = run(
                    root, condition, corpus=(recordings, manifest_path), keep_work=True,
                )
                self.assertEqual(
                    result["heldout_measured_against"], "real-recordings-only",
                )
                self.assertEqual(sorted(result["heldout_pcm_sha256"]), sorted(before))
                for entries in result["per_round"][1]["added_audio_per_ant"].values():
                    for entry in entries:
                        self.assertNotIn(entry["pcm_sha256"], protected)
            self.assertEqual(folder_pcm_hashes(heldout), before)
            self.assertEqual(sorted(path.name for path in heldout.glob("*.wav")), before_files)
            work_audio = list((root / "work").rglob("*.wav"))
            self.assertTrue(work_audio)
            for path in work_audio:
                self.assertNotIn(recordings.resolve(), path.resolve().parents)

    def test_the_guard_rejects_synthesized_audio_in_a_heldout_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings, manifest_path = build_corpus(root)
            heldout = recordings / "heldout"
            allowed = folder_pcm_hashes(heldout)
            self.assertEqual(assert_heldout_is_real(heldout, allowed), allowed)
            run(root, "SOCIAL", corpus=(recordings, manifest_path), keep_work=True)
            synthesized = sorted((root / "work").rglob("added-*.wav"))[0]
            poisoned = root / "poisoned-heldout"
            poisoned.mkdir()
            for path in heldout.glob("*.wav"):
                (poisoned / path.name).write_bytes(path.read_bytes())
            (poisoned / "synthetic.wav").write_bytes(synthesized.read_bytes())
            with self.assertRaisesRegex(ValueError, "real human recordings"):
                assert_heldout_is_real(poisoned, allowed)


class SocialitySeedTest(unittest.TestCase):
    def test_every_ant_in_a_colony_gets_a_distinct_seed(self):
        for colony_size in (2, 4, 8):
            seeds = colony_seeds(0, colony_size)
            self.assertEqual(len(seeds), colony_size)
            self.assertEqual(len(set(seeds)), colony_size)
            self.assertEqual(seeds, colony_seeds(0, colony_size))
            self.assertNotEqual(seeds, colony_seeds(1, colony_size))
        self.assertEqual(colony_seeds(0, 8)[:4], colony_seeds(0, 4))

    def test_a_run_records_distinct_seeds_shared_across_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = build_corpus(root)
            solo = run(root, "SOLO", corpus=corpus)
            social = run(root, "SOCIAL", corpus=corpus)
            self.assertEqual(len(set(solo["seeds"])), solo["colony_size"])
            self.assertEqual(solo["seeds"], social["seeds"])
            self.assertEqual(
                sorted(solo["seeds_by_ant"]), sorted(solo["ants"]),
            )
            replicated = run(root, "SOLO", corpus=corpus, replicate=1)
            self.assertNotEqual(solo["seeds"], replicated["seeds"])
            self.assertTrue((root / "results" / "solo-4-r1.json").exists())


if __name__ == "__main__":
    unittest.main()
