"""PROOF MIKO-13 -- the run surface: file-order ranks and a torch-shaped BM25 (2026-09-06).

Two things, both about numbers that are not what they look like:
  * bm25.search_all_ranked padded its hits with EVERY zero-overlap document in corpus file
    order, and callers then did `.index(gold) + 1`. Ranks like 554/835 were artefacts of
    where a line sits in corpus.jsonl, and MRR counted 1/554 for what is actually a miss.
  * `import torch` sat at search.py's module top, so the DEFAULT method -- BM25, pure stdlib,
    and the only method that wins anything -- could not run without torch.

FAILS against the 09-03 tree. PASSES against the fix.

    python proof_MIKO-13.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE))
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

checks: list[tuple[str, bool, str]] = []

from bm25 import BM25, eval_bm25  # noqa: E402

ids = [f"doc:{i}" for i in range(6)]
texts = ["alpha beta", "beta gamma", "gamma delta", "delta epsilon", "epsilon zeta", "zeta eta"]
idx = BM25(ids, texts)

ranked = idx.search_all_ranked("nosuchtermanywhere")
checks.append(("an unreachable query ranks nothing", len(ranked) == 0,
               f"search_all_ranked returned {len(ranked)} ids "
               f"({'file order padding' if ranked else 'empty, as it should be'})"))

rank_of = getattr(BM25, "rank_of", None)
checks.append(("a rank that can say 'no rank' exists", rank_of is not None,
               "BM25.rank_of(query, gold) -> int | None" if rank_of else "absent"))

if rank_of is not None:
    miss = idx.rank_of("nosuchtermanywhere", "doc:5")
    hit = idx.rank_of("alpha", "doc:0")
    checks.append(("a miss is None, not a file-order position", miss is None, f"rank = {miss!r}"))
    checks.append(("a real hit still ranks 1", hit == 1, f"rank = {hit!r}"))

# a miss must contribute 0 to MRR, not 1/554
m = eval_bm25(idx, [("nosuchtermanywhere", "doc:5")])
checks.append(("a miss contributes 0 to MRR", m["mrr"] == 0.0 and m["recall@5"] == 0.0,
               f"mrr={m['mrr']:.4f} recall@5={m['recall@5']:.4f} "
               "(the old padding gave a positive score for a miss)"))

# search.py must not need torch for the stdlib default
src = (TARGET / "search.py").read_text(encoding="utf-8")
top_level_torch = any(
    isinstance(n, (ast.Import, ast.ImportFrom))
    and any(getattr(a, "name", "").split(".")[0] == "torch" for a in n.names)
    for n in ast.parse(src).body)
checks.append(("search.py does not import torch at module level", not top_level_torch,
               "torch is imported inside the methods that need it" if not top_level_torch
               else "`import torch` at the top -- --method bm25 pays for it"))

for f in ("compare_all.py", "exam_detail.py", "eval_exam.py"):
    s = (TARGET / f).read_text(encoding="utf-8")
    checks.append((f"{f} uses rank_of instead of .index() on padded ranks",
                   "rank_of" in s,
                   "uses rank_of" if "rank_of" in s else "still indexes into a padded list"))

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-13: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
