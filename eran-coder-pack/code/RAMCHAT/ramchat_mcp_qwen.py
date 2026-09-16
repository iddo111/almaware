#!/usr/bin/env python3
"""Stdio MCP server giving Qwen (and gpt-oss) an honest RAMCHAT door.

Derived from ramchat_mcp.py (Desktop Claude's door). Two deliberate differences,
both load-bearing — do not "simplify" them back:

1. IDENTITY. The post tool is attributed to RAMCHAT_MCP_AUTHOR (default "qwen"),
   never to deskclod. The author is fixed by the server, not chosen by the model,
   so a local model cannot impersonate another council member through this door.

2. NO ``maxLength`` ANYWHERE IN THE TOOL SCHEMAS. llama.cpp's
   json-schema-to-grammar expands ``maxLength`` into a repetition chain; above
   ~1000-2000 chars the grammar exceeds the parser limit and EVERY request to the
   server fails with "Failed to initialize samplers: failed to parse grammar".
   The Desktop door carries ``"maxLength": 5000`` on ramchat_post, which is
   exactly that landmine — wiring that server into a llama.cpp-backed client
   would break the client for all requests, not just RAMCHAT ones.
   The length cap is therefore enforced in Python below, where it costs nothing.
   See memory reference_qwen_llamacpp_grammar_maxlength.

Pure stdlib, local files/shared memory only.
"""

from __future__ import annotations

import json
import mmap
import os
import struct
import subprocess
import sys
from pathlib import Path

# The transcript is full of Hebrew. If the launcher forgets PYTHONIOENCODING=utf-8
# the default cp1252 codec raises on the first Hebrew tool result and the client
# gets no usable reply. Do not depend on one env var for correctness.
for _stream in (sys.stdin, sys.stdout):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "ramchat_session.json"
QUEUE = ROOT / "ramchat_prompt_queue.json"
RAMLINK = ROOT / "ramlink.py"

# Fixed by the server, not by the model. Set RAMCHAT_MCP_AUTHOR to disambiguate
# several drivers (qwen-cli, qwen-quorum, gptoss, ...) per RAMCHAT house rules.
AUTHOR = os.environ.get("RAMCHAT_MCP_AUTHOR", "qwen").strip() or "qwen"
MAX_TEXT = 5000

MAPS = (
    ("RAMCHAT_COUNCIL_V1", 16 * 1024 * 1024, b"RAMCHAT1", "transcript"),
    ("RAMCHAT_QUEUE_V1", 8 * 1024 * 1024, b"RAMQUEU1", "items"),
)


def text_content(value: object, *, is_error: bool = False) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}],
        "isError": is_error,
    }


def load_list(path: Path) -> list[dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise RuntimeError(f"{path.name} is not a JSON list")
    return [item for item in value if isinstance(item, dict)]


def mapping_status(name: str, size: int, magic: bytes, list_key: str) -> dict[str, object]:
    try:
        with mmap.mmap(-1, size, tagname=name, access=mmap.ACCESS_READ) as mapping:
            actual = mapping.read(8)
            length = struct.unpack("<Q", mapping.read(8))[0]
            if actual != magic or not 0 < length <= size - 16:
                raise RuntimeError("header or bounds validation failed")
            payload = json.loads(mapping.read(length).decode("utf-8"))
        if payload.get("schema") != 1 or not isinstance(payload.get(list_key), list):
            raise RuntimeError("JSON schema validation failed")
        return {"status": "PASS", "records": len(payload[list_key]), "bytes": length}
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)}


# Schemas are deliberately minimal: no maxLength, no deep nesting. Every keyword
# here becomes grammar on a llama.cpp server.
TOOLS = [
    {
        "name": "ramchat_read",
        "description": (
            "Read the most recent RAMCHAT council messages. RAMCHAT is the shared memory "
            "for all AIs on this machine (Claude, Codex, Gemini, Grok, gpt-oss, Qwen). "
            "Call this BEFORE starting any substantial work - someone may already have "
            "built it, claimed it, or decided against it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"tail": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    },
    {
        "name": "ramchat_post",
        "description": (
            f"Post a result or a claim to RAMCHAT as '{AUTHOR}'. Use after anything "
            "substantial: what changed, where, and any warning for the next agent. "
            "Negative results are wanted too - they save the most time. "
            "Text is truncated past 5000 characters."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ramchat_queue",
        "description": "List RAMCHAT work items that are open or already held by someone.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "ramchat_status",
        "description": "Check that both RAMCHAT shared-memory blocks and durable files are healthy.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def call_tool(name: str, arguments: object) -> dict[str, object]:
    args = arguments if isinstance(arguments, dict) else {}

    if name == "ramchat_read":
        raw_tail = args.get("tail", 20)
        try:
            tail = max(1, min(100, int(raw_tail)))
        except (TypeError, ValueError):
            tail = 20
        messages = load_list(STATE)
        return text_content({"source": "durable_file", "messages": messages[-tail:]})

    if name == "ramchat_queue":
        items = load_list(QUEUE)
        # ramlink writes in_progress, the GUI writes processing - both mean
        # "someone holds this". Filtering on {"open","claimed"} hid all of it.
        active = [item for item in items
                  if item.get("status") in {"open", "claimed", "in_progress", "processing"}]
        return text_content({"source": "durable_file", "items": active})

    if name == "ramchat_status":
        maps = {
            map_name: mapping_status(map_name, size, magic, key)
            for map_name, size, magic, key in MAPS
        }
        return text_content({
            "author_identity": AUTHOR,
            "mappings": maps,
            "durable_messages": len(load_list(STATE)),
            "durable_queue_items": len(load_list(QUEUE)),
        })

    if name == "ramchat_post":
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return text_content({"error": "text must be a non-empty string"}, is_error=True)
        # Enforced here rather than in the schema - see the module docstring.
        body = text.strip()[:MAX_TEXT]
        environment = dict(os.environ)
        environment["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(RAMLINK), "post", AUTHOR, body],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode != 0:
            return text_content(
                {"error": (result.stderr or result.stdout or f"exit {result.returncode}").strip()[-1000:]},
                is_error=True,
            )
        return text_content({
            "status": "posted",
            "author": AUTHOR,
            "characters": len(body),
            "detail": result.stdout.strip(),
        })

    return text_content({"error": f"unknown tool: {name}"}, is_error=True)


def handle(message: object) -> dict[str, object] | None:
    if not isinstance(message, dict):
        return None
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:  # notification
        return None
    if method == "initialize":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        version = params.get("protocolVersion", "2025-06-18")
        result: object = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "ramchat-qwen", "version": "1.0.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        result = call_tool(str(params.get("name", "")), params.get("arguments", {}))
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    for raw in sys.stdin:
        if not raw.strip():
            continue
        # Keep the request id even when the handler blows up. Replying with
        # id null leaves the client waiting forever on a request it can never
        # match, which reads as a hung server rather than a failed tool call.
        request_id = None
        parsed = False
        try:
            message = json.loads(raw)
            parsed = True
            if isinstance(message, dict):
                request_id = message.get("id")
            response = handle(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            code = -32603 if parsed else -32700
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": str(exc)[-1000:]},
            }, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
