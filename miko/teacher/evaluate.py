#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evaluate.py -- the organ against its controls, on a frozen test set. Losses included.

Four controls run EVERY time, and three of them exist to catch the organ cheating:

  BM25         the 1994 algorithm MIKO has never beaten. Printed next to every number.
  length-only  ranks by page length alone. If the organ ties this, it learned length.
  overlap-only ranks by raw token overlap. If the organ ties this, it learned keywords
               and the weave added nothing over a word count.
  random       the floor.

Plus the two honesty checks the plan demands:
  abstention   on adversarial questions (source page hidden) the right answer is silence.
               An organ that never abstains cannot say "not found", and is marked as such.
  shuffled     train_loop.py trains a twin on SHUFFLED labels and evaluates it here. A
               shuffled twin that scores like the real organ means the metric is leaking.

    python evaluate.py --dry-run
    python evaluate.py --model runs/candidate.json --shuffled-model runs/shuffled.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import common
import organ

sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25, tokenize  # noqa: E402  (reused, not rewritten)

SILENT = -1e18


def ndcg_at_k(ranked_gains, k=10):
    """Same formula as miko/bench/bench2.py:ndcg_at_k, in stdlib."""
    g = ranked_gains[:k]
    dcg = sum(gi / math.log2(i + 2) for i, gi in enumerate(g))
    ideal = sorted(ranked_gains, reverse=True)[:k]
    idcg = sum(gi / math.log2(i + 2) for i, gi in enumerate(ideal))
    return dcg / idcg if idcg > 1e-9 else float("nan")


def evaluate_ranker(groups, score_fn, k=10, seed=0):
    """groups = [(question, [(row, page)])] -> ndcg@k, recall@1, MAE, abstention."""
    ndcgs, hits, errs, n1 = [], 0, [], 0
    abstain_ok, abstain_n, silent = 0, 0, 0
    tie_rng = random.Random(seed + 1717)
    for q, cands in groups:
        scored = []
        for row, page in cands:
            s = score_fn(q, page, row)
            if s is None:
                silent += 1
            scored.append((row, SILENT if s is None else s))
        absent = any(r.get("answer_absent") for r, _ in scored) and \
            all(r["label"] == 0 for r, _ in scored)
        if absent:
            # the right answer here is silence on every candidate
            abstain_n += 1
            if all(s <= SILENT / 10 for _, s in scored):
                abstain_ok += 1
            continue
        # Break ties RANDOMLY, never by file order. make_pairs.py writes the positive
        # row first for each question, and Python's sort is stable -- so a ranker that
        # scores everything equally, or stays SILENT on everything, would otherwise
        # collect a perfect ndcg@10 = 1.0 purely from the order of lines in the file.
        # Measured 2026-09-12: the first organ was silent on 55 of 68 calls and scored
        # exactly 1.0000 this way. miko/v1/bm25.py carries the same scar (MIKO-13).
        tie_rng.shuffle(scored)
        scored.sort(key=lambda t: -t[1])
        gains = [float(r["label"]) for r, _ in scored]
        if any(gains):
            ndcgs.append(ndcg_at_k(gains, k))
            n1 += 1
            if gains[0] > 0:
                hits += 1
        live = [s for _, s in scored if s > SILENT / 10]
        lo, hi = (min(live), max(live)) if live else (0.0, 1.0)
        rng = (hi - lo) or 1.0
        for r, s in scored:
            p = 0.0 if s <= SILENT / 10 else (s - lo) / rng
            errs.append(abs(p - r["label"]))
    return {
        "ndcg@%d" % k: (sum(ndcgs) / len(ndcgs)) if ndcgs else float("nan"),
        "recall@1": (hits / n1) if n1 else float("nan"),
        "mae": (sum(errs) / len(errs)) if errs else float("nan"),
        "questions": n1, "silent_calls": silent,
        "abstain_rate": (abstain_ok / abstain_n) if abstain_n else float("nan"),
        "abstain_n": abstain_n,
    }


def build_groups(judged, pages):
    by_id = {p["page_id"]: p for p in pages}
    g = defaultdict(list)
    for r in judged:
        p = by_id.get(r["cand_page_id"])
        if p:
            g[r["question"]].append((r, p))
    return [(q, c) for q, c in g.items() if len(c) >= 2]


