#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BASELINE: how good is Qwen3.5-4B-Base on OUR code BEFORE we touch a weight.

Two falsifiable numbers, token-weighted over a deterministic held-out set:
  - mean per-token cross-entropy (nats) -> perplexity
  - next-token top-1 accuracy
Read-only. No weights are modified, no checkpoint is written.
"""
import json, os, sys, time, math
from collections import defaultdict
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

REPO = "Qwen/Qwen3.5-4B-Base"
HELD = os.path.expanduser("~/coder-base-logs/heldout.jsonl")
SEQ = 2048

rows = [json.loads(l) for l in open(HELD, encoding="utf-8")]
print(f"held-out files: {len(rows)}", flush=True)

tok = AutoTokenizer.from_pretrained(REPO)
model = AutoModelForCausalLM.from_pretrained(
    REPO, dtype=torch.bfloat16, attn_implementation="sdpa").cuda().eval()
model.config.use_cache = False

tot_nll = 0.0
tot_tok = 0
tot_hit = 0
per_ext = defaultdict(lambda: [0.0, 0, 0])   # nll, ntok, nhit
t0 = time.time()

for i, r in enumerate(rows):
    ids = tok(r["text"], return_tensors="pt").input_ids[:, :SEQ].cuda()
    if ids.shape[1] < 2:
        continue
    with torch.no_grad():
        logits = model(input_ids=ids).logits.float()
    tgt = ids[:, 1:]
    lg = logits[:, :-1]
    nll = torch.nn.functional.cross_entropy(
        lg.reshape(-1, lg.shape[-1]), tgt.reshape(-1), reduction="sum").item()
    hit = (lg.argmax(-1) == tgt).sum().item()
    n = tgt.numel()
    tot_nll += nll; tot_tok += n; tot_hit += hit
    e = per_ext[r["ext"]]
    e[0] += nll; e[1] += n; e[2] += hit
    if i % 25 == 0:
        print(f"  {i}/{len(rows)}  running CE={tot_nll/max(tot_tok,1):.4f}", flush=True)

ce = tot_nll / tot_tok
res = {
    "model": REPO,
    "revision": "1001bb4d826a52d1f399e183466143f4da7b741b",
    "heldout_files": len(rows),
    "heldout_tokens_scored": tot_tok,
    "seq_cap": SEQ,
    "MEAN_CE_NATS": round(ce, 4),
    "PERPLEXITY": round(math.exp(ce), 3),
    "BITS_PER_TOKEN": round(ce / math.log(2), 4),
    "TOP1_ACCURACY": round(tot_hit / tot_tok, 4),
    "seconds": round(time.time() - t0, 1),
    "per_ext": {k: {"files_tokens": v[1],
                    "ce": round(v[0] / v[1], 4),
                    "ppl": round(math.exp(v[0] / v[1]), 3),
                    "top1": round(v[2] / v[1], 4)}
                for k, v in sorted(per_ext.items(), key=lambda x: -x[1][1])},
}
print(json.dumps(res, indent=2), flush=True)
with open(os.path.expanduser("~/coder-base-logs/baseline_result.json"), "w") as f:
    json.dump(res, f, indent=2)
print("BASELINE_DONE", flush=True)
