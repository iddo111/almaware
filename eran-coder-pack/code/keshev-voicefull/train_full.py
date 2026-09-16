#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 3 - THE BUILDER.  FULL fine-tune of ivrit-ai/whisper-large-v3-turbo.

FULL, not LoRA: every parameter of the 809M model carries a gradient.  There is
no adapter, no rank, no frozen base.  --assert-full verifies that at startup and
refuses to run if anything is frozen, because "full fine-tune" is a claim this
program should not be able to make falsely.

THE BUILDER IS NOT THE JUDGE.  This program:
  * cannot read the eval set - it aborts if an eval path is reachable from its
    arguments, and it never imports the judge;
  * computes NO accuracy metric of any kind.  It prints a training loss, which
    is a description of the optimisation, not a verdict on the model;
  * performs NO checkpoint selection.  The final step's weights are what the
    judge receives.  Selecting a checkpoint requires a criterion, and every
    criterion available here would be a metric the builder graded itself on.

Of ten failures on 2026-09-05, zero were caught by whoever built the thing.
That is the reason for every restriction above.
"""
from __future__ import annotations
import argparse, json, math, os, sys, time, wave
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (WhisperProcessor, WhisperForConditionalGeneration,
                          get_cosine_schedule_with_warmup)

BASE = os.environ.get("BASE_MODEL", "ivrit-ai/whisper-large-v3-turbo")


class Clips(Dataset):
    def __init__(self, manifest, audio_dir, proc):
        self.rows = [json.loads(l) for l in
                     Path(manifest).read_text(encoding="utf-8").splitlines() if l.strip()]
        self.dir = Path(audio_dir)
        self.proc = proc

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        with wave.open(str(self.dir / r["wav"])) as w:
            a = np.frombuffer(w.readframes(w.getnframes()),
                              dtype=np.int16).astype(np.float32) / 32768.0
        feat = self.proc.feature_extractor(
            a, sampling_rate=16000, return_tensors="np").input_features[0]
        ids = self.proc.tokenizer(r["text"]).input_ids
        return {"input_features": feat, "labels": ids}


def make_collate(dec_start):
    def collate(batch):
        feats = torch.tensor(np.stack([b["input_features"] for b in batch]))
        n = max(len(b["labels"]) for b in batch)
        lab = torch.full((len(batch), n), -100, dtype=torch.long)
        for i, b in enumerate(batch):
            lab[i, :len(b["labels"])] = torch.tensor(b["labels"], dtype=torch.long)
        if bool((lab[:, 0] == dec_start).all()):   # HF whisper shifts internally
            lab = lab[:, 1:].contiguous()
        return feats, lab
    return collate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--assert-full", action="store_true")
    ap.add_argument("--no-checkpoint", action="store_true",
                    help="disable gradient checkpointing - it halves memory but "
                         "roughly doubles compute, and memory is not the binding "
                         "constraint on this box")
    args = ap.parse_args()

    # --- refusal 1: the builder must not be able to reach the eval set
    mp = Path(args.manifest).resolve()
    ad = Path(args.audio).resolve()
    for p in (mp, ad):
        if "eval" in p.parts or "okwavs" in p.parts:
            sys.exit("REFUSED: the builder was pointed at an eval path (%s). "
                     "The builder is not the judge." % p)

    proc = WhisperProcessor.from_pretrained(BASE, language="he", task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(BASE).to("cuda")
    model.config.forced_decoder_ids = None
    model.generation_config.language = "he"
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None
    if not args.no_checkpoint:
        model.gradient_checkpointing_enable()
    model.config.use_cache = False

    # --- refusal 2: prove this really is a FULL fine-tune
    tot = sum(p.numel() for p in model.parameters())
    tr = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print("parameters: %.1fM total, %.1fM trainable (%.2f%%)"
          % (tot / 1e6, tr / 1e6, tr / tot * 100))
    if args.assert_full and tr != tot:
        sys.exit("REFUSED: %d parameters are frozen. This was asked to be a FULL "
                 "fine-tune, not a LoRA. Refusing to mislabel the run." % (tot - tr))

    ds = Clips(mp, ad, proc)
    dl = DataLoader(ds, batch_size=args.batch, shuffle=True, num_workers=args.workers,
                    collate_fn=make_collate(model.config.decoder_start_token_id),
                    pin_memory=True, drop_last=True,
                    persistent_workers=args.workers > 0)
    steps = max(1, int(len(dl) * args.epochs) // args.accum)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01,
                            betas=(0.9, 0.98))
    sch = get_cosine_schedule_with_warmup(opt, int(0.03 * steps), steps)
    print("%d clips | %d batches/epoch | %d optimiser steps | lr %g"
          % (len(ds), len(dl), steps, args.lr), flush=True)

    outp = Path(args.out)
    outp.mkdir(parents=True, exist_ok=True)
    logf = (outp / "trainloss.jsonl").open("a", encoding="utf-8")
    model.train()
    step = 0
    run = 0.0
    nb = 0
    t0 = time.monotonic()
    done = False
    for _ep in range(math.ceil(args.epochs)):
        if done:
            break
        for i, (feats, lab) in enumerate(dl):
            feats = feats.to("cuda", non_blocking=True)
            lab = lab.to("cuda", non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(input_features=feats, labels=lab).loss
            (loss / args.accum).backward()
            run += loss.item()
            nb += 1
            if (i + 1) % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sch.step()
                opt.zero_grad(set_to_none=True)
                step += 1
                if step <= 3 or step % 25 == 0:
                    el = time.monotonic() - t0
                    rec = {"step": step, "loss": round(run / max(nb, 1), 4),
                           "lr": round(sch.get_last_lr()[0], 8),
                           "elapsed_s": int(el),
                           "eta_min": round((steps - step) * el / max(step, 1) / 60, 1)}
                    print("  " + json.dumps(rec), flush=True)
                    logf.write(json.dumps(rec) + "\n")
                    logf.flush()
                    run = 0.0
                    nb = 0
                if step >= steps:
                    done = True
                    break

    # --- NO checkpoint selection. The final weights are what the judge gets.
    model.config.use_cache = True
    model.save_pretrained(str(outp / "hf"))
    proc.save_pretrained(str(outp / "hf"))
    (outp / "PROVENANCE.json").write_text(json.dumps({
        "base": BASE,
        "kind": "FULL fine-tune (no LoRA, no frozen layers)",
        "manifest": str(mp),
        "clips": len(ds),
        "optimiser_steps": step,
        "epochs": args.epochs,
        "lr": args.lr,
        "batch": args.batch,
        "accum": args.accum,
        "eval_seen_by_builder": False,
        "checkpoint_selection": "none - final step",
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2), encoding="utf-8")
    print("saved %s" % (outp / "hf"), flush=True)
    print("THE BUILDER REPORTS NO ACCURACY NUMBER. Run judge.py.", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
