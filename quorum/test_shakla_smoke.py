# לזכרה של עלמה ז״ל
"""Smoke test: the REAL shakla engine runs end-to-end offline and yields a verdict.

Proves the full dialectic pipeline (plan -> positions -> קושיא/תירוץ rounds -> מסקנה)
without any live API, by driving run_debate's deterministic simulation. stdlib only.
Run:  python test_shakla_smoke.py
"""
from __future__ import annotations

import asyncio

import run_debate as rd
import shakla


def _run(topic, rounds=2):
    rd._install_simulation()
    ids = [m["id"] for m in rd._SIM_MODELS]
    events = []

    async def go():
        async for ev in shakla.run_shakla(topic, model_ids=ids, num_rounds=rounds):
            events.append(ev)
    asyncio.run(go())
    return events


def main() -> int:
    evs = _run("האם מותר לשבור צום כדי להציל חיים?", rounds=2)
    kinds = [e["event"] for e in evs]
    done = evs[-1]["data"]

    checks = {
        "has plan": "plan" in kinds,
        ">=2 agents in plan": len(next(e for e in evs if e["event"] == "plan")["data"]["agents"]) >= 2,
        "streamed deltas": kinds.count("delta") > 0,
        "no disabled/backend error": not any(
            e["event"] == "error" and e["data"].get("error") in ("disabled", "backend") for e in evs),
        "ends with done": kinds[-1] == "done",
        "verdict is live": done.get("live") is True,
        "synthesis non-empty": bool(done.get("synthesis", "").strip()),
        "synthesis cites a voice": "[sim:" in done.get("synthesis", ""),
        "transcript has all rounds": {t["round"] for t in done.get("transcript", [])} >= {0, 1, 2},
        "synth model chosen": bool(done.get("synth_model")),
    }

    ok = all(checks.values())
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print(f"\n  synth_model={done.get('synth_model')}  turns={len(done.get('transcript', []))}"
          f"  elapsed={done.get('elapsed')}s")
    print(f"  verdict: {done.get('synthesis','')[:90]}...")
    print(f"\n{'ALL PASS' if ok else 'FAILURES PRESENT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
