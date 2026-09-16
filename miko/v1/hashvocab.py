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


def raw_gram_count(text: str, ns=(3, 4, 5)) -> int:
    """How many n-grams `text` WOULD produce before max_grams truncation."""
    t = "▁" + text.lower().strip() + "▁"
    return sum(max(0, len(t) - n + 1) for n in ns)


def truncation_report(texts: list[str], ns=(3, 4, 5), max_grams: int = 512) -> str:
    """MIKO-12 (code revision 2026-09-06): ngram_ids SILENTLY keeps only every k-th n-gram of
    any text longer than max_grams -- on the 2026-09-03 corpus that is 820 of 835 documents,
    median coverage 9.5%, i.e. the document tower never sees 90% of its own input. Silent
    lossy truncation is exactly the failure shape this revision hunts, so every script that
    trains on or evaluates this tokenizer prints this line before any number is trusted.
    (Whether to chunk-pool instead, or retire the from-scratch tower, is a decision that
    waits for post-MIKO-01 retrain numbers -- this only makes the loss VISIBLE.)"""
    total = len(texts)
    over = 0
    coverage = []
    for t in texts:
        n_raw = raw_gram_count(t, ns)
        if n_raw > max_grams:
            over += 1
        coverage.append(min(1.0, max_grams / n_raw) if n_raw else 1.0)
    coverage.sort()
    med = coverage[len(coverage) // 2] if coverage else 1.0
    return (f"HASHVOCAB-TRUNCATION: {over}/{total} texts exceed max_grams={max_grams} "
            f"(median n-gram coverage {med * 100:.1f}%). The tower sees a strided sample, "
            f"not the document. See MIKO-12.")
