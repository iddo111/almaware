#!/usr/bin/env python3
"""Submit a restricted exact-marker probe through the live RAMCHAT GUI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUEST = ROOT / "ramchat_gui_acceptance_request.json"
RECEIPT = ROOT / "ramchat_gui_acceptance_receipt.json"
SESSION = ROOT / "ramchat_session.json"
QUEUE = ROOT / "ramchat_prompt_queue.json"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_list(path: Path) -> list[dict[str, object]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if not args.nonce.replace("_", "").replace("-", "").replace(":", "").isalnum():
        raise SystemExit("nonce must contain only letters, digits, underscore, hyphen, or colon")
    request_id = "gui-" + datetime.now().strftime("%Y%m%dT%H%M%S%f")
    prompt = f"Reply exactly: {args.nonce}"
    atomic_json(REQUEST, {
        "schema": 1,
        "request_id": request_id,
        "provider": "Gemini",
        "text": prompt,
    })
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        messages = load_list(SESSION)
        queues = load_list(QUEUE)
        user_seen = any(m.get("who") == "עידו" and m.get("text") == prompt for m in messages)
        answer = next(
            (
                str(m.get("text", "")).strip()
                for m in reversed(messages)
                if m.get("who") == "Gemini" and args.nonce in str(m.get("text", ""))
            ),
            "",
        )
        queue_item = next(
            (
                item for item in reversed(queues)
                if item.get("targets") == ["Gemini"] and args.nonce in str(item.get("prompt", ""))
            ),
            {},
        )
        if user_seen and answer == args.nonce and queue_item.get("status") == "completed":
            receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
            result = {
                "status": "PASS",
                "request_id": request_id,
                "provider": "Gemini",
                "nonce": args.nonce,
                "gui_receipt": receipt,
                "queue_id": queue_item.get("id"),
                "queue_status": queue_item.get("status"),
                "answer": answer,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        time.sleep(1)
    print(json.dumps({
        "status": "FAIL",
        "request_id": request_id,
        "provider": "Gemini",
        "nonce": args.nonce,
        "error": "timed out waiting for attributable GUI response",
    }, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
