# -*- coding: utf-8 -*-
"""KESHEV -- the doubled-hallucination hole in textguard.

Scar, 2026-08-23 06:14: the mic typed "‫תודה רבה. ‫תודה רבה." straight into
Iddo's chat. He never said it -- it is the classic Whisper silence hallucination,
and Whisper had simply emitted it TWICE inside one segment.

Measured on the shipped guard at that moment:

    text_verdict("‫תודה רבה.")                    -> (False, 'blocklist:תודה רבה')   BLOCKED
    text_verdict("‫תודה רבה. ‫תודה רבה.")     -> (True,  'ok')                    TYPED

Why: _blocklisted() compares the phrase against the WHOLE normalized text, and all
four of its rules are length-gated (`len(norm) <= len(phrase)+4`, `len(phrase) >=
0.5*len(norm)`, exact match). Doubling the text doubles len(norm) and every gate
closes. _repetitive() is the backstop, but its cheapest rule needs >=6 tokens and
its 2-gram rule needs >=8; a doubled two-word phrase has 4. The blind spot is
exactly "a short blocklisted phrase, said twice".

The fix is to collapse consecutive duplicate sentences BEFORE matching, so the
doubled form reduces to the single form the blocklist already knows.

The second half of this file is the part that matters more: real speech that
merely REPEATS A WORD must still get through. A guard that eats Iddo's sentences
is worse than one that leaks a "תודה".

Run:  python tests\test_textguard_repeat.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

import textguard  # noqa: E402

RLE = "‫"  # RIGHT-TO-LEFT EMBEDDING, what faster-whisper prefixes Hebrew with

MUST_BLOCK = [
    (RLE + "תודה רבה. " + RLE + "תודה רבה.", "the exact string that reached Iddo's chat"),
    ("תודה. תודה.", "doubled, no bidi mark"),
    ("תודה. תודה. תודה.", "tripled"),
    (RLE + "תודה רבה. " + RLE + "תודה רבה. " + RLE + "תודה רבה.", "tripled with bidi marks"),
    ("thank you. thank you.", "the English twin"),
    ("subscribe. subscribe.", "and the other classic"),
    ("תודה רבה", "single -- must still block (no regression)"),
    (RLE + "תודה רבה.", "single with bidi mark -- must still block"),
]

MUST_PASS = [
    ("תודה רבה על העזרה עם המיקרופון", "a real sentence that merely contains תודה"),
    ("כן כן אני שומע אותך טוב", "real speech repeats words"),
    ("תודה שתיקנת לי את המיקרופון הבוקר", "real gratitude in a real sentence"),
    ("בוא נעשה את זה שוב, בוא נעשה את זה נכון", "a repeated clause that is real speech"),
    ("מה קורה", "short real speech"),
    ("אני רוצה שהמודל של דרוויש ינגן סייטראנס", "ordinary long sentence"),
]


def main():
    failures = []

    for text, why in MUST_BLOCK:
        ok, reason = textguard.text_verdict(text)
        if ok:
            failures.append(f"LEAKED ({why}): {text!r} -> ok")
            print(f"FAIL  leaked  [{why}] {text!r}")
        else:
            print(f"PASS  blocked [{why}] reason={reason}")

    for text, why in MUST_PASS:
        ok, reason = textguard.text_verdict(text)
        if not ok:
            failures.append(f"ATE REAL SPEECH ({why}): {text!r} -> {reason}")
            print(f"FAIL  ate real speech [{why}] {text!r} -> {reason}")
        else:
            print(f"PASS  passed  [{why}] {text!r}")

    if failures:
        print(f"\nTEXTGUARD REPEAT: {len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("\nTEXTGUARD REPEAT OK")


if __name__ == "__main__":
    main()
