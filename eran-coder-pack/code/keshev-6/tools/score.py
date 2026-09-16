# -*- coding: utf-8 -*-
"""Score the A/B: WER/CER against the reference decoder, names, and the diff table.

WHAT THE NUMBERS ARE WORTH, said before they are read:
  * The reference (ivrit-ai/whisper-large-v3, non-turbo, on eran2) is a
    STRONGER reader of the same audio, not ground truth. It shares a
    fine-tuning lineage with the model KESHEV-6 serves, so WER-against-it
    FLATTERS KESHEV-6. Read it as a tie-breaker, never as a verdict.
  * The unbiased evidence is the name table and the sentences Iddo actually
    said - both are checkable by eye, by him, in the morning.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_BIDI = re.compile("[‎‏‪-‮⁦-⁩]")
_PUNCT = re.compile(r"[^\w֐-׿ ]", re.UNICODE)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = _BIDI.sub("", s)
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def edit(a: list, b: list) -> int:
    if not a:
        return len(b)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def degenerate(s: str) -> bool:
    """Is this reference row a repetition loop rather than a transcript?

    MEASURED, and the reason this function exists: the reference was run
    through transformers' plain `generate`, which has no compression-ratio or
    no-speech guard, and on tonight's breath/laughter clips it fell into loops -
    a single letter repeated 160 times. Its mean output was 56 characters
    against 24-27 for both servers under test. Scoring against those rows does
    not compare the servers, it measures which one is longer.

    So they are EXCLUDED, and the count is printed: a filter you cannot see the
    size of is a thumb on the scale.
    """
    t = norm(s)
    if not t:
        return True
    run = best = 1
    for a, b in zip(t, t[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    if best >= 6:                      # 'ששששששש'
        return True
    w = t.split()
    if len(w) >= 4 and len(set(w)) <= max(1, len(w) // 4):
        return True                    # the same word over and over
    return False


def rates(hyp: str, ref: str) -> tuple[int, int, int, int]:
    """(word_errors, ref_words, char_errors, ref_chars)"""
    h, r = norm(hyp), norm(ref)
    return edit(h.split(), r.split()), len(r.split()), edit(list(h), list(r)), len(r)


def main() -> None:
    ab = [json.loads(l) for l in (ROOT / "state/ab_ok.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    refp = ROOT / "state/ref.jsonl"
    ref = {}
    if refp.exists():
        for l in refp.read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l)
                ref[d["wav"]] = d["ref"]
    print(f"A/B rows {len(ab)}   reference rows {len(ref)}")

    n_deg = sum(1 for r in ab if r["wav"] in ref and degenerate(ref[r["wav"]]))
    print(f"reference rows dropped as repetition loops: {n_deg}")

    for label, keep in (("ALL usable reference rows", lambda g: True),
                        ("SENTENCES ONLY (reference >= 4 words)",
                         lambda g: len(norm(g).split()) >= 4)):
        tot = {"old": [0, 0, 0, 0], "new": [0, 0, 0, 0]}
        wins = {"old": 0, "new": 0, "tie": 0}
        n_scored = 0
        for r in ab:
            gt = ref.get(r["wav"])
            if not gt or degenerate(gt) or not keep(gt):
                continue
            n_scored += 1
            per = {}
            for side in ("old", "new"):
                per[side] = rates(r[side].get("text", ""), gt)
                for i, v in enumerate(per[side]):
                    tot[side][i] += v
            o, n = per["old"][0], per["new"][0]
            wins["tie" if o == n else ("old" if o < n else "new")] += 1
        if not n_scored:
            continue
        print(f"\n{label}  (n={n_scored})")
        print(f"{'':<6} {'WER':>8} {'CER':>8}")
        for side in ("old", "new"):
            we, rw, ce, rc = tot[side]
            print(f"{side:<6} {we/max(rw,1)*100:>7.1f}% {ce/max(rc,1)*100:>7.1f}%")
        print(f"       closer to the reference: new {wins['new']}, "
              f"old {wins['old']}, tie {wins['tie']}")

    # ---- names
    GOOD = {"צ'ינצ'ילה": "Chinchilla", "סונט": "Sonnet", "OpenClaw": "OpenClaw",
            "Hermes": "Hermes", "פסייטראנס": "psytrance", "קלוד": "Claude",
            "אופוס": "Opus", "מיקו": "MIKO", "ערן": "ERAN", "וינסטון": "WINSTON"}
    BAD = {"צ'רלי וחצי": "Chinchilla", "סונת": "Sonnet", "מופן קלו": "OpenClaw",
           "אופן קלו": "OpenClaw", "אופנקלו": "OpenClaw", "ארמס": "Hermes",
           "רמס": "Hermes", "פסייטרנס": "psytrance"}
    print("\nNAMES (unbiased - no reference decoder involved)")
    print(f"{'name':<12} {'old ok':>7} {'new ok':>7} {'old garble':>11} {'new garble':>11}")
    for heb, en in GOOD.items():
        o = sum(r["old"].get("text", "").count(heb) for r in ab)
        n = sum(r["new"].get("text", "").count(heb) for r in ab)
        og = sum(r["old"].get("text", "").count(b) for r in ab for b, e in BAD.items() if e == en)
        ng = sum(r["new"].get("text", "").count(b) for r in ab for b, e in BAD.items() if e == en)
        if o or n or og or ng:
            print(f"{en:<12} {o:>7} {n:>7} {og:>11} {ng:>11}")

    # ---- the human table
    outp = ROOT / "state/difftable.md"
    lines = ["| # | wav | OLD :8737 | NEW :8738 | reference |", "|---|---|---|---|---|"]
    k = 0
    for r in ab:
        o, n = r["old"].get("text", ""), r["new"].get("text", "")
        if norm(o) == norm(n):
            continue
        k += 1
        g = ref.get(r["wav"], "")
        # a 160-character repetition loop is not a reference, and pasting one
        # into a table Iddo has to read is just noise wearing evidence's clothes
        if degenerate(g):
            g = f"_(לולאת חזרות — לא נספר)_ {g[:24]}…"
        lines.append(f"| {k} | {r['wav'][9:15]} | {o} | {n} | {g} |")
    outp.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {outp} ({k} segments where the two servers disagree)")


if __name__ == "__main__":
    main()
