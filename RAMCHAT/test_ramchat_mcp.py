from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ramchat_mcp


class RamchatMcpTests(unittest.TestCase):
    def test_initialize_and_tool_list_over_real_stdio(self) -> None:
        messages = "\n".join((
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            "",
        ))
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("ramchat_mcp.py"))],
            input=messages,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        )
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "ramchat")
        self.assertEqual(
            {tool["name"] for tool in replies[1]["result"]["tools"]},
            {"ramchat_read", "ramchat_post", "ramchat_queue", "ramchat_status"},
        )

    def test_read_is_bounded_and_post_is_always_deskclod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            state.write_text(json.dumps([{"who": "x", "text": str(i)} for i in range(5)]), encoding="utf-8")
            with mock.patch.object(ramchat_mcp, "STATE", state):
                reply = ramchat_mcp.call_tool("ramchat_read", {"tail": 2})
            payload = json.loads(reply["content"][0]["text"])
            self.assertEqual([m["text"] for m in payload["messages"]], ["3", "4"])

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            receipt = Path(directory) / "receipt.json"
            state.write_text(json.dumps([{"who": "deskclod", "text": "hello", "at": "12:00"}]), encoding="utf-8")
            completed = mock.Mock(returncode=0, stdout="posted", stderr="")
            fake_chain = [{"pid": 1, "executable": r"C:\Program Files\WindowsApps\Claude_x\app\Claude.exe"}]
            with (
                mock.patch.object(ramchat_mcp, "STATE", state),
                mock.patch.object(ramchat_mcp, "RECEIPT", receipt),
                mock.patch.object(ramchat_mcp, "process_chain", return_value=fake_chain),
                mock.patch.object(ramchat_mcp.subprocess, "run", return_value=completed) as run,
            ):
                reply = ramchat_mcp.call_tool("ramchat_post", {"text": "hello"})
            self.assertFalse(reply["isError"])
            self.assertEqual(run.call_args.args[0][3:5], ["deskclod", "hello"])
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(saved["author"], "deskclod")
            self.assertEqual(saved["text_sha256"], hashlib.sha256(b"hello").hexdigest())
            self.assertEqual(saved["process_chain"], fake_chain)


if __name__ == "__main__":
    unittest.main()
