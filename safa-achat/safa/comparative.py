"""Comparative-method module: find RECURRING sound correspondences.

The comparative method (19th c. Neogrammarians; see Campbell, *Historical
Linguistics*; Rankin in *The Handbook of Historical Linguistics*) does not
accept one similar word pair as evidence. It requires the SAME sound
correspondence to recur across many semantically matched pairs.

Here we align raw consonant inventories (no correspondence rules applied —
we want to SEE the correspondences, not assume them) for every same-concept
pair of a given language pair, and count aligned consonant pairs. A
correspondence attested in >= min_count distinct concepts is reported as
"recurring". Recurring correspondences are evidence; isolated similarity
is not.
"""
from __future__ import annotations

from collections import defaultdict

from .data import Entry, by_concept
from .distance import align
from .phonology import normalize_ipa

_VOWELS = set("aeiouɐɑɒæɛəɘɪɔœøɵʊʌʏyɜɨ")


def _consonants(ipa: str) -> str:
    return "".join(ch for ch in normalize_ipa(ipa) if ch not in _VOWELS)


def recurring_correspondences(
    entries: list[Entry],
    lang_a: str,
    lang_b: str,
    min_count: int = 2,
) -> dict[tuple[str, str], list[str]]:
    """Map (sound_in_a, sound_in_b) -> list of concepts where it is attested.

    Only correspondences attested in >= min_count concepts are returned.
    Gap alignments and identity pairs are kept too — identity is itself a
    correspondence (e.g. Hebrew m : Arabic m).
    """
    counts: dict[tuple[str, str], set[str]] = defaultdict(set)
    for concept, group in by_concept(entries).items():
        wa = next((e for e in group if e.lang == lang_a), None)
        wb = next((e for e in group if e.lang == lang_b), None)
        if not wa or not wb:
            continue
        for ca, cb in align(_consonants(wa.ipa), _consonants(wb.ipa)):
            if ca == "-" or cb == "-":
                continue
            counts[(ca, cb)].add(concept)  # count DISTINCT concepts only
    return {
        pair: sorted(concepts)
        for pair, concepts in counts.items()
        if len(concepts) >= min_count
    }
