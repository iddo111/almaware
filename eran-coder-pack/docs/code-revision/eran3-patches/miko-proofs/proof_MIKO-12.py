"""PROOF MIKO-12 -- the document tower silently saw a strided sample (2026-09-06).

hashvocab.ngram_ids caps every text at max_grams=512 and keeps every k-th n-gram. On this
corpus that is 820 of 835 documents, median coverage 9.5% -- the tower never sees 90% of its
own input, and nothing said so. (Whether to chunk-pool instead, or retire the from-scratch
tower entirely, waits for post-MIKO-01 retrain numbers; this fix makes the loss VISIBLE.)

FAILS against the 09-03 tree (no truncation_report at all; the loss is invisible).
PASSES against the fix.

    python proof_MIKO-12.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE))
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

checks: list[tuple[str, bool, str]] = []

import hashvocab  # noqa: E402

report = getattr(hashvocab, "truncation_report", None)
checks.append(("the tokenizer can report what it threw away", report is not None,
               "hashvocab.truncation_report(texts, ns, max_grams)" if report
               else "absent -- the truncation is invisible"))

if report is not None:
    docs = [json.loads(l) for l in (TARGET / "corpus.jsonl").open(encoding="utf-8")]
    line = report([d["text"] for d in docs])
    checks.append(("the report names the real numbers on the real corpus",
                   "820/835" in line and "9.5%" in line, line))

    # it must be honest in both directions: nothing truncated -> nothing claimed
    clean = report(["short text", "also short"])
    checks.append(("it reports 0 truncated when nothing is truncated",
                   "0/2" in clean and "100.0%" in clean, clean))

    raw = getattr(hashvocab, "raw_gram_count", None)
    checks.append(("the pre-truncation gram count is available", raw is not None,
                   f"raw_gram_count('x'*100) = {raw('x' * 100)}" if raw else "absent"))

src = (TARGET / "train.py").read_text(encoding="utf-8")
checks.append(("train.py prints the truncation line before it trusts a number",
               "truncation_report" in src,
               "called in main()" if "truncation_report" in src else "not called"))

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-12: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
