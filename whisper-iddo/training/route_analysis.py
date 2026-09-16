"""Is a two-model routed system better than either model alone?

Measured complementarity on his own speech:

  language-ID accuracy   his Hebrew (tierA)   his English (iddo_en)
  openai turbo                  77.1                 99.4
  ft70 (fine-tuned)             95.0                 79.9

Each model is good at recognising exactly the language the other one fumbles, and
the mic app already runs a language-ID pass before decoding, so routing costs one
extra forward pass and no new machinery.

This scores, from the saved per-utterance dumps (no GPU needed):
  * each model alone
  * routed: use ROUTER's language decision, then take the Hebrew specialist's text
    for 'he' and the English specialist's text for 'en'
  * oracle routing: the ceiling, if language ID were perfect
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import corpus_cer, corpus_wer  # noqa: E402

H = os.path.expanduser("~/whisper-iddo/hyps")


def load(tag, name):
    p = os.path.join(H, f"{tag}.{name}.jsonl")
    if not os.path.exists(p):
        return None
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def score(rows, hyps):
    return corpus_wer([r["ref"] for r in rows], hyps) * 100


def main():
    he_model = sys.argv[1] if len(sys.argv) > 1 else "ft70"
    en_model = sys.argv[2] if len(sys.argv) > 2 else "base_openai_whisper-large-v3-turbo"
    sets = sys.argv[3:] or ["iddo_tierA", "iddo_eval", "retain", "iddo_en"]

    print(f"he-specialist={he_model}   en-specialist={en_model}\n")
    for name in sets:
        A = load(he_model, name)
        B = load(en_model, name)
        if not A or not B or len(A) != len(B):
            print(f"{name:12s}  (missing or mismatched dumps)")
            continue

        def pick(rule):
            out = []
            for a, b in zip(A, B):
                out.append(a["hyp"] if rule(a, b) else b["hyp"])
            return score(A, out)

        res = {
            "he-spec alone": score(A, [r["hyp"] for r in A]),
            "en-spec alone": score(B, [r["hyp"] for r in B]),
            "router=he-spec": pick(lambda a, b: a["lid"] == "he"),
            "router=en-spec": pick(lambda a, b: b["lid"] == "he"),
            "router=AND": pick(lambda a, b: a["lid"] == "he" and b["lid"] == "he"),
            "router=OR": pick(lambda a, b: a["lid"] == "he" or b["lid"] == "he"),
            "ORACLE": pick(lambda a, b: a["lang"] in ("he", "mixed")),
        }
        if name == sets[0]:
            print(f"{'set':12s} " + " ".join(f"{k:>14s}" for k in res))
        print(f"{name:12s} " + " ".join(f"{v:14.2f}" for v in res.values()))


if __name__ == "__main__":
    main()
