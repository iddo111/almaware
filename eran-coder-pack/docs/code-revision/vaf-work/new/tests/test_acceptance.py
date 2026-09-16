import os
# Pin the search lane so the suite is deterministic on every machine.
# Without this, colony.node_lane() falls back to a hostname hash and each
# node trains a different seed schedule, which made these tests flaky.
os.environ.setdefault("VAF_NODE_LANE", "0")

import tempfile
import unittest
from pathlib import Path

from acceptance import build_report, report_digest
from acoustic_units import write_json_atomic
from colony import train_colony
from corpus import build_manifest
from test_colony import build_recordings


class AcceptanceReportTest(unittest.TestCase):
    def test_report_keeps_missing_product_layers_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            recordings = build_recordings(project)
            manifest = build_manifest(
                recordings, "speaker-a",
                {"train": "s1", "heldout": "s2", "evaluation": "s3"},
            )
            manifest_path = recordings / "manifest.json"
            write_json_atomic(manifest_path, manifest)
            train_colony(recordings, manifest_path, project / "state", units=4)

            report = build_report(project)
            self.assertEqual(report["overall"], "PARTIAL")
            self.assertEqual(report["layers"]["1_audio_capture"]["status"], "VERIFIED")
            self.assertEqual(report["layers"]["2_acoustic_learner"]["status"], "PARTIAL")
            self.assertEqual(report["layers"]["3_learning"]["status"], "VERIFIED")
            self.assertEqual(report["layers"]["4_evaluation"]["status"], "VERIFIED")
            self.assertEqual(report["layers"]["5_conversation"]["status"], "BLOCKED")
            self.assertFalse(report["runtime"]["persistent_service_started"])
            self.assertEqual(report["report_sha256"], report_digest(report))


if __name__ == "__main__":
    unittest.main()
