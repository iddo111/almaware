"""PROOF MIKO-04 -- held-out documents leaked through the hard negatives (2026-09-06).

The BM25 index the hard negatives were mined from was built over ALL 835 documents, so
val/test documents went through the encoder WITH GRADIENT as negatives for train queries.
Measured on this corpus: 609/669 train examples carried at least one held-out document among
their ten hard negatives, and 161/166 val+test docs (95/100 test docs) were seen that way.
The report's "documents the model never saw" was false as written.

FAILS against the 09-03 code (no train-only mining index exists; the whole-corpus index leaks).
PASSES against the fix (leak = 0, and the loops refuse if it is ever not).

    python proof_MIKO-04.py [--dir <tree>]
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

from bm25 import BM25  # noqa: E402

checks: list[tuple[str, bool, str]] = []

docs = [json.loads(l) for l in (TARGET / "corpus.jsonl").open(encoding="utf-8")]
by_id = {d["id"]: d for d in docs}
split = json.loads((TARGET / "split.json").read_text(encoding="utf-8"))
train_ids = split["train"]
held = set(split["val"]) | set(split["test"])
pairs = [(by_id[i]["query"], i) for i in train_ids if by_id[i].get("query")]


def mine(index: BM25, k: int = 10) -> dict:
    out = {}
    for q, gold in pairs:
        out[gold] = [d for d, _ in index.search(q, top_k=k + 3) if d != gold][:k]
    return out


# what the 09-03 code did: mine from the whole corpus
whole = BM25([d["id"] for d in docs], [d["text"] for d in docs])
hn_whole = mine(whole)
leak_docs = {g for hits in hn_whole.values() for g in hits if g in held}
leak_examples = sum(1 for hits in hn_whole.values() if any(g in held for g in hits))
test_leak = len(leak_docs & set(split["test"]))
print(f"[info] whole-corpus mining (the 09-03 path): {leak_examples}/{len(pairs)} train "
      f"examples carry a held-out doc; {len(leak_docs)}/{len(held)} held-out docs leak "
      f"({test_leak}/{len(split['test'])} test docs)")

try:
    import train
    build = getattr(train, "build_mining_index", None)
    leaked_fn = getattr(train, "leaked_negatives", None)
except Exception as e:                                            # pragma: no cover
    build = leaked_fn = None
    print(f"[info] could not import train: {e}")

checks.append(("a train-only mining index exists as a named function", build is not None,
               "train.build_mining_index(docs, train_ids)" if build
               else "absent -- mining is hard-wired to the whole-corpus index"))

if build is not None:
    idx = build(docs, train_ids)
    hn_train = mine(idx)
    leak_now = leaked_fn(hn_train, train_ids) if leaked_fn else \
        sorted({g for hits in hn_train.values() for g in hits if g not in set(train_ids)})
    checks.append(("hard negatives contain zero held-out documents", len(leak_now) == 0,
                   f"leaked = {len(leak_now)} (was {len(leak_docs)}/{len(held)} held-out docs)"))
    checks.append(("the mining index holds only train documents",
                   set(idx.doc_ids) == set(train_ids),
                   f"index = {len(idx.doc_ids)} docs, train = {len(train_ids)}"))
    n_with = sum(1 for v in hn_train.values() if v)
    checks.append(("mining still finds negatives for essentially every train query",
                   n_with >= 0.95 * len(pairs),
                   f"{n_with}/{len(pairs)} train examples still get hard negatives"))

for f in ("train.py", "adapter_train.py"):
    src = (TARGET / f).read_text(encoding="utf-8")
    checks.append((f"{f} refuses on any leak (HOLDOUT-LEAK)", "HOLDOUT-LEAK" in src,
                   "present" if "HOLDOUT-LEAK" in src else "nothing would notice"))

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-04: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
