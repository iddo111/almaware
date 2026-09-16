"""Focused tests for RAMCHAT's Codex JSONL acceptance gate."""

from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest


RAMCHAT = SourceFileLoader(
    "ramchat_for_test",
    str(Path(__file__).with_name("ramchat.pyw")),
).load_module()


class CodexAdapterTests(unittest.TestCase):
    def test_extracts_attributable_agent_message(self) -> None:
        output = "\n".join(
            [
                '{"type":"thread.started","thread_id":"test"}',
                '{"type":"item.completed","item":{"type":"reasoning","text":"hidden"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"שלום מהמועצה"}}',
                "Reading additional input from stdin...",
            ]
        )
        self.assertEqual(
            RAMCHAT.RamChat._extract_codex_answer(output),
            "שלום מהמועצה",
        )

    def test_rejects_logs_and_unattributed_text(self) -> None:
        output = "\n".join(
            [
                "server healthy",
                '{"type":"item.completed","item":{"type":"tool_output","text":"not a reply"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"   "}}',
            ]
        )
        self.assertEqual(RAMCHAT.RamChat._extract_codex_answer(output), "")

    def test_uses_last_completed_agent_message(self) -> None:
        output = "\n".join(
            [
                '{"type":"item.completed","item":{"type":"agent_message","text":"draft"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"final"}}',
            ]
        )
        self.assertEqual(RAMCHAT.RamChat._extract_codex_answer(output), "final")


if __name__ == "__main__":
    unittest.main()
