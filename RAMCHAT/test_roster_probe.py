from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import roster_probe


class RosterEvidenceTests(unittest.TestCase):
    def test_desktop_claude_rejects_non_desktop_output(self) -> None:
        completed = mock.Mock(returncode=0, stdout="")
        with mock.patch.object(roster_probe.subprocess, "run", return_value=completed) as run:
            self.assertFalse(roster_probe.desktop_claude_running())
        self.assertIn("WindowsApps", run.call_args.args[0][-1])

    def test_message_age_wraps_across_midnight(self) -> None:
        now = datetime(2026, 8, 8, 0, 3)
        self.assertEqual(roster_probe._message_age_minutes("23:58", now), 5)

    def test_recent_post_uses_record_timestamp_not_file_mtime(self) -> None:
        now = datetime.now()
        old = (now - timedelta(hours=4)).strftime("%H:%M")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            state.write_text(
                json.dumps([{"who": "Codex", "text": "JOINED RAMCHAT X", "at": old}]),
                encoding="utf-8",
            )
            with mock.patch.object(roster_probe, "STATE", state):
                self.assertFalse(
                    roster_probe.recent_transcript_post(
                        "Codex", minutes=120, markers=("joined", "ramchat")
                    )
                )

    def test_recent_post_requires_attribution_and_all_markers(self) -> None:
        now = datetime.now().strftime("%H:%M")
        records = [
            {"who": "someone", "text": "JOINED RAMCHAT N", "at": now},
            {"who": "deskclod", "text": "RAMCHAT N", "at": now},
            {"who": "deskclod", "text": "Desktop Claude JOINED RAMCHAT N", "at": now},
        ]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            state.write_text(json.dumps(records), encoding="utf-8")
            with mock.patch.object(roster_probe, "STATE", state):
                self.assertTrue(
                    roster_probe.recent_transcript_post(
                        ("deskclod", "clod"), markers=("joined", "ramchat")
                    )
                )
                self.assertFalse(
                    roster_probe.recent_transcript_post(
                        "someone-else", markers=("joined", "ramchat")
                    )
                )

    def test_desktop_attestation_requires_matching_post_and_packaged_parent(self) -> None:
        now = datetime.now().astimezone()
        text = "Desktop Claude JOINED RAMCHAT DESKCLOD_TEST"
        receipt_value = {
            "schema": 1,
            "issued_at": now.isoformat(timespec="seconds"),
            "author": "deskclod",
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "process_chain": [{
                "pid": 10,
                "executable": r"C:\Program Files\WindowsApps\Claude_1.0_x64__x\app\Claude.exe",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            receipt = Path(directory) / "receipt.json"
            state.write_text(json.dumps([{
                "who": "deskclod", "text": text, "at": now.strftime("%H:%M")
            }]), encoding="utf-8")
            receipt.write_text(json.dumps(receipt_value), encoding="utf-8")
            with (
                mock.patch.object(roster_probe, "STATE", state),
                mock.patch.object(roster_probe, "DESKCLOD_RECEIPT", receipt),
            ):
                self.assertTrue(roster_probe.attested_desktop_post())
                receipt_value["process_chain"] = [{"pid": 10, "executable": r"C:\Python\python.exe"}]
                receipt.write_text(json.dumps(receipt_value), encoding="utf-8")
                self.assertFalse(roster_probe.attested_desktop_post())


if __name__ == "__main__":
    unittest.main()
