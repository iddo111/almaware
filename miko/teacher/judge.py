#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""judge.py -- the free fleet model that scores pairs, AND the rule that keeps it honest.

A judge nobody checks is how a model learns to please a machine. So this file has two
jobs and the second one outranks the first:

  1. --score      a free fleet model rates (question, page) 0-5 against the rubric below,
                  written down verbatim, and the score is divided by 5.
  2. --calibrate  the judge is compared against a FROZEN SET IDDO LABELLED HIMSELF.
                  It reports plain agreement and Cohen's kappa. train_loop.py refuses to
                  train when that file is missing or when kappa falls under --min-kappa.
                  THE JUDGE MAY STEER TRAINING ONLY WHILE IT AGREES WITH IDDO.

  --make-sheet N  writes the labelling sheet Iddo fills in ONCE (data/iddo_sheet.txt),
                  and the empty answer file he types into (data/iddo_labels.jsonl).

    python judge.py --score --limit 30
    python judge.py --make-sheet 40
    python judge.py --calibrate
"""
from __future__ import annotations

import argparse
import random
import re
import sys

import common

SYSTEM = ("You are a strict search-relevance judge. You rate how well a web page answers "
          "a specific question. You reply with a single digit and nothing else.")

# Verbatim, and kept identical to miko/bench/judge.py RUBRIC_A so the 47,700 pairs already
# on disk and anything scored tonight sit on ONE scale.
RUBRIC = """QUESTION:
{q}

WEB PAGE (excerpt):
{p}

Rate how relevant this web page is for answering the QUESTION:
0 = completely unrelated topic
1 = same broad field, but does not address the question at all
2 = touches the question's topic, but gives no usable answer
3 = partially answers the question, or gives useful background
4 = answers the question well
5 = directly and fully answers the question with specifics

Reply with one digit only (0-5)."""

RELEVANT_AT = 0.6   # judge score >= this counts as "relevant" when comparing with Iddo
_DIGIT = re.compile(r"[0-5]")


def score_pair(question, page_text, excerpt_chars=2000, prefer=None):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": RUBRIC.format(q=question, p=page_text[:excerpt_chars])}]
    name, model, out = common.call_fleet(msgs, max_tokens=6, temperature=0.0, prefer=prefer)
    who = "%s (%s)" % (name, model)
    m = _DIGIT.search(out or "")
    if not m:
        return None, None, who, (out or "")[:40]
    d = int(m.group(0))
    return d / 5.0, d, who, (out or "").strip()[:40]


def kappa(a, b):
    """Cohen's kappa for two binary raters. Plain arithmetic, no library."""
    n = len(a)
    if n == 0:
        return float("nan")
    agree = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    chance = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return (agree - chance) / (1 - chance) if abs(1 - chance) > 1e-12 else float("nan")


def do_score(a):
    pairs = common.read_jsonl(a.pairs)
    if not pairs:
        print("no pairs in %s -- run make_pairs.py first" % a.pairs)
        return 1
    pages = {p["page_id"]: p for p in common.read_jsonl(a.pages)}
    if a.limit:
        pairs = pairs[:a.limit]
    if a.dry_run:
        print("[dry-run] would judge %d pairs with the rubric below. No model called.\n"
              % len(pairs))
        print(RUBRIC.format(q="<question>", p="<page excerpt>"))
        return 0
    out, fails = [], 0
    for i, r in enumerate(pairs, 1):
        page = pages.get(r["cand_page_id"])
        if not page:
            fails += 1
            continue
        try:
            s, d, who, raw = score_pair(r["question"], page["text"], a.excerpt_chars, a.prefer)
        except RuntimeError as e:
            print("  NO MODEL ANSWERED -- %s" % e)
            fails += 1
            continue
        if s is None:
            print("  [%d] unparsable judge reply %r" % (i, raw))
            fails += 1
            continue
        out.append(dict(r, judge_score=s, judge_digit=d, judge_model=who,
                        judge_rubric="A", judged_at=common.now()))
        if i <= 12 or i % 25 == 0:
            print("  [%3d/%d] label=%d judge=%.1f (%d)  %s"
                  % (i, len(pairs), r["label"], s, d, r["question"][:52]))
    common.write_jsonl(a.out, out)
    print("\njudged %d pairs (%d failed) -> %s" % (len(out), fails, a.out))
    if out:
        pos = [r["judge_score"] for r in out if r["label"] == 1]
        neg = [r["judge_score"] for r in out if r["label"] == 0]
        if pos and neg:
            print("mean judge score: positives %.3f (n=%d) vs negatives %.3f (n=%d)  gap %+.3f"
                  % (sum(pos) / len(pos), len(pos), sum(neg) / len(neg), len(neg),
                     sum(pos) / len(pos) - sum(neg) / len(neg)))
    return 0


