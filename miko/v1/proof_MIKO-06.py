"""PROOF MIKO-06 -- RAMCHAT document ids were positional (code revision 2026-09-06).

`ram:{i:04d}` was the index into ramchat_session.json -- a ROLLING 500-message window. Every
rebuild silently re-labelled every ram: id onto whatever message currently sat at that index:
no error, ids still "existed", split.json still resolved, the exam still scored. Verified on
2026-09-06: all five ram: exam targets had drifted onto different messages.

FAILS against the 09-03 tree (no content-addressed id function, no rebuild gate; ids are
positional, so a rebuild against today's RAMCHAT re-labels them silently).
PASSES against the fix.

    python proof_MIKO-06.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE))
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

checks: list[tuple[str, bool, str]] = []

docs = [json.loads(l) for l in (TARGET / "corpus.jsonl").open(encoding="utf-8")]
ram = [d for d in docs if d["id"].startswith("ram:")]
positional = [d for d in ram if re.fullmatch(r"ram:\d{4}", d["id"])]
checks.append(("no RAMCHAT id is a rolling-window position", len(positional) == 0,
               f"{len(positional)}/{len(ram)} ids look like ram:NNNN (a file index)"))

try:
    import build_corpus
    ram_doc_id = getattr(build_corpus, "ram_doc_id", None)
except Exception as e:                                            # pragma: no cover
    build_corpus = None
    ram_doc_id = None
    print(f"[info] could not import build_corpus: {e}")

checks.append(("ids are content-addressed by a named function", ram_doc_id is not None,
               "build_corpus.ram_doc_id(query, text)" if ram_doc_id
               else "absent -- ids come from enumerate()"))

if ram_doc_id is not None:
    mismatched = [d["id"] for d in ram if ram_doc_id(d["query"], d["text"]) != d["id"]]
    checks.append(("every stored ram id equals the hash of its own content",
                   len(mismatched) == 0,
                   f"{len(ram) - len(mismatched)}/{len(ram)} match; {len(mismatched)} do not"))

    # stability: the same message keeps its id no matter where it sits in the window
    shuffled = list(reversed(ram))
    ids_before = {d["id"] for d in ram}
    ids_after = {ram_doc_id(d["query"], d["text"]) for d in shuffled}
    checks.append(("ids survive the window moving (position-independent)",
                   ids_before == ids_after,
                   f"{len(ids_before & ids_after)}/{len(ids_before)} ids stable after "
                   "reordering the whole window"))

gate = getattr(build_corpus, "check_exam_targets", None) if build_corpus else None
checks.append(("a rebuild gate on the exam targets exists", gate is not None,
               "build_corpus.check_exam_targets(docs, allow_missing=...)" if gate
               else "absent -- a rebuild silently re-points the exam"))

if gate is not None:
    exam = json.loads((TARGET / "exam.json").read_text(encoding="utf-8"))
    targets = {e["target_id"] for e in exam}
    # 1. it must NOT fire on the corpus the exam was written against
    try:
        gate(docs, allow_missing=False)
        ok_full = True
        note_full = "no refusal on the intact corpus"
    except SystemExit as e:
        ok_full = False
        note_full = str(e)[:120]
    checks.append(("the gate stays quiet when every target resolves", ok_full, note_full))

    # 2. it MUST fire when a ram: message has left the rolling window
    victim = next((d for d in docs if d["id"] in targets and d["id"].startswith("ram:")), None)
    if victim is None:
        checks.append(("the gate refuses when a target has left the window", False,
                       "no ram: exam target found to test with"))
    else:
        thinned = [d for d in docs if d["id"] != victim["id"]]
        try:
            gate(thinned, allow_missing=False)
            fired = False
            msg = "it accepted a corpus missing an exam target"
        except SystemExit as e:
            fired = "EXAM-TARGETS-MISSING" in str(e)
            msg = str(e).splitlines()[0][:110]
        checks.append(("the gate REFUSES when a target has left the window", fired, msg))
        # and the override must exist, so the refusal is a decision, not a wall
        try:
            gate(thinned, allow_missing=True)
            override = True
        except SystemExit:
            override = False
        checks.append(("--allow-missing-exam-targets can override it deliberately", override,
                       "override works" if override else "no way past the gate"))

# every downstream artefact must agree with the corpus
split = json.loads((TARGET / "split.json").read_text(encoding="utf-8"))
all_ids = {d["id"] for d in docs}
sp = set(split["train"]) | set(split["val"]) | set(split["test"])
exam = json.loads((TARGET / "exam.json").read_text(encoding="utf-8"))
checks.append(("split.json still covers exactly the corpus", sp == all_ids,
               f"split {len(sp)} ids vs corpus {len(all_ids)}"))
checks.append(("every exam target still resolves",
               all(e["target_id"] in all_ids for e in exam),
               f"{sum(1 for e in exam if e['target_id'] in all_ids)}/{len(exam)}"))

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-06: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
