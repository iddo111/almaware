"""gates.py — is this decode real speech worth typing. Layered, measured.

Laws inherited (INSIGHTS §1.6, §4; textguard scars):
- Layers exist because each previous layer alone FAILED. Order: energy gate
  (client, pre-GPU) → decode guards (here, post-GPU): logprob floor →
  hallucination blocklist → language whitelist.
- The logprob floor must be REACHABLE: A shipped -1.0 with the whole real
  distribution above -0.913 — written, wired, journalled, never fired once.
  -0.6 is calibrated FROM 138 real decodes (drops the worst 14%).
- `language=None` is unrepresentable — "the single line that let noise come
  back as Icelandic". The whitelist is ('he','en'); None is not a member.
- Every refusal returns a distinct reason the caller journals as GUARD_DROP.
"""
from __future__ import annotations

import os

# Calibrated on 138 real decodes of Iddo's voice (mic-rebuild, 2026-08-14).
# A floor nothing can reach is a dead guard — change only WITH new data.
# 2026-08-19: env-overridable. Iddo's terse, code-switched words ("fix", "now") decode
# at -0.7..-0.9 and were being dropped at -0.6; KESHEV_LOGPROB_FLOOR=-1.0 lets them through
# while the -1.0+ garbage still drops. The owner-gate + loop-guard catch what slips.
LOGPROB_FLOOR: float = float(os.environ.get("KESHEV_LOGPROB_FLOOR", "-0.6"))

LANG_WHITELIST: tuple[str, ...] = ("he", "en", "ru")  # ru: Iddo 18:57 - his Russian was transliterated into Hebrew

# Whisper's classic ghosts on near-silence, plus their Hebrew cousins.
# Compared stripped+casefolded, trailing punctuation removed.
HALLUCINATIONS: frozenset[str] = frozenset({
    "thank you", "thanks for watching", "you", "bye", "so",
    "subtitles by the amara.org community",
    "sub by", "share this video with your friends",
    "תודה רבה", "תודה שצפיתם", "כתוביות", "תודה",
})

# Energy gate — measured from 854 live segments (config carries provenance
# in A; here the number and its origin live together).
GATE_RMS: float = 0.008        # speech median 0.0276, floor p90 0.0060


def energy_ok(rms: float, gate: float = GATE_RMS) -> bool:
    """Pre-GPU: don't wake the decoder for the room's hum."""
    return rms >= gate


def _norm(text: str) -> str:
    return text.strip().casefold().rstrip(".!?,;:״…").strip()


def _is_repetition_loop(text: str) -> bool:
    """Whisper's noise-loop: the same word/phrase repeated many times.
    Found LIVE 2026-08-18 13:07 - 'This is the one who is' * ~50 TYPED AND
    ENTERED into Iddo's chat as him. A loop is never his dictation.
    2026-08-20 01:05, live again: a YAWN decoded as one giant 'אההה…' (200+
    chars) - ONE word, so the word-level guard never looked. A run of the
    same character >=10 inside a single token is never dictation either."""
    for w in text.split():
        run, prev = 1, ""
        for ch in w:
            run = run + 1 if ch == prev else 1
            if run >= 10:
                return True
            prev = ch
    words = text.split()
    if len(words) < 8:
        return False
    uniq = len(set(w.casefold().strip(".,!?") for w in words))
    if uniq / len(words) < 0.35:          # heavy vocabulary collapse
        return True
    # exact phrase cycling: any 3-gram appearing 4+ times
    grams: dict[tuple, int] = {}
    for i in range(len(words) - 2):
        g = tuple(w.casefold() for w in words[i:i + 3])
        grams[g] = grams.get(g, 0) + 1
        if grams[g] >= 4:
            return True
    return False


def verdict(text: str, avg_logprob: float | None, lang: str | None,
            ) -> tuple[bool, str]:
    """(ok, reason). Reasons are the journal's GUARD_DROP vocabulary:
    empty | lang | logprob | hallucination | loop | ok."""
    if not text or not text.strip():
        return False, "empty"
    if _is_repetition_loop(text):
        return False, "loop"
    if lang not in LANG_WHITELIST:      # None is not a member — by design
        return False, "lang"
    if avg_logprob is not None and avg_logprob < LOGPROB_FLOOR:
        return False, "logprob"
    if _norm(text) in HALLUCINATIONS:
        return False, "hallucination"
    return True, "ok"
