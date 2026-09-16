"""KESHEV text metrics — K13 (criterion 10: he CER <= baseline + 2% absolute).

Character Error Rate utilities for the replay corpus, reused by the K16/K18
gate harnesses. Stdlib only, CPU-only, text-only — no model, no device.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable


def normalize_ws(text: str) -> str:
    """Whitespace-normalize a transcript for comparison — the SAME rule the
    corpus builder pins hashes against."""
    return re.sub(r"\s+", " ", text or "").strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def levenshtein(a: str, b: str) -> int:
    """Character-level edit distance, two-row DP."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cur[j] = min(prev[j] + 1,               # deletion
                         cur[j - 1] + 1,            # insertion
                         prev[j - 1] + (ca != cb))  # substitution
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    """CER of one utterance: edits / max(1, len(ref))."""
    return levenshtein(ref, hyp) / max(1, len(ref))


def aggregate_cer(pairs: Iterable[tuple[str, str]]) -> dict:
    """Corpus-level CER: total edits / total reference chars (length-weighted,
    the standard aggregation — one long clip cannot be hidden by many short
    ones and vice versa). Returns {n, ref_chars, edits, cer}."""
    n = ref_chars = edits = 0
    for ref, hyp in pairs:
        n += 1
        ref_chars += len(ref)
        edits += levenshtein(ref, hyp)
    return {"n": n, "ref_chars": ref_chars, "edits": edits,
            "cer": edits / max(1, ref_chars)}
