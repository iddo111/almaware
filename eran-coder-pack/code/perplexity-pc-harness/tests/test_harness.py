import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from computer_use import (
    ComputerLimits,
    ComputerUseSession,
    FakeComputerBackend,
    redacted_preview,
)
from harness import (
    LocalPolicyHarness,
    PerplexityAgentClient,
    PolicyError,
    extract_output_text,
    run_agent,
)


class HarnessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.audit = self.temp_path / "audit.jsonl"
        self.stop = self.temp_path / "STOP"
        self.harness = LocalPolicyHarness(
            audit_path=self.audit,
            stop_path=self.stop,
            approval=lambda _name, _args: True,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_pc_status_is_nonempty_and_audited_without_raw_args(self):
        result = self.harness.execute("pc_status", {})
        self.assertTrue(result["ok"])
        record = json.loads(self.audit.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["tool"], "pc_status")
        self.assertEqual(len(record["args_sha256"]), 64)
        self.assertNotIn("args", record)
        self.assertNotIn("result", record)

    def test_unknown_tool_fails_closed(self):
        result = self.harness.execute("shell", {"command": "whoami"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "PolicyError")

    def test_unknown_argument_fails_closed(self):
        result = self.harness.execute("pc_status", {"extra": True})
        self.assertFalse(result["ok"])
        self.assertIn("Unknown argument", result["message"])

    def test_path_escape_is_blocked(self):
        result = self.harness.execute("read_workspace_text", {"relative_path": "..\\Windows\\win.ini"})
        self.assertFalse(result["ok"])
        self.assertIn("Path escape", result["message"])

    def test_sensitive_path_is_blocked(self):
        result = self.harness.execute("list_workspace", {"relative_path": "_secrets", "limit": 5})
        self.assertFalse(result["ok"])
        self.assertIn("Sensitive path", result["message"])

    def test_kill_switch_blocks_before_execution(self):
        self.stop.write_text("stop", encoding="utf-8")
        result = self.harness.execute("pc_status", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "StopRequested")

    def test_non_allowlisted_diagnostic_is_rejected_by_schema(self):
        result = self.harness.execute("run_diagnostic", {"diagnostic": "powershell"})
        self.assertFalse(result["ok"])
        self.assertIn("not allowlisted", result["message"])

    def test_diagnostic_subprocess_does_not_inherit_api_key(self):
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "must-not-leak"}):
            with patch("harness.subprocess.run", return_value=completed) as mocked:
                result = self.harness.execute("run_diagnostic", {"diagnostic": "git_status"})
        self.assertTrue(result["ok"])
        child_env = mocked.call_args.kwargs["env"]
        self.assertNotIn("PERPLEXITY_API_KEY", child_env)

    def test_tool_definitions_have_no_general_shell(self):
        names = {item["name"] for item in self.harness.tool_definitions()}
        self.assertEqual(
            names,
            {
                "pc_status",
                "list_workspace",
                "read_workspace_text",
                "run_diagnostic",
                "list_windows",
                "observe_window",
                "computer_action",
            },
        )
        self.assertNotIn("shell", names)


class AgentProtocolTests(unittest.TestCase):
    def test_missing_key_is_actionable(self):
        with self.assertRaises(PolicyError):
            PerplexityAgentClient(api_key="")

    def test_extract_output_text_requires_message_content(self):
        response = {
            "output": [
                {"type": "reasoning", "content": []},
                {"type": "message", "content": [{"type": "output_text", "text": "MARKER_OK"}]},
            ]
        }
        self.assertEqual(extract_output_text(response), "MARKER_OK")


class ComputerUsePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.backend = FakeComputerBackend()
        self.session = ComputerUseSession(self.backend, self.temp_path / "STOP")
        self.harness = LocalPolicyHarness(
            audit_path=self.temp_path / "audit.jsonl",
            stop_path=self.temp_path / "STOP",
            approval=lambda _name, _args: True,
            computer_session=self.session,
        )
        listed = self.harness.execute("list_windows", {})
        self.window_id = listed["windows"][0]["id"]
        self.observation = self.harness.execute("observe_window", {"window_id": self.window_id})

    def tearDown(self):
        self.temp.cleanup()

    def action(self, **overrides):
        args = {
            "window_id": self.window_id,
            "observation_id": self.observation["observation_id"],
            "action": "click",
            "x": 10,
            "y": 10,
        }
        args.update(overrides)
        args = {key: value for key, value in args.items() if value is not None}
        return self.harness.execute("computer_action", args)

    def test_action_requires_fresh_matching_observation(self):
        result = self.action(observation_id="stale")
        self.assertFalse(result["ok"])
        self.assertIn("stale", result["message"])

    def test_coordinate_bounds_fail_closed(self):
        result = self.action(x=self.observation["image_width"])
        self.assertFalse(result["ok"])
        self.assertIn("outside", result["message"])

    def test_window_identity_and_material_move_are_enforced(self):
        self.backend.window["bounds"]["left"] += 100
        result = self.action()
        self.assertFalse(result["ok"])
        self.assertIn("moved", result["message"])

    def test_denied_approval_never_calls_backend(self):
        denied_harness = LocalPolicyHarness(
            audit_path=self.temp_path / "denied.jsonl",
            stop_path=self.temp_path / "STOP",
            approval=lambda _name, _args: False,
            computer_session=self.session,
        )
        result = denied_harness.execute(
            "computer_action",
            {
                "window_id": self.window_id,
                "observation_id": self.observation["observation_id"],
                "action": "click",
                "x": 1,
                "y": 1,
            },
        )
        self.assertTrue(result["denied"])
        self.assertEqual(self.backend.actions, [])

    def test_text_preview_redacts_secret_like_content(self):
        self.assertEqual(
            redacted_preview("api_key=do-not-log-this"),
            "[REDACTED_SENSITIVE_TEXT]",
        )
        result = self.action(action="type_text", text="token=do-not-type", x=None, y=None)
        self.assertFalse(result["ok"])
        self.assertIn("Sensitive", result["message"])

    def test_kill_switch_stops_next_action(self):
        (self.temp_path / "STOP").write_text("stop", encoding="utf-8")
        result = self.action()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "StopRequested")
        self.assertEqual(self.backend.actions, [])

    def test_action_limit_is_enforced(self):
        limited_backend = FakeComputerBackend()
        limited = ComputerUseSession(
            limited_backend,
            self.temp_path / "limited-stop",
            limits=ComputerLimits(max_actions=1),
        )
        listed = limited.list_windows()
        window_id = listed["windows"][0]["id"]
        observed = limited.observe_window({"window_id": window_id})
        first = limited.computer_action(
            {
                "window_id": window_id,
                "observation_id": observed["observation_id"],
                "action": "click",
                "x": 1,
                "y": 1,
            }
        )
        with self.assertRaisesRegex(Exception, "action limit"):
            limited.computer_action(
                {
                    "window_id": window_id,
                    "observation_id": first["observation_id"],
                    "action": "click",
                    "x": 2,
                    "y": 2,
                }
            )

    def test_no_progress_identical_action_is_detected(self):
        backend = FakeComputerBackend()
        limited = ComputerUseSession(
            backend,
            self.temp_path / "progress-stop",
            limits=ComputerLimits(max_identical_actions=1),
        )
        listed = limited.list_windows()
        window_id = listed["windows"][0]["id"]
        observed = limited.observe_window({"window_id": window_id})
        first = limited.computer_action(
            {
                "window_id": window_id,
                "observation_id": observed["observation_id"],
                "action": "wait",
                "duration_ms": 0,
            }
        )
        with self.assertRaisesRegex(Exception, "No-progress"):
            limited.computer_action(
                {
                    "window_id": window_id,
                    "observation_id": first["observation_id"],
                    "action": "wait",
                    "duration_ms": 0,
                }
            )

    def test_turn_limit_is_enforced(self):
        limited = ComputerUseSession(
            FakeComputerBackend(),
            self.temp_path / "turn-stop",
            limits=ComputerLimits(max_turns=1),
        )
        limited.list_windows()
        with self.assertRaisesRegex(Exception, "turn limit"):
            limited.list_windows()

    def test_screenshot_size_limit_is_enforced(self):
        limited = ComputerUseSession(
            FakeComputerBackend(),
            self.temp_path / "size-stop",
            limits=ComputerLimits(max_screenshot_bytes=20),
        )
        listed = limited.list_windows()
        with self.assertRaisesRegex(Exception, "Screenshot exceeds"):
            limited.observe_window({"window_id": listed["windows"][0]["id"]})

    def test_windows_key_chord_is_not_allowlisted(self):
        result = self.action(action="press_key", key="Super_L+r", x=None, y=None)
        self.assertFalse(result["ok"])
        self.assertIn("not allowlisted", result["message"])

    def test_observe_only_removes_and_blocks_action_tool(self):
        observe_session = ComputerUseSession(
            FakeComputerBackend(),
            self.temp_path / "observe-stop",
            observe_only=True,
        )
        observe_harness = LocalPolicyHarness(
            audit_path=self.temp_path / "observe.jsonl",
            stop_path=self.temp_path / "observe-stop",
            approval=lambda _name, _args: True,
            computer_session=observe_session,
            observe_only=True,
        )
        names = {item["name"] for item in observe_harness.tool_definitions()}
        self.assertNotIn("computer_action", names)
        result = observe_harness.execute(
            "computer_action",
            {"window_id": "x", "observation_id": "y", "action": "focus"},
        )
        self.assertFalse(result["ok"])

    def test_dry_run_does_not_inject_input(self):
        backend = FakeComputerBackend()
        dry = ComputerUseSession(backend, self.temp_path / "dry-stop", dry_run=True)
        listed = dry.list_windows()
        window_id = listed["windows"][0]["id"]
        observed = dry.observe_window({"window_id": window_id})
        result = dry.computer_action(
            {
                "window_id": window_id,
                "observation_id": observed["observation_id"],
                "action": "click",
                "x": 1,
                "y": 1,
            }
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(backend.actions, [])

    def test_post_action_observation_and_audit_are_fresh_and_redacted(self):
        result = self.action(action="type_text", text="SAFE_MARKER", x=None, y=None)
        self.assertTrue(result["ok"])
        self.assertNotEqual(result["screenshot_sha256"], self.observation["screenshot_sha256"])
        log_text = (self.temp_path / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn(result["screenshot_sha256"], log_text)
        self.assertIn(self.window_id, log_text)
        self.assertNotIn("SAFE_MARKER", log_text)


class FakeAgentE2ETests(unittest.TestCase):
    class FakeAgentClient:
        def __init__(self):
            self.payloads = []

        def create(self, payload):
            self.payloads.append(payload)
            turn = len(self.payloads)
            if turn == 1:
                return {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-list",
                            "name": "list_windows",
                            "arguments": "{}",
                        }
                    ]
                }
            outputs = payload["input"]
            function_outputs = [
                json.loads(item["output"])
                for item in outputs
                if item.get("type") == "function_call_output"
            ]
            if turn == 2:
                window_id = function_outputs[-1]["windows"][0]["id"]
                return {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-observe",
                            "name": "observe_window",
                            "arguments": json.dumps({"window_id": window_id}),
                        }
                    ]
                }
            if turn == 3:
                observation = function_outputs[-1]
                return {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-type",
                            "name": "computer_action",
                            "arguments": json.dumps(
                                {
                                    "window_id": observation["window"]["id"],
                                    "observation_id": observation["observation_id"],
                                    "action": "type_text",
                                    "text": "PPLX_FAKE_E2E_MARKER",
                                }
                            ),
                        }
                    ]
                }
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "PPLX_FAKE_AGENT_LOOP_OK",
                            }
                        ],
                    }
                ]
            }

    def test_fake_agent_observe_action_fresh_observe_final_text(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            backend = FakeComputerBackend()
            session = ComputerUseSession(backend, temp_path / "STOP")
            harness = LocalPolicyHarness(
                audit_path=temp_path / "audit.jsonl",
                stop_path=temp_path / "STOP",
                approval=lambda _name, _args: True,
                computer_session=session,
            )
            client = self.FakeAgentClient()
            result = run_agent("Use the safe test window.", "vision-tool-model", harness, client)
            self.assertEqual(result, "PPLX_FAKE_AGENT_LOOP_OK")
            self.assertEqual(backend.marker, "PPLX_FAKE_E2E_MARKER")
            image_payloads = [
                item
                for payload in client.payloads
                for item in (payload.get("input") if isinstance(payload.get("input"), list) else [])
                if item.get("role") == "user"
                and isinstance(item.get("content"), list)
                and any(part.get("type") == "input_image" for part in item["content"])
            ]
            self.assertEqual(len(image_payloads), 2)
            audit = (temp_path / "audit.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("PPLX_FAKE_E2E_MARKER", audit)
            self.assertIn("screenshot_sha256", audit)

    def test_malformed_function_call_shape_fails_closed(self):
        class BadClient:
            def create(self, _payload):
                return {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "pc_status",
                            "arguments": "{}",
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            harness = LocalPolicyHarness(
                audit_path=temp_path / "audit.jsonl",
                stop_path=temp_path / "STOP",
                approval=lambda _name, _args: True,
            )
            with self.assertRaisesRegex(RuntimeError, "ID is missing"):
                run_agent("test", "model", harness, BadClient())


if __name__ == "__main__":
    unittest.main()
