"""Interpolate ivrit-ai and openai turbo, and evaluate the path between them.

WHY THIS IS A REASONABLE THING TO DO, not a hack:
ivrit-ai/whisper-large-v3-turbo is a *continued fine-tune* of
openai/whisper-large-v3-turbo -- same architecture, same 808.9M parameters, and
one is a descendant of the other. Two checkpoints related that way sit in the
same loss basin, where linear interpolation between them is well behaved
("linear mode connectivity"; model soups / task arithmetic rely on it).

The measured problem is that each endpoint is broken where the other is strong:
ivrit is 2x better on human-labelled Hebrew and 6x worse on human-labelled
English. If the basin is as well connected as theory predicts, some point on the
segment keeps most of ivrit's Hebrew while recovering most of openai's English,
which is a strictly better place to start a fine-tune than either end.

alpha = weight on ivrit. alpha=1 is pure ivrit, alpha=0 is pure openai.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as ev  # noqa: E402

IVRIT = "ivrit-ai/whisper-large-v3-turbo"
OPENAI = "openai/whisper-large-v3-turbo"


def build(alpha, out=None):
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    a = WhisperForConditionalGeneration.from_pretrained(IVRIT, dtype=torch.float32)
    b = WhisperForConditionalGeneration.from_pretrained(OPENAI, dtype=torch.float32)
    sa, sb = a.state_dict(), b.state_dict()
    assert set(sa) == set(sb), "state dict mismatch -- not the same architecture"
    merged = {k: (alpha * sa[k] + (1 - alpha) * sb[k]).to(torch.float32) for k in sa}
    a.load_state_dict(merged)
    proc = WhisperProcessor.from_pretrained(OPENAI)   # tokenizer is identical
    if out:
        a.save_pretrained(out, safe_serialization=True)
        proc.save_pretrained(out)
    return a, proc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alphas", default="0.25,0.5,0.75")
    ap.add_argument("--sets", default="iddo_tierA,fleurs_he,fleurs_en")
    ap.add_argument("--save-best-to", default=None)
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()

    table = {}
    for alpha in [float(x) for x in args.alphas.split(",")]:
        model, proc = build(alpha)
        model = model.to("cuda", torch.bfloat16)
        model.config.forced_decoder_ids = None
        model.generation_config.forced_decoder_ids = None
        res = {}
        for name in args.sets.split(","):
            rows, blob = ev.load_set(name)
            hyps, lids = ev.run(model, proc, rows, blob, batch=args.batch)
            res[name] = ev.score(rows, hyps, lids)
        table[alpha] = res
        print(f"[alpha={alpha:.2f}] " + "  ".join(
            f"{k} WER {v['wer']*100:6.2f} LID {v['lid_acc']*100:5.1f}"
            for k, v in res.items()), flush=True)
        del model
        torch.cuda.empty_cache()
    print(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
