"""KESHEV 2 fleet harness — the 4D worker crew client (build tool, not runtime).

Talks OpenAI-style to the ONE router at http://<lan-ip>:8010 (verified
live 2026-08-17). Four workers: qwen3-coder-next-fp8 (fast coder),
glm-4.7-flash, nemotron-3-super, gpt-oss-120b. nemotron/gpt-oss need
max_tokens >= 900 or they return empty reasoning stubs.

King-rules protocol (Iddo, dictated 2026-08-17): workers advise and draft,
the lead rules every decision, every ruling lands in DECISIONS.md, every
worker contribution in WORKERS-LOG.md. This module is the transport only.

stdlib only. Never imported by k2/ runtime code (build tool -> listed in
ALLOWED_UNWIRED with that reason).
"""
from __future__ import annotations

import concurrent.futures
import json
import urllib.error
import urllib.request

ROUTER = "http://<lan-ip>:8010/v1/chat/completions"

WORKERS = (
    "qwen3-coder-next-fp8",
    "glm-4.7-flash",
    "nemotron-3-super",
    "gpt-oss-120b",
)

# nemotron / gpt-oss burn tokens on reasoning before content appears.
_MIN_TOKENS = {"nemotron-3-super": 1600, "gpt-oss-120b": 1600}


def ask(model: str, prompt: str, system: str = "", max_tokens: int = 900,
        temperature: float = 0.2, timeout: float = 180.0) -> str:
    """One completion from one worker. Raises on transport failure —
    the caller decides whether a dead worker blocks the build (it never
    does: king-rules protocol says build solo and note it)."""
    max_tokens = max(max_tokens, _MIN_TOKENS.get(model, 0))
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(
        ROUTER, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"] or ""


def ask_all(prompt: str, system: str = "", max_tokens: int = 900,
            timeout: float = 180.0) -> dict[str, str]:
    """The council fan-out: same question to all four workers in parallel.
    A worker that errors contributes its error string prefixed WORKER-DOWN
    instead of silently vanishing (a missing voice must be visible)."""
    out: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(WORKERS)) as ex:
        futs = {
            ex.submit(ask, m, prompt, system, max_tokens, 0.2, timeout): m
            for m in WORKERS
        }
        for fut in concurrent.futures.as_completed(futs):
            model = futs[fut]
            try:
                out[model] = fut.result()
            except Exception as exc:  # noqa: BLE001 — recorded, never silent
                out[model] = f"WORKER-DOWN {type(exc).__name__}: {exc}"
    return out


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Say READY and your model name."
    for m, a in ask_all(q, max_tokens=100).items():
        print(f"=== {m} ===\n{a[:500]}\n")
