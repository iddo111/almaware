"""Final head-to-head on every eval set, for the report.

Compares, on identical audio and identical scoring:
  openai turbo   -- what the mic app runs today (production)
  ivrit-ai turbo -- the off-the-shelf Hebrew model the task asked about
  soup_20        -- the interpolated starting point, UNTRAINED
  the fine-tune  -- whichever checkpoint won on WER with guards intact

Everything goes through common.score_norm, and the iddo_* references are
machine-generated, so those columns measure agreement with a machine labeller.
fleurs_* are human transcripts and are the only rows that measure accuracy
outright.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as ev  # noqa: E402

SETS = ["iddo_tierA", "iddo_eval", "retain", "iddo_en", "fleurs_he", "fleurs_en"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True,
                    help="comma-separated tag=path pairs")
    ap.add_argument("--sets", default=",".join(SETS))
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--out", default=os.path.expanduser("~/whisper-iddo/results/final.json"))
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    os.makedirs(os.path.expanduser("~/whisper-iddo/hyps"), exist_ok=True)
    table = {}
    for spec in args.models.split(","):
        tag, path = spec.split("=", 1)
        model, proc = ev.load_model(path)
        table[tag] = {}
        for name in args.sets.split(","):
            rows, blob = ev.load_set(name)
            hyps, lids = ev.run(model, proc, rows, blob, batch=args.batch)
            r = ev.score(rows, hyps, lids)
            table[tag][name] = r
            with open(os.path.expanduser(f"~/whisper-iddo/hyps/{tag}.{name}.jsonl"),
                      "w", encoding="utf-8") as f:
                for rr, h, l in zip(rows, hyps, lids):
                    f.write(json.dumps({"ref": rr["text"], "hyp": h, "lang": rr["lang"],
                                        "lid": l, "dur": rr["dur"]}, ensure_ascii=False) + "\n")
            print(f"[{tag}] {name:12s} WER {r['wer']*100:6.2f}  CER {r['cer']*100:6.2f}  "
                  f"LID {r['lid_acc']*100:5.1f}  he {r.get('wer_he', float('nan'))*100:6.2f}  "
                  f"en {r.get('wer_en', float('nan'))*100:6.2f}", flush=True)
        del model
        torch.cuda.empty_cache()
    json.dump(table, open(args.out, "w"), indent=2, ensure_ascii=False)

    # markdown table for the report
    print("\n| set | metric | " + " | ".join(table) + " |")
    print("|---|---|" + "---|" * len(table))
    for name in args.sets.split(","):
        for m in ("wer", "wer_he", "wer_en", "lid_acc"):
            vals = []
            for tag in table:
                v = table[tag][name].get(m)
                vals.append("-" if v is None else f"{v*100:.2f}")
            if all(v == "-" for v in vals):
                continue
            print(f"| {name} | {m} | " + " | ".join(vals) + " |")


if __name__ == "__main__":
    main()
