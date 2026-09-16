"""Shared contract: text normalisation, scoring, and the packed-blob dataset.

The trainer and every evaluator import from here so that a number produced in
one place means the same thing in another.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

import numpy as np

# ---------------------------------------------------------------- normalisation
# Vendored verbatim from D:\CLAUDE\whisper-iddo\dataset\normalise.py (R1-R9) so
# the training node needs no path back to the PC. If that file changes, this
# must change with it -- the targets and the scored hypotheses have to agree.

_BIDI = dict.fromkeys(
    [0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
     0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF, 0x00AD], None)

_NIQQUD = re.compile("[\u0591-\u05bd\u05bf-\u05c7]")

_FOLD = {
    "\u05f3": "'", "\u05f4": '"', "\u05be": "-",
    "\u2018": "'", "\u2019": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2032": "'", "\u2033": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u2026": "...",
    "\u00a0": " ", "\u2009": " ", "\u200a": " ", "\u202f": " ",
}
_FOLD_RE = re.compile("|".join(re.escape(k) for k in _FOLD))
_WS = re.compile(r"\s+")
_LEAD_PUNCT = re.compile(r"^[\s.,!?;:\-\"']+")

HEBREW_LETTER = re.compile(r"[\u05d0-\u05ea]")
LATIN_LETTER = re.compile(r"[A-Za-z]")


def normalise(text: str) -> str:
    """R1-R9. The canonical training target."""
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text)
    s = s.translate(_BIDI)
    s = _NIQQUD.sub("", s)
    s = _FOLD_RE.sub(lambda m: _FOLD[m.group()], s)
    s = _WS.sub(" ", s)
    s = _LEAD_PUNCT.sub("", s)
    return s.strip()


def script_of(text: str) -> str:
    h = bool(HEBREW_LETTER.search(text))
    l = bool(LATIN_LETTER.search(text))
    if h and l:
        return "mixed"
    if h:
        return "he"
    if l:
        return "en"
    return "other"


# ------------------------------------------------------------------- scoring
# WER is reported two ways and BOTH are printed, because they answer different
# questions:
#   score_norm  - punctuation and case removed. "Did he get the words right?"
#                 This is the comparable-to-literature number.
#   verbatim    - normalise() only. The app types this string straight into
#                 other programs, so punctuation IS the product (rule R7).
_PUNCT = re.compile(r"[.,!?;:\"'()\[\]{}<>\u2026/\\|`~@#$%^&*_+=]")


def score_norm(text: str) -> str:
    s = normalise(text)
    s = _PUNCT.sub(" ", s)
    s = s.lower()                 # only affects Latin; Hebrew has no case
    s = _WS.sub(" ", s)
    return s.strip()


def wer_parts(ref: str, hyp: str):
    """Levenshtein at word level. Returns (errors, ref_len)."""
    r, h = ref.split(), hyp.split()
    if not r:
        return (len(h), 0)
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return (prev[-1], len(r))


def cer_parts(ref: str, hyp: str):
    r, h = list(ref.replace(" ", "")), list(hyp.replace(" ", ""))
    if not r:
        return (len(h), 0)
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hc in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return (prev[-1], len(r))


def corpus_wer(refs, hyps, norm=score_norm):
    """Corpus-level WER: total errors / total reference words. NOT the mean of
    per-utterance WERs -- that would let a 2-word clip outweigh a 40-word one."""
    e = n = 0
    for a, b in zip(refs, hyps):
        de, dn = wer_parts(norm(a), norm(b))
        e += de
        n += dn
    return e / n if n else float("nan")


def corpus_cer(refs, hyps, norm=score_norm):
    e = n = 0
    for a, b in zip(refs, hyps):
        de, dn = cer_parts(norm(a), norm(b))
        e += de
        n += dn
    return e / n if n else float("nan")


# -------------------------------------------------------------------- dataset
class PackedAudio:
    """Memory-maps the flat int16 blob produced by pack.py."""

    def __init__(self, root):
        self.root = root
        self.meta = json.load(open(os.path.join(root, "pack_meta.json")))
        self.blob = np.memmap(os.path.join(root, "audio.bin"), dtype=np.int16, mode="r")
        self.rows = [json.loads(l) for l in
                     open(os.path.join(root, "index.jsonl"), encoding="utf-8")]

    def audio(self, row):
        start = row["off"] // 2
        a = np.asarray(self.blob[start:start + row["n"]], dtype=np.float32)
        return a / 32768.0

    def split(self, name):
        return [r for r in self.rows if r["split"] == name]
