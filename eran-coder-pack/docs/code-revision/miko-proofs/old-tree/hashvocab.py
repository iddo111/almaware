"""MIKO v1 -- hashed char n-gram tokenizer.  No external vocab, no BPE.

Stable across processes and machines: Python's built-in `hash(str)` is salted per
process (PYTHONHASHSEED), so it CANNOT be used here -- a model trained on eran3 would
disagree with itself run on the PC. We use FNV-1a, a small deterministic 32-bit hash,
computed over the UTF-8 bytes of each n-gram.
"""
from __future__ import annotations

FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193
MASK32 = 0xFFFFFFFF


def fnv1a(s: str) -> int:
    h = FNV_OFFSET
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * FNV_PRIME) & MASK32
    return h


def ngram_ids(text: str, vocab_size: int, ns=(3, 4, 5), max_grams: int = 512) -> list[int]:
    """Char n-grams of `text` (lowercased), hashed into [0, vocab_size)."""
    t = "▁" + text.lower().strip() + "▁"   # boundary marker, like sentencepiece
    ids = []
    for n in ns:
        if len(t) < n:
            continue
        for i in range(len(t) - n + 1):
            g = t[i:i + n]
            ids.append(fnv1a(g) % vocab_size)
    if len(ids) > max_grams:
        # deterministic downsample: keep every k-th gram, not random -- reproducible
        step = len(ids) / max_grams
        ids = [ids[int(i * step)] for i in range(max_grams)]
    if not ids:
        ids = [0]
    return ids
