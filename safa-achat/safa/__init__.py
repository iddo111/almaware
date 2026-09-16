"""Safa Achat (שפה אחת) — comparative-linguistics toolkit prototype.

Honest computational historical linguistics:
- byte/script-universal input handling (Unicode NFC + UTF-8 byte n-grams)
- phonetic normalization + Dolgopolsky-style sound classes
- cognate candidate scoring within semantic slots (Swadesh concepts)
- documented sound-correspondence rules (Grimm, Proto-Semitic reflexes)
- extraction of RECURRING correspondences (the comparative method's core test)

This package makes candidate suggestions with uncertainty labels.
It does NOT reconstruct proto-languages and does NOT claim proof of cognacy.
"""

__version__ = "0.1.0"

from .data import Entry, load_wordlist, DATA_FILE  # noqa: F401
from .cognates import score_pair, judge_pair, all_pairs  # noqa: F401
from .comparative import recurring_correspondences  # noqa: F401
