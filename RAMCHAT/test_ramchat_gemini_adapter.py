"""Focused tests for RAMCHAT's Antigravity Gemini adapter."""

from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest


RAMCHAT = SourceFileLoader(
    "ramchat_gemini_for_test",
    str(Path(__file__).with_name("ramchat.pyw")),
).load_module()


class GeminiAdapterTests(unittest.TestCase):
    def test_antigravity_is_preferred_when_installed(self) -> None:
        if RAMCHAT.AGY:
            self.assertEqual(RAMCHAT.GEMINI_RUNNER, RAMCHAT.AGY)

    def test_product_tip_is_removed(self) -> None:
        output = "answer\n\n**Gemini Tip:** use /schedule"
        self.assertEqual(RAMCHAT.RamChat._clean_gemini_output(output), "answer")

    def test_product_tip_with_emoji_and_rule_is_removed(self) -> None:
        output = "answer\n\n***\n**Gemini Tip 💡**\nnoisy product advice"
        self.assertEqual(RAMCHAT.RamChat._clean_gemini_output(output), "answer")

    def test_product_tip_with_leading_emoji_is_removed(self) -> None:
        output = "answer\n\n💡 **Gemini Tip:** noisy product advice"
        self.assertEqual(RAMCHAT.RamChat._clean_gemini_output(output), "answer")

    def test_normal_output_is_preserved(self) -> None:
        self.assertEqual(
            RAMCHAT.RamChat._clean_gemini_output("  תשובה אמיתית  "),
            "תשובה אמיתית",
        )

    def test_gui_acceptance_inbox_is_gemini_nonce_only(self) -> None:
        value = {
            "schema": 1,
            "request_id": "gui-acceptance_1234",
            "provider": "Gemini",
            "text": "Reply exactly: GEMINI_GUI_NONCE_1234",
        }
        self.assertEqual(
            RAMCHAT.RamChat._validate_gui_acceptance(value),
            ("Gemini", value["text"], value["request_id"]),
        )
        for bad in (
            {**value, "provider": "Codex"},
            {**value, "text": "Do arbitrary work"},
            {**value, "request_id": "../escape"},
        ):
            with self.assertRaises(ValueError):
                RAMCHAT.RamChat._validate_gui_acceptance(bad)


if __name__ == "__main__":
    unittest.main()
