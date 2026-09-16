"""curriculum.py — "the logic training from you," as data with ground truth.
Iddo, 2026-08-20: "שיקבל אימון לוגיקה ורמח״ל ושקלא וטריא ממך."

The logic engine (logic.py, reused from the worm, self-test ALL PASS) is not only a
checker — it is a GENERATOR of labelled problems. It builds a premise set and a goal,
then decides the goal by valid inference, and the decision IS the label. A model
trained on this is trained toward valid inference with a teacher that cannot lie,
instead of on hand-written examples that can carry a mistake.

Emits JSONL: {premises:[...], goal:str, label:0|1, form:str}. Deterministic per seed
(no RNG that would break resume — index-driven), so a run is reproducible.
"""
from __future__ import annotations

import json
import pathlib

from .logic import Implies, Logic, Prop

SUBJECTS = ["אבן", "חול", "מים", "עץ", "ברזל", "זהב", "כלב", "ציפור", "דג", "אדם"]
PREDS = ["מטמא", "כבד", "חי", "צף", "בוער", "יקר", "רץ", "עף", "שוחה", "מדבר"]


def _modus_ponens(i: int) -> dict:
    """A→B, B→C, ...; A given; is the last consequent proved? Half the items break
    one link so the label is genuinely 0 sometimes (a teacher that always says yes
    teaches nothing — the 48.2% 'one fixed answer per form' scar)."""
    n = 3 + (i % 3)                                   # chain length 3..5
    subj = SUBJECTS[i % len(SUBJECTS)]
    preds = [PREDS[(i + k) % len(PREDS)] for k in range(n + 1)]
    props = [Prop(subj, p) for p in preds]
    premises = [props[0]]                             # A is given
    links = [Implies(props[k], props[k + 1]) for k in range(n)]
    broken = (i % 2 == 1)
    if broken:
        del links[n // 2]                             # snap one link -> unprovable
    premises += links
    goal = props[n]
    proved = Logic(premises).proves(goal)
    return {"form": "modus_ponens", "premises": [str(p) for p in premises],
            "goal": str(goal), "label": int(proved)}


def _modus_tollens(i: int) -> dict:
    """A→B, not-B; therefore not-A. Break by giving B instead of not-B."""
    subj = SUBJECTS[(i + 3) % len(SUBJECTS)]
    a, b = Prop(subj, PREDS[i % len(PREDS)]), Prop(subj, PREDS[(i + 1) % len(PREDS)])
    valid = (i % 2 == 0)
    premises = [Implies(a, b), (~b if valid else b)]
    goal = ~a
    return {"form": "modus_tollens", "premises": [str(p) for p in premises],
            "goal": str(goal), "label": int(Logic(premises).proves(goal))}


GENERATORS = [_modus_ponens, _modus_tollens]


def generate(n: int, out: pathlib.Path) -> dict:
    rows = [GENERATORS[i % len(GENERATORS)](i) for i in range(n)]
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                   encoding="utf-8")
    pos = sum(r["label"] for r in rows)
    return {"n": n, "positive": pos, "negative": n - pos,
            "balance": round(pos / n, 2)}


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parent.parent / "logic_curriculum.jsonl"
    stats = generate(400, out)
    print(f"wrote {out.name}: {stats}")
    for line in out.read_text(encoding="utf-8").splitlines()[:3]:
        print("  ", line[:120])
