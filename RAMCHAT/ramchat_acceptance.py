#!/usr/bin/env python3
"""Truth-gated, repeatable acceptance check for the complete RAMCHAT council.

This script intentionally distinguishes infrastructure from participation.  A
binary, process, HTTP listener, model list, or Cockpit page is not enough: each
required AI must also have a recent attributable RAMCHAT post, while model
routes must remain callable.  It validates both named memory mappings before
considering the council usable.
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import roster_probe


ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "ramchat_acceptance.json"
REQUIRED_AI = (
    "deskclod",
    "claude-cli",
    "Codex",
    "Grok",
    "Gemini",
    "Qwen-CLI",
    "Qwen3-480B",
    "GPT-OSS 120B",
    "GLM-5.2",
    "Perplexity",
    "Nemotron",
)
MAPPINGS = (
    ("RAMCHAT_COUNCIL_V1", 16 * 1024 * 1024, b"RAMCHAT1", "transcript"),
    ("RAMCHAT_QUEUE_V1", 8 * 1024 * 1024, b"RAMQUEU1", "items"),
)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def validate_mapping(name: str, size: int, magic: bytes, list_key: str) -> dict[str, object]:
    try:
        with mmap.mmap(-1, size, tagname=name, access=mmap.ACCESS_READ) as mapping:
            actual_magic = mapping.read(8)
            payload_size = struct.unpack("<Q", mapping.read(8))[0]
            if actual_magic != magic:
                raise RuntimeError(f"bad magic {actual_magic!r}")
            if not 0 < payload_size <= size - 16:
                raise RuntimeError(f"invalid payload size {payload_size}")
            payload = json.loads(mapping.read(payload_size).decode("utf-8"))
        if payload.get("schema") != 1 or not isinstance(payload.get(list_key), list):
            raise RuntimeError("invalid JSON schema")
        return {
            "status": "PASS",
            "payload_bytes": payload_size,
            "records": len(payload[list_key]),
        }
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)}


def build_result() -> dict[str, object]:
    mappings = {
        name: validate_mapping(name, size, magic, list_key)
        for name, size, magic, list_key in MAPPINGS
    }
    roster = roster_probe.probe_all()
    participants = {
        name: roster.get(
            name,
            {"status": "missing", "detail": "not present in roster", "fails": 0},
        )
        for name in REQUIRED_AI
    }
    missing = [name for name, info in participants.items() if info.get("status") != "alive"]
    mapping_failures = [name for name, info in mappings.items() if info.get("status") != "PASS"]
    return {
        "schema": 1,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "PASS" if not missing and not mapping_failures else "FAIL",
        "required_ai": list(REQUIRED_AI),
        "participants": participants,
        "missing_or_unverified": missing,
        "mappings": mappings,
        "mapping_failures": mapping_failures,
        "truth_rule": "callable route plus recent attributable RAMCHAT participation; presence alone is insufficient",
    }


def write_result(payload: dict[str, object]) -> None:
    temporary = RESULT.with_name(RESULT.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, RESULT)


def post_result(payload: dict[str, object]) -> None:
    status = payload["status"]
    missing = ", ".join(payload["missing_or_unverified"]) or "none"
    message = (
        f"RAMCHAT ALL-AI ACCEPTANCE {status}: mappings="
        f"{len(payload['mappings']) - len(payload['mapping_failures'])}/{len(payload['mappings'])}; "
        f"participants={len(REQUIRED_AI) - len(payload['missing_or_unverified'])}/{len(REQUIRED_AI)}; "
        f"missing_or_unverified={missing}. Evidence: {RESULT}."
    )
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(
        [sys.executable, str(ROOT / "ramlink.py"), "post", "codex", message],
        cwd=ROOT,
        env=environment,
        check=True,
        timeout=30,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", action="store_true", help="post the concise result to RAMCHAT")
    args = parser.parse_args()
    payload = build_result()
    write_result(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.post:
        post_result(payload)
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
