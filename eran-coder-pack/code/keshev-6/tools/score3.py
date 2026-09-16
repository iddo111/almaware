# -*- coding: utf-8 -*-
"""Score the THREE-way A/B (eran1 old :8737 | PC :8738 | eran1 new :8739).

Same scoring code as score.py -- normalisation, edit distance, the degenerate-
reference filter and the name table are copied unchanged so the numbers stay
comparable to the 2026-09-04 report line for line. The only change is that
there are three columns instead of two.

WHAT THE NUMBERS ARE WORTH, said before they are read (unchanged from score.py):
the reference decoder (ivrit-ai/whisper-large-v3, non-turbo, on eran2) is a
STRONGER reader of the same audio, not ground truth, and it shares a fine-tuning
lineage with the model both KESHEV-6 servers run -- so WER/CER against it
FLATTERS them both equally. Here that bias is harmless: the question is not
"is KESHEV-6 better than the old model" (that was settled on 09-04) but
"is the DGX copy of KESHEV-6 the same as the PC copy", and both sides of THAT
comparison carry the identical bias.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDES = ("old", "pc", "dgx")
LABEL = {"old": "eran1 :8737 (old model)",
         "pc": "PC :8738 (KESHEV-6)",
         "dgx": "eran1 :8739 (KESHEV-6 NEW)"}

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
    """A reference row that is a repetition loop, not a transcript. See score.py."""
    t = norm(s)
    if not t:
        return True
    run = best = 1
    for a, b in zip(t, t[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    if best >= 6:
        return True
    w = t.split()
    if len(w) >= 4 and len(set(w)) <= max(1, len(w) // 4):
        return True
    return False


def rates(hyp: str, ref: str):
    """(word_errors, ref_words, char_errors, ref_chars)"""
    h, r = norm(hyp), norm(ref)
    return edit(h.split(), r.split()), len(r.split()), edit(list(h), list(r)), len(r)


def pct(sorted_v, q):
    if not sorted_v:
        return 0
    i = min(len(sorted_v) - 1, max(0, int(round(q * len(sorted_v))) - 1))
    return sorted_v[i]


# The names. GOOD = written the way Iddo says them; BAD = the exact garbles the
# old model produced on this same audio on 2026-09-03. Copied from score.py.
GOOD = {
    "צ'ינצ'ילה": "Chinchilla",
    "סונט": "Sonnet",
    "OpenClaw": "OpenClaw",
    "Hermes": "Hermes",
    "פסייטראנס": "psytrance",
    "קלוד": "Claude",
    "אופוס": "Opus",
    "מיקו": "MIKO",
    "ערן": "ERAN",
    "וינסטון": "WINSTON",
}
BAD = {
    "צ'רלי וחצי": "Chinchilla",
    "סונת": "Sonnet",
    "מופן קלו": "OpenClaw",
    "אופן קלו": "OpenClaw",
    "אופנקלו": "OpenClaw",
    "ארמס": "Hermes",
    "רמס": "Hermes",
    "פסייטרנס": "psytrance",
}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ab_name = sys.argv[1] if len(sys.argv) > 1 else "ab3_20260905.jsonl"
    ab_path = ROOT / "state" / ab_name
    ab = [json.loads(l) for l in ab_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    ref = {}
    refp = ROOT / "state/ref.jsonl"
    if refp.exists():
        for l in refp.read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l)
                ref[d["wav"]] = d["ref"]
    print(f"A/B rows {len(ab)}   reference rows {len(ref)}   file {ab_path.name}\n")

    # ---- transport
    print("TRANSPORT")
    print(f"{'side':<28} {'http200':>8} {'errors':>7} {'empty':>7}")
    for s in SIDES:
        ok = sum(1 for r in ab if r.get(s, {}).get("http") == 200)
        err = sum(1 for r in ab if r.get(s, {}).get("http") != 200)
        emp = sum(1 for r in ab if not (r.get(s, {}).get("text") or "").strip())
        print(f"{LABEL[s]:<28} {ok:>8} {err:>7} {emp:>7}")

    # ---- latency
    print("\nLATENCY, client wall clock (ms) - LAN hop included for eran1")
    print(f"{'side':<28} {'p50':>7} {'p95':>7} {'max':>7}")
    for s in SIDES:
        v = sorted(r[s]["wall_ms"] for r in ab if r.get(s, {}).get("http") == 200)
        print(f"{LABEL[s]:<28} {pct(v, 0.5):>7} {pct(v, 0.95):>7} {(v[-1] if v else 0):>7}")

    # ---- WER/CER
    n_deg = sum(1 for r in ab if r["wav"] in ref and degenerate(ref[r["wav"]]))
    print(f"\nreference rows dropped as repetition loops: {n_deg}")
    for label, keep in (("ALL usable reference rows", lambda g: True),
                        ("SENTENCES ONLY (reference >= 4 words)",
                         lambda g: len(norm(g).split()) >= 4)):
        tot = {s: [0, 0, 0, 0] for s in SIDES}
        n_scored = 0
        for r in ab:
            gt = ref.get(r["wav"])
            if not gt or degenerate(gt) or not keep(gt):
                continue
            n_scored += 1
            for s in SIDES:
                for i, v in enumerate(rates(r.get(s, {}).get("text", ""), gt)):
                    tot[s][i] += v
        if not n_scored:
            continue
        print(f"\n{label}  (n={n_scored})")
        print(f"{'side':<28} {'WER':>8} {'CER':>8}")
        for s in SIDES:
            we, rw, ce, rc = tot[s]
            print(f"{LABEL[s]:<28} {we / max(rw, 1) * 100:>7.1f}% {ce / max(rc, 1) * 100:>7.1f}%")

    # ---- names (unbiased: no reference decoder involved)
    print("\nNAMES (unbiased - no reference decoder involved)")
    print(f"{'name':<12}" + "".join(f"{s + ' ok':>9}" for s in SIDES)
          + "  " + "".join(f"{s + ' bad':>10}" for s in SIDES))
    tok = {s: 0 for s in SIDES}
    tbad = {s: 0 for s in SIDES}
    for heb, en in GOOD.items():
        ok = {s: sum(r.get(s, {}).get("text", "").count(heb) for r in ab) for s in SIDES}
        bad = {s: sum(r.get(s, {}).get("text", "").count(b) for r in ab
                      for b, e in BAD.items() if e == en) for s in SIDES}
        for s in SIDES:
            tok[s] += ok[s]
            tbad[s] += bad[s]
        if any(ok.values()) or any(bad.values()):
            print(f"{en:<12}" + "".join(f"{ok[s]:>9}" for s in SIDES)
                  + "  " + "".join(f"{bad[s]:>10}" for s in SIDES))
    print(f"{'TOTAL':<12}" + "".join(f"{tok[s]:>9}" for s in SIDES)
          + "  " + "".join(f"{tbad[s]:>10}" for s in SIDES))

    # ---- THE DECISIVE ONE: is the DGX copy the same decoder as the PC copy?
    same = sum(1 for r in ab if norm(r.get("pc", {}).get("text", ""))
               == norm(r.get("dgx", {}).get("text", "")))
    print(f"\nPC :8738 vs eran1 :8739 - IDENTICAL text (normalised): "
          f"{same}/{len(ab)}  ({same / max(len(ab), 1) * 100:.1f}%)")
    diffs = [r for r in ab if norm(r.get("pc", {}).get("text", ""))
             != norm(r.get("dgx", {}).get("text", ""))]
    if diffs:
        print("\nEvery segment where the two KESHEV-6 copies disagree "
              "(printed in full - a difference you cannot see is not a measurement):")
        for r in diffs:
            print(f"  {r['wav'][9:15]}  PC : {r['pc'].get('text', '')!r}")
            print(f"          DGX: {r['dgx'].get('text', '')!r}")

    # ---- the human table
    outp = ROOT / "state/difftable3.md"
    lines = ["| # | wav | eran1 OLD :8737 | PC :8738 | eran1 NEW :8739 | reference |",
             "|---|---|---|---|---|---|"]
    k = 0
    for r in ab:
        o = r.get("old", {}).get("text", "")
        p = r.get("pc", {}).get("text", "")
        d = r.get("dgx", {}).get("text", "")
        if norm(o) == norm(p) == norm(d):
            continue
        k += 1
        g = ref.get(r["wav"], "")
        if degenerate(g):
            g = f"_(repetition loop - not counted)_ {g[:24]}"
        lines.append(f"| {k} | {r['wav'][9:15]} | {o} | {p} | {d} | {g} |")
    outp.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {outp} ({k} segments where at least two servers disagree)")


if __name__ == "__main__":
    main()
