# לזכרה של עלמה ז״ל
"""QUORUM · judge · cli — one door in, one door out.

    python cli.py case cases/kropotkin-mutual-aid.json  [--sheet NAME]
    python cli.py debate live_debate.json               [--sheet NAME]
    python cli.py --help

`case` judges a hand-built case file (premises, קושיות, evidence grades).
`debate` judges QUORUM's own `done` payload straight off a finished שקלא וטריא.
Both go through exactly one ruling path, so a verdict never depends on which
door it came through. --sheet also renders the PDF + JPEG verdict sheet.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import quorum_bridge                     # noqa: E402
import render as render_mod              # noqa: E402
from rules import VERDICT_EN, VERDICT_HE, judge_case   # noqa: E402
from schema import load_case             # noqa: E402

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")


def _print(res, case):
    print("z3:", res["z3"])
    print()
    for v in res["verdicts"]:
        c = case.claim(v.claim_id)
        print("%-14s %-11s %-6s %3d/100  %d of 5 gates%s" % (
            v.claim_id, VERDICT_EN[v.verdict], v.layer or "-", v.score,
            v.applicable, "   [THIN]" if v.thin else ""))
        head = (c.text_en or c.text_he or "").replace("\n", " ")
        print("   claim :", head[:150])
        print("   ruling:", v.reason_en[:200])
        for g in v.gates:
            print("      %s %s %-8s %s" % (
                {"pass": "+", "fail": "X", "abstain": "."}[g.result],
                g.gate, g.result, g.note_en[:110]))
        print()
    t = res["tally"]
    print("TALLY  held=%d  partial=%d  rejected=%d  CANNOT-RULE=%d"
          % (t["held"], t["partial"], t["rejected"], t["norule"]))
    if res["rejected_total"]:
        print("rejections: %d total, %d about the WHY, %d about the WHAT"
              % (res["rejected_total"], res["rejected_why"], res["rejected_what"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="QUORUM · THE JUDGE")
    ap.add_argument("mode", choices=("case", "debate"))
    ap.add_argument("path")
    ap.add_argument("--sheet", default="", help="render PDF+JPEG under this stem")
    ap.add_argument("--out", default=DESKTOP, help="where the PDF+JPEG land")
    ap.add_argument("--json", default="", help="also write the ledger as JSON")
    a = ap.parse_args(argv)

    if a.mode == "case":
        case = load_case(a.path)
        res = judge_case(case)
    else:
        done = quorum_bridge.load_debate(a.path)
        res = quorum_bridge.judge_done_event(done)
        case = res["case"]

    _print(res, case)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"tally": res["tally"],
                       "rejected_why": res["rejected_why"],
                       "rejected_what": res["rejected_what"],
                       "z3": res["z3"],
                       "verdicts": [v.to_dict() for v in res["verdicts"]]},
                      f, ensure_ascii=False, indent=1)
        print("ledger json ->", a.json)

    if a.sheet:
        out = render_mod.render(res, case, a.out, a.sheet)
        print("sheet ->", out["pdf"])
        print("sheet ->", out["jpg"], out["px"], "pages:", out["pages"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
