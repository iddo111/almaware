import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import studio_server as studio  # noqa: E402


class StudioContractTests(unittest.TestCase):
    def test_manifest_has_only_the_two_studio_workers(self):
        manifest = studio.load_manifest()
        ids = [node["id"] for node in manifest["nodes"]]
        self.assertEqual(ids, ["dgx3", "dgx4"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_brain_is_one_pp2_service_outside_worker_pool(self):
        manifest = studio.load_manifest()
        self.assertEqual(
            manifest["brain"]["topology"],
            "one PP2 model across DGX1 and DGX2",
        )
        self.assertNotIn("dgx1", [node["id"] for node in manifest["nodes"]])
        self.assertNotIn("dgx2", [node["id"] for node in manifest["nodes"]])

    def test_only_brain_can_reference_dgx1_or_dgx2(self):
        manifest = studio.load_manifest()
        render_models = [m for m in manifest["models"] if m["lane"] != "brain"]
        self.assertTrue(all(m["node"] in {"dgx3", "dgx4"} for m in render_models))
        self.assertFalse(any("340B" in m["id"] for m in manifest["models"]))

    def test_models_have_provenance_and_license(self):
        for model in studio.load_manifest()["models"]:
            self.assertTrue(model["source"].startswith("https://"))
            self.assertTrue(model["license"])
            self.assertGreater(model["expected_bytes"], 0)

    def test_routable_models_are_revision_pinned(self):
        manifest = studio.load_manifest()
        routable_lanes = {"image-fast", "video-fast-fallback", "music", "tts-and-voice"}
        routed = {model["lane"]: model for model in manifest["models"] if model["lane"] in routable_lanes}
        self.assertEqual(set(routed), routable_lanes)
        for model in routed.values():
            self.assertRegex(model["revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(manifest["finishing"]["engine"], "FFmpeg")
        self.assertTrue(manifest["finishing"]["engine_revision"])

    def test_job_schema_is_valid_json_and_requires_provenance_fields(self):
        schema = json.loads((ROOT / "workflows" / "job.schema.json").read_text(encoding="utf-8"))
        required = set(schema["required"])
        self.assertTrue({"model_revision", "model_license", "workflow_sha256", "acceptance_tests"} <= required)

    def test_system_prompt_enforces_the_two_plus_two_allocation(self):
        prompt = " ".join(studio.load_system_prompt().split())
        self.assertIn("one PP2 model across DGX1 and DGX2", prompt)
        self.assertIn("image and video work only to DGX3", prompt)
        self.assertIn("music, voice, and finishing work only to DGX4", prompt)

    @mock.patch("studio_server.urllib.request.urlopen")
    def test_brain_plan_requires_exact_model_and_visible_output(self, urlopen):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "model": studio.BRAIN_MODEL,
                    "choices": [{"message": {"content": "VERIFIED PLAN"}}],
                    "usage": {"completion_tokens": 2},
                    "alma_harness": {"node": "DGX1 + DGX2 · PP2"},
                }).encode("utf-8")

        urlopen.return_value = Response()
        result = studio.call_brain("Plan this shot", {"shot_id": "sc01-sh010"}, 256)
        self.assertEqual(result["content"], "VERIFIED PLAN")
        self.assertEqual(result["model"], studio.BRAIN_MODEL)
        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], studio.BRAIN_MODEL)
        self.assertEqual(body["messages"][0]["role"], "system")


if __name__ == "__main__":
    unittest.main()
