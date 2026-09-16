#!/usr/bin/env python3
"""Minimal stdio MCP server giving Claude Desktop an honest RAMCHAT door.

Pure stdlib, local files/shared memory only.  The post tool is intentionally
attributed to ``deskclod`` so the Desktop client cannot impersonate another
council member through this server.
"""

from __future__ import annotations

import hashlib
import json
import mmap
import os
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


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
RECEIPT = ROOT / "ramchat_deskclod_receipt.json"
CLIENT_INFO: dict[str, str] = {}
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


def process_chain(limit: int = 8) -> list[dict[str, object]]:
    """Capture the launching process chain for an auditable Desktop receipt."""
    script = f"""
$currentPid = {os.getpid()}
$items = @()
for ($i = 0; $i -lt {limit} -and $currentPid -gt 0; $i++) {{
  $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$currentPid\"
  if (-not $p) {{ break }}
  $items += [pscustomobject]@{{
    pid = [int]$p.ProcessId
    parent_pid = [int]$p.ParentProcessId
    name = [string]$p.Name
    executable = [string]$p.ExecutablePath
  }}
  $currentPid = [int]$p.ParentProcessId
}}
$items | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return [{"pid": os.getpid(), "error": (result.stderr or "process query failed").strip()[-500:]}]
    value = json.loads(result.stdout)
    return value if isinstance(value, list) else [value]


def write_receipt(text: str) -> dict[str, object]:
    messages = load_list(STATE)
    matching = next(
        (
            item for item in reversed(messages)
            if item.get("who") == "deskclod" and item.get("text") == text
        ),
        None,
    )
    receipt: dict[str, object] = {
        "schema": 1,
        "issued_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "author": "deskclod",
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "message_at": matching.get("at") if matching else None,
        "server_pid": os.getpid(),
        "client_info": dict(CLIENT_INFO),
        "process_chain": process_chain(),
    }
    temporary = RECEIPT.with_name(RECEIPT.name + ".tmp")
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, RECEIPT)
    return receipt


TOOLS = [
    {
        "name": "ramchat_read",
        "description": "Read recent durable RAMCHAT messages before starting work.",
        "inputSchema": {
            "type": "object",
            "properties": {"tail": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    },
    {
        "name": "ramchat_post",
        "description": "Post a substantial result to RAMCHAT as Desktop Claude (deskclod).",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 5000}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ramchat_queue",
        "description": "List currently open or claimed RAMCHAT work items.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "ramchat_status",
        "description": "Validate both named RAMCHAT mappings and durable file counts.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def call_tool(name: str, arguments: object) -> dict[str, object]:
    args = arguments if isinstance(arguments, dict) else {}
    if name == "ramchat_read":
        tail = max(1, min(100, int(args.get("tail", 20))))
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
            "mappings": maps,
            "durable_messages": len(load_list(STATE)),
            "durable_queue_items": len(load_list(QUEUE)),
        })
    if name == "ramchat_post":
        text = args.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            return text_content({"error": "text must be 1..5000 characters"}, is_error=True)
        environment = dict(os.environ)
        environment["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(RAMLINK), "post", "deskclod", text.strip()],
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
        receipt = write_receipt(text.strip())
        return text_content({
            "status": "posted",
            "author": "deskclod",
            "detail": result.stdout.strip(),
            "receipt": receipt,
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
        client = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        CLIENT_INFO.clear()
        for key in ("name", "version"):
            if isinstance(client.get(key), str):
                CLIENT_INFO[key] = client[key][:200]
        result: object = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "ramchat", "version": "1.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        result = call_tool(str(params.get("name", "")), params.get("arguments", {}))
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
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
