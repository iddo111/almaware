"""Universal byte/script tokenizer baseline.

Every string in every script becomes a sequence of UTF-8 bytes after Unicode
NFC normalization — no per-language tokenizer, no alphabet assumptions.
We expose byte n-grams + Jaccard similarity as an ORTHOGRAPHIC baseline.

Honest note: byte similarity across *different scripts* (Hebrew vs Latin) is
near zero by construction, which is exactly why the pipeline leans on the
phonetic layer for cross-script comparison. The byte layer is still useful
within a script, and it is the representation a future byte-level neural
model would consume.
"""
from __future__ import annotations

import unicodedata


def to_bytes(text: str) -> bytes:
    """NFC-normalize and encode as UTF-8 — the universal representation."""
    return unicodedata.normalize("NFC", text).encode("utf-8")


def byte_ngrams(text: str, n: int = 2) -> set[bytes]:
    b = to_bytes(text)
    if len(b) < n:
        return {b} if b else set()
    return {b[i : i + n] for i in range(len(b) - n + 1)}


def byte_jaccard(a: str, b: str, n: int = 2) -> float:
    """Jaccard similarity of byte n-gram sets, in [0, 1]."""
    ga, gb = byte_ngrams(a, n), byte_ngrams(b, n)
    if not ga and not gb:
        return 1.0
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)
