"""Documented sound-correspondence rules (KNOWN sound laws, not discoveries).

Each ruleset maps a language's attested reflexes back toward a shared
pre-form frame so that comparison happens in comparable "coordinates".
These are textbook, citable regularities:

Germanic (Grimm's law, ~1st millennium BCE; Rask 1818, Grimm 1822):
    PIE *p *t *k  ->  Proto-Germanic f θ h   (e.g. Latin pater ~ English father)
    We therefore map Germanic f->p, θ->t, h->k, x->k before comparing
    Germanic words with non-Germanic Indo-European words.
    German additionally underwent the High German consonant shift
    (t -> ts/s, p -> pf/f, k -> x), so German gets ts->t as well.

Semitic (standard Proto-Semitic reflex tables; e.g. Huehnergard 2019):
    Proto-Semitic *ṯ  ->  Hebrew ʃ, Aramaic t, Arabic θ   (šaloš~θalāθa~tlāθ)
    Proto-Semitic *ḏ  ->  Hebrew z, Aramaic d, Arabic ð   (ʔozen~ʔuðn)
    We map Arabic θ->ʃ and ð->z (and Aramaic ð->z) into the Hebrew frame.

LIMITS (honest): real sound laws are conditioned by environment (position,
stress, neighboring sounds). These context-free substitutions are a crude
approximation used to DEMONSTRATE the mechanism; they are applied only to
the phonetic string, and every rule application is reported to the caller.
"""
from __future__ import annotations

# lang -> list of (from, to) substitutions applied to normalized IPA
RULESETS: dict[str, list[tuple[str, str]]] = {
    # Grimm normalization toward pre-Germanic obstruents
    "eng": [("f", "p"), ("θ", "t"), ("ð", "t"), ("h", "k"), ("x", "k")],
    "deu": [("ts", "t"), ("f", "p"), ("θ", "t"), ("h", "k"), ("x", "k"), ("d", "t")],
    # Proto-Semitic reflexes mapped into the Hebrew frame
    "arb": [("θ", "ʃ"), ("ð", "z")],
    "arc": [("ð", "z"), ("θ", "t")],
    # Hebrew, Latin used as reference frames here
    "heb": [],
    "lat": [],
}


def apply_rules(lang: str, ipa: str) -> tuple[str, list[str]]:
    """Apply the documented ruleset for `lang` to a normalized IPA string.

    Returns (rewritten_ipa, list_of_rule_descriptions_actually_applied).
    """
    applied = []
    out = ipa
    for src, dst in RULESETS.get(lang, []):
        if src in out:
            out = out.replace(src, dst)
            applied.append(f"{lang}: {src}->{dst}")
    return out, applied
