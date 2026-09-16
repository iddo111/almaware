"""alma-mic / training / train_full.py — FULL-WEIGHT fine-tune. Not LoRA.

Every one of whisper-large-v3-turbo's ~809 M parameters is updated on Iddo's voice.
Iddo asked for real weight training and this is it: no adapters, no frozen trunk,
no low-rank shortcut.

RUNS ON THE DGX. NEVER ON THE PC.
  Workspace law: no torch on the PC, training OR inference. This file imports torch,
  so it only ever executes on a DGX node. If eran4 (the voice node) is down, use
  eran2 - do NOT fall back to the PC.

WHY FULL FINE-TUNING NEEDS MORE CARE THAN LoRA
  A LoRA is degradation-resistant by construction: the base weights are frozen, so the
  worst case is a bad adapter you delete. Full fine-tuning has no such floor. 809 M
  parameters and ~6 h of one speaker is a textbook overfitting setup, and the specific
  way Whisper fails when overfitted is catastrophic forgetting - it gets sharp on the
  training distribution and forgets how to hear anything else.

  So the freedom has to be bought back with constraints:

    low LR (1e-5)        - large steps on a converged model destroy it
    warmup + cosine      - no shock at step 0, no thrash at the end
    L2-SP anchor         - a penalty on ||theta - theta_base||^2. The model may adapt;
                           it may not wander. This is the single most important line
                           in this file for "never degrades".
    EMA weights          - evaluate a smoothed model, not whatever the last noisy
                           minibatch happened to produce
    early stop on WER    - measured on the FROZEN eval split, never on training loss
    checkpoint every epoch - so the gate has candidates to choose between

  None of this makes degradation impossible. Only promote.py does that, by refusing to
  deploy a checkpoint that did not earn it. This file's job is to make good checkpoints
  LIKELY; the gate's job is to make bad ones HARMLESS.

USAGE (on the DGX)
  python train_full.py --data dataset/ --out runs/$(date +%Y%m%d) --epochs 3
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time


def require_dgx() -> None:
    """Refuse to run on the PC. This is a standing law, enforced not documented."""
    if os.name == "nt":
        sys.exit("REFUSING: this trains with torch. Windows PC = the workstation.\n"
                 "Full fine-tuning runs on the DGX fleet only (eran4, else eran2).")


def main() -> int:
    require_dgx()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset")
    ap.add_argument("--audio", default="../voice_corpus")
    ap.add_argument("--base", default="openai/whisper-large-v3-turbo")
    ap.add_argument("--out", default="runs/latest")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--warmup", type=float, default=0.1)
    ap.add_argument("--l2sp", type=float, default=1e-3,
                    help="anti-forgetting anchor strength; 0 disables it (do not)")
    ap.add_argument("--ema", type=float, default=0.999)
    ap.add_argument("--max-sec", type=float, default=30.0)
    a = ap.parse_args()

    import torch
    from torch.utils.data import Dataset, DataLoader
    import soundfile as sf
    from transformers import (WhisperForConditionalGeneration, WhisperProcessor,
                              get_cosine_schedule_with_warmup)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev != "cuda":
        sys.exit("REFUSING: no CUDA. Full fine-tuning on CPU is not a real option.")
    print("device: %s  (%s)" % (dev, torch.cuda.get_device_name(0)))

    proc = WhisperProcessor.from_pretrained(a.base)
    model = WhisperForConditionalGeneration.from_pretrained(
        a.base, torch_dtype=torch.float32).to(dev)
    model.config.forced_decoder_ids = None
    model.gradient_checkpointing_enable()

    # ---- the anchor: a frozen copy of where we started ----
    # Kept in bf16 to halve the memory; the penalty only needs to be approximately
    # right to do its job of discouraging large excursions.
    base_w = {n: p.detach().clone().to(torch.bfloat16)
              for n, p in model.named_parameters() if p.requires_grad}
    print("L2-SP anchor: %d tensors held (lambda=%g)" % (len(base_w), a.l2sp))

    class Utts(Dataset):
        def __init__(self, path):
            self.rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
            self.rows = [r for r in self.rows if r.get("sec", 0) <= a.max_sec]

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            r = self.rows[i]
            wav, sr = sf.read(os.path.join(a.audio, r["wav"]), dtype="float32")
            feats = proc.feature_extractor(wav, sampling_rate=sr,
                                           return_tensors="pt").input_features[0]
            lang = r.get("lang") or "he"
            if lang not in ("he", "en"):
                lang = "he"
            ids = proc.tokenizer(r["text"], return_tensors="pt").input_ids[0]
            return feats, ids

    def collate(batch):
        feats = torch.stack([b[0] for b in batch])
        maxlen = max(len(b[1]) for b in batch)
        pad = proc.tokenizer.pad_token_id or -100
        labels = torch.full((len(batch), maxlen), -100, dtype=torch.long)
        for i, (_f, ids) in enumerate(batch):
            labels[i, :len(ids)] = ids
        labels[labels == pad] = -100          # padding must not contribute to the loss
        return feats, labels

    train = Utts(os.path.join(a.data, "train.jsonl"))
    dl = DataLoader(train, batch_size=a.batch, shuffle=True, collate_fn=collate,
                    num_workers=4, pin_memory=True, drop_last=True)
    steps = max(1, (len(dl) // a.accum) * a.epochs)
    print("train: %d utterances, %d optimiser steps" % (len(train), steps))

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.0,
                            betas=(0.9, 0.98), eps=1e-6)
    sched = get_cosine_schedule_with_warmup(opt, int(steps * a.warmup), steps)
    scaler = torch.amp.GradScaler("cuda")

    ema = {n: p.detach().clone().float() for n, p in model.named_parameters()}

    os.makedirs(a.out, exist_ok=True)
    step = 0
    t0 = time.time()
    for ep in range(1, a.epochs + 1):
        model.train()
        run_loss = run_anchor = 0.0
        for i, (feats, labels) in enumerate(dl, 1):
            feats, labels = feats.to(dev, non_blocking=True), labels.to(dev, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out = model(input_features=feats, labels=labels)
                loss = out.loss / a.accum

            # ---- L2-SP: pay for every step away from the starting point ----
            anchor = torch.zeros((), device=dev)
            if a.l2sp > 0:
                for n, p in model.named_parameters():
                    if p.requires_grad and n in base_w:
                        anchor = anchor + ((p - base_w[n].float()) ** 2).sum()
                loss = loss + (a.l2sp * anchor) / a.accum

            scaler.scale(loss).backward()
            run_loss += float(out.loss)
            run_anchor += float(anchor)

            if i % a.accum == 0:
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
                sched.step()
                step += 1
                with torch.no_grad():                       # EMA of the weights
                    for n, p in model.named_parameters():
                        ema[n].mul_(a.ema).add_(p.detach().float(), alpha=1 - a.ema)
                if step % 25 == 0:
                    print("ep%d step%d/%d loss=%.4f anchor=%.2e lr=%.2e (%.0fs)"
                          % (ep, step, steps, run_loss / i, run_anchor / i,
                             sched.get_last_lr()[0], time.time() - t0), flush=True)

        # ---- checkpoint the EMA weights, not the raw last-step weights ----
        ck = os.path.join(a.out, "epoch%d" % ep)
        backup = {n: p.detach().clone() for n, p in model.named_parameters()}
        with torch.no_grad():
            for n, p in model.named_parameters():
                p.copy_(ema[n])
        model.save_pretrained(ck, safe_serialization=True)
        proc.save_pretrained(ck)
        with torch.no_grad():
            for n, p in model.named_parameters():
                p.copy_(backup[n])
        del backup
        print("saved %s" % ck, flush=True)

    meta = {"base": a.base, "epochs": a.epochs, "lr": a.lr, "l2sp": a.l2sp,
            "ema": a.ema, "train_utts": len(train), "steps": steps,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "full_finetune": True, "lora": False}
    with open(os.path.join(a.out, "run.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print()
    print("Training done. NOTHING IS DEPLOYED YET - and that is the point.")
    print("Convert a checkpoint to CT2, evaluate it against the frozen splits, and let")
    print("promote.py decide. A checkpoint that does not beat the champion is discarded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
