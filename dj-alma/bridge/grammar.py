# -*- coding: utf-8 -*-
"""grammar.py -- Hebrew voice-command grammar for the ALMA psytrance DJ bridge.

Takes ONE recognized utterance (a string of Hebrew, as KESHEV would type it)
and returns either a ParsedCommand or None (not recognized -> ignored, never
guessed). Deliberately keyword-based, not strict regex-anchored: real STT
output is noisy (missing niqqud, run-together words, the occasional English
loanword), so this matches on the presence of stems/keywords rather than
exact phrasing. See README.md / the status report for the full v1 grammar
table this file implements.

This module has NO side effects and NO MIDI/audio/network access -- it is
pure text-in, command-out, so it can be unit-tested without Mixcraft, MIDI,
or a microphone anywhere nearby (see smoke_test.py).
"""
import re
from dataclasses import dataclass

import protocol


@dataclass
class ParsedCommand:
    command: str        # a key in protocol.COMMANDS by NAME, or a JSON-side
                        # command the Ableton Remote Script handles
                        # (SET_TEMPO_EXACT, SET_SONG_SCALE -- see dispatch.py)
    param: int = 0       # 0-127, meaning is command-specific (see protocol.py)
    matched_text: str = ""   # what in the utterance triggered this, for logging
    fields: dict = None      # extra JSON fields for the socket wire
                             # (e.g. {"bpm": 140.0}); None = none.
                             # voice_to_live forwards them; booth/dj_bridge
                             # ignore them, so old consumers are unaffected.

    def __post_init__(self):
        if self.fields is None:
            self.fields = {}


