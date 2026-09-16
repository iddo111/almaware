# לזכרה של עלמה ז״ל
"""QUORUM · judge · run_live_debate — drive a REAL debate and keep the transcript.

Deliberate, not incidental: QUORUM is born inert on purpose and that default is
not a bug to fix. This script does not touch config.ENABLED; it runs only if the
operator has already enabled QUORUM, and it says so and stops if not.

Seats are restricted to the callable CLIs (claude / grok / gemini) so that a
judge test puts ZERO inference load on the fleet. eran1 carries ERAN himself and
his live mic decoder, and eran3 carries the coder training — neither is a place
to run a debate for a demo.

    python run_live_debate.py "<topic>" out.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_clients as c          # noqa: E402
import config                   # noqa: E402
import shakla                   # noqa: E402

CLI_ONLY = ("claude", "grok", "gemini")     # no fleet, no local inference


async def main(topic: str, out_path: str, rounds: int = 2):
    if not config.is_enabled():
        print("QUORUM is inert (config.ENABLED False). Not enabling it here — "
              "that default is a safety property, not a bug. Enable deliberately "
              "with run-quorum.ps1 -Enable and re-run.")
        return 2
    live = [m["id"] for m in c.detect_models()]
    seats = [m for m in CLI_ONLY if m in live]
    print("live:", live)
    print("seats:", seats)
    if len(seats) < 2:
        print("need at least 2 callable CLI seats; got", seats)
        return 2

    done = {}
    async for ev in shakla.run_shakla(topic, model_ids=seats, num_rounds=rounds):
        kind = ev.get("event")
        d = ev.get("data", {})
        if kind == "status" and d.get("state") in ("round-start", "writing", "done"):
            print("  [%s] %s %s %s" % (d.get("state"), d.get("agent", ""),
                                       d.get("model", ""), d.get("label", "")),
                  flush=True)
        elif kind == "error":
            print("  ERROR", d.get("error"), d.get("note", "")[:200], flush=True)
        elif kind == "done":
            done = d
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1)
    print("turns:", len(done.get("transcript") or []), "-> ", out_path)
    return 0


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "האם מדד שמעולם לא סירב הוא מדד?"
    out = sys.argv[2] if len(sys.argv) > 2 else "live_debate.json"
    raise SystemExit(asyncio.run(main(topic, out)))
