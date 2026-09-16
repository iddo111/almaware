import os
# Pin the search lane so the suite is deterministic on every machine.
# Without this, colony.node_lane() falls back to a hostname hash and each
# node trains a different seed schedule, which made these tests flaky.
os.environ.setdefault("VAF_NODE_LANE", "0")

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from acoustic_units import load_checkpoint, write_json_atomic
from boundary_repeatability import (
    ANNOTATION_ARCHITECTURE,
    ANNOTATION_FORMAT,
    BOUNDARY_TOLERANCE_SECONDS,
    alignment_similarity,
    annotation_digest,
    evaluate_annotations,
    match_boundaries,
    report_digest,
)
from colony import train_colony
from corpus import build_manifest
from test_colony import build_recordings


class BoundaryRepeatabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.project = Path(cls.temporary.name)
        cls.recordings = build_recordings(cls.project)
        manifest = build_manifest(
            cls.recordings,
            "speaker-a",
            {"train": "session-a", "heldout": "session-b", "evaluation": "session-c"},
        )
        cls.manifest_path = cls.recordings / "manifest.json"
        write_json_atomic(cls.manifest_path, manifest)
        train_colony(cls.recordings, cls.manifest_path, cls.project / "state", units=4)
        cls.checkpoint_path = cls.project / "state" / "ant-a" / "current.json"
        checkpoint = load_checkpoint(cls.checkpoint_path)
        entries = []
        for item in manifest["entries"]:
            if item["split"] == "train":
                continue
            opaque_group = "rg-" + hashlib.sha256(
                Path(item["path"]).stem.encode()
            ).hexdigest()[:32]
            entries.append({
                "path": item["path"],
                "split": item["split"],
                "speaker_id": item["speaker_id"],
                "session_id": item["session_id"],
                "audio_sha256": item["audio_sha256"],
                "pcm_sha256": item["pcm_sha256"],
                "repetition_group_id": opaque_group,
                "boundaries_samples": [item["sample_count"] // 2],
            })
        cls.annotations = {
            "format_version": ANNOTATION_FORMAT,
            "architecture": ANNOTATION_ARCHITECTURE,
            "corpus_manifest_sha256": manifest["manifest_sha256"],
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "entries": entries,
        }
        cls.annotations["annotations_sha256"] = annotation_digest(cls.annotations)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def write_annotations(self, value: dict, name: str = "annotations.json") -> Path:
        path = self.project / name
        write_json_atomic(path, value)
        return path

    def reseal(self, value: dict) -> dict:
        value["annotations_sha256"] = annotation_digest(value)
        return value

    def test_complete_sealed_annotations_compute_candidate_only_metrics(self):
        mixed_coordinates = copy.deepcopy(self.annotations)
        first_entry = mixed_coordinates["entries"][0]
        sample_boundary = first_entry.pop("boundaries_samples")[0]
        first_entry["boundaries_seconds"] = [sample_boundary / 16000]
        self.reseal(mixed_coordinates)
        path = self.write_annotations(mixed_coordinates)
        first = evaluate_annotations(
            self.checkpoint_path, self.manifest_path, self.recordings, path
        )
        second = evaluate_annotations(
            self.checkpoint_path, self.manifest_path, self.recordings, path
        )
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "METRICS_COMPUTED")
        self.assertEqual(first["acceptance_status"], "UNVERIFIED")
        self.assertIn("candidate metrics only", first["claim_limit"])
        self.assertEqual(first["boundary_metrics"]["tolerance_seconds"], 0.020)
        self.assertEqual(first["coverage"]["independent_repetition_group_count"], 3)
        self.assertEqual(
            first["repeatability_metrics"]["within_group_cross_session_pair_count"], 3
        )
        self.assertGreater(
            first["repeatability_metrics"]["between_group_cross_session_pair_count"], 0
        )
        self.assertTrue(first["checkpoint"]["unit_namespace"].endswith(":unit_id"))
        self.assertEqual(first["report_sha256"], report_digest(first))

    def test_annotation_seal_and_exact_schema_fail_closed(self):
        tampered = copy.deepcopy(self.annotations)
        tampered["entries"][0]["boundaries_samples"] = [100]
        path = self.write_annotations(tampered, "tampered.json")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            evaluate_annotations(
                self.checkpoint_path, self.manifest_path, self.recordings, path
            )

        forbidden = copy.deepcopy(self.annotations)
        forbidden["entries"][0]["transcript"] = "forbidden"
        self.reseal(forbidden)
        path = self.write_annotations(forbidden, "forbidden.json")
        with self.assertRaisesRegex(ValueError, "forbidden fields"):
            evaluate_annotations(
                self.checkpoint_path, self.manifest_path, self.recordings, path
            )

        wrong_type = copy.deepcopy(self.annotations)
        wrong_type["format_version"] = True
        self.reseal(wrong_type)
        path = self.write_annotations(wrong_type, "wrong-type.json")
        with self.assertRaisesRegex(ValueError, "unsupported annotation format"):
            evaluate_annotations(
                self.checkpoint_path, self.manifest_path, self.recordings, path
            )

    def test_missing_annotation_or_incomplete_coverage_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "annotation file is required"):
            evaluate_annotations(
                self.checkpoint_path,
                self.manifest_path,
                self.recordings,
                self.project / "absent.json",
            )
        incomplete = copy.deepcopy(self.annotations)
        incomplete["entries"].pop()
        self.reseal(incomplete)
        path = self.write_annotations(incomplete, "incomplete.json")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            evaluate_annotations(
                self.checkpoint_path, self.manifest_path, self.recordings, path
            )

    def test_train_paths_and_single_session_groups_are_rejected(self):
        train_leak = copy.deepcopy(self.annotations)
        manifest = build_manifest(
            self.recordings,
            "speaker-a",
            {"train": "session-a", "heldout": "session-b", "evaluation": "session-c"},
        )
        train = next(item for item in manifest["entries"] if item["split"] == "train")
        target = train_leak["entries"][0]
        for field in (
            "path", "split", "speaker_id", "session_id", "audio_sha256", "pcm_sha256"
        ):
            target[field] = train[field]
        self.reseal(train_leak)
        path = self.write_annotations(train_leak, "train-leak.json")
        with self.assertRaisesRegex(ValueError, "only heldout/evaluation"):
            evaluate_annotations(
                self.checkpoint_path, self.manifest_path, self.recordings, path
            )

        unpaired = copy.deepcopy(self.annotations)
        for index, entry in enumerate(unpaired["entries"]):
            entry["repetition_group_id"] = "rg-" + f"{index + 1:032x}"
        self.reseal(unpaired)
        path = self.write_annotations(unpaired, "unpaired.json")
        with self.assertRaisesRegex(ValueError, "at least two sessions"):
            evaluate_annotations(
                self.checkpoint_path, self.manifest_path, self.recordings, path
            )

    def test_boundary_types_bounds_and_order_are_strict(self):
        mutations = [
            ([True], "integers"),
            ([0], "outside audio"),
            ([5000, 4000], "strictly increasing"),
        ]
        for index, (boundaries, message) in enumerate(mutations):
            with self.subTest(boundaries=boundaries):
                invalid = copy.deepcopy(self.annotations)
                invalid["entries"][0]["boundaries_samples"] = boundaries
                self.reseal(invalid)
                path = self.write_annotations(invalid, f"invalid-{index}.json")
                with self.assertRaisesRegex(ValueError, message):
                    evaluate_annotations(
                        self.checkpoint_path, self.manifest_path, self.recordings, path
                    )

    def test_checkpoint_and_corpus_provenance_are_bound(self):
        wrong = copy.deepcopy(self.annotations)
        wrong["checkpoint_sha256"] = "0" * 64
        self.reseal(wrong)
        path = self.write_annotations(wrong, "wrong-checkpoint.json")
        with self.assertRaisesRegex(ValueError, "checkpoint provenance"):
            evaluate_annotations(
                self.checkpoint_path, self.manifest_path, self.recordings, path
            )
        candidate_path = self.checkpoint_path.with_name(
            f"candidate-{load_checkpoint(self.checkpoint_path)['checkpoint_sha256'][:12]}.json"
        )
        with self.assertRaisesRegex(ValueError, "current.json"):
            evaluate_annotations(candidate_path, self.manifest_path, self.recordings, path)

    def test_fixed_boundary_match_and_alignment_mechanics(self):
        tp, fp, fn, errors = match_boundaries(
            [0.09, 0.31, 0.50], [0.10, 0.30], BOUNDARY_TOLERANCE_SECONDS
        )
        self.assertEqual((tp, fp, fn), (2, 1, 0))
        self.assertTrue(np.allclose(errors, [0.01, 0.01]))
        with self.assertRaisesRegex(ValueError, "fixed"):
            match_boundaries([0.1], [0.1], 0.1)
        self.assertEqual(alignment_similarity((1, 2, 3), (1, 2, 3)), 1.0)
        self.assertLess(alignment_similarity((1, 2, 3), (3, 3, 3)), 1.0)


if __name__ == "__main__":
    unittest.main()
