"""
train_v2.py — ERAN v2 AUDIO, OVERFIT-FIX trainer (NEW, non-destructive).

Identical training loop to train.py, but every path is read from config_v2.json so
it CANNOT clobber the live v1 run:
    config    : config_v2.json          (smaller model, dropout 0.2, wd 0.15)
    tokens    : tokens_cache_full.npy    (full ~19h collection, built on CPU)
    ckpts     : checkpoints_v2/latest.pt
    logs      : eran_audio_v2.log, watch_v2.log, logs/metrics_v2.jsonl
The live v1 trainer (train.py -> checkpoints/latest.pt) and config.json are never
touched. Reuses model.py unchanged (same lego, just fewer/smaller layers).

Run (on GPU, when eran-live is NOT using it):
    python -s train_v2.py
The -s uses the cu121 torch (same as train.py). VRAM is still hard-capped
(train.vram_cap_mb) and the loop still sleeps each step, so the Hebrew mic is safe.
"""
import os, sys, json, time, math, datetime
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

CONFIG_PATH = os.path.join(HERE, "config_v2.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def model_cfg_from(cfg):
    codec = cfg["codec"]
    m = dict(cfg["model"])
    m["vocab_size"] = codec["n_codebooks"] * codec["codebook_size"]
    return m


def get_batch(stream, block_size, batch_size, device):
    n = stream.size(0)
    ix = torch.randint(0, n - block_size - 1, (batch_size,))
    x = torch.stack([stream[i:i + block_size] for i in ix])
    y = torch.stack([stream[i + 1:i + 1 + block_size] for i in ix])
    return x.to(device, non_blocking=True), y.to(device, non_blocking=True)


def get_lr(step, tr):
    warmup, lr, min_lr, decay = tr["warmup_steps"], tr["lr"], tr["min_lr"], tr["max_steps"]
    if step < warmup:
        return lr * (step + 1) / max(1, warmup)
    if step > decay:
        return min_lr
    ratio = (step - warmup) / max(1, (decay - warmup))
    return min_lr + 0.5 * (1.0 + math.cos(math.pi * ratio)) * (lr - min_lr)


def main():
    cfg = load_config()
    tr = cfg["train"]

    cache_npy = os.path.join(HERE, cfg.get("cache_file", "tokens_cache_full.npy"))
    ckpt_dir = os.path.join(HERE, cfg.get("ckpt_dir", "checkpoints_v2"))
    log_path = os.path.join(HERE, "eran_audio_v2.log")
    watch_path = os.path.join(HERE, "watch_v2.log")
    metrics_path = os.path.join(HERE, "logs", "metrics_v2.jsonl")
    os.makedirs(ckpt_dir, exist_ok=True)
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    ckpt_path = os.path.join(ckpt_dir, "latest.pt")

    def log_line(msg):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def append_metric(obj):
        try:
            with open(metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception:
            pass

    torch.manual_seed(1337)

    if torch.cuda.is_available():
        device = "cuda"
        total_mb = torch.cuda.get_device_properties(0).total_memory / 1e6
        frac = min(0.95, float(tr["vram_cap_mb"]) / total_mb)
        torch.cuda.set_per_process_memory_fraction(frac, 0)
        log_line(f"device=cuda ({torch.cuda.get_device_name(0)}) vram_cap={tr['vram_cap_mb']}MB "
                 f"-> frac={frac:.3f} torch={torch.__version__}")
    else:
        device = "cpu"
        log_line(f"device=cpu (cuda not available) torch={torch.__version__}")

    use_amp = bool(tr.get("amp", True)) and device == "cuda"
    amp_dtype = torch.bfloat16

    def load_cache():
        if not os.path.exists(cache_npy):
            return None, 0.0
        try:
            return np.load(cache_npy).astype(np.int64), os.path.getmtime(cache_npy)
        except Exception as e:
            log_line(f"cache load failed: {e}")
            return None, 0.0

    stream_np, cache_mtime = load_cache()
    if stream_np is None or stream_np.size < cfg["model"]["block_size"] + 2:
        n = 0 if stream_np is None else stream_np.size
        log_line(f"NOT ENOUGH audio ({n} tokens) in {cache_npy}. Build tokens_cache_full.npy first.")
        return
    stream = torch.from_numpy(stream_np.astype(np.int64))
    secs = stream_np.size / (cfg["codec"]["frame_rate"] * cfg["codec"]["n_codebooks"])
    log_line(f"heard-world stream: {stream_np.size:,} audio tokens (~{secs/60:.1f} min) from {cache_npy}")

    mcfg = model_cfg_from(cfg)
    model = build_model(mcfg).to(device)
    log_line(f"Model built: {model.num_params()/1e6:.2f}M params, vocab={mcfg['vocab_size']}, "
             f"block={mcfg['block_size']}, n_layer={mcfg['n_layer']}, n_embd={mcfg['n_embd']}, "
             f"dropout={mcfg['dropout']}.")

    optimizer = torch.optim.AdamW(model.parameters(), lr=tr["lr"],
                                  betas=(0.9, 0.95), weight_decay=tr["weight_decay"])

    step = 0
    if os.path.exists(ckpt_path):
        try:
            ck = torch.load(ckpt_path, map_location=device, weights_only=False)
            model.load_state_dict(ck["model"])
            optimizer.load_state_dict(ck["optim"])
            step = int(ck.get("step", 0))
            log_line(f"RESUMED from {ckpt_path} at step {step}.")
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

        if step > 0 and step % int(tr["rescan_samples_every"]) == 0:
            try:
                if os.path.exists(cache_npy) and os.path.getmtime(cache_npy) != cache_mtime:
                    ns, cache_mtime = load_cache()
                    if ns is not None and ns.size > block_size + 2:
                        stream = torch.from_numpy(ns.astype(np.int64))
                        log_line(f"Reloaded cache: {ns.size:,} tokens.")
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
                with open(watch_path, "a", encoding="utf-8") as f:
                    f.write(f"[{ts}] step={step} loss={lval:.4f} ema={running:.4f} "
                            f"ppl={math.exp(min(20,running)):.1f}\n")
            except Exception:
                pass

        step += 1


if __name__ == "__main__":
    main()
