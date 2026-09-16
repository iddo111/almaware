"""MIKO v1 -- BM25 control, pure stdlib (Okapi BM25, k1=1.5, b=0.75).

Every neural number in this project is reported next to this. If the trained net does
not beat BM25, MIKO v1's report says so plainly -- a real number below the control is
worth more than a claim (Iddo's standing rule).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


class BM25:
    def __init__(self, doc_ids: list[str], texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_ids = doc_ids
        self.N = len(doc_ids)
        self.doc_tokens = [tokenize(t) for t in texts]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avgdl = sum(self.doc_len) / max(1, self.N)
        self.tf: list[Counter] = [Counter(t) for t in self.doc_tokens]
        df = defaultdict(int)
        for c in self.tf:
            for w in c:
                df[w] += 1
        self.idf = {w: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        # inverted index: term -> list of doc indices with nonzero tf, for speed
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, c in enumerate(self.tf):
            for w in c:
                self.postings[w].append(i)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        q_tokens = tokenize(query)
        scores = defaultdict(float)
        for w in q_tokens:
            idf = self.idf.get(w)
            if idf is None:
                continue
            for i in self.postings.get(w, []):
                f = self.tf[i][w]
                dl = self.doc_len[i]
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * (f * (self.k1 + 1)) / denom
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
        return [(self.doc_ids[i], s) for i, s in ranked]

    def search_all_ranked(self, query: str) -> list[str]:
        """Full ranking over every doc that shares at least one term (rest are tied last)."""
        hits = self.search(query, top_k=self.N)
        hit_ids = {d for d, _ in hits}
        rest = [d for d in self.doc_ids if d not in hit_ids]
        return [d for d, _ in hits] + rest


def eval_bm25(bm25: "BM25", pairs: list[tuple[str, str]]) -> dict:
    """pairs = [(query, gold_doc_id), ...]. Returns recall@1, recall@5, MRR."""
    r1 = r5 = mrr = 0.0
    n = len(pairs)
    for q, gold in pairs:
        ranked = bm25.search_all_ranked(q)
        try:
            rank = ranked.index(gold) + 1
        except ValueError:
            rank = None
        if rank == 1:
            r1 += 1
        if rank is not None and rank <= 5:
            r5 += 1
        if rank is not None:
            mrr += 1.0 / rank
    return {"recall@1": r1 / n, "recall@5": r5 / n, "mrr": mrr / n, "n": n}
