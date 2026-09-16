#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE THIRD CONTROL: the rules engine, measured on exactly the same rows.

ALMA-GUARD-IMMEDIATE (the sibling project, `claude-cli-FABLE-guard`) shipped
`D:\\CLAUDE\\wa-chat-agent\\shield.py` on 2026-09-11, with a hand-written pattern
bank - `detect_injection()`. That is the thing Iddo said the network is NOT
("זה לא רעיון, זה פרויקט חדש - מודל רשת נוירונים, לא קוד"), so it is the most
interesting control of the three: it says what the learned model has to beat to
have been worth building.

    python -m alma_guard.compare_rules

READ THE RESULT WITH THIS CAVEAT, WHICH CUTS AGAINST ALMA-GUARD
---------------------------------------------------------------
The rules engine and `seed_corpus.py` were written hours apart, by two agents,
from the same public literature. So on the `seed` rows the pattern bank is being
tested on nearly the phrasings it was written for - and it will look better than
it is. The rows where the comparison is FAIR are `gate`, `ramchat`, and above all
`fresh.jsonl`, which neither side wrote. Judge on those.

This module only READS shield.py. It never modifies it (another agent owns it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma_guard import data as D                                    # noqa: E402
from alma_guard.train import report                                 # noqa: E402

SHIELD_DIR = Path(r"D:\CLAUDE\wa-chat-agent")
HERE = Path(__file__).resolve().parent


def load_shield():
    if not (SHIELD_DIR / "shield.py").exists():
        raise SystemExit(f"shield.py not found in {SHIELD_DIR}")
    sys.path.insert(0, str(SHIELD_DIR))
    import shield                                                    # noqa: E402
    return shield


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    shield = load_shield()
    out = {}
    for name, path in (("dataset", None), ("fresh", HERE / "fresh.jsonl")):
        rows = D.load(path)
        truth = [D.binarise(r["label"]) for r in rows]
        pred = [D.ATTACK if shield.detect_injection(r["text"]) else D.BENIGN
                for r in rows]
        out[name] = report(f"RULES ENGINE (shield.detect_injection) on {name}",
                           rows, truth, pred, list(range(len(rows))), "binary")
        misses = [(r, t) for r, t, p in zip(rows, truth, pred)
                  if t == D.ATTACK and p == D.BENIGN]
        if misses and name == "fresh":
            print("  attacks the rules engine did NOT flag:")
            for r, _ in misses:
                print(f"    [{r['source']}] {r['text'][:88]}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
