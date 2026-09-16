#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_pairs.py -- turn harvested pages into (question, right answer) pairs, for free.

THE TRICK, in one line: a page IS the answer to questions nobody has written yet. So a
free fleet model reads the page and writes the questions it answers. That gives a
POSITIVE with no human effort. The HARD NEGATIVES then come from BM25's near misses on
the same corpus -- pages that look right to a 1994 algorithm and are not the source.
Easy negatives teach nothing; BM25's second-best is the negative worth having.

Three kinds of row come out:
  pos          question + the page it was written from        label 1
  hardneg      question + BM25's top near-miss page           label 0
  adversarial  question whose source page is REMOVED from the pool entirely; every
               candidate is label 0 and the right answer is "not found". Without these
               an organ can score well while being incapable of ever saying no.

The adversarial count is EXACT, not a coin flip per question: round(frac x questions),
chosen by a seeded shuffle. Measured 2026-09-12 -- with a per-question random draw at
15%, Random(0)'s first 24 draws happen to contain none under 0.15 (minimum 0.251), so a
whole run came out with zero adversarial pairs and the anti-gaming check silently did
not exist. A guarantee the seed can cancel is not a guarantee.

Questions are cached in data/questions.jsonl, so rebuilding the pairs (different
negatives, different adversarial fraction) costs no model calls at all.

    python make_pairs.py --dry-run
    python make_pairs.py --limit 8 --questions-per-page 3 --negatives 2
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys

import common

sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25  # noqa: E402  (reused, not rewritten)

PROMPT = """You are given an excerpt from a public web page. Write exactly {k} short \
factual questions that THIS page answers and that a person would plausibly type into a \
search engine. Each question must be answerable from the excerpt alone. Do not mention \
"the page" or "this document" in the questions.

Output strict JSON and nothing else: {{"questions": ["...", "..."]}}

PAGE EXCERPT:
{excerpt}"""

_JSON = re.compile(r"\{.*\}", re.S)


def parse_questions(text: str, k: int) -> list[str]:
    m = _JSON.search(text or "")
    if m:
        try:
            qs = json.loads(m.group(0)).get("questions", [])
            out = [str(q).strip() for q in qs if str(q).strip()]
            if out:
                return out[:k]
        except Exception:
            pass
    lines = [re.sub(r'^[\s\-\*\d\.\)"]+', "", ln).strip(' "')
             for ln in (text or "").splitlines()]
    return [ln for ln in lines if ln.endswith("?")][:k]


def get_questions(pages, a):
    """Phase 1: ask a free model, or reuse the cache. Returns [(page, question)]."""
    cache = {r["page_id"]: r for r in common.read_jsonl(a.questions_cache)}
    out, fresh = [], []
    for i, p in enumerate(pages, 1):
        hit = cache.get(p["page_id"])
        if hit and not a.refresh_questions and len(hit["questions"]) >= a.questions_per_page:
            qs, how = hit["questions"][:a.questions_per_page], "cache"
            made_by = hit.get("made_by", "cache")
        else:
            try:
                name, model, raw = common.call_fleet(
                    [{"role": "user", "content": PROMPT.format(
                        k=a.questions_per_page, excerpt=p["text"][:a.excerpt_chars])}],
                    max_tokens=400, temperature=0.3, prefer=a.prefer)
            except RuntimeError as e:
                print("  [%d/%d] NO MODEL ANSWERED -- %s" % (i, len(pages), e))
                continue
            qs, how = parse_questions(raw, a.questions_per_page), name
            made_by = "%s (%s)" % (name, model)
            fresh.append({"page_id": p["page_id"], "url": p["url"], "questions": qs,
                          "made_by": made_by, "made_at": common.now()})
        print("  [%d/%d] %-46s -> %d question(s) via %s"
              % (i, len(pages), p["host"] + "..." + p["url"][-26:], len(qs), how))
        for q in qs:
            out.append((p, q, made_by))
    if fresh:
        keep = [r for r in common.read_jsonl(a.questions_cache)
                if r["page_id"] not in {f["page_id"] for f in fresh}]
        common.write_jsonl(a.questions_cache, keep + fresh)
        print("  cached %d page(s) of questions -> %s" % (len(fresh), a.questions_cache))
    return out


