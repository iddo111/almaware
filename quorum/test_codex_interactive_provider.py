from __future__ import annotations

import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ai_clients
import shakla


class _Store:
    def __init__(self, *, active: bool = True, exact_identity: bool = True):
        self.active = active
        self.exact_identity = exact_identity
        self.enqueued: list[dict] = []
        self.polls = 0

    def status(self):
        provider = (
            ai_clients.CODEX_INTERACTIVE_ID
            if self.exact_identity
            else "not-codex-interactive"
        )
        return {
            "canonical_provider_id": provider,
            "participants": [
                {
                    "participant_id": ai_clients.CODEX_INTERACTIVE_ID,
                    "active": self.active,
                }
            ],
        }

    def enqueue_turn(self, prompt, *, debate_id, participant_id):
        turn = {
            "prompt": prompt,
            "debate_id": debate_id,
            "participant_id": participant_id,
            "turn_id": "turn-test",
            "request_nonce": "nonce-test",
        }
        self.enqueued.append(turn)
        return dict(turn)

    def completed_turn(self, turn_id):
        self.polls += 1
        if self.polls == 1:
            return None
        response = "exact correlated contribution"
        return {
            "participant_id": ai_clients.CODEX_INTERACTIVE_ID,
            "debate_id": self.enqueued[-1]["debate_id"],
            "turn_id": turn_id,
            "request_nonce": self.enqueued[-1]["request_nonce"],
            "response": response,
            "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
        }


class DiscoveryTests(unittest.TestCase):
    def _detect(self, *, enabled, root, database, store):
        with (
            mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_ENABLED", enabled),
            mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_ROOT", root),
            mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_DB", database),
            mock.patch.object(ai_clients.config, "CLI_LABELS", {}),
            mock.patch.object(ai_clients.config, "ALMA_HARNESS_URL", ""),
            mock.patch.object(ai_clients, "_which", return_value=None),
            mock.patch.object(ai_clients, "_interactive_store", return_value=store) as opened,
        ):
            models = ai_clients.detect_models()
        return models, opened

    def test_discovery_is_fail_closed_until_complete_config_and_active_exact_identity(self):
        models, opened = self._detect(
            enabled=False,
            root=r"C:\bridge",
            database=r"C:\bridge\state.sqlite3",
            store=_Store(),
        )
        self.assertNotIn(
            ai_clients.CODEX_INTERACTIVE_ID,
            {model["id"] for model in models},
        )
        opened.assert_not_called()

        models, opened = self._detect(
            enabled=True,
            root="",
            database=r"C:\bridge\state.sqlite3",
            store=_Store(),
        )
        self.assertNotIn(
            ai_clients.CODEX_INTERACTIVE_ID,
            {model["id"] for model in models},
        )
        opened.assert_not_called()

        for store in (_Store(active=False), _Store(exact_identity=False)):
            models, _opened = self._detect(
                enabled=True,
                root=r"C:\bridge",
                database=r"C:\bridge\state.sqlite3",
                store=store,
            )
            self.assertNotIn(
                ai_clients.CODEX_INTERACTIVE_ID,
                {model["id"] for model in models},
            )

        models, _opened = self._detect(
            enabled=True,
            root=r"C:\bridge",
            database=r"C:\bridge\state.sqlite3",
            store=_Store(),
        )
        interactive = [
            model for model in models
            if model["id"] == ai_clients.CODEX_INTERACTIVE_ID
        ]
        self.assertEqual(len(interactive), 1)
        self.assertFalse(interactive[0]["default"])

    def test_bridge_module_is_loaded_only_from_validated_absolute_root(self):
        with (
            mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_ENABLED", True),
            mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_ROOT", "relative"),
            mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_DB", "relative.sqlite3"),
        ):
            with self.assertRaisesRegex(ValueError, "must be absolute"):
                ai_clients._load_interactive_bridge()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            database = root / "state.sqlite3"
            database.touch()
            (root / "bridge_state.py").write_text(
                "CODEX_INTERACTIVE_ID = 'codex-interactive'\n"
                "class BridgeStore:\n"
                "    def __init__(self, path): self.path = path\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_ENABLED", True),
                mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_ROOT", str(root)),
                mock.patch.object(ai_clients.config, "CODEX_INTERACTIVE_DB", str(database)),
                mock.patch.dict(ai_clients._INTERACTIVE_MODULE_CACHE, {}, clear=True),
            ):
                module = ai_clients._load_interactive_bridge()
            self.assertEqual(
                module.CODEX_INTERACTIVE_ID,
                ai_clients.CODEX_INTERACTIVE_ID,
            )


