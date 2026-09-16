#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qwen3.5-4B-Base smoke test on GB10 (sm_121). SMOKE ONLY - no checkpoint written."""
import os, sys, time, json, gc
import torch

REPO = "Qwen/Qwen3.5-4B-Base"
OUT = {}
def say(k, v):
    OUT[k] = v
    print(f"[{k}] {v}", flush=True)

def gb(x): return round(x / 1024**3, 2)

say("USE_MCORE_GDN_env", os.environ.get("USE_MCORE_GDN", "<unset>"))
say("torch", torch.__version__)
say("cc", torch.cuda.get_device_capability(0))
say("device", torch.cuda.get_device_name(0))

# Cap so a blow-up is a clean CUDA OOM, never a system OOM that kills sarid.
torch.cuda.set_per_process_memory_fraction(0.82, 0)
say("mem_cap_gb", gb(0.82 * torch.cuda.get_device_properties(0).total_memory))

from transformers import AutoTokenizer, AutoModelForCausalLM, AutoConfig

tok = AutoTokenizer.from_pretrained(REPO)
say("vocab_size_tokenizer", len(tok))

cfg = AutoConfig.from_pretrained(REPO)
say("config_class", type(cfg).__name__)

# ---- PHASE A: load (text tower only; the vision tower is dead weight for a coder)
t0 = time.time()
try:
    model = AutoModelForCausalLM.from_pretrained(
        REPO, dtype=torch.bfloat16, device_map=None,
        attn_implementation="sdpa",
    ).cuda()
    say("load_path", "AutoModelForCausalLM")
except Exception as e:
    say("AutoModelForCausalLM_failed", f"{type(e).__name__}: {e}")
    raise
say("load_seconds", round(time.time() - t0, 1))
say("model_class", type(model).__name__)

n_all = sum(p.numel() for p in model.parameters())
say("params_total_B", round(n_all / 1e9, 4))
say("weights_bf16_GB", gb(n_all * 2))
say("mem_after_load_GB", gb(torch.cuda.memory_allocated()))

# ---- PHASE B: generation from a REAL code prompt. Text out, or it did not work.
prompt = "def fibonacci(n):\n    \"\"\"Return the n-th Fibonacci number.\"\"\"\n"
ids = tok(prompt, return_tensors="pt").to("cuda")
model.eval()
t0 = time.time()
with torch.no_grad():
    out = model.generate(**ids, max_new_tokens=80, do_sample=False,
                         pad_token_id=tok.eos_token_id)
say("generate_seconds", round(time.time() - t0, 1))
gen = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
print("=" * 60, flush=True)
print("GENERATED_TEXT_BEGIN", flush=True)
print(prompt + gen, flush=True)
print("GENERATED_TEXT_END", flush=True)
print("=" * 60, flush=True)
OUT["generated"] = gen

# ---- PHASE C: forward + backward, tiny batch. Are the gradients finite?
model.train()
model.gradient_checkpointing_enable()
model.config.use_cache = False
torch.cuda.reset_peak_memory_stats()
B, S = 2, 512
x = torch.randint(0, 100000, (B, S), device="cuda")
t0 = time.time()
loss = model(input_ids=x, labels=x).loss
loss.backward()
torch.cuda.synchronize()
say("fwdbwd_b2_s512_seconds", round(time.time() - t0, 2))
say("loss_b2_s512", round(loss.item(), 4))
say("peak_fwdbwd_b2_s512_GB", gb(torch.cuda.max_memory_allocated()))
bad = [n for n, p in model.named_parameters()
       if p.grad is not None and not torch.isfinite(p.grad).all()]
say("nonfinite_grad_tensors", len(bad))
say("nonfinite_examples", bad[:5])
gsum = sum(p.grad.float().pow(2).sum().item()
           for p in model.parameters() if p.grad is not None)
say("grad_global_norm", round(gsum ** 0.5, 4))

# ---- PHASE D: one REAL training step with AdamW at the planned seq length.
model.zero_grad(set_to_none=True)
gc.collect(); torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
SEQ = int(os.environ.get("SMOKE_SEQ", "4096"))
try:
    opt = torch.optim.AdamW(model.parameters(), lr=1e-5)
    x = torch.randint(0, 100000, (1, SEQ), device="cuda")
    times = []
    for i in range(3):
        t0 = time.time()
        loss = model(input_ids=x, labels=x).loss
        loss.backward()
        opt.step()
        opt.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        times.append(time.time() - t0)
        say(f"step{i}_seconds", round(times[-1], 2))
    say("step_seconds_steady", round(min(times[1:]), 2))
    say("train_step_loss", round(loss.item(), 4))
    say("PEAK_TRAINING_GB", gb(torch.cuda.max_memory_allocated()))
    say("PEAK_RESERVED_GB", gb(torch.cuda.max_memory_reserved()))
    say("seq_len", SEQ)
except torch.cuda.OutOfMemoryError as e:
    say("train_step_OOM", f"at seq {SEQ}: {str(e)[:300]}")
    say("PEAK_TRAINING_GB", gb(torch.cuda.max_memory_allocated()))
except Exception as e:
    say("train_step_failed", f"{type(e).__name__}: {str(e)[:300]}")

with open(os.path.expanduser("~/coder-base-logs/smoke_result.json"), "w") as f:
    json.dump(OUT, f, indent=2, default=str)
print("SMOKE_DONE", flush=True)
