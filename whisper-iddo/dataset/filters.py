"""whisper-iddo / dataset / filters.py — what gets thrown away, and the reason.

Every rejection returns a STRING REASON, and every reason is counted in the report.
A filter with no measured hit count is a filter nobody can defend, so nothing here is
speculative — each rule fires on real rows in this corpus.

THE GOVERNING FACT
  Not one transcript in this dataset was typed by a human. Every label was produced by
  a Whisper model — mostly by large-v3-turbo, the very model we are fine-tuning. That
  makes the default failure mode self-distillation: the student practises the teacher's
  mistakes until they become reflexes. Filtering is therefore not tidying, it is the
  only thing standing between "training data" and "a machine for amplifying errors".
"""
from __future__ import annotations

import re

from normalise import FOREIGN_SCRIPT, HEBREW_LETTER, LATIN_LETTER, script_of

# ── Stock phrases Whisper emits when it hears nothing ────────────────────────────
# Whisper was trained on scraped subtitles, so over silence or noise it falls back to
# subtitle boilerplate. Measured in this corpus: "תודה רבה." alone is the label on 194
# clips, "תודה." on 123 more. Those are not things Iddo said 300 times; they are the
# model filling a void. Training on them teaches it to fill voids MORE eagerly, which
# is exactly the hallucination Iddo complains about.
STOCK = {
    "תודה", "תודה רבה", "תודה לצפייה", "תודה על הצפייה", "כתוביות", "תרגום",
    "עריכה", "הכתוביות", "עמותת", "בהצלחה", "להתראות", "שלום", "המשך",
    "תודה רבה.", "תודה.",
    "thank you", "thanks for watching", "thank you for watching", "subscribe",
    "please subscribe", "bye", "you", "okay", "ok", "hello", "hi", "so",
    "amara.org", "www.", "http",
}
_STRIP = " \t.,!?-\"'"


def _stock_key(t: str) -> str:
    return t.strip(_STRIP).lower()


def is_stock(text: str) -> bool:
    """True if the transcript is ONLY boilerplate, possibly repeated."""
    k = _stock_key(text)
    if not k:
        return False
    if k in STOCK:
        return True
    # "תודה רבה, תודה רבה, תודה רבה." — the same stock phrase looped
    parts = [p.strip(_STRIP).lower() for p in re.split(r"[,.!?]+", k) if p.strip(_STRIP)]
    return bool(parts) and len(parts) > 1 and all(p in STOCK for p in parts)


# ── Degenerate loops ────────────────────────────────────────────────────────────
def degenerate(text: str) -> str | None:
    """Whisper's repetition collapse — the most damaging label type in the corpus.

    The model does not fail on Iddo by mishearing one word; it falls into a loop and
    never exits ("דודשן, דודשן, דודשן, דודשן"). A target like that teaches the model
    that looping is the CORRECT response to hard audio. No downstream eval gate can
    repair a target this bad, so these die here.
    """
    s = (text or "").strip()
    if not s:
        return None
    toks = s.split()
    run = best = 1
    for i in range(1, len(toks)):
        run = run + 1 if toks[i] == toks[i - 1] else 1
        best = max(best, run)
    if best >= 4:
        return "degenerate: word repeated 4+ times"
    # a repeated 2- or 3-gram covering most of the utterance
    for n in (2, 3):
        if len(toks) >= n * 4:
            grams = [" ".join(toks[i:i + n]) for i in range(0, len(toks) - n + 1, n)]
            if len(set(grams)) == 1:
                return "degenerate: phrase looped"
    # one character smeared out: "אאאאאאאא", "ל ל ל ל ל"
    letters = re.sub(r"[^\w]", "", s)
    if len(letters) >= 8 and len(set(letters)) <= 2:
        return "degenerate: single character smear"
    if re.search(r"(.)\1{7,}", s):
        return "degenerate: character run 8+"
    return None


# ── Pure filler ─────────────────────────────────────────────────────────────────
# "אההה", "חחח", "אממ" — real vocalisations, but they carry no lexical content, they
# are wildly inconsistent in spelling (אההה / אההההה / אהההההה are three targets for
# one sound), and there are hundreds. They add noise to the loss and nothing to WER.
_FILLER = re.compile(r"^[אהחמנעםוי\s.,!?'\"-]{1,12}$")


def is_filler(text: str) -> bool:
    k = text.strip(_STRIP)
    if not k or len(k) > 12:
        return False
    if not _FILLER.match(k):
        return False
    # a short REAL word is not filler — keep anything with 2+ distinct letters
    # that is not a stretched vowel
    letters = re.sub(r"[^א-ת]", "", k)
    if not letters:
        return True
    return len(set(letters)) <= 2


def check_pair(text: str, seconds: float, *, min_sec=0.5, max_sec=30.0):
    """Return (reason, None) if the pair must be dropped, else (None, tier_hint).

    Order matters: cheap text checks first, alignment checks last.
    """
    t = (text or "").strip()

    if not t:
        return "empty transcript", None
    if not HEBREW_LETTER.search(t) and not LATIN_LETTER.search(t):
        return "no letters in transcript", None
    if FOREIGN_SCRIPT.search(t):
        # Arabic/Cyrillic/CJK in a Hebrew dictation = language mis-detection.
        return "foreign script (language mis-detect)", None

    if seconds is None:
        return "no audio duration", None
    if seconds < min_sec:
        return "audio under %.2fs" % min_sec, None
    if seconds > max_sec:
        return "audio over 30s (exceeds whisper window)", None

    if is_stock(t):
        return "stock phrase (hallucination over silence)", None
    d = degenerate(t)
    if d:
        return d, None
    if is_filler(t):
        return "pure filler vocalisation", None

    # ── alignment sanity: chars per second ──────────────────────────────────────
    # Hebrew dictation runs ~9-16 chars/s. Far outside that band the audio and the
    # text are describing different things — a misalignment. Those poison training
    # because the model learns to emit text that is not in the audio (too fast) or
    # to swallow speech (too slow).
    cps = len(t) / seconds
    if cps > 28:
        return "impossible speech rate (>28 chars/s) - misalignment", None
    if seconds >= 3.0 and cps < 1.2:
        return "text far too short for audio (<1.2 chars/s) - misalignment", None

    return None, None
