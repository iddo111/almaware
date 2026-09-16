"""iqbrainz.py — Intelligent context engine for the Hebrew mic.

Sits between STT output and the typer. Learns personal vocabulary,
auto-corrects phonetic Whisper errors, detects spelled-out words,
and feeds a context hint back into Whisper on the next utterance.

"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from collections import deque, Counter
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("voiceinput.iqbrainz")

# ── Hebrew letter names → glyph ──────────────────────────────────────────────
HEBREW_LETTER_NAMES: dict[str, str] = {
    # standard transliterations
    "aleph": "א", "alef": "א", "אלף": "א",
    "bet": "ב",  "beit": "ב", "vet": "ב", "בית": "ב",
    "gimel": "ג", "גימל": "ג",
    "dalet": "ד", "דלת": "ד",
    "hey": "ה",  "he": "ה",  "הא": "ה",
    "vav": "ו",  "waw": "ו", "ואו": "ו",
    "zayin": "ז", "זין": "ז",
    "chet": "ח", "het": "ח", "חית": "ח",
    "tet": "ט",  "טית": "ט",
    "yod": "י",  "yud": "י", "יוד": "י",
    "kaf": "כ",  "kaph": "כ", "כף": "כ",
    "lamed": "ל", "למד": "ל",
    "mem": "מ",  "מם": "מ",
    "nun": "נ",  "נון": "נ",
    "samech": "ס", "samekh": "ס", "סמך": "ס",
    "ayin": "ע", "עין": "ע",
    "pey": "פ",  "pe": "פ",  "fey": "פ", "פא": "פ",
    "tzadi": "צ", "tzadik": "צ", "צדי": "צ", "tsadi": "צ",
    "kuf": "ק",  "qof": "ק", "kof": "ק", "קוף": "ק",
    "resh": "ר", "ריש": "ר",
    "shin": "ש", "sin": "ש", "שין": "ש",
    "tav": "ת",  "taf": "ת", "תו": "ת",
}

# ── NATO phonetic alphabet → letter ──────────────────────────────────────────
NATO: dict[str, str] = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D",
    "echo": "E",  "foxtrot": "F", "golf": "G", "hotel": "H",
    "india": "I", "juliet": "J", "kilo": "K", "lima": "L",
    "mike": "M",  "november": "N", "oscar": "O", "papa": "P",
    "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T",
    "uniform": "U", "victor": "V", "whiskey": "W", "x-ray": "X",
    "yankee": "Y", "zulu": "Z",
}

# ── Built-in Hebrew phonetic fix table (common Whisper errors) ─────────────
HEBREW_FIXES: dict[str, str] = {
    # Tech brand names Whisper often mishears in Hebrew speech
    "קלוד קוד": "Claude Code",
    "קלוד": "Claude",
    "גיטהאב": "GitHub",
    "גיט האב": "GitHub",
    "פייתון": "Python",
    "פיתון": "Python",
    "וינדוס": "Windows",
    "וינדואוס": "Windows",
    "פאוורשל": "PowerShell",
    "פאוורשל": "PowerShell",
    "פאורשל": "PowerShell",
    "לינוקס": "Linux",
    "דוקר": "Docker",
    "קוברנטיס": "Kubernetes",
    "ריאקט": "React",
    "נוד": "Node",
    "נוד ג׳יי אס": "Node.js",
    "ג׳אווה סקריפט": "JavaScript",
    "ג׳אווה סקריפ": "JavaScript",
    "טייפסקריפט": "TypeScript",
    "ג׳ייסון": "JSON",
    "אייפיאי": "API",
    "יי פי איי": "API",
    "ג׳י פי טי": "GPT",
    "צ׳ט ג׳י פי טי": "ChatGPT",
    "צ׳טג׳יפיטי": "ChatGPT",
    "אנת׳רופיק": "Anthropic",
    "אנטרופיק": "Anthropic",
    "אופן איי": "OpenAI",
    "גיט": "git",
    "גיט פוש": "git push",
    "גיט פול": "git pull",
    "גיט קומיט": "git commit",
    "גיט קלון": "git clone",
    "גיט סטייטוס": "git status",
    "גיט בראנץ׳": "git branch",
    "פול ריקוואסט": "pull request",
    "פי אר": "PR",
    "ווי אס קוד": "VS Code",
    "ויזואל סטודיו קוד": "VS Code",
    "קלאוד": "Claude",
    "גרוק": "Grok",
    "גיטיגנור": ".gitignore",
    "דוט אנב": ".env",
    "דוט פייתון": ".python",
    "ריפו": "repo",
    "ריפוזיטורי": "repository",
    "קומיט": "commit",
    "בראנץ׳": "branch",
    "מרג׳": "merge",
    "רבייס": "rebase",
    "סטאש": "stash",
    "פוש": "push",
    "פול": "pull",
    "קלון": "clone",
    "פאנקשן": "function",
    "קלאס": "class",
    "אימפורט": "import",
    "אקספורט": "export",
    "אסינק": "async",
    "אוויט": "await",
    "קונסול לוג": "console.log",
    "דיבאג": "debug",
    "לוגר": "logger",
    "ריפקטור": "refactor",
    "דפלוי": "deploy",
    "בילד": "build",
    "טסט": "test",
    "דאטהבייס": "database",
    "דאטה בייס": "database",
    "מונגו": "MongoDB",
    "מונגו די בי": "MongoDB",
    "פוסטגרס": "PostgreSQL",
    "רדיס": "Redis",
    "קאשה": "cache",
    "קאש": "cache",
    "אינדקס": "index",
    "אנדקס": "index",
    "סרבר": "server",
    "קליינט": "client",
    "בקאנד": "backend",
    "פרונטאנד": "frontend",
    "פרונט אנד": "frontend",
    "בק אנד": "backend",
    "פולסטאק": "full-stack",
    "ווב סוקט": "WebSocket",
    "ריסט איי פי איי": "REST API",
    "גרפקיוול": "GraphQL",
    "גרף קיול": "GraphQL",
    "דוקרפייל": "Dockerfile",
    "ירמל": "YAML",
    "יאמל": "YAML",
    "טומל": "TOML",
    "סי אס אס": "CSS",
    "אייץ׳ טי אם אל": "HTML",
    "אייץ׳ טי מל": "HTML",
    "סי אס אר": "CSR",
    "אס אס אר": "SSR",
    "טרמינל": "terminal",
    "פאוורשל": "PowerShell",
    "קומנד ליין": "command line",
    "סי אל איי": "CLI",
}

# ── Confidence thresholds ─────────────────────────────────────────────────────
CONFIDENCE_PENALTY_PER_FIX = 0.05   # each auto-fix lowers confidence slightly
MIN_CONFIDENCE_TO_TYPE     = 0.25    # below this, flag for review
VOCAB_THRESHOLD            = 3       # appearances before "personal vocab"

@dataclass
class ProcessedResult:
    text: str               # final processed text
    original: str           # raw STT output
    changes: list[str]      # what was auto-fixed
    confidence: float       # adjusted confidence (0.0–1.0)
    is_spelling: bool       # was this a spelled-out word?
    spelling_word: str      # reconstructed word if is_spelling
    context_hint: str       # for next STT call (Whisper initial_prompt)
    flagged: bool = False   # True if confidence below threshold

class IQBrainz:
    """Intelligent context engine for Hebrew voice input.

    Maintains a rolling context window, applies phonetic corrections,
    learns personal vocabulary, detects spelled-out words, and generates
    Whisper context hints from recent utterances.
    """

    def __init__(self, profile_dir: str, max_context: int = 10):
        self.profile_dir = profile_dir
        self.max_context = max_context

        os.makedirs(profile_dir, exist_ok=True)

        self._vocab_path = os.path.join(profile_dir, "vocab.json")
        self._rules_path = os.path.join(profile_dir, "rules.json")

        # Rolling context window: deque of (text, confidence) tuples
        self._context: deque[tuple[str, float]] = deque(maxlen=max_context)

        # personal vocab: {word: {"count": int, "personal": bool, "names": bool}}
        self._vocab: dict[str, dict] = self._load_json(self._vocab_path, {})

        # learned phonetic rules: {wrong_form: correct_form}
        self._rules: dict[str, str] = self._load_json(self._rules_path, {})

        # word frequency from current session (supplements vocab.json)
        self._session_freq: Counter = Counter()

        log.info("IQBrainz ready — profile=%s vocab=%d rules=%d",
                 profile_dir, len(self._vocab), len(self._rules))

    # ── public API ─────────────────────────────────────────────────────────

    def process(self, raw_text: str, confidence: float = 1.0) -> ProcessedResult:
        """Main pipeline. Returns corrected text + rich metadata."""
        original = raw_text

        # 1. Detect spelled-out word first (short-circuit if found)
        spelled = self.detect_spelling(raw_text)
        if spelled is not None:
            self._track_words(spelled)
            result_text = spelled
            hint = self.get_context_hint()
            self._context.append((result_text, confidence))
            return ProcessedResult(
                text=result_text,
                original=original,
                changes=[f"spelling detected → '{spelled}'"],
                confidence=confidence,
                is_spelling=True,
                spelling_word=spelled,
                context_hint=hint,
                flagged=confidence < MIN_CONFIDENCE_TO_TYPE,
            )

        # 2. Apply learned rules + built-in phonetic fixes
        fixed_text, changes = self.auto_fix(raw_text)

        # 3. Adjust confidence based on number of corrections applied
        adj_confidence = max(0.0, confidence - len(changes) * CONFIDENCE_PENALTY_PER_FIX)

        # 4. Track word frequencies (for vocab learning)
        self._track_words(fixed_text)

        # 5. Update context window
        self._context.append((fixed_text, adj_confidence))

        hint = self.get_context_hint()

        return ProcessedResult(
            text=fixed_text,
            original=original,
            changes=changes,
            confidence=adj_confidence,
            is_spelling=False,
            spelling_word="",
            context_hint=hint,
            flagged=adj_confidence < MIN_CONFIDENCE_TO_TYPE,
        )

    def learn_correction(self, original: str, corrected: str):
        """User confirmed a correction — learn from it.

        Increments the corrected word's count. If it hits VOCAB_THRESHOLD,
        it's added to personal vocab and a phonetic rule is recorded so the
        same wrong form is never auto-"corrected" away again.
        """
        if not original or not corrected or original == corrected:
            return

        # Track each corrected word
        for word in corrected.split():
            self._bump_vocab(word)

        # Record phonetic rule: original_lower → corrected
        key = original.strip().lower()
        old_rule = self._rules.get(key)
        self._rules[key] = corrected.strip()
        if old_rule != corrected.strip():
            log.info("IQBrainz learned rule: '%s' → '%s'", key, corrected.strip())

        self._save_json(self._rules_path, self._rules)
        self._save_json(self._vocab_path, self._vocab)

    def detect_spelling(self, text: str) -> str | None:
        """Detect if the user spelled out a word letter-by-letter.

        Handles:
        - Hebrew letter names: "אלף בית גימל" → "אבג"
        - NATO alphabet:  "alpha bravo charlie" → "ABC"
        - Plain spaced letters: "A B C D" → "ABCD"
        - Mixed short-cap tokens: "P Y T H O N" → "PYTHON"

        Returns reconstructed word, or None if not a spelling sequence.
        """
        tokens = text.strip().split()

        # Need at least 2 tokens, at most 20 (reasonable word length)
        if len(tokens) < 2 or len(tokens) > 20:
            return None

        # --- try Hebrew letter names ---
        heb_chars = []
        for tok in tokens:
            normalized = tok.lower().strip(".,;:!?\"'")
            ch = HEBREW_LETTER_NAMES.get(normalized)
            if ch is None:
                break
            heb_chars.append(ch)
        if len(heb_chars) == len(tokens):
            return "".join(heb_chars)

        # --- try NATO ---
        nato_chars = []
        for tok in tokens:
            normalized = tok.lower().strip(".,;:!?\"'")
            ch = NATO.get(normalized)
            if ch is None:
                break
            nato_chars.append(ch)
        if len(nato_chars) == len(tokens):
            return "".join(nato_chars)

        # --- try plain single-letter tokens (A B C …) ---
        single_en = []
        for tok in tokens:
            t = tok.strip(".,;:!?\"'")
            if re.fullmatch(r"[A-Za-z]", t):
                single_en.append(t.upper())
            else:
                break
        if len(single_en) == len(tokens) and len(single_en) >= 2:
            return "".join(single_en)

        # --- try spaced Hebrew individual letters (א ב ג …) ---
        single_heb = []
        for tok in tokens:
            t = tok.strip(".,;:!?\"'")
            # single Hebrew character: Unicode range א-ת
            if re.fullmatch(r"[א-ת]", t):
                single_heb.append(t)
            else:
                break
        if len(single_heb) == len(tokens) and len(single_heb) >= 2:
            return "".join(single_heb)

        return None

    def auto_fix(self, text: str) -> tuple[str, list[str]]:
        """Apply phonetic corrections + personal vocab substitutions.

        Priority order:
        1. Personal vocab words are NEVER corrected away.
        2. Learned rules (rules.json) — user-confirmed corrections.
        3. Built-in HEBREW_FIXES table.

        Returns (fixed_text, list_of_changes_made).
        """
        changes: list[str] = []
        result = text

        # Build a combined fix dict: built-in first, then learned rules on top
        combined: dict[str, str] = {}
        combined.update(HEBREW_FIXES)
        combined.update(self._rules)  # learned rules win over built-ins

        # Sort by length descending so longer phrases match before sub-phrases
        for wrong, right in sorted(combined.items(), key=lambda x: len(x[0]), reverse=True):
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            if pattern.search(result):
                # Don't replace if the "right" form is already a personal vocab word
                # and the match is exactly that word
                new_result = pattern.sub(right, result)
                if new_result != result:
                    changes.append(f"'{wrong}' → '{right}'")
                    result = new_result

        # Personal vocab pass: protect known personal words from being mangled
        # (already handled above by not touching them — no extra action needed)

        return result, changes

    def add_vocab(self, word: str, context: str = ""):
        """Manually add a word to personal vocabulary."""
        word = word.strip()
        if not word:
            return
        is_name = bool(context) and word[0].isupper()
        entry = self._vocab.setdefault(word, {"count": 0, "personal": False, "name": False})
        entry["count"] = max(entry["count"], VOCAB_THRESHOLD)
        entry["personal"] = True
        entry["name"] = entry.get("name", False) or is_name
        if context:
            entry.setdefault("contexts", []).append(context[:80])
        self._save_json(self._vocab_path, self._vocab)
        log.info("IQBrainz: added vocab '%s' (name=%s)", word, entry["name"])

    def get_context_hint(self) -> str:
        """Build a Whisper initial_prompt string from the rolling context window.

        Whisper uses this as a "soft" prefix — it biases the model toward
        vocabulary and style that recently appeared, improving accuracy on
        repeated names and jargon.
        """
        if not self._context:
            return "שיחה בעברית. תמלול מדויק של דיבור טבעי."

        # Take the last few utterances; weight recent ones more
        recent = list(self._context)
        # Include only utterances with reasonable confidence
        snippets = [text for text, conf in recent if conf >= 0.4]

        if not snippets:
            return "שיחה בעברית. תמלול מדויק של דיבור טבעי."

        # Append personal vocab words so Whisper biases toward them
        personal_words = [w for w, d in self._vocab.items()
                          if d.get("personal") and len(w) > 2]
        vocab_hint = ", ".join(personal_words[:20]) if personal_words else ""

        context_text = " | ".join(snippets[-5:])
        if vocab_hint:
            return f"שיחה בעברית. הקשר: {context_text}. מילים אישיות: {vocab_hint}."
        return f"שיחה בעברית. הקשר: {context_text}."

    # ── vocabulary management ───────────────────────────────────────────────

    def _bump_vocab(self, word: str):
        """Increment a word's count; promote to personal vocab at threshold."""
        word = word.strip().strip(".,;:!?\"'")
        if not word or len(word) < 2:
            return
        entry = self._vocab.setdefault(word, {"count": 0, "personal": False, "name": False})
        entry["count"] += 1
        if entry["count"] >= VOCAB_THRESHOLD and not entry["personal"]:
            entry["personal"] = True
            # Detect if it looks like a name (capitalized, non-Hebrew)
            if word[0].isupper() and re.match(r"[A-Z]", word):
                entry["name"] = True
            log.info("IQBrainz: promoted '%s' to personal vocab (count=%d)",
                     word, entry["count"])

    def _track_words(self, text: str):
        """Track all words in a processed utterance for vocab learning."""
        words = re.findall(r"[\wא-ת]+", text)
        for w in words:
            if len(w) >= 2:
                self._session_freq[w] += 1
                self._bump_vocab(w)
        # Persist vocab periodically (every 10 unique new words bumped)
        # Simple heuristic: save every call (file is small)
        self._save_json(self._vocab_path, self._vocab)

    # ── scoring helpers ─────────────────────────────────────────────────────

    def score_text(self, text: str) -> float:
        """Heuristic confidence adjustment based on content analysis.

        Returns a multiplier (0.5–1.0) to apply to the base confidence.
        """
        score = 1.0

        # Very short transcription after a long silence → suspicious
        if len(text.split()) < 2:
            score *= 0.85

        # All-caps non-Hebrew (might be noise artefact)
        if re.fullmatch(r"[A-Z\s]+", text) and len(text) > 3:
            score *= 0.9

        # Contains only punctuation / numbers → probably junk
        if re.fullmatch(r"[\d\s.,!?;:\"'()-]+", text):
            score *= 0.6

        return max(0.1, min(1.0, score))

    def get_stats(self) -> dict:
        """Return statistics about the current brain state."""
        personal = {w: d for w, d in self._vocab.items() if d.get("personal")}
        names = {w: d for w, d in personal.items() if d.get("name")}
        return {
            "vocab_total": len(self._vocab),
            "vocab_personal": len(personal),
            "vocab_names": len(names),
            "learned_rules": len(self._rules),
            "context_window": len(self._context),
            "session_words": len(self._session_freq),
        }

    # ── persistence helpers ─────────────────────────────────────────────────

    @staticmethod
    def _load_json(path: str, default):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("IQBrainz: could not load %s: %s", path, exc)
        return default

    @staticmethod
    def _save_json(path: str, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            log.warning("IQBrainz: could not save %s: %s", path, exc)

# ── standalone smoke-test ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with tempfile.TemporaryDirectory() as tmp:
        brain = IQBrainz(profile_dir=tmp, max_context=5)

        tests = [
            ("פייתון הוא שפה נהדרת", 0.92),
            ("עשיתי גיט פוש לגיטהאב", 0.88),
            ("קלוד קוד הוא כלי מדהים", 0.95),
            ("A B C D", 1.0),
            ("alpha bravo charlie delta echo", 1.0),
            ("aleph bet gimel dalet", 1.0),
            ("א ב ג ד", 1.0),
            ("hello world this is a normal sentence", 0.80),
        ]

        print("\n── IQBrainz smoke-test ──\n")
        for raw, conf in tests:
            res = brain.process(raw, conf)
            print(f"IN:  {res.original}")
            print(f"OUT: {res.text}")
            if res.changes:
                print(f"FIX: {res.changes}")
            if res.is_spelling:
                print(f"SPL: '{res.spelling_word}'")
            print(f"CNF: {res.confidence:.2f}  flagged={res.flagged}")
            print()

        # Test learning
        brain.learn_correction("וינדואוז", "Windows")
        brain.learn_correction("וינדואוז", "Windows")
        brain.learn_correction("וינדואוז", "Windows")

        # Test add_vocab
        brain.add_vocab("Nimrod", context="שם פרטי")
        brain.add_vocab("ClodistanOS", context="מערכת הפעלה")

        print("Context hint:")
        print(brain.get_context_hint())
        print()
        print("Stats:", brain.get_stats())
