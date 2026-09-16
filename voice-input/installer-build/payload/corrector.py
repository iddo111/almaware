"""corrector.py — voice dictation post-processing for Hebrew/English input.

Modules:
  1. detect_spelled_word   — reconstruct a word spelled letter-by-letter
  2. parse_correction      — detect and extract user corrections
  3. log_correction        — append correction pairs to JSONL for LoRA training
  4. maybe_fix_phonetic    — fix common Whisper Hebrew transcription errors

"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("voiceinput.corrector")

# ── 1. Hebrew letter-name → character map ──────────────────────────────────────
# Each Hebrew letter name maps to its Unicode character.
_HE_LETTER_NAME: dict[str, str] = {
    "אלף":  "א",
    "בית":  "ב",
    "גימל": "ג",
    "דלת":  "ד",
    "הא":   "ה",
    "וו":   "ו",
    "זין":  "ז",
    "חית":  "ח",
    "טית":  "ט",
    "יוד":  "י",
    "כף":   "כ",
    "למד":  "ל",
    "מם":   "מ",
    "נון":  "נ",
    "סמך":  "ס",
    "עין":  "ע",
    "פא":   "פ",
    "צדי":  "צ",
    "קוף":  "ק",
    "ריש":  "ר",
    "שין":  "ש",
    "תו":   "ת",
}

# Hebrew phonetic spellings of English letter names → English character.
# Ordered longest-first so "אייץ" matches before "אי" etc.
_HE_EN_LETTER_NAME: dict[str, str] = {
    "אייץ":  "H",
    "דבלו":  "W",
    "אואו":  "O",
    "וואי":  "Y",
    "אקס":   "X",
    "ג'יי":  "J",
    "ג'י":   "G",
    "בי":    "B",
    "סי":    "C",
    "די":    "D",
    "אף":    "F",
    "איי":   "I",
    "קיי":   "K",
    "אל":    "L",
    "אם":    "M",
    "אן":    "N",
    "פי":    "P",
    "קיו":   "Q",
    "אר":    "R",
    "אס":    "S",
    "טי":    "T",
    "יו":    "U",
    "וי":    "V",
    "זד":    "Z",
    "אי":    "E",   # also doubles as A/I — context decides; we keep E (most common)
}

# English letter-name spellings (NATO phonetic not listed — just spoken letter names)
_EN_LETTER_NAME: dict[str, str] = {
    "alpha":   "A",
    "bravo":   "B",
    "charlie": "C",
    "delta":   "D",
    "echo":    "E",
    "foxtrot": "F",
    "golf":    "G",
    "hotel":   "H",
    "india":   "I",
    "juliet":  "J",
    "kilo":    "K",
    "lima":    "L",
    "mike":    "M",
    "november": "N",
    "oscar":   "O",
    "papa":    "P",
    "quebec":  "Q",
    "romeo":   "R",
    "sierra":  "S",
    "tango":   "T",
    "uniform": "U",
    "victor":  "V",
    "whiskey": "W",
    "x-ray":   "X",
    "xray":    "X",
    "yankee":  "Y",
    "zulu":    "Z",
}

# Single Hebrew letter characters (sorted longest-name-first doesn't matter here)
_HE_CHARS: set[str] = set(_HE_LETTER_NAME.values())

# Threshold: need at least this many tokens recognised as letter-names to trigger
_MIN_SPELL_TOKENS = 2

def _strip_niqqud(s: str) -> str:
    """Remove Hebrew diacritics (niqqud, cantillation) from *s*."""
    return re.sub(r"[֑-ׇ]", "", s)

def _tokenise(text: str) -> list[str]:
    """Split on whitespace / commas / punctuation, return non-empty tokens."""
    return [t for t in re.split(r"[\s,،،.;]+", text.strip()) if t]

def detect_spelled_word(text: str) -> str | None:
    """Detect letter-by-letter dictation and reconstruct the intended word.

    Recognises three naming conventions (can be mixed in a single utterance):
      • Hebrew letter names  ("אלף", "בית", …)
      • Hebrew phonetics of English letters  ("אי", "בי", …)
      • English letter names / NATO phonetic  ("alpha", "bravo", … or "A B C")

    Returns the reconstructed string if ≥ _MIN_SPELL_TOKENS tokens are
    recognised as letter names, otherwise returns None.

    Examples:
        detect_spelled_word("אלף, למד, מם, הא")  → "אלמה"
        detect_spelled_word("Y A H O O")           → "yahoo"
        detect_spelled_word("שלום")                → None  (ordinary word)
    """
    text = _strip_niqqud(text)
    tokens = _tokenise(text)
    if not tokens:
        return None

    # Build lookup structures keyed by lowercase token.
    # Longer keys win over shorter when a token could match multiple entries.
    he_sorted = sorted(_HE_LETTER_NAME.keys(), key=len, reverse=True)
    he_en_sorted = sorted(_HE_EN_LETTER_NAME.keys(), key=len, reverse=True)
    en_sorted = sorted(_EN_LETTER_NAME.keys(), key=len, reverse=True)

    chars: list[str] = []
    recognised = 0

    for tok in tokens:
        low = tok.lower()

        # 1) Single Hebrew letter character (user typed/dictated raw glyph)
        if tok in _HE_CHARS:
            chars.append(tok)
            recognised += 1
            continue

        # 2) Hebrew letter name ("אלף", "בית", …)
        matched = False
        for name in he_sorted:
            if low == name.lower():
                chars.append(_HE_LETTER_NAME[name])
                recognised += 1
                matched = True
                break
        if matched:
            continue

        # 3) Hebrew phonetic of English letter ("אי", "בי", …)
        for name in he_en_sorted:
            if low == name.lower():
                chars.append(_HE_EN_LETTER_NAME[name])
                recognised += 1
                matched = True
                break
        if matched:
            continue

        # 4) English letter name / NATO ("alpha", "bravo", …)
        # Only match if the token is exactly a known name (avoids matching
        # common words like "echo", "golf", "india", "lima", "mike", "oscar",
        # "papa", "romeo", "sierra", "tango", "uniform", "victor", "yankee",
        # "zulu" that appear in normal sentences).
        # We require that ALL tokens in the utterance are letter-names (handled
        # by the recognised-count check at the end), but we still skip tokens
        # that are unambiguously common English words unless the caller is
        # clearly spelling something (e.g. surrounded by other letter names).
        for name in en_sorted:
            if low == name.lower():
                chars.append(_EN_LETTER_NAME[name])
                recognised += 1
                matched = True
                break
        if matched:
            continue

        # 5) Single ASCII letter spoken aloud ("A", "B", …)
        if len(tok) == 1 and tok.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            chars.append(tok.upper())
            recognised += 1
            continue

        # Unrecognised token — keep as-is but do not count as letter
        chars.append(tok)

    if recognised < _MIN_SPELL_TOKENS:
        return None

    # Require that the majority (>= 2/3) of tokens are recognised letter-names.
    # This prevents false positives when only 2 of 10 tokens happen to be
    # letter names (e.g. "gamma delta echo" → "delta" + "echo" = 2/3 ≥ 0.67).
    if recognised / len(tokens) < 0.67:
        return None

    # If all recognised tokens are ASCII letters, lowercase the result
    result = "".join(chars)
    if all(c.isascii() and c.isalpha() for c in result):
        return result.lower()
    return result

# ── 2. Correction detection ────────────────────────────────────────────────────
# Trigger phrases — if any is found at the start (or anywhere) of the utterance
# we attempt to extract the "intended" text that follows.
_CORRECTION_TRIGGERS_HE = [
    "לא",
    "תיקון",
    "תקן",
    "אני אמרתי",
    "אמרתי",
]
_CORRECTION_TRIGGERS_EN = [
    "fix",
    "correction",
    "wrong",
    "not that",
    "i said",
    "i meant",
]

# Patterns that mark the boundary between trigger and payload.
# The payload is everything AFTER the matched group.
_CORRECTION_PATTERN = re.compile(
    r"""
    (?:
        # Hebrew triggers — may chain: "לא, אמרתי" → consume both
        (?:לא\s*[,،،]?\s*)?                    # optional "לא" prefix
        (?:
            תיקון\s*[:\-,]?\s*                 |
            תקן\s*[:\-,]?\s*                   |
            אני\s+אמרתי\s*                      |
            אמרתי\s*                            |
            לא\s*[,،،]?\s*                      # "לא" alone as trigger
        )
        |
        # English triggers
        (?:fix|correction|wrong|not\s+that)\s*[:\-,]?\s*  |
        i\s+(?:said|meant)\s*
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

def parse_correction(text: str, last_text: str = "") -> str | None:
    """Detect if *text* is a correction command and return the intended text.

    Checks whether *text* starts with (or contains early) a known correction
    trigger and extracts the payload.

    Args:
        text:       The new utterance to test.
        last_text:  The previous utterance (not used for detection, reserved
                    for future context-aware logic).

    Returns:
        The corrected string (stripped), or None if not a correction.

    Examples:
        parse_correction("לא, אמרתי שלום")         → "שלום"
        parse_correction("תיקון: להתראות")          → "להתראות"
        parse_correction("fix: hello world")        → "hello world"
        parse_correction("שלום עולם")               → None
    """
    clean = _strip_niqqud(text).strip()

    # Try to match a trigger at the START of the utterance (allowing short
    # filler before it, e.g. "אה, לא, אמרתי…")
    # We scan through leading tokens (up to 4 words) to find the trigger.
    words = clean.split()
    for start in range(min(4, len(words))):
        candidate = " ".join(words[start:])
        m = _CORRECTION_PATTERN.match(candidate)
        if m:
            payload = candidate[m.end():].strip(" ,;:.-")
            if payload:
                logger.debug("correction detected: trigger=%r payload=%r", m.group(), payload)
                return payload
            # Trigger present but nothing after it — the LAST text was wrong
            # and user is waiting to re-dictate; signal via empty-string sentinel
            return ""

    return None

# ── 3. Correction logging for LoRA training ───────────────────────────────────

def log_correction(original: str, corrected: str, profile_dir: str) -> None:
    """Append a correction pair to ``{profile_dir}/corrections.jsonl``.

    Each line is a JSON object:
      {"original": "...", "corrected": "...", "ts": "2026-06-14T08:00:00"}

    Args:
        original:    The erroneous text that was produced by the ASR.
        corrected:   The text as the user intended it.
        profile_dir: Path to the user profile directory (will be created if
                     it does not exist).
    """
    path = Path(profile_dir) / "corrections.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "original":  original,
        "corrected": corrected,
        "ts":        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.debug("logged correction: %s → %s", original, corrected)

# ── 4. Phonetic similarity fixes (Hebrew Whisper errors) ──────────────────────
# Map of (wrong ASR output) → (intended text).
# Keys are lowercase; values preserve intended casing.
_PHONETIC_FIXES: dict[str, str] = {
    # Claude variants
    "קלוד":   "Claude",
    "קולד":   "Claude",
    "כלוד":   "Claude",
    "קלוו":   "Claude",
    "קלואד":  "Claude",

    # Grok variants
    "גרוק":   "Grok",
    "גרק":    "Grok",
    "גראק":   "Grok",
    "גרוכ":   "Grok",

    # Common Whisper confusions in Hebrew
    "להזמין":   "להזמין",   # identity — placeholder for future
    "בסדר":     "בסדר",
    "אוקיי":    "אוקיי",
    "אוקי":     "אוקיי",
    "אוקאי":    "אוקיי",
    "וואלה":    "וואלה",
    "ואלה":     "וואלה",
    "שמע":      "שמע",
    "דוד":      "דוד",
    "גוגל":     "Google",
    "גוגל.":    "Google",
    "ישראל":    "ישראל",
    "תל אביב":  "תל אביב",
    "ירושלים":  "ירושלים",

    # English proper nouns often garbled in Hebrew context
    "פייתון":   "Python",
    "פייתן":    "Python",
    "גיטהאב":   "GitHub",
    "גיט האב":  "GitHub",
    "גיט-האב":  "GitHub",
    "ויזיואל קוד": "VS Code",
    "ויז'ואל קוד": "VS Code",
    "קלוד קוד": "Claude Code",
    "ווינדוז":  "Windows",
    "פאוורשל":  "PowerShell",
    "פאואר של": "PowerShell",
}

# Precompile a single regex that matches any key (whole-word, case-insensitive).
# Build from longest key to shortest to prevent short matches shadowing long ones.
def _build_phonetic_regex() -> re.Pattern:
    # Sort descending by length so longer patterns match first.
    keys = sorted(_PHONETIC_FIXES.keys(), key=len, reverse=True)
    parts = [re.escape(k) for k in keys]
    return re.compile(r"(?<!\w)(" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)

_PHONETIC_RE = _build_phonetic_regex()

def maybe_fix_phonetic(text: str) -> str:
    """Replace known Whisper Hebrew mis-transcriptions with correct forms.

    Uses whole-word matching so "קלוד" in the middle of a sentence is fixed
    without disturbing surrounding text.  Substitution is case-insensitive for
    matching but the replacement preserves the value from the fix dict.

    Args:
        text: Raw ASR output.

    Returns:
        Corrected text (may be identical to input if no fixes applied).

    Example:
        maybe_fix_phonetic("כלוד, גרוק, פייתן")  → "Claude, Grok, Python"
    """
    def _replace(m: re.Match) -> str:
        key_lower = _strip_niqqud(m.group(0)).lower()
        # Look up with stripped key
        for k, v in _PHONETIC_FIXES.items():
            if k.lower() == key_lower:
                return v
        return m.group(0)

    return _PHONETIC_RE.sub(_replace, _strip_niqqud(text))

# ── Self-test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    sep = "─" * 60

    print(sep)
    print("detect_spelled_word tests")
    print(sep)
    cases_spell = [
        ("אלף, למד, מם, הא",          "אלמה"),
        ("Y A H O O",                  "yahoo"),
        ("alpha bravo charlie",         "abc"),
        ("אי, בי, סי",                 "ebc"),   # אי → E; acceptable
        ("שלום",                        None),
        ("A B C D E",                   "abcde"),
        ("gamma delta echo",            None),    # not letter names → None
    ]
    for text, expected in cases_spell:
        result = detect_spelled_word(text)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] {text!r:40} → {result!r}  (expected {expected!r})")

    print()
    print(sep)
    print("parse_correction tests")
    print(sep)
    cases_corr = [
        ("לא, אמרתי שלום",         "שלום"),
        ("תיקון: להתראות",          "להתראות"),
        ("fix: hello world",        "hello world"),
        ("i said good morning",     "good morning"),
        ("wrong, I meant goodbye",  "I meant goodbye"),
        ("שלום עולם",               None),
        ("אמרתי תודה רבה",          "תודה רבה"),
    ]
    for text, expected in cases_corr:
        result = parse_correction(text)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] {text!r:40} → {result!r}  (expected {expected!r})")

    print()
    print(sep)
    print("maybe_fix_phonetic tests")
    print(sep)
    cases_phon = [
        ("כלוד, גרוק",                     "Claude, Grok"),
        ("אני כותב קוד בפייתן",            "אני כותב קוד ב-Python"),   # won't match "ב" prefix — expected partial
        ("גרוק ו-קלוד הם מודלים",          "Grok ו-Claude הם מודלים"),
        ("שמע, גיטהאב נפל",               "שמע, GitHub נפל"),
        ("אין כאן שגיאות",                 "אין כאן שגיאות"),
    ]
    for text, _ in cases_phon:
        result = maybe_fix_phonetic(text)
        print(f"  {text!r:45} → {result!r}")

    print()
    print(sep)
    print("log_correction test (writes to /tmp/test_profile/corrections.jsonl)")
    print(sep)
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        log_correction("גרוק", "Grok", td)
        log_correction("כלוד", "Claude", td)
        jsonl_path = os.path.join(td, "corrections.jsonl")
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                print(" ", line.rstrip())
    print("  log_correction OK")
