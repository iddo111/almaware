from __future__ import annotations

import asyncio
import json
import os
import subprocess
import unittest
from unittest import mock

import ai_clients
import shakla


class CliInvocationTests(unittest.TestCase):
    def test_current_cli_prompt_contracts_and_safe_modes(self):
        argv, stdin_text = ai_clients._cli_invocation("claude", "nonce")
        self.assertEqual(stdin_text, "nonce")
        self.assertNotIn("nonce", argv)

        argv, stdin_text = ai_clients._cli_invocation("grok", "nonce")
        self.assertIsNone(stdin_text)
        self.assertEqual(argv[-2:], ["-p", "nonce"])
        self.assertIn("--no-subagents", argv)
        self.assertIn("--disable-web-search", argv)
        self.assertIn("plan", argv)

        argv, stdin_text = ai_clients._cli_invocation("gemini", "nonce")
        self.assertIsNone(stdin_text)
        self.assertEqual(argv[-2:], ["-p", "nonce"])
        self.assertIn("plan", argv)

    def test_ask_never_uses_a_shell(self):
        completed = subprocess.CompletedProcess(["grok"], 0, "ok\n", "")
        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients, "_which", return_value="grok.exe"),
            mock.patch.object(ai_clients.subprocess, "run", return_value=completed) as run,
        ):
            reply = ai_clients.ask("nonce", "grok", timeout=3)
        self.assertTrue(reply)
        self.assertEqual(reply.text, "ok")
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertIsNone(run.call_args.kwargs["input"])

    def test_gemini_cmd_shim_is_materialized_as_node_without_shell(self):
        completed = subprocess.CompletedProcess(["node"], 0, "ok\n", "")

        def which(name):
            return {
                "gemini": r"C:\npm\gemini.CMD",
                "node": r"C:\node\node.exe",
            }.get(name)

        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients, "_which", side_effect=which),
            mock.patch.object(ai_clients.os.path, "isfile", return_value=True),
            mock.patch.object(ai_clients.subprocess, "run", return_value=completed) as run,
        ):
            reply = ai_clients.ask("nonce", "gemini", timeout=3)
        self.assertTrue(reply)
        argv = run.call_args.args[0]
        self.assertEqual(argv[0], r"C:\node\node.exe")
        self.assertTrue(argv[1].endswith(r"@google\gemini-cli\bundle\gemini.js"))
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_nonzero_or_entitlement_error_cannot_pass_with_stdout(self):
        cases = (
            subprocess.CompletedProcess(["grok"], 1, "plausible text", "backend failed"),
            subprocess.CompletedProcess(
                ["grok"], 0, "plausible text", "403 permission-denied: requires a Grok subscription"
            ),
        )
        for completed in cases:
            with (
                self.subTest(returncode=completed.returncode),
                mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
                mock.patch.object(ai_clients, "_which", return_value="grok.exe"),
                mock.patch.object(ai_clients.subprocess, "run", return_value=completed),
            ):
                reply = ai_clients.ask("nonce", "grok", timeout=3)
            self.assertFalse(reply)
            self.assertEqual(reply.error, ai_clients.ErrorKind.BACKEND)


class AlmaHarnessProviderTests(unittest.TestCase):
    class Response:
        def __init__(self, value):
            self.raw = json.dumps(value).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return self.raw

    def test_harness_root_must_be_private_and_https_for_tailnet_dns(self):
        with mock.patch.object(ai_clients.config, "ALMA_HARNESS_URL", "https://dgx4.example.ts.net:8446"):
            self.assertEqual(ai_clients._validated_alma_root(), "https://dgx4.example.ts.net:8446")
        for value in ("https://public.example.com", "http://dgx4.example.ts.net:8446"):
            with mock.patch.object(ai_clients.config, "ALMA_HARNESS_URL", value):
                with self.assertRaises(ValueError):
                    ai_clients._validated_alma_root()

    def test_detection_requires_exact_ready_alma_owned_model(self):
        value = {
            "data": [
                {"id": "nvidia/nemotron-3-super", "ready": True, "owned_by": "alma-local"},
                {"id": "openai/gpt-oss-120b", "ready": False, "owned_by": "alma-local"},
            ]
        }
        with (
            mock.patch.object(ai_clients.config, "ALMA_HARNESS_URL", "https://dgx4.example.ts.net:8446"),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(value)),
        ):
            models = ai_clients._detect_alma_models()
        self.assertEqual([model["id"] for model in models], ["alma:nemotron"])
        self.assertEqual(models[0]["model"], "nvidia/nemotron-3-super")

    def test_generation_requires_exact_model_and_route_identity(self):
        value = {
            "model": "nvidia/nemotron-3-super",
            "alma_harness": {"model_key": "nemotron"},
            "choices": [{"message": {"content": "ALMA_OK"}}],
        }
        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients.config, "ALMA_HARNESS_URL", "https://dgx4.example.ts.net:8446"),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(value)) as opened,
        ):
            reply = ai_clients.ask("nonce", "alma:nemotron", timeout=3)
        self.assertTrue(reply)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://dgx4.example.ts.net:8446/v1/chat/completions")
        self.assertEqual(json.loads(request.data)["model"], "nvidia/nemotron-3-super")

        value["alma_harness"]["model_key"] = "gptoss120b"
        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients.config, "ALMA_HARNESS_URL", "https://dgx4.example.ts.net:8446"),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(value)),
        ):
            reply = ai_clients.ask("nonce", "alma:nemotron", timeout=3)
        self.assertFalse(reply)
        self.assertIn("different model or route", reply.note)


