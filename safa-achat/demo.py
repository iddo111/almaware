# -*- coding: utf-8 -*-
"""Safa Achat demo — runs fully offline on the bundled 18-concept wordlist.

Usage:  python demo.py
"""
from __future__ import annotations

import io
import sys
from statistics import mean

from safa import __version__, load_wordlist
from safa.cognates import LIKELY, POSSIBLE, all_pairs, score_pair
from safa.comparative import recurring_correspondences
from safa.data import LANG_NAMES

# Windows consoles may default to a legacy codepage; force UTF-8 output.
# Reconfigure IN PLACE. The old code wrapped sys.stdout.buffer in a NEW
# TextIOWrapper, which takes ownership of a buffer it does not own -- under
# pytest that closed the capture stream and the demo test died with
# "I/O operation on closed file" (fixed 2026-09-01).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, io.UnsupportedOperation):
    pass  # captured or already unicode-safe -- nothing to force.


def hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def fmt(p) -> str:
    return (
        f"{p.a.concept:<7} {p.a.lang}:{p.a.orthography} [{p.a.ipa}]  ~  "
        f"{p.b.lang}:{p.b.orthography} [{p.b.ipa}]  "
        f"score={p.combined:.2f}  -> {p.verdict}"
    )


def main() -> int:
    entries = load_wordlist()
    langs = sorted({e.lang for e in entries})
    concepts = sorted({e.concept for e in entries})
    hr(f"Safa Achat v{__version__} — comparative-linguistics prototype")
    print(f"Wordlist: {len(entries)} words, {len(concepts)} Swadesh-style concepts, "
          f"{len(langs)} languages: " + ", ".join(LANG_NAMES[l] for l in langs))
    print("Method: within-concept comparison only (semantic control), "
          "Dolgopolsky-style sound classes,")
    print("documented sound laws (Grimm / Proto-Semitic reflexes), "
          "recurring-correspondence check.")

    scores = all_pairs(entries, use_rules=True)

    hr("Top cognate candidates (within family)")
    shown = 0
    for p in scores:
        if p.same_family and p.combined >= LIKELY:
            print("  " + fmt(p))
            shown += 1
            if shown >= 15:
                break

    hr("Cross-family lookalikes (NOT claimed as cognates)")
    any_x = False
    for p in scores:
        if not p.same_family and p.combined >= POSSIBLE:
            print("  " + fmt(p))
            any_x = True
    if not any_x:
        print("  (none above threshold)")
    print("\n  Note: single-pair similarity across families (e.g. 'earth'~'eretz',")
    print("  'six'~'shesh') is NOT evidence of common origin. The comparative")
    print("  method requires the same sound correspondence to recur across many")
    print("  semantically matched pairs. This tool refuses to upgrade lookalikes.")

    hr("Sound-change rules in action (Grimm's law: Latin p ~ Germanic f)")
    ents = {(e.concept, e.lang): e for e in entries}
    pairs = [("father", "lat", "eng"), ("three", "lat", "deu"), ("ear", "heb", "arb")]
    for concept, la, lb in pairs:
        a, b = ents[(concept, la)], ents[(concept, lb)]
        raw = score_pair(a, b, use_rules=False)
        ruled = score_pair(a, b, use_rules=True)
        print(f"  {concept:<7} {la}:{a.ipa} ~ {lb}:{b.ipa}   "
              f"raw={raw.combined:.2f} -> with documented sound laws={ruled.combined:.2f}"
              + (f"   (rules: {', '.join(ruled.rules_applied)})" if ruled.rules_applied else ""))

    hr("Recurring correspondences (the comparative method's real test)")
    # min_count=3 distinct concepts: below that, chance pairs sneak in
    for la, lb in [("heb", "arb"), ("eng", "deu"), ("heb", "eng")]:
        rec = recurring_correspondences(entries, la, lb, min_count=3)
        print(f"  {LANG_NAMES[la]} ~ {LANG_NAMES[lb]}: "
              f"{len(rec)} recurring consonant correspondences (>=3 concepts)")
        for (ca, cb), cs in sorted(rec.items(), key=lambda kv: -len(kv[1]))[:6]:
            print(f"      {ca} : {cb}   in {len(cs)} concepts ({', '.join(sorted(cs)[:5])})")

    hr("Honesty check: same-family vs cross-family separation")
    same = [p.combined for p in scores if p.same_family]
    cross = [p.combined for p in scores if not p.same_family]
    print(f"  mean score, same family : {mean(same):.3f}  (n={len(same)})")
    print(f"  mean score, cross family: {mean(cross):.3f}  (n={len(cross)})")
    ok = mean(same) > mean(cross) + 0.15
    print(f"  separation > 0.15: {'YES' if ok else 'NO'} — "
          "known families cluster; no proto-world signal is claimed.")

    print("\nDone. See SPEC.md for scope and limits; this is evidence-ranking, "
          "not proto-language reconstruction.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