class InteractiveRoundTripTests(unittest.TestCase):
    def test_exact_turn_is_enqueued_polled_and_returned_with_correlation(self):
        store = _Store()
        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients, "_interactive_store", return_value=store),
            mock.patch.object(
                ai_clients.subprocess,
                "run",
                side_effect=AssertionError("interactive provider must not spawn a process"),
            ),
        ):
            reply = ai_clients.ask(
                "user prompt",
                ai_clients.CODEX_INTERACTIVE_ID,
                system="system contract",
                timeout=1,
                correlation_id="debate-test",
            )
        self.assertTrue(reply)
        self.assertEqual(reply.provider, ai_clients.CODEX_INTERACTIVE_ID)
        self.assertEqual(reply.correlation_id, "debate-test")
        self.assertEqual(reply.turn_id, "turn-test")
        self.assertEqual(reply.request_nonce, "nonce-test")
        self.assertGreaterEqual(store.polls, 2)
        self.assertEqual(store.enqueued[0]["debate_id"], "debate-test")
        self.assertEqual(
            store.enqueued[0]["participant_id"],
            ai_clients.CODEX_INTERACTIVE_ID,
        )
        self.assertIn("system contract", store.enqueued[0]["prompt"])
        self.assertIn("user prompt", store.enqueued[0]["prompt"])

    def test_missing_correlation_id_is_a_failure_value(self):
        with mock.patch.object(ai_clients.config, "is_enabled", return_value=True):
            reply = ai_clients.ask(
                "prompt",
                ai_clients.CODEX_INTERACTIVE_ID,
                timeout=0.1,
            )
        self.assertFalse(reply)
        self.assertEqual(reply.error, ai_clients.ErrorKind.BACKEND)
        self.assertIn("correlation_id", reply.note)

    def test_mismatched_request_nonce_is_rejected(self):
        store = _Store()

        def mismatched(turn_id):
            response = "plausible but unattributed"
            return {
                "participant_id": ai_clients.CODEX_INTERACTIVE_ID,
                "debate_id": "debate-test",
                "turn_id": turn_id,
                "request_nonce": "different-nonce",
                "response": response,
                "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            }

        store.completed_turn = mismatched
        with (
            mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
            mock.patch.object(ai_clients, "_interactive_store", return_value=store),
        ):
            reply = ai_clients.ask(
                "prompt",
                ai_clients.CODEX_INTERACTIVE_ID,
                timeout=1,
                correlation_id="debate-test",
            )
        self.assertFalse(reply)
        self.assertEqual(reply.error, ai_clients.ErrorKind.BACKEND)
        self.assertIn("correlation mismatch", reply.note)


class DebateCorrelationTests(unittest.TestCase):
    @staticmethod
    def _run() -> tuple[list[dict], list[str]]:
        events: list[dict] = []
        calls: list[str] = []

        async def fake_astream(_prompt, provider, *, correlation_id="", **_kwargs):
            calls.append(correlation_id)
            yield ai_clients.Chunk(
                "text",
                f"{provider} non-empty",
                provider=provider,
                correlation_id=correlation_id,
            )

        async def drive():
            with (
                mock.patch.object(ai_clients.config, "is_enabled", return_value=True),
                mock.patch.object(
                    ai_clients,
                    "detect_models",
                    return_value=[{"id": "voice-a"}, {"id": "voice-b"}],
                ),
                mock.patch.object(ai_clients, "astream", side_effect=fake_astream),
            ):
                async for event in shakla.run_shakla(
                    "deterministic correlation test",
                    model_ids=["voice-a", "voice-b"],
                    num_rounds=1,
                ):
                    events.append(event)

        asyncio.run(drive())
        return events, calls

    def test_every_public_event_and_model_call_uses_one_fresh_debate_id(self):
        events, calls = self._run()
        debate_ids = {event["data"]["debate_id"] for event in events}
        self.assertEqual(len(debate_ids), 1)
        debate_id = next(iter(debate_ids))
        self.assertTrue(debate_id.startswith("debate-"))
        self.assertTrue(all(
            event["data"]["correlation_id"] == debate_id
            for event in events
        ))
        self.assertTrue(calls)
        self.assertEqual(set(calls), {debate_id})
        self.assertTrue(all(
            turn["debate_id"] == debate_id
            and turn["correlation_id"] == debate_id
            for turn in events[-1]["data"]["transcript"]
        ))

        second_events, _second_calls = self._run()
        self.assertNotEqual(
            debate_id,
            second_events[0]["data"]["debate_id"],
        )


if __name__ == "__main__":
    unittest.main()