class FleetProviderTests(unittest.TestCase):
    Response = AlmaHarnessProviderTests.Response

    ROUTER = "http://<lan-ip>:8010"  # the ONE 4D router (alma-router v3, eran1)

    def test_fleet_root_must_be_private(self):
        with mock.patch.object(ai_clients.config, "FLEET_ROUTER_URL", self.ROUTER):
            self.assertEqual(ai_clients._validated_fleet_root("gpt-oss-120b"),
                             self.ROUTER)
        for value in ("https://public.example.com", "", "http://8.8.8.8:8000"):
            with mock.patch.object(ai_clients.config, "FLEET_ROUTER_URL", value):
                with self.assertRaises(ValueError):
                    ai_clients._validated_fleet_root("gpt-oss-120b")

    def test_detection_requires_exact_listed_model(self):
        value = {"data": [{"id": "gpt-oss-120b", "object": "model"}]}
        with (
            mock.patch.object(ai_clients.config, "FLEET_ROUTER_URL", self.ROUTER),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(value)) as opened,
        ):
            models = ai_clients._detect_fleet_models()
        self.assertEqual([model["id"] for model in models], ["gpt-oss-120b"])
        # all four providers share the router; the listing is fetched ONCE
        self.assertEqual(opened.call_count, 1)

        wrong = {"data": [{"id": "some-other-model", "object": "model"}]}
        with (
            mock.patch.object(ai_clients.config, "FLEET_ROUTER_URL", self.ROUTER),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(wrong)),
        ):
            self.assertEqual(ai_clients._detect_fleet_models(), [])

    def test_all_four_council_models_detected_from_one_router(self):
        value = {"data": [{"id": mid, "object": "model"}
                          for mid in ("qwen3-coder-next-fp8", "glm-4.7-flash",
                                      "nemotron-3-super", "gpt-oss-120b")]}
        with (
            mock.patch.object(ai_clients.config, "FLEET_ROUTER_URL", self.ROUTER),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(value)),
        ):
            models = ai_clients._detect_fleet_models()
        self.assertEqual([m["id"] for m in models],
                         ["qwen3-coder-next-fp8", "glm-4.7-flash",
                          "nemotron-3-super", "gpt-oss-120b"])

    def test_generation_requires_exact_model_echo_and_strips_harmony(self):
        value = {
            "model": "gpt-oss-120b",
            "choices": [{"message": {"content":
                "<|channel|>analysis<|message|>thinking<|end|>FLEET_OK"}}],
        }
        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients.config, "FLEET_ROUTER_URL", self.ROUTER),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(value)) as opened,
        ):
            reply = ai_clients.ask("nonce", "gpt-oss-120b", timeout=3)
        self.assertTrue(reply)
        self.assertEqual(reply.text, "FLEET_OK")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, self.ROUTER + "/v1/chat/completions")
        self.assertEqual(json.loads(request.data)["model"], "gpt-oss-120b")

        value["model"] = "some-other-model"
        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients.config, "FLEET_ROUTER_URL", self.ROUTER),
            mock.patch.object(ai_clients.urllib.request, "urlopen", return_value=self.Response(value)),
        ):
            reply = ai_clients.ask("nonce", "gpt-oss-120b", timeout=3)
        self.assertFalse(reply)
        self.assertIn("different model", reply.note)


class LiveProviderFilteringTests(unittest.TestCase):
    def _run(self, live_providers: set[str]) -> list[dict]:
        events: list[dict] = []

        async def fake_astream(_prompt, provider, **_kwargs):
            if provider in live_providers:
                yield ai_clients.Chunk("text", f"{provider} non-empty reply")
            else:
                yield ai_clients.Chunk("status", "[backend: unavailable]")

        async def drive():
            with (
                mock.patch.object(
                    ai_clients,
                    "detect_models",
                    return_value=[{"id": p} for p in ("claude", "grok", "gemini")],
                ),
                mock.patch.object(ai_clients, "astream", side_effect=fake_astream),
                mock.patch.dict(os.environ, {"QUORUM_ENABLED": "1"}),
            ):
                async for event in shakla.run_shakla(
                    "harmless deterministic test",
                    model_ids=["claude", "grok", "gemini"],
                    num_rounds=1,
                ):
                    events.append(event)

        asyncio.run(drive())
        return events

    def test_failed_installed_provider_is_not_synthesizer(self):
        events = self._run({"grok", "gemini"})
        done = events[-1]["data"]
        self.assertTrue(done["live"])
        self.assertEqual(done["synth_model"], "gemini")
        self.assertNotIn("claude", {t["model"] for t in done["transcript"] if t["round"] > 0})

    def test_one_real_provider_cannot_pass_multi_provider_gate(self):
        events = self._run({"grok"})
        self.assertFalse(events[-1]["data"]["live"])
        self.assertTrue(any(e["event"] == "error" for e in events))


if __name__ == "__main__":
    unittest.main()
