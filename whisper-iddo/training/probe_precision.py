"""Does a bf16 weight actually move at lr 1e-5?

bf16 has ~8 mantissa bits, so its relative resolution is about 2^-8 = 3.9e-3.
An Adam update is lr * m/(sqrt(v)+eps) ~= lr in magnitude, and typical Whisper
weights are ~0.02-0.05, so the relative update is ~1e-5/0.03 = 3e-4 -- roughly
13x FINER than bf16 can represent. If that reasoning is right, most weights
never change and the run is quietly crippled while the loss still drifts down
on the minority of parameters that do move.

That is an argument, not evidence. This measures it: run real steps and count
how many parameters actually differ afterwards, bf16 master vs fp32 master.
"""
from __future__ import annotations

import os
import sys

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import melgpu  # noqa: E402
from train import TrainSet, collate  # noqa: E402

ROOT = os.path.expanduser("~/whisper-iddo")
BASE = os.path.join(ROOT, "soup_20")


def probe(dtype, steps=6, bs=8, lr=1e-5):
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    dev = "cuda"
    model = WhisperForConditionalGeneration.from_pretrained(BASE, dtype=dtype).to(dev)
    proc = WhisperProcessor.from_pretrained(BASE)
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    pk = common.PackedAudio(ROOT)
    rows = pk.split("train")[:steps * bs]
    ds = TrainSet(rows, pk.blob, proc.tokenizer, ts_frac=0.2, seed=0)
    dl = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=0, collate_fn=collate)
    mel = melgpu.GpuMel(proc.feature_extractor, dev)

    # decoder only, matching epoch 1 of the real run
    params = [p for n, p in model.named_parameters() if not n.startswith("model.encoder")]
    for n, p in model.named_parameters():
        p.requires_grad_(not n.startswith("model.encoder"))
    before = {n: p.detach().clone().float()
              for n, p in model.named_parameters() if p.requires_grad}
    opt = torch.optim.AdamW(params, lr=lr, betas=(0.9, 0.98), eps=1e-6)

    for wav, labels in dl:
        wav = wav.to(dev)
        feats = mel(wav).to(dtype)
        with torch.autocast("cuda", torch.bfloat16, enabled=(dtype == torch.float32)):
            out = model(input_features=feats, labels=labels.to(dev))
        out.loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)

    tot = moved = 0
    for n, p in model.named_parameters():
        if not p.requires_grad:
            continue
        d = (p.detach().float() - before[n]).abs()
        tot += d.numel()
        moved += (d > 0).sum().item()
    opt_dtype = next(iter(opt.state.values()))["exp_avg"].dtype
    print(f"  master={str(dtype):22s} adam_state={opt_dtype}  "
          f"moved {moved/tot*100:6.2f}%  of {tot/1e6:.1f}M params  loss {out.loss.item():.4f}")
    del model, opt, before
    torch.cuda.empty_cache()
    return moved / tot


if __name__ == "__main__":
    print("fraction of trainable params that CHANGED after 6 real steps @ lr 1e-5:")
    a = probe(torch.bfloat16)
    b = probe(torch.float32)
    print(f"\nbf16 master moved {a*100:.2f}% vs fp32 master {b*100:.2f}%")
