#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CODER-04: score a TRAINED export on the held-out set. The act that returns.

Right now nothing the coder training produces ever comes back. save-hf-every is
0, so no usable model is exported; the masters live only inside a 50 GB
optim.pt; no process on eran3 or anywhere else loads ckpt2; and ~/coder-base-logs
holds exactly one number -- taken on 2026-09-04 07:30, twelve hours BEFORE
training began, on the base model, by a script (baseline.py) that can only load
an HF repo by name and therefore cannot score a checkpoint at all.

So the held-out set that the four-guard contract protects (400 files, its own
exit code 5, a self-test at every boot) has never been re-scored. That is the
loop's open end: 430 hours of GB10 time producing a loss curve and nothing that
can be compared to anything.

This closes it. Same loop as baseline.py, token for token -- same SEQ cap, same
cross-entropy reduction, same top-1 rule, same per-extension breakdown -- so the
result is directly comparable to baseline_result.json rather than merely similar.
The only change is WHERE the weights come from.

  python3 eval_ckpt.py <export-dir|--base> [--out ~/coder-base-logs/eval.jsonl]

Appends one JSON line per run: {step, ce, ppl, bits, top1, per_ext, ...}. The
watchdog reports the newest line so the number is visible without anyone
remembering to look.

READ-ONLY with respect to training: it loads its own copy of the weights, writes
no checkpoint, and never touches ckpt2/.

RUN IT DELIBERATELY, NOT ON A TIMER.
  - This box holds ONE model at a time in 121 GB of unified memory and the
    trainer already reserves ~84 GB of it. A 4B bf16 model at seq 2048 is ~9 GB
    of weights plus activations -- it is expected to fit in the ~19 GB that
    remains, but that has NOT been measured, and an OOM here is an OOM for the
    trainer too.
  - Never run it while Qwen3-Coder-480B is resident.
  - Measure first with --dry-run 5 (five files, prints peak memory), and only
    then run the full 400.
"""
import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict

BASE_REPO = "Qwen/Qwen3.5-4B-Base"
BASE_REVISION = "1001bb4d826a52d1f399e183466143f4da7b741b"
HELD_DEFAULT = "~/coder-base-logs/heldout.jsonl"
OUT_DEFAULT = "~/coder-base-logs/eval.jsonl"
SEQ = 2048                     # identical to baseline.py -- do not "improve" it


def step_of(path):
    """Training step an export dir represents, from its `step_NNNNNNNN` name."""
    name = os.path.basename(os.path.normpath(path))
    if name.startswith("step_"):
        try:
            return int(name[5:])
        except ValueError:
            return None
    return None


def summarise(tot_nll, tot_tok, tot_hit, per_ext):
    """Pure: the same fields baseline_result.json carries, so the two compare."""
    if tot_tok <= 0:
        raise SystemExit("no tokens scored -- refusing to write a result")
    ce = tot_nll / tot_tok
    return {
        "MEAN_CE_NATS": round(ce, 4),
        "PERPLEXITY": round(math.exp(ce), 3),
        "BITS_PER_TOKEN": round(ce / math.log(2), 4),
        "TOP1_ACCURACY": round(tot_hit / tot_tok, 4),
        "heldout_tokens_scored": tot_tok,
        "per_ext": {k: {"files_tokens": v[1],
                        "ce": round(v[0] / v[1], 4),
                        "ppl": round(math.exp(v[0] / v[1]), 3),
                        "top1": round(v[2] / v[1], 4)}
                    for k, v in sorted(per_ext.items(), key=lambda x: -x[1][1])},
    }


def delta_vs_baseline(result, baseline):
    """Pure: the comparison a human actually wants, or None if no baseline.

    Lower CE is better, so a NEGATIVE delta_ce is an improvement. Say so in the
    field name -- a bare number invites the reader to guess the sign convention.
    """
    if not baseline:
        return None
    try:
        d_ce = result["MEAN_CE_NATS"] - baseline["MEAN_CE_NATS"]
        d_top1 = result["TOP1_ACCURACY"] - baseline["TOP1_ACCURACY"]
    except (KeyError, TypeError):
        return None
    return {
        "baseline_ce": baseline.get("MEAN_CE_NATS"),
        "delta_ce_nats_negative_is_better": round(d_ce, 4),
        "delta_top1_positive_is_better": round(d_top1, 4),
        "improved": bool(d_ce < 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="path to an HF export dir, or --base")
    ap.add_argument("--heldout", default=HELD_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--baseline", default="~/coder-base-logs/baseline_result.json")
    ap.add_argument("--dry-run", type=int, default=0,
                    help="score only this many files, print peak memory, write nothing")
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    held = os.path.expanduser(args.heldout)
    rows = [json.loads(l) for l in open(held, encoding="utf-8")]
    if args.dry_run:
        rows = rows[:args.dry_run]
    print(f"held-out files: {len(rows)}", flush=True)

    is_base = args.model in ("--base", "base", BASE_REPO)
    src = BASE_REPO if is_base else os.path.expanduser(args.model)
    if not is_base and not os.path.isdir(src):
        sys.exit(f"{src} is not a directory. Point this at an HF export "
                 f"(train.py --save-hf-every writes them under out/export/), "
                 f"not at a ckpt2/step_* optimiser checkpoint -- the masters "
                 f"inside optim.pt must be extracted first.")

    tok = AutoTokenizer.from_pretrained(src if not is_base else BASE_REPO)
    model = AutoModelForCausalLM.from_pretrained(
        src, dtype=torch.bfloat16, attn_implementation="sdpa").cuda().eval()
    model.config.use_cache = False

    tot_nll, tot_tok, tot_hit = 0.0, 0, 0
    per_ext = defaultdict(lambda: [0.0, 0, 0])
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
        tot_nll += nll
        tot_tok += n
        tot_hit += hit
        e = per_ext[r["ext"]]
        e[0] += nll
        e[1] += n
        e[2] += hit
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}  running CE={tot_nll/max(tot_tok,1):.4f}",
                  flush=True)

    res = summarise(tot_nll, tot_tok, tot_hit, per_ext)
    res.update({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": BASE_REPO if is_base else src,
        "revision": BASE_REVISION if is_base else None,
        "step": None if is_base else step_of(src),
        "heldout": held,
        "heldout_files": len(rows),
        "seq_cap": SEQ,
        "seconds": round(time.time() - t0, 1),
        "peak_gb": round(torch.cuda.max_memory_allocated() / 1024 ** 3, 2),
        "dry_run": bool(args.dry_run),
    })

    baseline = None
    bp = os.path.expanduser(args.baseline)
    if os.path.exists(bp):
        try:
            baseline = json.load(open(bp, encoding="utf-8"))
        except Exception:
            baseline = None
    d = delta_vs_baseline(res, baseline)
    if d:
        res["vs_base"] = d

    print(json.dumps(res, indent=2), flush=True)
    if args.dry_run:
        print("DRY RUN -- nothing written. Peak memory above is the number that "
              "decides whether the full run is safe alongside the trainer.")
        return
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    print(f"appended -> {out}", flush=True)
    print("EVAL_DONE", flush=True)


if __name__ == "__main__":
    main()