def _norm(text: str) -> str:
    """Strip punctuation/diacritics noise, collapse whitespace. Hebrew has no
    case to fold. Keeps digits intact (needed for BPM/bar-count numbers)."""
    text = re.sub(r"[^\w\s֐-׿]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---- vocabulary -------------------------------------------------------------
# Each list is "any of these substrings present" -- OR match, not AND.
STEM_WORDS = {
    "BASS":  ["בס", "בייס", "באס"],
    "LEAD":  ["ליד", "מלודיה", "מנגינה"],
    "DRUMS": ["תופים", "דראמס", "קליק", "בית"],
    "FX":    ["אפקטים", "פיקסים", "אפקט"],
    "MASTER": ["מאסטר", "הכל", "כללי"],
}
DOWN_WORDS = ["תוריד", "תנמיך", "תחליש", "נמוך יותר", "פחות"]
UP_WORDS = ["תעלה", "תגביר", "תחזק", "חזק יותר", "יותר"]
MUTE_WORDS = ["השתק", "מיוט", "כבה"]
UNMUTE_WORDS = ["בטל השתקה", "תחזיר", "הדלק"]

PLAY_WORDS = ["נגן", "תריץ", "תפעיל", "פליי", "המשך"]
STOP_WORDS = ["עצור", "סטופ", "תעצור", "תפסיק"]
STOP_ALL_WORDS = ["עצור הכל", "תעצור הכל", "סטופ הכל"]
RECORD_WORDS = ["הקלטה", "תקליט", "רקורד"]

SECTION_WORDS = {
    "DROP":  ["דרופ", "תן דרופ", "עכשיו דרופ", "תפיל"],
    "BUILD": ["בילד", "בילד אפ", "תעלה מתח", "עלייה", "ריייזר", "רייזר"],
    "BREAK": ["ברייק", "ברייקדאון", "תוריד הכל", "ירידה", "נשימה"],
    "INTRO": ["אינטרו", "תתחיל", "פתיחה"],
    "OUTRO": ["אאוטרו", "תסיים", "סיום", "תוריד לאט"],
}

TEMPO_UP_WORDS = ["מהר יותר", "תגביר קצב", "תאיץ", "יותר מהר"]
TEMPO_DOWN_WORDS = ["לאט יותר", "תוריד קצב", "תאט", "יותר לאט"]

_BPM_RE = re.compile(r"(?:קצב|טמפו|bpm)\D{0,6}(\d{2,3})")
# digits-first: "increase to 160 bpm", "160 bpm", "160 בי פי אם".
# A bare number with NO unit and NO tempo word is ignored (never guessed --
# it could be bars, a param, or noise).
_BPM_RE2 = re.compile(r"(\d{2,3})\s*(?:bpm|בי פי אם)")
_BARS_RE = re.compile(r"(?:עוד\s+)?(\d{1,2})\s*(?:בר|בארים|בארס|bars?)")

# ---- musical key ------------------------------------------------------------
# "go to C#", "עבור לסול", "סולם לה מינור". root 0-11, C=0 (Live convention).
# A note name only counts inside a key/scale context ("go to", "סולם", ...)
# so a stray "C" in chatter never retunes the set. Accidentals are read off
# the RAW utterance because _norm strips "#": C# arrives as "C" + "#".
_KEY_CTX = ["סולם", "לסולם", "בסולם", "scale", "key", "go to", "עבור ל", "תעבור ל"]
_SCALE_MINOR = ["מינור", "מינורי", "minor"]
_SCALE_MAJOR = ["מזור", "מזורי", "major"]
# (base EN, base HE variants, semitone offset); sharps/flats via markers below.
_KEY_BASES = [
    ("C", ["דו"], 0), ("D", ["רה"], 2), ("E", ["מי"], 4),
    ("F", ["פה"], 5), ("G", ["סול"], 7), ("A", ["לה"], 9), ("B", ["סי"], 11),
]
_SHARP_MARK = ["דיאז", "שארפ", "sharp", "#", "♯"]
_FLAT_MARK = ["במול", "flat", "♭"]


def _any_in(text: str, words: list) -> str | None:
    for w in words:
        if w in text:
            return w
    return None


def _parse_key(raw: str, text: str) -> ParsedCommand | None:
    """Musical key: "go to C#", "עבור לסול", "סולם לה מינור".

    Returns SET_SONG_SCALE (root_note 0-11 C=0 in param AND fields,
    scale_name in fields) or None. Scale defaults to Minor -- the psytrance
    lineage of this project (A-minor measured) -- and the default is always
    visible in matched_text, never silent. No key context words -> None, so
    everyday words that collide with note names ("מי", "פה") never retune.
    """
    low = raw.lower()
    if not any(c in text or c in low for c in _KEY_CTX):
        return None
    base = None
    for en, he_vars, off in _KEY_BASES:
        if re.search(r"\b%s\b" % en, text, re.IGNORECASE):
            base = (en, off)
            break
        for hv in he_vars:
            # standalone token with optional single-letter Hebrew prefix
            # (ל/ב/כ/ה/ו/ש/מ: "לסול", "בסול") -- so the context word "סולם"
            # never matches the note "סול".
            if re.search(r"(?:^|\s)[לבכהושמ]?%s(?:\s|$)" % hv, text):
                base = (hv, off)
                break
        if base:
            break
    if not base:
        return None
    name, off = base
    if any(m in raw for m in _SHARP_MARK):
        off += 1
        acc = "#"
    elif any(m in text for m in _FLAT_MARK):
        off -= 1
        acc = "b"
    else:
        acc = ""
    root = off % 12
    if _any_in(text, _SCALE_MAJOR) or "major" in low:
        scale = "Major"
    else:
        scale = "Minor"  # default, see docstring
    return ParsedCommand("SET_SONG_SCALE", root,
                         f"{name}{acc} {scale}",
                         {"root_note": root, "scale_name": scale})


def parse(utterance: str) -> ParsedCommand | None:
    """Parse one recognized Hebrew sentence into a DJ command, or None."""
    if not utterance or not utterance.strip():
        return None
    text = _norm(utterance)

    # --- numeric commands first (most specific) ---
    m = _BPM_RE.search(text)
    if m:
        bpm = float(m.group(1))
        return ParsedCommand("SET_TEMPO", protocol.bpm_to_param(bpm), m.group(0),
                             {"bpm": bpm})
    m = _BPM_RE2.search(text)
    if m:
        bpm = float(m.group(1))
        return ParsedCommand("SET_TEMPO", protocol.bpm_to_param(bpm), m.group(0),
                             {"bpm": bpm})

    key = _parse_key(utterance, text)
    if key:
        return key

    m = _BARS_RE.search(text)
    if m and ("עוד" in text or "extend" in text.lower()):
        bars = int(m.group(1))
        # bar param encoding per protocol.py: 0=8, 1=16, 2=32 (closest match)
        code = 0 if bars <= 8 else (1 if bars <= 16 else 2)
        return ParsedCommand("EXTEND_SECTION", code, m.group(0))

    # --- sections (before generic up/down so "תן דרופ" doesn't get read as volume) ---
    for name, words in SECTION_WORDS.items():
        hit = _any_in(text, words)
        if hit:
            return ParsedCommand(f"SECTION_{name}", 0, hit)

    # --- transport ---
    if _any_in(text, STOP_ALL_WORDS):
        return ParsedCommand("STOP_ALL_CLIPS", 0, "stop-all")
    hit = _any_in(text, STOP_WORDS)
    if hit:
        return ParsedCommand("STOP", 0, hit)
    hit = _any_in(text, PLAY_WORDS)
    if hit:
        return ParsedCommand("PLAY", 0, hit)
    hit = _any_in(text, RECORD_WORDS)
    if hit:
        return ParsedCommand("RECORD_TOGGLE", 0, hit)

    # --- tempo nudge ---
    hit = _any_in(text, TEMPO_UP_WORDS)
    if hit:
        return ParsedCommand("TEMPO_NUDGE_UP", 2, hit)  # default: 2 steps = 1.0 BPM
    hit = _any_in(text, TEMPO_DOWN_WORDS)
    if hit:
        return ParsedCommand("TEMPO_NUDGE_DOWN", 2, hit)

    # --- stem volume / mute (needs a stem word AND a direction word) ---
    stem_hit = None
    stem_name = None
    for name, words in STEM_WORDS.items():
        hit = _any_in(text, words)
        if hit:
            stem_hit, stem_name = hit, name
            break

    if stem_name:
        mute_hit = _any_in(text, MUTE_WORDS)
        if mute_hit:
            if stem_name == "MASTER":
                return None  # muting "everything" has no MASTER_MUTE command in v1
            return ParsedCommand(f"{stem_name}_MUTE_TOGGLE", 0, f"{mute_hit} {stem_hit}")
        unmute_hit = _any_in(text, UNMUTE_WORDS)
        if unmute_hit:
            if stem_name == "MASTER":
                return None
            return ParsedCommand(f"{stem_name}_MUTE_TOGGLE", 0, f"{unmute_hit} {stem_hit}")

        down_hit = _any_in(text, DOWN_WORDS)
        if down_hit:
            cmd = "MASTER_VOL" if stem_name == "MASTER" else f"{stem_name}_VOL"
            # *_VOL is a NUDGE, not an absolute set -- see protocol.nudge_param()
            # docstring for why (no read-back channel in v1).
            return ParsedCommand(cmd, protocol.nudge_param("down"), f"{down_hit} {stem_hit}")
        up_hit = _any_in(text, UP_WORDS)
        if up_hit:
            cmd = "MASTER_VOL" if stem_name == "MASTER" else f"{stem_name}_VOL"
            return ParsedCommand(cmd, protocol.nudge_param("up"), f"{up_hit} {stem_hit}")

    return None
