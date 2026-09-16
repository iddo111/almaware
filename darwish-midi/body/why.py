"""why.py — explainability. For any context, print who votes and how loudly.

Usage: python why.py <token1,token2,...> [phase]
Prints the top voting cells and their weighted candidates — the bird's reasons.
"""
import sys

import genome
from brain import Brain, _ctx_key


def explain(brain, history, phase=0, top=8):
    lines = []
    h = list(history)[-genome.ORDER_MAX:]
    for k in range(1, genome.ORDER_MAX + 1):
        if len(h) < k:
            break
        cell = _ctx_key(k, h[-k:])
        cw = brain.w.get(cell)
        if not cw:
            continue
        n = brain.n.get(cell, 0)
        lam = n / (n + genome.LAMBDA_C)
        best = sorted(cw.items(), key=lambda kv: -kv[1])[:3]
        cand = ", ".join(f"{t}:{v:.1f}" for t, v in best)
        lines.append(f"order-{k} cell '{cell}' n={n} voice={lam:.2f} -> {cand}")
    if not lines:
        lines.append("(no experienced cells for this context — the unigram floor decides)")
    return lines


if __name__ == "__main__":
    import gzip, os
    state = os.path.join(os.path.dirname(__file__), "..", "state", "brain.json.gz")
    b = Brain.load(state)
    toks = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else [genome.TOK_BOS]
    phase = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    b.history = toks[-genome.ORDER_MAX:]
    for line in explain(b, toks, phase):
        print(line)