def do_make_sheet(a):
    rows = common.read_jsonl(a.out) or common.read_jsonl(a.pairs)
    if not rows:
        print("nothing to put on a sheet -- run make_pairs.py (and --score) first")
        return 1
    pages = {p["page_id"]: p for p in common.read_jsonl(a.pages)}
    rng = random.Random(a.seed)
    rows = rows[:]
    rng.shuffle(rows)
    rows = rows[:a.make_sheet]
    sheet = common.DATA / "iddo_sheet.txt"
    answers = common.DATA / "iddo_labels.jsonl"
    head = (
        "MIKO - the frozen set. %d items. One tap each: 1 = useful answer, 0 = not.\n"
        "Write your answers into %s, one JSON line per item:\n"
        '  {"pair_id": "...", "label": 1}\n'
        "The judge is allowed to teach MIKO only while it agrees with THIS file.\n"
        "Nothing here was scored by a model for you -- that is the whole point.\n"
        % (len(rows), answers)
    )
    with open(sheet, "w", encoding="utf-8") as f:
        f.write(head + "=" * 78 + "\n\n")
        for i, r in enumerate(rows, 1):
            pg = pages.get(r["cand_page_id"], {})
            excerpt = (pg.get("text", "")[:500]).replace("\n", " ")
            f.write("[%d] pair_id: %s\nQUESTION: %s\nPAGE: %s\nEXCERPT: %s\n\n"
                    "YOUR LABEL (1/0): ____\n%s\n\n"
                    % (i, r["pair_id"], r["question"], r.get("cand_url", ""),
                       excerpt, "-" * 78))
    if not answers.exists():
        answers.write_text("", encoding="utf-8")
    print("wrote the sheet: %s (%d items)" % (sheet, len(rows)))
    print("empty answer file ready: %s" % answers)
    print("Iddo labels this ONCE. Until he does, train_loop.py refuses to promote weights.")
    return 0


def do_calibrate(a):
    labels = {r["pair_id"]: int(r["label"]) for r in common.read_jsonl(a.labels)}
    judged = common.read_jsonl(a.out)
    if not labels:
        print("NO FROZEN LABELS in %s." % a.labels)
        print("The judge has not been checked against Iddo, so it may NOT steer training.")
        print("Run: python judge.py --make-sheet 40")
        common.log_run({"stage": "calibrate", "status": "NO_LABELS", "n": 0}, a.runlog)
        return 2
    if not judged:
        print("no judged pairs in %s -- run --score first" % a.out)
        return 1
    jm = {r["pair_id"]: r for r in judged}
    keys = [k for k in labels if k in jm]
    if not keys:
        print("the frozen set and the judged set do not overlap on any pair_id")
        return 1
    iddo = [labels[k] for k in keys]
    judge = [1 if jm[k]["judge_score"] >= RELEVANT_AT else 0 for k in keys]
    acc = sum(1 for x, y in zip(iddo, judge) if x == y) / len(keys)
    k = kappa(iddo, judge)
    ok = (k == k) and (k >= a.min_kappa) and (acc >= a.min_acc)
    common.log_run({"stage": "calibrate", "n": len(keys), "accuracy": round(acc, 4),
                    "kappa": round(k, 4) if k == k else None, "min_kappa": a.min_kappa,
                    "min_acc": a.min_acc, "status": "PASS" if ok else "FAIL",
                    "judge_model": judged[0].get("judge_model")}, a.runlog)
    print("CALIBRATION against Iddo's frozen set")
    print("  overlap        : %d pairs" % len(keys))
    print("  plain accuracy : %.3f   (gate >= %.2f)" % (acc, a.min_acc))
    print("  Cohen's kappa  : %s   (gate >= %.2f)"
          % (("%.3f" % k) if k == k else "undefined", a.min_kappa))
    print("  VERDICT        : %s" % ("PASS - the judge may steer training" if ok
                                     else "FAIL - training is NOT allowed"))
    return 0 if ok else 3


def main() -> int:
    common.utf8()
    common.lower_priority()
    ap = argparse.ArgumentParser(prog="judge.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score", action="store_true", help="judge the pairs")
    ap.add_argument("--calibrate", action="store_true", help="check the judge against Iddo")
    ap.add_argument("--make-sheet", type=int, default=0, metavar="N",
                    help="write the N-item sheet for Iddo to label once")
    ap.add_argument("--pairs", default=str(common.DATA / "pairs.jsonl"))
    ap.add_argument("--pages", default=str(common.DATA / "pages.jsonl"))
    ap.add_argument("--out", default=str(common.DATA / "judged.jsonl"))
    ap.add_argument("--labels", default=str(common.DATA / "iddo_labels.jsonl"))
    ap.add_argument("--runlog", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--excerpt-chars", type=int, default=2000)
    ap.add_argument("--prefer", default=None, help="pin a fleet endpoint name first")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--min-kappa", type=float, default=0.40)
    ap.add_argument("--min-acc", type=float, default=0.70)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.make_sheet:
        return do_make_sheet(a)
    if a.calibrate:
        return do_calibrate(a)
    if a.score:
        return do_score(a)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