def main() -> int:
    common.utf8()
    common.lower_priority()
    ap = argparse.ArgumentParser(prog="make_pairs.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", default=str(common.DATA / "pages.jsonl"))
    ap.add_argument("--out", default=str(common.DATA / "pairs.jsonl"))
    ap.add_argument("--questions-cache", default=str(common.DATA / "questions.jsonl"))
    ap.add_argument("--refresh-questions", action="store_true",
                    help="ignore the cache and ask the model again")
    ap.add_argument("--limit", type=int, default=0, help="use at most N pages")
    ap.add_argument("--questions-per-page", type=int, default=3)
    ap.add_argument("--negatives", type=int, default=2, help="hard negatives per question")
    ap.add_argument("--adversarial-frac", type=float, default=0.15,
                    help="fraction of questions whose source page is hidden ('not found')")
    ap.add_argument("--excerpt-chars", type=int, default=2400)
    ap.add_argument("--prefer", default=None, help="pin a fleet endpoint name first")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="call no model, write nothing")
    a = ap.parse_args()

    pages = common.read_jsonl(a.pages)
    if not pages:
        print("no pages in %s -- run harvest.py first" % a.pages)
        return 1
    if a.limit:
        pages = pages[:a.limit]

    print("pages: %d | questions/page: %d | hard negatives/question: %d | adversarial: %.0f%%"
          % (len(pages), a.questions_per_page, a.negatives, 100 * a.adversarial_frac))
    if a.dry_run:
        cached = {r["page_id"] for r in common.read_jsonl(a.questions_cache)}
        for p in pages:
            src = "CACHE" if p["page_id"] in cached and not a.refresh_questions else "MODEL"
            print("  WOULD GET %d questions from %s (%s, %d chars)"
                  % (a.questions_per_page, p["url"], src, p["chars"]))
        nq = len(pages) * a.questions_per_page
        print("  WOULD MARK exactly %d of ~%d questions adversarial ('not found')"
              % (round(a.adversarial_frac * nq), nq))
        print("\n[dry-run] no model called, no file written.")
        return 0

    qlist = get_questions(pages, a)
    if not qlist:
        print("no questions were produced -- nothing to write.")
        return 1

    # exact, seeded, reproducible: which questions get their source page hidden
    rng = random.Random(a.seed)
    n_adv = int(round(a.adversarial_frac * len(qlist)))
    adv_idx = set(rng.sample(range(len(qlist)), n_adv)) if n_adv else set()

    index = BM25([p["page_id"] for p in pages],
                 [p["title"] + "\n" + p["text"] for p in pages])
    by_id = {p["page_id"]: p for p in pages}

    rows = []
    for i, (p, q, made_by) in enumerate(qlist):
        qid = "q_" + common.sha256_text(q)[:12]
        absent = i in adv_idx
        ranked = index.search(q, top_k=a.negatives + 3)
        negs = [d for d, _ in ranked if d != p["page_id"]][:a.negatives]
        base = dict(question=q, question_id=qid, source_page_id=p["page_id"],
                    source_url=p["url"], made_by=made_by, made_at=common.now(),
                    answer_absent=absent)
        if not absent:
            rows.append(dict(base, pair_id="%s__%s" % (qid, p["page_id"]),
                             cand_page_id=p["page_id"], cand_url=p["url"],
                             label=1, kind="pos", bm25_rank=None))
        for r, d in enumerate(negs, 1):
            rows.append(dict(base, pair_id="%s__%s" % (qid, d),
                             cand_page_id=d, cand_url=by_id[d]["url"],
                             label=0, kind="adversarial" if absent else "hardneg",
                             bm25_rank=r))

    common.write_jsonl(a.out, rows)
    npos = sum(1 for r in rows if r["label"] == 1)
    nadv = sum(1 for r in rows if r["kind"] == "adversarial")
    print("\n%d questions, %d of them adversarial ('not found', source page hidden)"
          % (len(qlist), n_adv))
    print("wrote %d pairs (%d positive, %d hard negative, %d adversarial) -> %s"
          % (len(rows), npos, len(rows) - npos - nadv, nadv, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
