#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 2 - BUILD THE TRAINING MANIFEST.  Separate from both the teacher and the
trainer so that what was thrown away is auditable after the fact.

The filters, and why each exists:
  empty            - the teacher heard nothing; training on "" teaches silence
  degenerate       - repetition loops ("ששש...").  Same detector as keshev-6
                     score3.py, copied unchanged, because a loop is the teacher
                     failing, and training on a teacher's failure is the exact
                     mistake that sank iddo-lora-run2.
  too short/long   - < 0.6 s carries no phonetics; > 20 s is a VAD failure
  one-char / digit-only - not speech Iddo produced
"""
from __future__ import annotations
import argparse, json, re, unicodedata
from pathlib import Path
from collections import Counter

_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_PUNCT = re.compile(r"[^\w\u0590-\u05ff ]", re.UNICODE)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = _BIDI.sub("", s)
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def degenerate(s: str) -> bool:
    """Copied verbatim from keshev-6/tools/score3.py."""
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-secs", type=float, default=0.6)
    ap.add_argument("--max-secs", type=float, default=20.0)
    ap.add_argument("--min-words", type=int, default=1,
                    help="drop labels with fewer words than this")
    ap.add_argument("--max-dup", type=int, default=0,
                    help="keep at most N clips per identical normalised transcript "
                         "(0 = no cap)")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.labels).read_text(encoding="utf-8").splitlines() if l.strip()]
    why = Counter()
    keep = []
    for r in rows:
        t = (r.get("text") or "").strip()
        if not t:                                   why["empty"] += 1;      continue
        if degenerate(t):                           why["degenerate"] += 1; continue
        if not (args.min_secs <= r["secs"] <= args.max_secs): why["duration"] += 1; continue
        if len(norm(t)) < 2:                        why["too_short_text"] += 1; continue
        if not re.search(r"[\u0590-\u05ff]", t):    why["no_hebrew"] += 1;  continue
        if len(norm(t).split()) < args.min_words:   why["too_few_words"] += 1; continue
        keep.append(r)

    # MEASURED 2026-09-06, and the reason --max-dup exists: only 41% of the
    # teacher's transcripts are unique, and 67% of clips are 1-2 word VAD
    # fragments against 22% in the eval set. Training on that raw mix teaches
    # the model to emit two words and collapses CER for a reason that has
    # nothing to do with adapting to Iddo's voice.
    if args.max_dup > 0:
        seen, ded = Counter(), []
        for r in keep:
            k = norm(r["text"])
            if seen[k] < args.max_dup:
                ded.append(r)
                seen[k] += 1
            else:
                why["duplicate_phrase"] += 1
        keep = ded

    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in keep) + "\n", encoding="utf-8")
    hrs = sum(r["secs"] for r in keep) / 3600
    print(f"in {len(rows)}  kept {len(keep)}  ({hrs:.2f} h)")
    for k, v in why.most_common():
        print(f"  dropped {k:<16} {v:>6}  ({v/max(len(rows),1)*100:.1f}%)")
    # the hash list the judge will use to prove disjointness
    hp = Path(args.out).with_name("train_hashes.txt")
    hp.write_text("\n".join(r["sha256"] for r in keep) + "\n", encoding="utf-8")
    print("wrote", args.out, "and", hp.name)


if __name__ == "__main__":
    main()
