# -*- coding: utf-8 -*-
"""TEXT -> SPARKS. The one thing ALMA had no word for.

ALMA's five words are knot, thread, strand, spark, beat. A spark is a number (or
a chord of numbers). A message is not. So before a weave can judge text, someone
has to decide how text becomes sparks, and that decision is the whole of this
file. It is the part of ALMA-GUARD that is *designed* rather than learned, so it
is the part that has to be argued for.

THE DESIGN, AND WHY THIS ONE
----------------------------
**One knot per feature, fed a presence spark of 1.0; absent features are not
seeded at all.** That is forced by ALMA's learning rule, not chosen for taste.
`alma/loom.py` step 3 reads:

    term = st.drift if dst in fired_now else -st.drift * 0.25

The Hebbian term does **not** look at how big the spark was. A cord carrying
0.001 and a cord carrying 5.0 earn exactly the same eligibility. So if every
feature knot fired on every message - carrying its value, zero included - every
cord would be eligible on every message and the verdict could not tell one
feature from another. Credit assignment in ALMA is carried by *which knots were
silent*, so a feature must be able to say nothing. Absent = unseeded = silent.
That makes every feature binary, and makes the weave an honest perceptron over
presence.

**Features are character n-grams + word n-grams, hashed into a fixed width.**
Reasons, in order:

1. *Hebrew and English in one pipe.* Iddo dictates in Hebrew and types in both.
   A character n-gram needs no tokenizer, no vocabulary file and no language id,
   and `feedback_tldr_law`-sized data cannot afford to learn two vocabularies.
   Hashing removes the vocabulary file entirely, so the model has no
   out-of-vocabulary cliff and the dataset can grow without a re-fit.
2. *Robust to the obfuscation this task actually faces.* `i g n o r e` and
   `ıgnore` and `1gnore` share no word with `ignore` but share 3-grams with it.
3. *It fits a few hundred examples.* A hashed binary bag over ~1-2k buckets with
   one weight each is the largest model this dataset can honestly support.

**The 16 structural features carry NO vocabulary.** Buckets 0..15 are reserved
for message *shape* - length, a URL, a code fence, invisible/bidi characters, a
base64-looking run, script mixing, and so on. Every one of them is a property of
the bytes, not of any word list. This is deliberate and it is the honesty line of
the whole project: Iddo rejected a rules engine, so no file in `alma_guard/` is
allowed to contain the phrase an attacker would type. `tests/test_encoding.py`
asserts that, by grepping this module for attack vocabulary and failing if it
finds any. If ALMA-GUARD learns that "ignore previous instructions" is dangerous,
it learned it from cords thickening under pain - the feature extractor never knew.

WHAT THIS IS NOT
----------------
Not an embedding (nothing is learned here), not a tokenizer (no vocabulary), not
a chord (SPEC.md v0.4 gives the *spark* a width but leaves the *strand* one
number, so a cord can scale a chord and cannot rotate one - a chord therefore
cannot carry a weighted sum, and one-knot-per-feature is the only shape in which
ALMA can currently compute a dot product). That last point is a real finding
about the substrate and it is written down in RESULTS.md, not hidden here.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# ---------------------------------------------------------------- constants

#: bucket 0..STRUCTURAL-1 are the shape features; hashed features start after.
STRUCTURAL = 16

#: default number of feature buckets (knots in the weave).
DEFAULT_WIDTH = 1024

#: fixed key so a bucket means the same thing on the PC, on eran1 and next year.
#: Python's built-in hash() is randomised per process and would silently move
#: every feature between runs - the exact class of quiet failure ALMA refuses.
_KEY = b"alma-guard-v0.1"

#: character n-gram sizes, over a word-boundary-marked string.
CHAR_NGRAMS = (3, 4)

#: word n-gram sizes.
WORD_NGRAMS = (1, 2)

# Characters that are invisible or reverse reading order. Their PRESENCE is a
# feature; they are stripped before anything else looks at the text, because a
# zero-width space inside a word must not create three new n-grams.
_INVISIBLE = "​‌‍⁠﻿­"
_BIDI = "‪‫‬‭‮⁦⁧⁨⁩"

_WS = re.compile(r"\s+")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://|www\.)", re.I)
_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_FENCE = re.compile(r"```|<\s*script|<\s*/\s*script|<\s*img|\[/?INST\]", re.I)
_ROLEISH = re.compile(r"(?m)^\s*[\w֐-׿]{2,15}\s*:")
_CAPS = re.compile(r"[A-Z]{4,}")
_DIGITS = re.compile(r"\d{8,}")
_PATHISH = re.compile(r"(?:[A-Za-z]:\\|/etc/|/usr/|\./|~/|\\\\)")
_ENVISH = re.compile(r"(?:\$\{?[A-Za-z_]\w*|%[A-Za-z_]\w*%|\{\{[^}]{1,40}\}\})")
_QUOTED = re.compile(r"[\"'«»“”‘’]")
_HEB = re.compile(r"[֐-׿]")
_LAT = re.compile(r"[A-Za-z]")


def _bucket(token: str, width: int, offset: int = STRUCTURAL) -> int:
    """Stable hash of a feature string into [offset, width)."""
    h = hashlib.blake2b(token.encode("utf-8"), key=_KEY, digest_size=8).digest()
    return offset + int.from_bytes(h, "big") % (width - offset)


def normalise(text: str) -> str:
    """Fold the text down to what an n-gram should see.

    NFKC first, so a fullwidth or mathematical-alphanumeric lookalike collapses
    onto the plain letter it is imitating - that is a real obfuscation and
    Unicode already knows how to undo it. Then casefold, then drop invisible and
    bidi controls (their presence is recorded separately, in `shape`), then
    collapse whitespace.
    """
    t = unicodedata.normalize("NFKC", text)
    t = t.casefold()
    t = t.translate({ord(c): None for c in _INVISIBLE + _BIDI})
    return _WS.sub(" ", t).strip()


def shape(text: str) -> dict[int, float]:
    """The 16 structural features. Message SHAPE only - no vocabulary, ever.

    Each is 1.0 when present and absent from the dict otherwise, because in ALMA
    an absent feature must be a silent knot (see the module docstring).
    """
    n = len(text)
    words = _WORD.findall(text)
    nonalnum = sum(1 for c in text if not c.isalnum() and not c.isspace())
    f: dict[int, float] = {}

    def on(i: int, cond) -> None:
        if cond:
            f[i] = 1.0

    on(0, n > 200)
    on(1, n > 600)
    on(2, bool(_URL.search(text)))
    on(3, bool(_FENCE.search(text)))
    on(4, bool(_B64.search(text)))
    on(5, any(c in text for c in _INVISIBLE + _BIDI))
    on(6, bool(_HEB.search(text)) and bool(_LAT.search(text)))
    on(7, text.count("\n") >= 3)
    on(8, bool(_ROLEISH.search(text)))
    on(9, n > 0 and nonalnum / n > 0.25)
    on(10, bool(_CAPS.search(text)))
    on(11, bool(_DIGITS.search(text)))
    on(12, bool(_QUOTED.search(text)))
    on(13, bool(_PATHISH.search(text)))
    on(14, bool(_ENVISH.search(text)))
    on(15, len(words) > 60)
    return f


def features(text: str, width: int = DEFAULT_WIDTH) -> dict[int, float]:
    """The whole encoding: shape features + hashed n-grams, all binary.

    Returns a sparse {bucket: 1.0}. The caller seeds exactly these knots and
    leaves every other feature knot silent.
    """
    if width <= STRUCTURAL:
        raise ValueError(f"width {width} must exceed {STRUCTURAL} structural buckets")
    f = shape(text)
    norm = normalise(text)
    words = _WORD.findall(norm)

    # character n-grams over a boundary-marked string, so "cat " and " cat"
    # differ and a word start is itself a signal.
    marked = "▁" + "▁".join(words) + "▁" if words else ""
    for k in CHAR_NGRAMS:
        for i in range(len(marked) - k + 1):
            f[_bucket(f"c{k}:{marked[i:i + k]}", width)] = 1.0

    for k in WORD_NGRAMS:
        for i in range(len(words) - k + 1):
            f[_bucket(f"w{k}:{' '.join(words[i:i + k])}", width)] = 1.0

    return f


def describe(text: str, width: int = DEFAULT_WIDTH) -> str:
    """Human-readable trace of what a message became. For the README and for eyes."""
    f = features(text, width)
    st = sorted(i for i in f if i < STRUCTURAL)
    names = ["len>200", "len>600", "url", "code-fence", "base64-run", "invisible",
             "he+en", "3+newlines", "role-colon", "punct-heavy", "CAPS-run",
             "digit-run", "quotes", "path", "env-var", "60+words"]
    return (f"{len(f)} sparks of {width} knots | "
            f"shape: {', '.join(names[i] for i in st) or '(none)'}")
