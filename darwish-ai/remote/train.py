# train.py — Task 6: 24/7 capped trainer for DarwishLM on eran3.
# Resumable (ckpt/latest.pt), bf16, grad-accum; polite to Qwen (small bursts).
import json
import os
import random
import time

import numpy as np
import torch

from model import DarwishLM, loss_fn

HOME = os.path.expanduser("~/darwish-ai")
TOKENS = os.path.join(HOME, "tokens")
CKPT = os.path.join(HOME, "ckpt")
os.makedirs(CKPT, exist_ok=True)

SEQ_T = 2048          # ~24 s of audio per sample
MICRO_B = 4
ACCUM = 8             # effective batch 32
LR = 3e-4
WARMUP = 1000
MAX_STEPS = 500_000
EVAL_EVERY = 2000
SAVE_EVERY = 1000

index = json.load(open(os.path.join(TOKENS, "index.json")))
train_shards = [np.load(os.path.join(TOKENS, f"{e['sha']}.npy"), mmap_mode="r")
                for e in index if e["split"] == "train"]
held_shards = [np.load(os.path.join(TOKENS, f"{e['sha']}.npy"), mmap_mode="r")
               for e in index if e["split"] == "heldout"]
assert train_shards, "no train shards"
print(f"train shards: {len(train_shards)}  heldout: {len(held_shards)}", flush=True)


def sample_window(shards):
    s = random.choice(shards)
    t0 = random.randint(0, s.shape[1] - SEQ_T - 2)
    return torch.from_numpy(np.array(s[:, t0 : t0 + SEQ_T + 1], dtype=np.int64))


def batch(shards, b=MICRO_B):
    return torch.stack([sample_window(shards) for _ in range(b)]).cuda()


device = "cuda"
model = DarwishLM().to(device)
opt = torch.optim.AdamW(model.parameters(), lr=LR, betas=(0.9, 0.95), weight_decay=0.1)
step = 0

latest = os.path.join(CKPT, "latest.pt")
if os.path.exists(latest):
    state = torch.load(latest, map_location=device, weights_only=False)
    model.load_state_dict(state["model"])
    opt.load_state_dict(state["opt"])
    step = state["step"]
    print(f"resumed at step {step}", flush=True)


def lr_at(s):
    if s < WARMUP:
        return LR * s / WARMUP
    import math
    p = min(1.0, (s - WARMUP) / (MAX_STEPS - WARMUP))
    return 3e-5 + 0.5 * (LR - 3e-5) * (1 + math.cos(math.pi * p))


@torch.no_grad()
def heldout_loss():
    if not held_shards:
        return float("nan")
    model.eval()
    losses = []
    for _ in range(8):
        with torch.autocast("cuda", dtype=torch.bfloat16):
            l, _ = loss_fn(model, batch(held_shards, 2))
        losses.append(float(l))
    model.train()
    return sum(losses) / len(losses)


model.train()
t0 = time.time()
while step < MAX_STEPS:
    for g in opt.param_groups:
        g["lr"] = lr_at(step)
    opt.zero_grad(set_to_none=True)
    parts_acc = {"ce": 0.0, "gist": 0.0}
    for _ in range(ACCUM):
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss, parts = loss_fn(model, batch(train_shards))
        (loss / ACCUM).backward()
        parts_acc["ce"] += parts["ce"] / ACCUM
        parts_acc["gist"] += parts["gist"] / ACCUM
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    step += 1

    if step % 50 == 0:
        dt = time.time() - t0
        t0 = time.time()
        print(f"step={step} ce={parts_acc['ce']:.4f} gist={parts_acc['gist']:.4f} "
              f"lr={lr_at(step):.2e} sec/50={dt:.1f}", flush=True)
    if step % SAVE_EVERY == 0:
        tmp = latest + ".tmp"
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": step}, tmp)
        os.replace(tmp, latest)
    if step % EVAL_EVERY == 0:
        print(f"step={step} heldout={heldout_loss():.4f}", flush=True)