def main() -> int:
    common.utf8()
    common.lower_priority()
    ap = argparse.ArgumentParser(prog="evaluate.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", default=str(common.DATA / "judged.jsonl"))
    ap.add_argument("--pages", default=str(common.DATA / "pages.jsonl"))
    ap.add_argument("--model", default=None, help="organ weights to evaluate")
    ap.add_argument("--shuffled-model", default=None, help="the shuffled-label twin")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    judged = common.read_jsonl(a.judged)
    pages = common.read_jsonl(a.pages)
    if not judged or not pages:
        print("need %s and %s" % (a.judged, a.pages))
        return 1
    groups = build_groups(judged, pages)
    if a.dry_run:
        print("[dry-run] would evaluate %d questions over %d pairs, %d pages."
              % (len(groups), len(judged), len(pages)))
        print("[dry-run] controls: BM25, length-only, overlap-only, random"
              + (", shuffled twin" if a.shuffled_model else "") + ". Nothing computed.")
        return 0

    index = BM25([p["page_id"] for p in pages],
                 [p["title"] + "\n" + p["text"] for p in pages])
    bm = {q: dict(index.search(q, top_k=len(pages))) for q, _ in groups}
    rng = random.Random(a.seed)

    def body(p):
        return p["title"] + "\n" + p["text"][:4000]

    rankers = {
        "BM25 (control, 1994)": lambda q, p, r: bm[q].get(p["page_id"], 0.0),
        "length-only (control)": lambda q, p, r: float(p["chars"]),
        "overlap-only (control)": lambda q, p, r: float(
            len(set(tokenize(q)) & set(tokenize(body(p))))),
        "random (floor)": lambda q, p, r: rng.random(),
    }
    if a.model and Path(a.model).exists():
        o = organ.MikoOrgan.load(a.model)
        rankers["ALMA organ (ours)"] = (
            lambda q, p, r, o=o: o.score(organ.meeting_features(q, body(p), o.width)))
    if a.shuffled_model and Path(a.shuffled_model).exists():
        so = organ.MikoOrgan.load(a.shuffled_model)
        rankers["ALMA shuffled twin (anti-gaming)"] = (
            lambda q, p, r, o=so: o.score(organ.meeting_features(q, body(p), o.width)))

    print("frozen test: %d questions, %d pairs, %d pages\n"
          % (len(groups), len(judged), len(pages)))
    hdr = "%-34s %9s %9s %8s %9s" % ("ranker", "ndcg@%d" % a.k, "recall@1", "mae", "abstain")
    print(hdr)
    print("-" * len(hdr))
    results = {}
    key = "ndcg@%d" % a.k
    for name, fn in rankers.items():
        m = evaluate_ranker(groups, fn, a.k, a.seed)
        results[name] = m
        ab = ("%.2f" % m["abstain_rate"]) if m["abstain_rate"] == m["abstain_rate"] else "n/a"
        print("%-34s %9.4f %9.4f %8.4f %9s"
              % (name, m[key], m["recall@1"], m["mae"], ab))

    ours = results.get("ALMA organ (ours)")
    if ours:
        base = results["BM25 (control, 1994)"]
        beats = ours[key] > base[key]
        print("\n-> the organ %s BM25 on %s (%.4f vs %.4f)."
              % ("BEATS" if beats else "LOSES TO", key, ours[key], base[key]))
        for ctrl in ("length-only (control)", "overlap-only (control)"):
            if not (ours[key] > results[ctrl][key]):
                print("   WARNING: it does not beat %s -- suspect it learned that, "
                      "not relevance." % ctrl)
        sh = results.get("ALMA shuffled twin (anti-gaming)")
        if sh and abs(sh[key] - ours[key]) < 0.02:
            print("   WARNING: the shuffled-label twin scores the same. The metric leaks.")
        if ours["abstain_n"] and not (ours["abstain_rate"] > 0):
            print("   NOTE: it never abstained on the adversarial questions -- "
                  "it cannot say 'not found'.")
        total_calls = sum(len(c) for _, c in groups)
        if total_calls and ours["silent_calls"] > 0.5 * total_calls:
            print("   WARNING: the organ was SILENT on %d of %d calls (%.0f%%). It is "
                  "abstaining, not ranking -- read every number above with that in mind."
                  % (ours["silent_calls"], total_calls,
                     100.0 * ours["silent_calls"] / total_calls))

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(
            {"at": common.now(), "questions": len(groups), "pairs": len(judged),
             "results": results}, indent=1), encoding="utf-8")
        print("\nwrote %s" % a.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
