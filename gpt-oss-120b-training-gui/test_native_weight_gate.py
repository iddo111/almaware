from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import server


class NativeWeightGateTests(unittest.TestCase):
    def test_requirement_is_exact_and_adapters_are_forbidden(self) -> None:
        self.assertIn("original GPT-OSS-120B base tensors", server.NATIVE_REQUIREMENT)
        self.assertEqual(
            set(server.FORBIDDEN_ADAPTER_METHODS),
            {"lora", "qlora", "peft", "adapter"},
        )
        self.assertEqual(
            server.NATIVE_ACCEPTANCE_REQUIREMENTS,
            (
                "changed_original_tensor_hash",
                "complete_derived_checkpoint",
                "fresh_process_reload",
                "nonempty_exact_model_generation",
                "heldout_evaluation",
            ),
        )

    def test_adapter_request_is_rejected(self) -> None:
        for method in ("LoRA", "QLoRA", "PEFT", "adapter merge"):
            status, payload = server.training_start_rejection({"method": method})
            self.assertEqual(status, 400)
            self.assertIn("forbidden", payload["error"])

    def test_native_request_stays_locked(self) -> None:
        status, payload = server.training_start_rejection({"method": "native"})
        self.assertEqual(status, 409)
        self.assertIn("locked", payload["error"])
        self.assertEqual(
            payload["acceptance_requirements"],
            list(server.NATIVE_ACCEPTANCE_REQUIREMENTS),
        )

    def test_legacy_environment_flag_cannot_unlock(self) -> None:
        code = (
            "import json,server; "
            "g=server.native_training_gate([]); "
            "print(json.dumps({'legacy':g['legacy_training_env_requested'],"
            "'unlocked':g['start_unlocked'],'launcher':g['launcher_implemented']}))"
        )
        env = os.environ.copy()
        env["GPTOSS_ENABLE_TRAINING"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            result.stdout.strip(),
            '{"legacy": true, "unlocked": false, "launcher": false}',
        )

    def test_visible_gui_names_native_scope_not_adapter_control(self) -> None:
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("NATIVE WEIGHT TRAINING", html)
        self.assertIn("Original-tensor SFT gate", html)
        self.assertNotIn("LoRA run control", html)
        self.assertNotIn("QLoRA / LoRA", html)

    def test_status_source_does_not_claim_training_from_process_roster(self) -> None:
        source = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("pgrep", source)
        self.assertIn("'training_process_state':'UNVERIFIED'", source)
        gate = server.native_training_gate([])
        self.assertFalse(gate["start_unlocked"])

    def test_gui_response_requires_exact_model_nonempty_nonce(self) -> None:
        nonce = "GPTOSS-GUI-0123456789ABCDEF"
        error, content = server.validate_gui_chat_response(
            {"model": server.MODEL, "done": True, "message": {"content": f"verified {nonce}"}},
            nonce,
        )
        self.assertIsNone(error)
        self.assertIn(nonce, content)
        for response in (
            {"model": "wrong-model", "message": {"content": nonce}},
            {"model": server.MODEL, "message": {"content": ""}},
            {"model": server.MODEL, "message": {"content": "missing challenge"}},
            {"model": server.MODEL, "done": False, "message": {"content": nonce}},
        ):
            error, _ = server.validate_gui_chat_response(response, nonce)
            self.assertIsNotNone(error)

    def test_route_binding_requires_stable_exact_digest(self) -> None:
        good = {"loaded": True, "model": server.MODEL, "digest": "abc"}
        self.assertIsNone(server.validate_route_binding(good, good))
        self.assertIsNotNone(server.validate_route_binding(good, {**good, "digest": "def"}))
        self.assertIsNotNone(server.validate_route_binding(good, {"loaded": False, "model": server.MODEL}))

    def test_gui_and_gate_expose_scope_and_workload_evidence(self) -> None:
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("ATTENTION-ONLY ENGINEERING LANE", html)
        self.assertIn("Two-node checkpoint copies", html)
        self.assertIn("Route listed", js)
        self.assertIn("GPTOSS-GUI-", js)
        self.assertIn("result.done !== true", js)
        self.assertIn("route_digest", js)
        self.assertIn("VERIFICATION_TTL_MS", js)
        self.assertIn("verificationExpiryTimer = setTimeout", js)
        self.assertIn("STATUS_POLL_MS", js)
        self.assertIn("setInterval", js)
        self.assertIn('setState(byId("model-state"), "Checking", "pending")', js)
        self.assertGreaterEqual(js.count("clearVerifiedRoute();"), 4)
        self.assertIn("mem_available_bytes", (ROOT / "server.py").read_text(encoding="utf-8"))

    def test_attention_and_fullweights_workload_gates_are_separate(self) -> None:
        eran1 = {
            "name": "Eran1", "reachable": True, "weight_files": 15, "index_present": True,
            "native_project_present": True, "native_runner_present": True,
            "native_handoff_present": True, "native_source_clean": True,
            "mem_available_bytes": 128 * 1024**3, "gpu_process_query_ok": True,
            "gpu_processes": [], "container_query_ok": True, "containers": [],
            "fullweights_project_present": True,
        }
        eran2 = {
            "name": "Eran2", "reachable": True, "weight_files": 15, "index_present": True,
            "mem_available_bytes": 4 * 1024**3, "gpu_process_query_ok": True,
            "gpu_processes": ["vllm"], "container_query_ok": True,
            "containers": ["gptoss-vllm"], "fullweights_project_present": False,
        }
        attention = server.native_training_gate([eran1, eran2])
        fullweights = server.fullweights_training_gate([eran1, eran2])
        self.assertFalse(any("Eran2" in item for item in attention["blockers"]))
        self.assertTrue(any("Eran2" in item for item in fullweights["blockers"]))
        self.assertFalse(attention["start_unlocked"])
        self.assertFalse(fullweights["start_unlocked"])


if __name__ == "__main__":
    unittest.main()
