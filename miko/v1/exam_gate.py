"""MIKO v1 -- the exam gate.  לזכרה של עלמה ז"ל.   (code revision 2026-09-06, MIKO-05)

The 30-query hand-written exam is "the one number Iddo will actually care about" -- and it
was silently text-corrupted. In every Hebrew query that should carry the letter TAV
(U+05EA) the file held U+05AA instead (HEBREW ACCENT YERAH BEN YOMO, a *combining mark*):
13 of 30 queries, ZERO real tav in the whole file, while the corpus has 3588 tav and not a
single U+05AA. BM25 was therefore tokenising a truncated word, and e5_exam_emb.pt was
embedded from the corrupted strings. Nothing anywhere checked.

So this module exists, and it REFUSES -- it does not warn:

  assert_exam_valid(exam, by_id)        every query is well-formed Hebrew/Latin text and
                                        every target id really exists in the corpus
  assert_exam_cache_fresh(pack, exam)   a cached embedding pack (e5_exam_emb.pt) was
                                        embedded from EXACTLY these query strings
  exam_composition(exam, split)         what the exam actually measures, printed, not hidden

Composition is reported rather than enforced: on the 09-03 exam 26 of 30 targets are TRAIN
documents and only 4 are test, so the headline number mostly measures documents the nets
trained on. Rebalancing that is a v2-exam decision for Iddo, not a silent edit.
"""
from __future__ import annotations

import unicodedata

# Hebrew letters, plus the two Hebrew punctuation marks that legitimately appear in words.
HEB_LETTERS = set(range(0x05D0, 0x05EA + 1))
HEB_ALLOWED_PUNCT = {0x05BE, 0x05F3, 0x05F4}          # maqaf, geresh, gershayim
HEB_BLOCK = range(0x0591, 0x05F5)                      # the whole Hebrew block


def bad_hebrew_codepoints(text: str) -> list[tuple[int, str, str]]:
    """Hebrew-block codepoints that are neither letters nor allowed punctuation.

    That is: every cantillation accent (U+0591-U+05AF, which is where U+05AA lives), every
    nikud point (U+05B0-U+05BD, U+05BF-U+05C7), and the Yiddish ligatures. None of these
    belong in a hand-typed search query, and every one of them changes tokenization.
    """
    out = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp in HEB_BLOCK and cp not in HEB_LETTERS and cp not in HEB_ALLOWED_PUNCT:
            out.append((i, f"U+{cp:04X}", unicodedata.name(ch, "?")))
    return out


def check_exam(exam: list[dict], by_id: dict | None = None) -> dict:
    """Returns a report. Does not raise -- assert_exam_valid() is the gate."""
    bad_text, missing_target, empty = [], [], []
    for n, ex in enumerate(exam):
        q = ex.get("query", "")
        if not q or not q.strip():
            empty.append(n)
            continue
        bad = bad_hebrew_codepoints(q)
        if bad:
            bad_text.append({"i": n, "query": q, "bad": bad})
        if by_id is not None and ex.get("target_id") not in by_id:
            missing_target.append({"i": n, "target_id": ex.get("target_id")})
    return {
        "n": len(exam),
        "bad_text": bad_text,
        "missing_target": missing_target,
        "empty_query": empty,
        "PASS": not (bad_text or missing_target or empty),
    }


def assert_exam_valid(exam: list[dict], by_id: dict | None = None) -> dict:
    rep = check_exam(exam, by_id)
    if not rep["PASS"]:
        lines = ["EXAM-INVALID: refusing to report a number from this exam (MIKO-05)."]
        for b in rep["bad_text"]:
            marks = ", ".join(f"{cp} ({nm}) at {i}" for i, cp, nm in b["bad"])
            lines.append(f"  q[{b['i']}] carries non-letter Hebrew codepoints: {marks}")
            lines.append(f"           {b['query']}")
        for m in rep["missing_target"]:
            lines.append(f"  q[{m['i']}] target_id {m['target_id']!r} is not in the corpus")
        for i in rep["empty_query"]:
            lines.append(f"  q[{i}] has an empty query")
        raise SystemExit("\n".join(lines))
    return rep


def assert_exam_cache_fresh(pack: dict, exam: list[dict], name: str = "e5_exam_emb.pt") -> None:
    """A cached embedding pack must have been embedded from EXACTLY the current queries.

    This is the check that was missing on 09-03: exam.json's text and e5_exam_emb.pt's text
    can drift apart with no error, and every e5/adapter exam number then comes from strings
    nobody can see. (Repairing the tav on 2026-09-06 deliberately invalidates the old cache.)
    """
    cached_q = list(pack.get("queries", []))
    cached_t = list(pack.get("targets", []))
    now_q = [e["query"] for e in exam]
    now_t = [e["target_id"] for e in exam]
    if cached_q != now_q or cached_t != now_t:
        n_diff = sum(1 for a, b in zip(cached_q, now_q) if a != b) + abs(len(cached_q) - len(now_q))
        raise SystemExit(
            f"EXAM-CACHE-STALE: {name} was embedded from different text than exam.json "
            f"({n_diff} of {len(now_q)} queries differ). Any e5/adapter exam number from it "
            "would be a number about strings that no longer exist.\n"
            "  Re-embed on a fleet box (never the PC -- no inference here):\n"
            "    ssh eran3 \"cd ~/miko/v1 && python3 encode_e5.py\"\n"
            "  See MIKO-05.")


def exam_composition(exam: list[dict], split: dict | None = None) -> str:
    """What the exam measures, said out loud (MIKO-05)."""
    from collections import Counter
    langs = Counter(e.get("lang", "?") for e in exam)
    line = f"EXAM-COMPOSITION: n={len(exam)} by language {dict(langs)}"
    if split:
        member = {}
        for name in ("train", "val", "test"):
            member.update({i: name for i in split.get(name, [])})
        by_split = Counter(member.get(e["target_id"], "NOT-IN-SPLIT") for e in exam)
        line += f"; targets by split {dict(by_split)}"
        if by_split.get("train", 0) > len(exam) / 2:
            line += ("  <-- WARNING: most targets are TRAIN documents, so this number is "
                     "mostly about documents the nets trained on. See MIKO-05.")
    return line
