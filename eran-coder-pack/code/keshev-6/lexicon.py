# -*- coding: utf-8 -*-
"""KESHEV-6 lexicon — the words Iddo actually says that vanilla Whisper has
never heard.

Measured cause (INQUIRY-garble-20260826.md + tonight's transcripts): the model
does fine on ordinary Hebrew and falls apart on NAMES. Tonight it produced
"צ'רלי וחצי" for Chinchilla, "לכן סונת" for "סוכן סונט". Names are exactly what
`initial_prompt` is for: it is prepended as decoder context, so the tokens
become cheap instead of unreachable.

TWO separate mechanisms, deliberately kept apart:
  PROMPT   — biases the decoder BEFORE it commits. Costs context, cannot
             corrupt anything, but is bounded: Whisper's prompt window is
             224 tokens and a long prompt starts leaking into the output.
  REPAIR   — a post-hoc similarity map, applied ONLY at high similarity.
             It CAN corrupt a real word, so it is narrow, measured, and every
             substitution is reported.
"""
from __future__ import annotations

import difflib
import re

# --- the prompt (kept SHORT on purpose: measured, not maximal) ----------------
# Whisper's initial_prompt is capped at half the decoder context (224 tokens).
# Hebrew costs ~2-4 tokens a word here, so this sentence is ~120 tokens: enough
# to carry the names, short enough that the model does not start reciting it.
# MEASURED AND TRIMMED, 2026-09-04 00:04. The first version also listed ordinary
# Hebrew words - סוכן, מודל, אימון, פענוח, מיקרופון, מקום, מורה, קו, צלם - on the
# theory that more context is better context. Then the loud-empties sweep caught
# the cost: the LOUDEST non-speech segment of the night (peak_rms 22,278) came
# back as "פענוח, פענוח, פענוח." - a word that exists in the output only because
# it was in this string. On real speech there were zero leaks across 209
# segments, but on non-speech the prompt is something for the model to grab.
#
# So the rule is now: a word earns its place here ONLY if the model cannot be
# expected to know it. Common Hebrew words are removed - Whisper already has
# them, they added nothing, and every one of them was a fresh thing to
# hallucinate. Names only.
PROMPT_HE = (
    "שיחה על הפרויקטים של עידו פרז: ערן, וינסטון, מיקו, נצר, קשב, "
    "דרוויש, עלמה, הולובריין, "
    "קלוד, סונט, אופוס, הייקו, פייבל, צ'ינצ'ילה, קודקס, גרוק, ג'מיני, קוון, "
    "OpenClaw, Hermes, Godot, WebXR, DGX, Quest, LoRA, Whisper, "
    "Assassin's Creed, Meshtastic, Kropotkin."
)
# 2026-09-06 04:30 -- three names added, and ONLY three, deliberately.
# Iddo demonstrated the failure himself at 02:41: "המיק לא תופס אססינס קריד
# כשאני אומר את זה אבל כן תופס הי". A Hebrew-tuned decoder cannot reach an
# English proper noun that is not in this string; "hi" lands because it is a
# common Hebrew word.
#
# The cost is real and is documented above: at 03:35 his COUGH came back as
# "אופוס, אופוס, אופוס, אופוס" -- and "אופוס" is in this very string. Every
# word added here is one more thing for the model to grab when the input is
# not speech. So these three earn their place by the file's own rule -- a
# name the model cannot be expected to know, that he actually says -- and
# nothing else was added on the theory that more context is better context.
# That theory was already tested here and it lost.

# --- the repair map ----------------------------------------------------------
# LHS = what the model produced tonight (verbatim from trial.log / his chat),
# RHS = what he said. Exact-phrase repairs only; nothing here is a guess.
EXACT_REPAIRS: dict[str, str] = {
    "צ'רלי וחצי": "צ'ינצ'ילה",
    "לכן סונת": "סוכן סונט",
    "לכן סונט": "סוכן סונט",
    "סוכן סונת": "סוכן סונט",
    "אופן קלאו": "OpenClaw",
    "הרמס": "Hermes",
    "הרמיס": "Hermes",
    "גודו": "Godot",
    "ווב אקס אר": "WebXR",
}

# Single-token targets for the fuzzy repair. Deliberately short: every entry is
# a chance to corrupt a real Hebrew word, so only names that are (a) frequent in
# his speech and (b) not near-homographs of a common word.
FUZZY_TARGETS: tuple[str, ...] = (
    "צ'ינצ'ילה", "הולובריין", "וינסטון", "דרוויש", "אופוס", "סונט",
)
FUZZY_MIN_RATIO = 0.86      # difflib SequenceMatcher; below this we do nothing
FUZZY_MIN_LEN = 4           # never touch short words

_WORD_RE = re.compile(r"[\w֐-׿']+", re.UNICODE)


def repair(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(repaired_text, [(before, after), ...]).

    Exact phrases first (safe), then a conservative per-word fuzzy pass.
    Every change is returned so the caller can COUNT it — a repair nobody can
    audit is a fabrication with good manners.
    """
    if not text:
        return text, []
    changes: list[tuple[str, str]] = []
    out = text
    for bad, good in EXACT_REPAIRS.items():
        if bad in out:
            out = out.replace(bad, good)
            changes.append((bad, good))

    def _fix_word(m: re.Match) -> str:
        w = m.group(0)
        if len(w) < FUZZY_MIN_LEN:
            return w
        best, best_r = None, 0.0
        for t in FUZZY_TARGETS:
            if w == t:
                return w
            r = difflib.SequenceMatcher(None, w, t).ratio()
            if r > best_r:
                best, best_r = t, r
        if best is not None and best_r >= FUZZY_MIN_RATIO:
            changes.append((w, best))
            return best
        return w

    out = _WORD_RE.sub(_fix_word, out)
    return out, changes
