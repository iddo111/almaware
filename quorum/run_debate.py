# לזכרה של עלמה ז״ל
"""QUORUM · run_debate — headless CLI that drives the REAL shakla engine to a verdict.

Two modes, one engine (shakla.run_shakla is never re-implemented — only fed):

  live      : uses ai_clients as-is (needs config.ENABLED + >=2 installed CLIs/ollama).
  --simulate: injects a deterministic persona backend into ai_clients so the full
              שקלא-וטריא (positions -> קושיא/תירוץ/ראיה/דחייה -> מסקנה) runs OFFLINE.
              This makes the pipeline provable with zero API access.

Usage:
  python run_debate.py "האם מותר לשבור צום כדי להציל חיים?" --simulate --rounds 2
  python run_debate.py "..."                      # live (requires enable + models)

Prints the streamed transcript, then the aggregated verdict (מסקנה). stdlib only.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import config
import ai_clients as c
import shakla

try:  # Windows consoles default to cp1252; the debate is Hebrew-first.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# ── deterministic offline persona backend ────────────────────────────────────
_PERSONAS = {
    "sim:rambam":  "לדעתי ההכרעה נקבעת לפי הכלל 'וחי בהם' — פיקוח נפש דוחה, וזו עמדה עקרונית.",
    "sim:ramban":  "אני חולק: יש לשקול גם קדושת המעשה עצמו, לא רק התוצאה — הדין אינו תועלתני בלבד.",
    "sim:meiri":   "עמדת ביניים: הכלל תלוי בוודאות הסכנה; בספק-ספקא מקילים, בסכנה ודאית מצילים מיד.",
}
_SIM_MODELS = [{"id": mid, "provider": mid, "model": mid,
                "label": mid, "default": True} for mid in _PERSONAS]


def _sim_ask(prompt: str, provider: str, model: str = "", *, system: str = "",
             timeout: float = 0.0, correlation_id: str = "") -> c.Reply:
    """Deterministic Reply that respects the dialectic prompt shape. Never raises."""
    base = _PERSONAS.get(provider, "עמדה כללית בנושא.")
    if "מסקנה" in prompt or (system and "הפוסק המסכם" in system):
        txt = ("כולם מסכימים שיש ערך עליון לחיי אדם. "
               "המחלוקת: [sim:ramban] מדגיש קדושת המעשה מול [sim:rambam] התוצאה. "
               "העמדה החזקה ביותר היא [sim:meiri] — הכרעה לפי מידת ודאות הסכנה. "
               "מסקנה: פיקוח נפש ודאי דוחה; בספק — מכריעים לקולא לטובת הצלה.")
    elif "קושיא" in prompt:
        txt = (f"קושיא: הנחתך אינה מכסה מקרה גבול. תירוץ: {base} "
               "ראיה: מן הכלל המקובל בסוגיה. דחייה: כאן דעת בר-הפלוגתא נדחית בחלקה.")
    else:
        txt = base
    return c.Reply(True, text=txt, provider=provider, model=model or provider, elapsed=0.01)


def _install_simulation() -> None:
    os.environ["QUORUM_ENABLED"] = "1"          # open the master gate (offline is safe)
    c.ask = _sim_ask                            # astream() wraps ask() -> personas flow through
    c.detect_models = lambda: list(_SIM_MODELS)  # present the simulated council as "live"


async def _drive(topic: str, rounds: int, model_ids, simulate: bool) -> dict:
    if simulate:
        _install_simulation()
    final = {}
    async for ev in shakla.run_shakla(topic, model_ids=model_ids, num_rounds=rounds):
        e = ev["event"]; d = ev["data"]
        if e == "plan":
            print(f"\n=== QUORUM · שקלא-וטריא · {len(d['agents'])} minds · {d['rounds']} rounds ===")
        elif e == "status" and d.get("state") == "round-start":
            print(f"\n--- round {d.get('round')} · {d.get('label','')} ---")
        elif e == "status" and d.get("state") == "writing":
            print(f"\n[{d.get('model')}] ", end="")
        elif e == "delta":
            print(d.get("text", ""), end="")
        elif e == "error":
            print(f"\n!! error: {d.get('error')} — {d.get('note','')}", file=sys.stderr)
        elif e == "done":
            final = d
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description="Drive the QUORUM shakla debate to a verdict.")
    ap.add_argument("topic", help="the question to argue")
    ap.add_argument("--rounds", type=int, default=config.DEFAULT_ROUNDS)
    ap.add_argument("--simulate", action="store_true",
                    help="run offline with deterministic persona voices (no APIs)")
    ap.add_argument("--models", nargs="*", default=None,
                    help="explicit model ids (default: all detected)")
    a = ap.parse_args()

    ids = a.models
    if a.simulate and not ids:
        ids = [m["id"] for m in _SIM_MODELS]

    final = asyncio.run(_drive(a.topic, a.rounds, ids, a.simulate))

    print("\n\n=== מסקנה (verdict) ===")
    print(f"synth model : {final.get('synth_model','—')}")
    print(f"live        : {final.get('live')}   elapsed: {final.get('elapsed')}s")
    print(f"turns       : {len(final.get('transcript', []))}")
    print("\n" + (final.get("synthesis") or final.get("note") or "(no synthesis)"))
    return 0 if final.get("live") else 1


if __name__ == "__main__":
    raise SystemExit(main())
