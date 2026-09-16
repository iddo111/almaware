#!/usr/bin/env python3
"""Build the K13 textguard corpus manifest (criterion 10, text level).

Two halves:

  * hallucinations / must_pass — synthetic + OBSERVED failure texts, inline.
    Every hallucination entry is a class that really typed on the old mic
    (PHASE1-INQUIRY.md scars 27/28: the תודה family, laughter blobs,
    subscribe-junk, CJK/RU/AR credits, repeat loops, char-runs, short junk).
    These are data (known model attractors), NOT a second copy of the guard.

  * real_he — real transcribed utterances sampled from the alma-mic
    voice_corpus, READ-ONLY. Selection is DETERMINISTIC and GUARD-BLIND
    (sorted filenames, Hebrew-content threshold, fixed stride) so the CER
    measurement cannot be cherry-picked around the guard. Scar 49: the
    manifest stores FILENAMES + sha256 integrity hashes + lengths only —
    transcript text never enters git.

Usage:
    python tools/build_textguard_corpus.py [--corpus-dir DIR] [--n 40]

Writes tools/replay/textguard_corpus.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE / "replay"))
import textmetrics  # noqa: E402

DEFAULT_CORPUS_DIR = Path(r"D:\CLAUDE\alma-mic\voice_corpus")
OUT = HERE / "replay" / "textguard_corpus.json"

MIN_HEBREW_LETTERS = 8
MIN_CHARS = 12

# Observed / synthetic hallucination texts, by class. Every class maps to a
# real logged failure of the old mic (see PHASE1-INQUIRY.md scar 28).
HALLUCINATIONS: list[dict] = [
    # laughter / filler blobs — typed all night 2026-08-08 (laughfix)
    {"id": "laugh-1", "class": "laughter", "text": "חחח"},
    {"id": "laugh-2", "class": "laughter", "text": "חחחח"},
    {"id": "laugh-3", "class": "laughter", "text": "אהה"},
    {"id": "laugh-4", "class": "laughter", "text": "אההה"},
    {"id": "laugh-5", "class": "laughter", "text": "חחח."},
    {"id": "laugh-6", "class": "laughter", "text": "ההה"},
    # the Hebrew תודה family — Whisper's #1 Hebrew silence attractor
    {"id": "todah-1", "class": "todah", "text": "תודה"},
    {"id": "todah-2", "class": "todah", "text": "תודה רבה"},
    {"id": "todah-3", "class": "todah", "text": "תודה רבה."},
    {"id": "todah-4", "class": "todah", "text": "תודה על הצפייה"},
    {"id": "todah-5", "class": "todah", "text": "תודה שצפיתם"},
    {"id": "todah-6", "class": "todah", "text": "תודה רבה לכם"},
    # subtitle credits (Hebrew)
    {"id": "subs-he-1", "class": "subtitles", "text": "כתוביות"},
    {"id": "subs-he-2", "class": "subtitles", "text": "כתוביות בעברית"},
    {"id": "subs-he-3", "class": "subtitles", "text": "תרגום וכתוביות"},
    # subscribe-junk (English + Hebrew CTA)
    {"id": "sub-1", "class": "subscribe", "text": "Subscribe!"},
    {"id": "sub-2", "class": "subscribe", "text": "please subscribe"},
    {"id": "sub-3", "class": "subscribe", "text": "Thanks for watching"},
    {"id": "sub-4", "class": "subscribe", "text": "Thank you for watching"},
    {"id": "sub-5", "class": "subscribe", "text": "like and subscribe"},
    {"id": "sub-6", "class": "subscribe", "text": "Subtitles by the Amara.org community"},
    {"id": "sub-7", "class": "subscribe", "text": "אל תשכחו להירשם לערוץ"},
    {"id": "sub-8", "class": "subscribe", "text": "www."},
    # CJK credits
    {"id": "cjk-1", "class": "cjk", "text": "ご視聴ありがとうございました"},
    {"id": "cjk-2", "class": "cjk", "text": "請訂閱我的頻道"},
    {"id": "cjk-3", "class": "cjk", "text": "字幕"},
    {"id": "cjk-4", "class": "cjk", "text": "チャンネル登録"},
    # Russian credits
    {"id": "ru-1", "class": "ru", "text": "Продолжение следует"},
    {"id": "ru-2", "class": "ru", "text": "Субтитры сделал"},
    {"id": "ru-3", "class": "ru", "text": "Спасибо за просмотр"},
    {"id": "ru-4", "class": "ru", "text": "Подписывайтесь на канал"},
    # Arabic credits
    {"id": "ar-1", "class": "ar", "text": "اشتركوا في القناة"},
    {"id": "ar-2", "class": "ar", "text": "شكرا للمشاهدة"},
    {"id": "ar-3", "class": "ar", "text": "ترجمة"},
    # repeat loops — the 'ма ма ма' spirals
    {"id": "rep-1", "class": "repeat", "text": "ма ма ма ма ма"},
    {"id": "rep-2", "class": "repeat", "text": "אמא אמא אמא אמא אמא"},
    {"id": "rep-3", "class": "repeat", "text": "amma amma amma amma"},
    {"id": "rep-4", "class": "repeat", "text": "אבאבאבאבאבאב"},
    # char-runs / low variety
    {"id": "run-1", "class": "charrun", "text": "אבגאהההההההה"},
    {"id": "run-2", "class": "charrun", "text": "aaaaaaaaaaaa"},
    {"id": "run-3", "class": "charrun", "text": "בבבבבבבבב"},
    # observed IN THE WILD inside the old mic's own voice_corpus (K13 review,
    # 2026-08-12): the old pipeline SAVED these hallucinations as "corpus" —
    # the exact contamination class the guard + owner gate exist to kill.
    {"id": "todah-wild-1", "class": "todah", "text": "תודה רבה לכם.",
     "note": "verbatim in voice_corpus 20260630_172208_858661.txt"},
    {"id": "run-wild-1", "class": "charrun", "text": "‫אוווווווווווו",
     "note": "219-char vav-run in voice_corpus 20260702_193832_667020.txt (representative prefix)"},
    # ultra-short junk
    {"id": "short-1", "class": "short", "text": "a"},
    {"id": "short-2", "class": "short", "text": "?"},
    {"id": "short-3", "class": "short", "text": "1"},
]

# Real-speech shapes that sit CLOSE to a detector and must pass (the
# aba/ima-pass property and its cousins).
MUST_PASS: list[dict] = [
    {"id": "pass-aba", "class": "real_word", "text": "אבא"},
    {"id": "pass-ima", "class": "real_word", "text": "אמא"},
    {"id": "pass-aba-sent", "class": "real_word", "text": "אבא בוא הנה"},
    {"id": "pass-het", "class": "real_word", "text": "החתול חתך חתיכת חסה"},
    {"id": "pass-heh", "class": "real_word", "text": "ההר ההוא"},
    {"id": "pass-ken", "class": "real_word", "text": "כן"},
    {"id": "pass-lo", "class": "real_word", "text": "לא"},
    {"id": "pass-en", "class": "real_word", "text": "This is spoken English, plain and simple."},
    {"id": "pass-mix", "class": "real_word", "text": "תריץ את הסקריפט על eran1 עכשיו בבקשה"},
    {"id": "pass-url", "class": "real_word", "text": "הכתובת היא www.example.com ותשמור אותה בקובץ"},
]


# K13 REVIEW LEDGER (2026-08-12) \u2014 the deterministic sample is drawn from the
# OLD mic's own corpus-capture transcripts, which CONTAIN its hallucinations
# (that contamination is scar 49 / RC-8's whole point). Sampled entries that a
# human/agent review identified as the old pipeline's saved hallucinations are
# excluded HERE, by name, with the reason \u2014 a transparent auditable ledger,
# never a silent filter, and NEVER a guard call (selection stays guard-blind;
# exclusion is by review verdict only). Excluded files are recorded in the
# manifest under excluded_as_junk so anyone can re-audit the call.
REVIEWED_JUNK: dict[str, dict] = {
    "20260630_172208_858661.txt": {
        "class": "todah",
        "reason": "verbatim \u05EA\u05D5\u05D3\u05D4-family attractor ('\u05EA\u05D5\u05D3\u05D4 \u05E8\u05D1\u05D4 \u05DC\u05DB\u05DD.') \u2014 the #1 "
                  "Hebrew silence hallucination, saved by the old mic into its "
                  "own corpus; dropped BY DESIGN (scar 28 accepted tradeoff), "
                  "so it cannot serve as guard-pass ground truth"},
    "20260702_193832_667020.txt": {
        "class": "charrun",
        "reason": "219-char vav-run ('\u05D0\u05D5\u05D5\u05D5\u05D5\u2026') \u2014 a char-run hallucination the "
                  "old mic saved as corpus; not speech"},
    "20260701_020520_635739.txt": {
        "class": "laughter",
        "reason": "78-char \u05D0\u05D4\u05D4-blob \u2014 the laughfix class (scar 28) saved by "
                  "the old mic as corpus; not speech"},
}


def hebrew_letters(text: str) -> int:
    return sum(1 for c in text if "\u0590" <= c <= "\u05FF")


def select_real(corpus_dir: Path, n: int) -> tuple[list[dict], list[dict]]:
    """Deterministic, guard-blind sample of real Hebrew utterances.
    Returns (picked, excluded_as_junk)."""
    eligible: list[tuple[str, str]] = []
    for f in sorted(corpus_dir.glob("*.txt")):
        norm = textmetrics.normalize_ws(f.read_text(encoding="utf-8", errors="replace"))
        if len(norm) >= MIN_CHARS and hebrew_letters(norm) >= MIN_HEBREW_LETTERS:
            eligible.append((f.name, norm))
    if not eligible:
        raise SystemExit(f"no eligible utterances under {corpus_dir}")
    clean = [(name, norm) for name, norm in eligible if name not in REVIEWED_JUNK]
    stride = max(1, len(clean) // n)
    picked = clean[::stride][:n]
    excluded = [{"file": name, "class": REVIEWED_JUNK[name]["class"],
                 "reason": REVIEWED_JUNK[name]["reason"]}
                for name, _ in eligible if name in REVIEWED_JUNK]
    return ([{"file": name, "sha256": textmetrics.sha256_text(norm),
              "n_chars": len(norm)} for name, norm in picked], excluded)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args(argv)

    real, excluded = select_real(args.corpus_dir, args.n)
    manifest = {
        "version": 1,
        "built_by": "tools/build_textguard_corpus.py",
        "voice_corpus_dir": str(args.corpus_dir),
        "selection": {
            "rule": "sorted *.txt; whitespace-normalized; kept if "
                    f"len>={MIN_CHARS} and hebrew_letters>={MIN_HEBREW_LETTERS}; "
                    "fixed stride to n — deterministic and guard-blind "
                    "(no guard call during selection, so the CER measurement "
                    "cannot be cherry-picked); reviewed-junk exclusions are a "
                    "named, reasoned ledger (see excluded_as_junk), never a "
                    "silent filter",
            "n_requested": args.n,
            "privacy": "scar 49 — filenames + sha256 + lengths only; "
                       "transcript text never enters git",
        },
        "hallucinations": HALLUCINATIONS,
        "must_pass": MUST_PASS,
        "real_he": real,
        "excluded_as_junk": excluded,
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    total = sum(e["n_chars"] for e in real)
    print(f"wrote {OUT}")
    print(f"  hallucinations={len(HALLUCINATIONS)} must_pass={len(MUST_PASS)} "
          f"real_he={len(real)} (total {total} ref chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
