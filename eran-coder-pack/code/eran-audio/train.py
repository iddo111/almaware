"""
train.py — ERAN v2 (AUDIO) continuous, never-stops trainer.

Eran predicts the next SOUND token of his heard world. Directives honored — same
as v1, the mic ALWAYS wins:
  * VRAM hard-capped (config train.vram_cap_mb) via set_per_process_memory_fraction.
  * GPU throttled (small batch + per-step sleep) -> ~10-20%, mic never starved.
  * bf16 autocast (amp) for low VRAM.
  * Checkpoints every N steps -> checkpoints/latest.pt; RESUMES on restart.
  * Re-reads the heard-world token stream every rescan_samples_every steps, so the
    growing 24/7 recording collection keeps feeding him (he hears more of his life).
  * Writes a text line to watch.log each checkpoint; listen.py turns the latest
    checkpoint into an actual babble .wav you can play.

Run:  python -s train.py   (the -s is REQUIRED so it uses Python312's cu121 torch,
                            not the shadowing user-site CPU torch.)
"""

import os
import sys
import json
import time
import math
import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from model import build_model

CONFIG_PATH = os.path.join(HERE, "config.json")
CACHE_NPY = os.path.join(HERE, "tokens_cache.npy")

CKPT_DIR = os.path.join(HERE, "checkpoints")
LOG_PATH = os.path.join(HERE, "eran_audio.log")
METRICS_PATH = os.path.join(HERE, "logs", "metrics.jsonl")
WATCH_PATH = os.path.join(HERE, "watch.log")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def log_line(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def append_metric(obj):
    try:
        with open(METRICS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        pass


def model_cfg_from(cfg):
    codec = cfg["codec"]
    vocab = codec["n_codebooks"] * codec["codebook_size"]
    m = dict(cfg["model"])
    m["vocab_size"] = vocab
    return m


def get_batch(stream, block_size, batch_size, device):
    n = stream.size(0)
    ix = torch.randint(0, n - block_size - 1, (batch_size,))
    x = torch.stack([stream[i:i + block_size] for i in ix])
    y = torch.stack([stream[i + 1:i + 1 + block_size] for i in ix])
    return x.to(device, non_blocking=True), y.to(device, non_blocking=True)


def get_lr(step, tr):
    warmup = tr["warmup_steps"]
    lr = tr["lr"]
    min_lr = tr["min_lr"]
    decay = tr["max_steps"]
    if step < warmup:
        return lr * (step + 1) / max(1, warmup)
    if step > decay:
        return min_lr
    ratio = (step - warmup) / max(1, (decay - warmup))
    coeff = 0.5 * (1.0 + math.cos(math.pi * ratio))
    return min_lr + coeff * (lr - min_lr)


def main():
    cfg = load_config()
    tr = cfg["train"]
    os.makedirs(CKPT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    ckpt_path = os.path.join(CKPT_DIR, "latest.pt")

    torch.manual_seed(1337)

    # device + HARD VRAM CAP (mic always wins)
    if torch.cuda.is_available():
        device = "cuda"
        total_mb = torch.cuda.get_device_properties(0).total_memory / 1e6
        frac = min(0.95, float(tr["vram_cap_mb"]) / total_mb)
        torch.cuda.set_per_process_memory_fraction(frac, 0)
        dev_name = torch.cuda.get_device_name(0)
        log_line(f"device=cuda ({dev_name}) vram_cap={tr['vram_cap_mb']}MB -> frac={frac:.3f} "
                 f"torch={torch.__version__}")
    else:
        device = "cpu"
        log_line(f"device=cpu (cuda not available) torch={torch.__version__}")

    use_amp = bool(tr.get("amp", True)) and device == "cuda"
    amp_dtype = torch.bfloat16

    # heard-world token stream (ALL his sound, not gated). The trainer ONLY reads
    # the cache .npy — it NEVER loads the EnCodec ear (loading EnCodec inside this
    # hot-CUDA process hard-crashes). A separate process (supervisor -> data.py)
    # owns encoding and keeps the cache growing.
    def load_cache():
        if not os.path.exists(CACHE_NPY):
            return None, 0.0
        try:
            return np.load(CACHE_NPY).astype(np.int64), os.path.getmtime(CACHE_NPY)
        except Exception as e:
            log_line(f"cache load failed: {e}")
            return None, 0.0

    stream_np, cache_mtime = load_cache()
    if stream_np is None or stream_np.size < cfg["model"]["block_size"] + 2:
        n = 0 if stream_np is None else stream_np.size
        log_line(f"NOT ENOUGH audio yet ({n} tokens). Waiting for the cache to fill.")
        return
    stream = torch.from_numpy(stream_np.astype(np.int64))
    secs = stream_np.size / (cfg["codec"]["frame_rate"] * cfg["codec"]["n_codebooks"])
    log_line(f"heard-world stream: {stream_np.size:,} audio tokens (~{secs/60:.1f} min of sound).")

    mcfg = model_cfg_from(cfg)
    model = build_model(mcfg).to(device)
    log_line(f"Model built: {model.num_params()/1e6:.2f}M params, vocab={mcfg['vocab_size']}, "
             f"block={mcfg['block_size']}, blank/random init (age zero).")

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=tr["lr"],
        betas=(0.9, 0.95), weight_decay=tr["weight_decay"],
    )

    step = 0
    if os.path.exists(ckpt_path):
        try:
            ck = torch.load(ckpt_path, map_location=device, weights_only=False)
            model.load_state_dict(ck["model"])
            optimizer.load_state_dict(ck["optim"])
            step = int(ck.get("step", 0))
            log_line(f"RESUMED from checkpoint at step {step}.")
        except Exception as e:
            log_line(f"Checkpoint resume failed ({e}); starting fresh at step 0.")

    block_size = mcfg["block_size"]
    batch_size = tr["batch_size"]
    grad_accum = int(tr.get("grad_accum", 1))
    sleep_ms = float(tr["gpu_sleep_ms"])
    max_steps = int(tr["max_steps"])

    model.train()
    t0 = time.time()
    running = None

    while True:
        if max_steps and step >= max_steps:
            log_line(f"Reached max_steps={max_steps}; stopping.")
            break

        # the 24/7 collection grows -> reload the cache if the ear-process extended
        # it (we ONLY read the .npy here; encoding happens in a separate process).
        if step > 0 and step % int(tr["rescan_samples_every"]) == 0:
            try:
                if os.path.exists(CACHE_NPY) and os.path.getmtime(CACHE_NPY) != cache_mtime:
                    ns, cache_mtime = load_cache()
                    if ns is not None and ns.size > block_size + 2:
                        stream = torch.from_numpy(ns.astype(np.int64))
                        log_line(f"Reloaded heard world from cache: {ns.size:,} audio tokens (live growth).")
            except Exception as e:
                log_line(f"Cache reload failed: {e}")

        lr = get_lr(step, tr)
        for g in optimizer.param_groups:
            g["lr"] = lr

        optimizer.zero_grad(set_to_none=True)
        lval = 0.0
        for _ in range(grad_accum):
            x, y = get_batch(stream, block_size, batch_size, device)
            if use_amp:
                with torch.autocast(device_type="cuda", dtype=amp_dtype):
                    _, loss = model(x, y)
            else:
                _, loss = model(x, y)
            (loss / grad_accum).backward()
            lval += loss.item() / grad_accum
        torch.nn.utils.clip_grad_norm_(model.parameters(), tr["grad_clip"])
        optimizer.step()

        running = lval if running is None else 0.9 * running + 0.1 * lval

        # THROTTLE so the mic is never starved
        time.sleep(sleep_ms / 1000.0)

        if step % int(tr["log_every"]) == 0:
            dt = time.time() - t0
            t0 = time.time()
            sps = int(tr["log_every"]) / dt if dt > 0 else 0.0
            vram_mb = (torch.cuda.memory_reserved(0) / 1e6) if device == "cuda" else 0.0
            ppl = math.exp(min(20, running)) if running is not None else 0.0
            log_line(f"step {step:>7} | loss {lval:.4f} | ema {running:.4f} | ppl {ppl:.1f} | "
                     f"lr {lr:.2e} | {sps:.1f} it/s | vram {vram_mb:.0f}MB")
            append_metric({"ts": time.time(), "step": step, "loss": lval,
                           "ema_loss": running, "ppl": ppl, "lr": lr, "steps_per_s": sps})

        if step > 0 and step % int(tr["checkpoint_every"]) == 0:
            tmp = ckpt_path + ".tmp"
            torch.save({"model": model.state_dict(), "optim": optimizer.state_dict(),
                        "step": step, "cfg": mcfg, "codec": cfg["codec"]}, tmp)
            os.replace(tmp, ckpt_path)
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(WATCH_PATH, "a", encoding="utf-8") as f:
                    f.write(f"[{ts}] step={step} loss={lval:.4f} ema={running:.4f} "
                            f"ppl={math.exp(min(20,running)):.1f}  (run listen.py to hear it babble)\n")
            except Exception:
                pass

        step += 1


if __name__ == "__main__":
    main()
