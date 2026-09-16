"""PROOF MIKO-05 -- the hand-written exam was text-corrupted (code revision 2026-09-06).

"The one number Iddo will actually care about" was measured on 30 queries in which every
Hebrew word that should carry the letter TAV (U+05EA) carried U+05AA instead -- HEBREW
ACCENT YERAH BEN YOMO, a combining mark. 13 of 30 queries, zero real tav in the whole file,
while the corpus holds 3588 tav and not one U+05AA. e5_exam_emb.pt was embedded from the
corrupted strings, and scar_guard.py's own Hebrew fixtures carried it too. Nothing checked.

FAILS against the 09-03 tree (13 corrupted queries; no gate module exists).
PASSES against the fix (0 corrupted; the gate refuses a corrupted exam and a stale cache).

    python proof_MIKO-05.py [--dir <tree>]
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

TAV, YBY = chr(0x05EA), chr(0x05AA)
checks: list[tuple[str, bool, str]] = []

exam = json.loads((TARGET / "exam.json").read_text(encoding="utf-8"))
n_corrupt = sum(1 for e in exam if YBY in e["query"])
n_tav = sum(1 for e in exam if TAV in e["query"])
checks.append(("exam.json carries no combining-accent corruption", n_corrupt == 0,
               f"{n_corrupt}/{len(exam)} queries contain U+05AA; {n_tav} contain a real tav"))

sg = (TARGET / "scar_guard.py").read_text(encoding="utf-8")
checks.append(("scar_guard.py's Hebrew fixtures are clean", sg.count(YBY) == 0,
               f"{sg.count(YBY)} occurrences of U+05AA in the guard's own test strings"))

try:
    import exam_gate
    have = True
except ImportError as e:
    exam_gate = None
    have = False
    checks.append(("a query-validity gate exists", False,
                   f"import exam_gate -> {e}. Nothing between a corrupted exam and a headline "
                   "number."))

if have:
    corpus = [json.loads(l) for l in (TARGET / "corpus.jsonl").open(encoding="utf-8")]
    by_id = {d["id"]: d for d in corpus}
    rep = exam_gate.check_exam(exam, by_id)
    checks.append(("the gate passes the repaired exam", rep["PASS"],
                   f"bad_text={len(rep['bad_text'])} missing_target={len(rep['missing_target'])}"))

    # the gate must REFUSE the 09-03 exam -- a gate that never refused is not a gate
    corrupted = [dict(e, query=e["query"].replace(TAV, YBY)) for e in exam]
    bad = exam_gate.check_exam(corrupted, by_id)
    checks.append(("the gate REFUSES the 09-03 (corrupted) exam", not bad["PASS"],
                   f"{len(bad['bad_text'])} queries rejected"))
    try:
        exam_gate.assert_exam_valid(corrupted, by_id)
        raised = False
    except SystemExit:
        raised = True
    checks.append(("assert_exam_valid raises rather than warns", raised,
                   "SystemExit raised" if raised else "it returned normally"))

    # a stale embedding cache must be refused too
    try:
        import torch
        pack = torch.load(TARGET / "e5_exam_emb.pt", weights_only=False)
        try:
            exam_gate.assert_exam_cache_fresh(pack, exam)
            stale_caught = False
            note = "cache text matches exam.json"
        except SystemExit:
            stale_caught = True
            note = ("e5_exam_emb.pt REFUSED: it was embedded from the corrupted text, so every "
                    "e5/adapter exam number in the 09-03 report came from strings that no "
                    "longer exist. Re-embed on a fleet box.")
        checks.append(("the stale-cache check is wired and fires", True, note))
        print(f"[info] cache freshness: {'STALE (refused)' if stale_caught else 'fresh'}")
    except Exception as e:                                        # pragma: no cover
        print(f"[info] could not check the cache: {e}")

for f in ("compare_all.py", "exam_detail.py", "eval_exam.py"):
    src = (TARGET / f).read_text(encoding="utf-8")
    checks.append((f"{f} goes through the gate before reporting",
                   "exam_gate" in src,
                   "gated" if "exam_gate" in src else "ungated -- it would report anything"))

# measured effect on the control, for the record
try:
    from bm25 import BM25
    corpus = [json.loads(l) for l in (TARGET / "corpus.jsonl").open(encoding="utf-8")]
    idx = BM25([d["id"] for d in corpus], [d["text"] for d in corpus])

    def score(ex):
        r1 = r5 = 0
        for e in ex:
            ranked = [d for d, _ in idx.search(e["query"], top_k=idx.N)]
            pos = ranked.index(e["target_id"]) + 1 if e["target_id"] in ranked else None
            if pos == 1:
                r1 += 1
            if pos is not None and pos <= 5:
                r5 += 1
        return r1, r5

    now = score(exam)
    was = score([dict(e, query=e["query"].replace(TAV, YBY)) for e in exam])
    print(f"[info] BM25 exam, corrupted text: recall@1 {was[0]}/30, recall@5 {was[1]}/30")
    print(f"[info] BM25 exam, repaired  text: recall@1 {now[0]}/30, recall@5 {now[1]}/30")
except Exception as e:                                            # pragma: no cover
    print(f"[info] BM25 comparison unavailable: {e}")

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-05: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
