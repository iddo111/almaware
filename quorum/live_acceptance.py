"""Harmless, bounded live-provider acceptance for Quorum.

It first requires an exact nonce from each requested provider.  Only providers
that pass that real call may enter the one-round debate.  Output is metadata and
hashes, never the provider prose or credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import hashlib
import json
import os
from typing import Any

import ai_clients
import config
import shakla


def _probe(provider: str, timeout: float) -> dict[str, Any]:
    nonce = f"QUORUM_{provider.upper().replace(':', '_')}_OK_20260720"
    reply = ai_clients.ask(
        f"Reply with exactly {nonce} and nothing else.",
        provider,
        timeout=timeout,
    )
    normalized = reply.text.strip()
    return {
        "provider": provider,
        "call_ok": bool(reply),
        "exact_nonce": normalized == nonce,
        "error": reply.error.value,
        "note": reply.note[:200],
        "elapsed_seconds": reply.elapsed,
        "response_chars": len(normalized),
        "response_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else "",
    }


async def _debate(providers: list[str]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    async for event in shakla.run_shakla(
        "For a harmless deterministic deployment check, which is stronger: verifying a file by size only, or by size plus SHA-256, and why?",
        model_ids=providers,
        num_rounds=1,
    ):
        events.append(event)
    done = events[-1]["data"] if events else {}
    errors = [event["data"] for event in events if event["event"] == "error"]
    return {
        "live": bool(done.get("live")),
        "providers": providers,
        "synth_model": done.get("synth_model", ""),
        "turns": len(done.get("transcript", [])),
        "synthesis_chars": len(done.get("synthesis", "")),
        "synthesis_sha256": hashlib.sha256(done.get("synthesis", "").encode("utf-8")).hexdigest()
        if done.get("synthesis") else "",
        "elapsed_seconds": done.get("elapsed"),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", nargs="+", default=["claude", "grok", "gemini"])
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    os.environ["QUORUM_ENABLED"] = "1"
    # --timeout also raises the debate/synthesis budgets: slow local models
    # (~8 tok/s) need whole minutes per turn, and shakla reads these at call time.
    config.PER_TURN_TIMEOUT = max(config.PER_TURN_TIMEOUT, args.timeout)
    config.SYNTH_TIMEOUT = max(config.SYNTH_TIMEOUT, args.timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.providers)) as pool:
        probes = list(pool.map(lambda p: _probe(p, args.timeout), args.providers))
    live = [item["provider"] for item in probes if item["call_ok"] and item["exact_nonce"]]
    debate = asyncio.run(_debate(live)) if len(live) >= 2 else {
        "live": False,
        "providers": live,
        "reason": "fewer than two providers passed exact live generation",
    }
    result = {"probes": probes, "debate": debate, "pass": bool(debate.get("live"))}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
