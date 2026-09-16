"""MELUMAD corrections: claims found wrong during review, patched in lessons.jsonl.

Every correction records what was claimed, what was measured instead, and by what test.
Run AFTER merge.py.  Read-only except lessons.jsonl.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
LESSONS = os.path.join(HERE, "lessons.jsonl")

# id -> (field, new value, why)
CORRECTIONS = {
    "vaada-018": {
        "title": "Softmax cannot reorder a ranking, but a Hopfield UPDATE is not a softmax reranking",
        "failure": (
            "Two different claims were collapsed into one. Ranking documents by the softmax WEIGHTS "
            "softmax(beta * X^T x) is indeed identical to plain cosine ranking for every beta > 0, because "
            "softmax is strictly monotone and argsort ignores monotone transforms. But the Hopfield update "
            "does not rank by the weights - it forms a new vector x_new = X^T softmax(beta * X^T x), a weighted "
            "BLEND of the document vectors, and ranks by similarity to that blend. That is NOT a monotone "
            "transform of the cosine scores and it does reorder results. The sweep looked identical only "
            "because top-1 converges to cosine's top-1 once beta is large."
        ),
        "measurement": (
            "Re-tested directly (numpy, 200 docs x 32 dims, 50 queries, beta in {1,8,128}): ranking by softmax "
            "weights differed from cosine in 0/150 cases; ranking by the updated vector differed in 150/150 cases. "
            "Sweeping beta on one query: top-1 matches cosine from beta>=4 onward, but only 10-20% of the top-10 "
            "ORDER matches at any beta. Original report's own numbers already implied this - beta=1 scoring 0/30 "
            "while beta=128 scored 8/30 is impossible under a genuinely beta-invariant ranking."
        ),
        "rule": (
            "A monotone transform of a score (softmax, sigmoid, temperature) cannot change a ranking - but check "
            "what is actually being ranked; if the mechanism ranks by a function of the WEIGHTED COMBINATION "
            "rather than by the weights, the monotonicity argument does not apply."
        ),
        "_correction": (
            "Corrected 2026-09-04 by melumad. Original claimed the Hopfield retriever was 'mathematically "
            "identical in ranking to cosine for any temperature'. That is true only for the softmax weights, "
            "not for the Hopfield update actually implemented; the original's own beta=1 vs beta=128 numbers "
            "contradicted it. Verified by direct numerical test, not by argument."
        ),
    }
}


def main():
    if not os.path.exists(LESSONS):
        raise SystemExit("run merge.py first")
    rows = [json.loads(l) for l in open(LESSONS, encoding="utf-8") if l.strip()]
    n = 0
    for r in rows:
        patch = CORRECTIONS.get(r.get("id"))
        if patch:
            for k, v in patch.items():
                r[k] = v
            n += 1
            print(f"corrected {r['id']}: {r['title']}")
    with open(LESSONS, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n{n} correction(s) applied to {len(rows)} lessons")


if __name__ == "__main__":
    main()
