#!/usr/bin/env python3
"""Safe continuous project-review jobs for the local Qwen and Gemma workers.

Each invocation sends bounded, read-only project context to the two models and
writes their recommendations as a timestamped JSON report.  It never edits a
project, starts training, restarts a service, or contacts external services.
"""

from __future__ import annotations

import base64
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(r"D:\CLAUDE")
OUT = ROOT / "fleet" / "worker_reports"
OUT.mkdir(parents=True, exist_ok=True)


def read_context(paths: list[Path], max_chars: int = 18_000) -> str:
    chunks: list[str] = []
    remaining = max_chars
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            text = f"[unreadable: {exc}]"
        piece = f"\n--- {path.relative_to(ROOT)} ---\n{text[:remaining]}"
        chunks.append(piece)
        remaining -= len(piece)
        if remaining <= 0:
            break
    return "".join(chunks)


def remote_json(target: str, endpoint: str, payload: dict, timeout: int) -> dict:
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    remote = (
        f"echo {encoded} | base64 -d | "
        f"curl -sS --max-time {timeout} -H 'Content-Type: application/json' "
        f"--data-binary @- {endpoint}"
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", target, remote],
        text=True, capture_output=True, encoding="utf-8", errors="replace",
        timeout=timeout + 20,
    )
    if result.returncode:
        return {"ok": False, "error": result.stderr.strip() or result.stdout.strip()}
    try:
        return {"ok": True, "response": json.loads(result.stdout)}
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid JSON", "raw": result.stdout[-2000:]}


def main() -> int:
    eran = read_context([
        ROOT / "eran-live" / "train.py",
        ROOT / "eran-live" / "supervisor.py",
        ROOT / "eran-live" / "config.json",
    ])
    mic = read_context([
        ROOT / "alma-mic-release" / "config.py",
        ROOT / "alma-mic-release" / "vad.py",
        ROOT / "alma-mic-release" / "stt.py",
    ])
    qwen_prompt = (
        "You are the local Qwen worker reviewing the Eran project. Read the supplied "
        "code only. Return in Hebrew: (1) the one highest-impact technical risk, "
        "(2) one small, reversible next step, (3) evidence by filename. Do not invent "
        "tests or claim execution.\n" + eran
    )
    gemma_prompt = (
        "You are the local Gemma worker reviewing the ALMA Mic project. Read the supplied "
        "code only. Return a concise Hebrew engineering note: one likely false-positive "
        "risk for cough/non-speech, one safe measurement to collect, and filenames that "
        "support it. Do not suggest muting the microphone or modifying code.\n" + mic
    )
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_project_review",
        "qwen": remote_json(
            "eran1@<lan-ip>", "http://127.0.0.1:8081/v1/chat/completions",
            {"model": "qwen3-coder-480b-q4km", "messages": [{"role": "user", "content": qwen_prompt}],
             "max_tokens": 180, "temperature": 0.2}, 180,
        ),
        "gemma": remote_json(
            "eran4@<lan-ip>", "http://127.0.0.1:8084/completion",
            {"prompt": gemma_prompt, "n_predict": 120, "temperature": 0.2, "top_p": 0.9, "seed": 42}, 240,
        ),
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT / f"project_review_{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0 if report["qwen"]["ok"] and report["gemma"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
