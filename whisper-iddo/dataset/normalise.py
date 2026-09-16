"""whisper-iddo / dataset / normalise.py — the text normalisation contract.

ONE FILE, ONE TRUTH. Every transcript that enters the manifest passes through
`normalise()` here, and the trainer's decoded output must pass through the SAME
function before it is scored. Inconsistent text is the single most common reason a
fine-tune makes things WORSE: if training targets say "אמרתי" and the tokenizer sees
a stray RTL mark, the model spends capacity learning invisible characters instead of
Hebrew.

THE RULES, and why each one exists (all grounded in a character census of the real
corpus — 220 distinct characters across 11,396 transcripts, not guesswork):

  R1  BIDI CONTROLS ARE DELETED.  U+202B RIGHT-TO-LEFT EMBEDDING appears 211 times,
      always as a leading invisible prefix ("‫תודה" vs "תודה"). Two transcripts
      that read identically to a human were becoming two different training targets.
      Deleted: U+200E U+200F U+202A-U+202E U+2066-U+2069 U+FEFF.

  R2  NIQQUD AND CANTILLATION ARE STRIPPED.  U+0591-U+05BD, U+05BF-U+05C7. Whisper's
      Hebrew output is unpointed, so a pointed target ("טטוּז") teaches the model to
      emit a character it will then be penalised for. Note U+05BE MAQAF is KEPT — it
      is a hyphen, not a vowel point.

  R3  HEBREW PUNCTUATION FOLDS TO ASCII.  U+05F3 GERESH -> ' and U+05F4 GERSHAYIM -> ".
      Both are rare (8 and 9 occurrences) and Whisper emits the ASCII forms far more
      often. Folding the rare form into the common one removes a coin-flip the model
      would otherwise have to learn.

  R4  TYPOGRAPHIC QUOTES FOLD TO ASCII.  " " „ -> "  and ' ' -> '. Same argument as R3.
      Also U+05BE MAQAF and the dashes – — fold to ASCII hyphen.

  R5  DIGITS STAY DIGITS.  Whisper emits "4" not "ארבע"; forcing words would fight the
      pretrained model for no gain. We do NOT rewrite numerals in either direction.

  R6  ENGLISH TECHNICAL TERMS STAY IN LATIN SCRIPT, VERBATIM.  Iddo code-switches
      constantly ("יש דאטאבייס", "Claude", "Grok"). Whisper handles inline Latin fine.
      Transliterating either way would be inventing a convention the model has never
      seen. Casing is left ALONE — "Claude" stays capitalised.

  R7  SENTENCE PUNCTUATION IS KEPT (. , ? !).  The app types this text straight into
      other programs, so punctuation is part of the product, not decoration. Keeping it
      also matches what large-v3 already produces, so it is cheap to learn.

  R8  WHITESPACE COLLAPSES.  All runs of whitespace (including newlines from the .txt
      sidecars) become a single space; leading/trailing stripped.

  R9  LEADING ORPHAN PUNCTUATION IS REMOVED.  A target starting ", היי" is an artefact
      of segment slicing, never speech.

Deliberately NOT done, and why:
  - No lowercasing. Destroys proper nouns Iddo actually dictates.
  - No punctuation stripping. See R7.
  - No spelling correction. We have no authority to invent what he said.
"""
from __future__ import annotations

import re
import unicodedata

# R1 — invisible direction controls
_BIDI = dict.fromkeys(
    [0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
     0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF, 0x00AD], None)

# R2 — Hebrew points + cantillation, but NOT U+05BE MAQAF (a hyphen)
_NIQQUD = re.compile(r"[֑-ֽֿ-ׇ]")

# R3/R4 — character folds
_FOLD = {
    "׳": "'",   # HEBREW PUNCTUATION GERESH
    "״": '"',   # HEBREW PUNCTUATION GERSHAYIM
    "־": "-",   # HEBREW PUNCTUATION MAQAF
    "‘": "'", "’": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "′": "'", "″": '"',
    "–": "-", "—": "-", "−": "-",
    "…": "...",
    " ": " ", " ": " ", " ": " ", " ": " ",
}
_FOLD_RE = re.compile("|".join(re.escape(k) for k in _FOLD))

_WS = re.compile(r"\s+")
_LEAD_PUNCT = re.compile(r"^[\s.,!?;:\-\"']+")

HEBREW_LETTER = re.compile(r"[א-ת]")
LATIN_LETTER = re.compile(r"[A-Za-z]")
# Scripts that must NOT appear — their presence means Whisper mis-detected the
# language and the whole transcript is untrustworthy (Arabic/Cyrillic/CJK/Greek).
FOREIGN_SCRIPT = re.compile(
    r"[؀-ۿЀ-ӿͰ-Ͽ"
    r"぀-ヿ一-鿿가-힯]")


def normalise(text: str) -> str:
    """Apply R1-R9. Returns the canonical training target."""
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text)
    s = s.translate(_BIDI)                    # R1
    s = _NIQQUD.sub("", s)                    # R2
    s = _FOLD_RE.sub(lambda m: _FOLD[m.group()], s)   # R3, R4
    s = _WS.sub(" ", s)                       # R8
    s = _LEAD_PUNCT.sub("", s)                # R9
    return s.strip()


def script_of(text: str) -> str:
    """he / en / mixed / other — for reporting and for language-consistency checks."""
    h = bool(HEBREW_LETTER.search(text))
    l = bool(LATIN_LETTER.search(text))
    if h and l:
        return "mixed"
    if h:
        return "he"
    if l:
        return "en"
    return "other"
