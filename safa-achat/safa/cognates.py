"""Cognate-candidate scoring with honest verdicts.

Score components (all in [0,1]):
  dolgo_sim  — normalized edit similarity of Dolgopolsky-style consonant
               skeletons (after documented sound-correspondence rules)
  ipa_sim    — normalized edit similarity of full normalized IPA strings
               (after rules), vowels included
  initial    — 1.0 if the first consonant class matches (initials are the
               most stable position cross-linguistically), else 0.0
  byte_sim   — UTF-8 byte-bigram Jaccard of the orthography (reported, NOT
               part of the combined score: it is script-bound by design)

combined = 0.50*dolgo_sim + 0.35*ipa_sim + 0.15*initial

Verdict policy (the honesty layer):
  combined >= 0.60 and same family  -> "likely cognate (within family)"
  combined >= 0.60, different family-> "lookalike — needs systematic
                                        correspondence evidence" (NEVER
                                        auto-claimed as cognate)
  0.40 <= combined < 0.60           -> "possible — weak signal"
  else                              -> "no signal"

Comparison is only ever done WITHIN a semantic slot (same Swadesh concept):
semantic control is a precondition of the comparative method.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .bytetok import byte_jaccard
from .data import Entry
from .distance import norm_sim
from .phonology import consonant_skeleton, normalize_ipa
from .rules import apply_rules

LIKELY = 0.60
POSSIBLE = 0.40


@dataclass
class PairScore:
    a: Entry
    b: Entry
    dolgo_sim: float
    ipa_sim: float
    initial: float
    byte_sim: float
    combined: float
    rules_applied: list[str]
    same_family: bool
    verdict: str


def _prepared(e: Entry, use_rules: bool) -> tuple[str, str, list[str]]:
    """Return (normalized_ipa, skeleton, rules_applied) for an entry."""
    ipa = normalize_ipa(e.ipa)
    applied: list[str] = []
    if use_rules:
        ipa, applied = apply_rules(e.lang, ipa)
    return ipa, consonant_skeleton(ipa), applied


def score_pair(a: Entry, b: Entry, use_rules: bool = True) -> PairScore:
    ipa_a, skel_a, rules_a = _prepared(a, use_rules)
    ipa_b, skel_b, rules_b = _prepared(b, use_rules)

    dolgo = norm_sim(skel_a, skel_b)
    ipa = norm_sim(ipa_a, ipa_b)
    initial = 1.0 if (skel_a and skel_b and skel_a[0] == skel_b[0]) else 0.0
    byte_s = byte_jaccard(a.orthography, b.orthography)
    combined = 0.50 * dolgo + 0.35 * ipa + 0.15 * initial

    same_family = a.family == b.family
    if combined >= LIKELY:
        verdict = (
            "likely cognate (within family)"
            if same_family
            else "lookalike — needs systematic correspondence evidence"
        )
    elif combined >= POSSIBLE:
        verdict = "possible — weak signal"
    else:
        verdict = "no signal"

    return PairScore(
        a=a, b=b, dolgo_sim=dolgo, ipa_sim=ipa, initial=initial,
        byte_sim=byte_s, combined=combined,
        rules_applied=rules_a + rules_b,
        same_family=same_family, verdict=verdict,
    )


def judge_pair(a: Entry, b: Entry, use_rules: bool = True) -> str:
    return score_pair(a, b, use_rules).verdict


def all_pairs(entries: list[Entry], use_rules: bool = True) -> list[PairScore]:
    """Score every cross-language pair WITHIN each concept slot."""
    from .data import by_concept

    scores: list[PairScore] = []
    for _, group in sorted(by_concept(entries).items()):
        for a, b in combinations(group, 2):
            if a.lang == b.lang:
                continue
            scores.append(score_pair(a, b, use_rules))
    scores.sort(key=lambda s: s.combined, reverse=True)
    return scores
