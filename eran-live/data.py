"""
data.py - ERAN's VOICE-ONLY corpus loader.

CRITICAL DIRECTIVE: Eran learns ONLY from Iddo's own voice / lived experience.
It must NEVER read a book corpus. The earlier mistake (training on a BOOK corpus,
e.g. eran_all_corpus.txt / eran-corpus-v2) is corrected here: this loader pulls
exclusively from the live voice-dictation sources and refuses anything else.

Voice sources (all under D:/CLAUDE/voice-input):
  1. profiles/iddo1/iddo_clean_corpus.jsonl   -> 'text' field (clean owner-gated)
  2. history/*.txt                            -> the live daily dictation logs
  3. profiles/iddo1/samples.jsonl             -> 'text' field (de-duped against the above)

These files GROW 24/7 as Iddo speaks. build_corpus() is called fresh every epoch
by the trainer, so Eran keeps learning new speech as the collection grows.

Output: one big UTF-8 string, samples joined by newlines, ready for the byte tokenizer.
"""

import json
import re
import os
import sys

# make stdout UTF-8 so Hebrew/Arabic samples print on a cp1252 console without crashing
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- hard allow-list of voice sources. Nothing else is ever read. ---
# ERAN_VOICE_DIR env var overrides the Windows default so the SAME loader
# works on the Linux DGX (still voice-only; the _FORBIDDEN guard stays).
VOICE_DIR = os.environ.get("ERAN_VOICE_DIR", r"D:\CLAUDE\voice-input")
CLEAN_CORPUS = os.path.join(VOICE_DIR, "profiles", "iddo1", "iddo_clean_corpus.jsonl")
SAMPLES = os.path.join(VOICE_DIR, "profiles", "iddo1", "samples.jsonl")
HISTORY_DIR = os.path.join(VOICE_DIR, "history")

# guard: these substrings in a path mean "BOOK corpus" -> forbidden.
_FORBIDDEN = ("eran_all_corpus", "eran-corpus-v2", "eran-corpus", "corpus-v2")

# history line looks like: [06:05:28] [dictation] <the actual words>
_HIST_RE = re.compile(r"^\s*\[\d{2}:\d{2}:\d{2}\]\s*\[[^\]]+\]\s*(.*)$")


def _assert_voice_only(path: str):
    low = path.lower()
    for bad in _FORBIDDEN:
        if bad in low:
            raise RuntimeError(
                f"REFUSING to load forbidden BOOK corpus: {path}. "
                f"ProtoEran learns ONLY from Iddo's voice."
            )


def _read_jsonl_text(path: str):
    out = []
    if not os.path.exists(path):
        return out
    _assert_voice_only(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            txt = obj.get("text")
            if isinstance(txt, str):
                txt = txt.strip()
                if txt:
                    out.append(txt)
    return out


def _read_history(history_dir: str):
    out = []
    if not os.path.isdir(history_dir):
        return out
    for name in sorted(os.listdir(history_dir)):
        if not name.lower().endswith(".txt"):
            continue
        path = os.path.join(history_dir, name)
        _assert_voice_only(path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = _HIST_RE.match(line)
                    if m:
                        txt = m.group(1).strip()
                    else:
                        txt = line.strip()
                    if txt:
                        out.append(txt)
        except Exception:
            continue
    return out


def build_corpus(verbose: bool = False) -> str:
    """Return Iddo's full VOICE corpus as one string. De-duped, voice-only.

    Re-reads the live files every call so the growing 24/7 collection keeps
    feeding Eran new speech.
    """
    seen = set()
    ordered = []

    def add_all(items, tag):
        n = 0
        for t in items:
            key = t
            if key in seen:
                continue
            seen.add(key)
            ordered.append(t)
            n += 1
        if verbose:
            print(f"  [data] {tag}: +{n} new unique lines (total {len(ordered)})")

    # order: clean corpus first (curated), then history (live), then samples (de-duped)
    add_all(_read_jsonl_text(CLEAN_CORPUS), "clean_corpus")
    add_all(_read_history(HISTORY_DIR), "history/*.txt")
    add_all(_read_jsonl_text(SAMPLES), "samples")

    text = "\n".join(ordered) + "\n"
    return text


def corpus_stats():
    text = build_corpus()
    return {
        "chars": len(text),
        "bytes": len(text.encode("utf-8")),
        "lines": text.count("\n"),
    }


if __name__ == "__main__":
    text = build_corpus(verbose=True)
    b = text.encode("utf-8")
    print(f"\nVOICE corpus: {len(text)} chars, {len(b)} bytes, {text.count(chr(10))} lines")
    print("--- sample (first 600 chars, THIS IS IDDO'S VOICE, not books) ---")
    print(text[:600])
