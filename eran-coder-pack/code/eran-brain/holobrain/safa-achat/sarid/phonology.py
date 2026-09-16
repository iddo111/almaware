"""Phonetic normalization and Dolgopolsky-style sound classes.

The transcriptions in the bundled data are *broad* IPA. We reduce them to
consonant sound classes following the spirit of Dolgopolsky (1986), as
popularized in computational historical linguistics (e.g. LingPy's `dolgo`
model): sounds that frequently correspond across attested language histories
share a class, so class-level comparison is more robust than raw-symbol
comparison.

This is a simplified, documented mapping — not a claim of completeness.
"""
from __future__ import annotations

import unicodedata

# Characters removed during normalization: length marks, stress, schwa-like
# release symbols, tie bars, and combining diacritics.
_STRIP = set("ːˑ.ˈˌ‿͡")

# Dolgopolsky-style consonant classes (simplified):
#   P  labial obstruents           p b f v
#   T  dental/alveolar obstruents  t d θ ð
#   S  sibilants/affricates        s z ʃ ʒ ts dʒ tʃ
#   K  velar/uvular obstruents     k g q x χ ɣ
#   M  labial nasal                m
#   N  other nasals                n ŋ
#   R  liquids                     r l
#   W  labio-velar glide           w
#   J  palatal glide               j
#   H  laryngeals/pharyngeals      h ʔ ħ ʕ ɦ
_CLASS = {}
for _sounds, _cls in [
    ("pbfv", "P"),
    ("tdθð", "T"),
    ("szʃʒ", "S"),
    ("kɡgqxχɣ", "K"),
    ("m", "M"),
    ("nŋɲ", "N"),
    ("rlɫɾ", "R"),
    ("w", "W"),
    ("j", "J"),
    ("hʔħʕɦ", "H"),
]:
    for _ch in _sounds:
        _CLASS[_ch] = _cls

_VOWELS = set("aeiouɐɑɒæɛəɘɪɔœøɵʊʌʏyɜɨ")


def normalize_ipa(ipa: str) -> str:
    """NFC-normalize and strip length/stress marks and combining diacritics."""
    s = unicodedata.normalize("NFC", ipa.strip().lower())
    out = []
    for ch in s:
        if ch in _STRIP:
            continue
        if unicodedata.combining(ch):
            continue
        out.append(ch)
    return "".join(out)


def sound_classes(ipa: str, keep_vowels: bool = False) -> str:
    """Encode a broad-IPA string as a Dolgopolsky-style class string.

    By default vowels are dropped (classic Dolgopolsky consonant skeleton);
    with keep_vowels=True every vowel is collapsed to the placeholder 'V'.
    Unknown symbols are skipped (broad transcriptions only).
    """
    s = normalize_ipa(ipa)
    out = []
    i = 0
    while i < len(s):
        # two-character affricates first
        two = s[i : i + 2]
        if two in ("ts", "dz", "tʃ", "dʒ"):
            out.append("S")
            i += 2
            continue
        ch = s[i]
        if ch in _CLASS:
            out.append(_CLASS[ch])
        elif ch in _VOWELS:
            if keep_vowels:
                out.append("V")
        # anything else: skip silently (broad data only)
        i += 1
    return "".join(out)


def consonant_skeleton(ipa: str) -> str:
    """Consonant-class skeleton — the Semitic-root-friendly view of a word."""
    return sound_classes(ipa, keep_vowels=False)
