"""
train.py - ERAN's continuous, never-stops trainer.

Directives honored:
  * VRAM capped <=1.5GB via torch.cuda.set_per_process_memory_fraction (~0.18 of 8GB)
    -- but ONLY when 0 < vram_fraction < 1 (DGX sets it to 0/1 = no cap, dedicated box).
  * GPU throttled to ~10-20% (small batch + per-step sleep). MIC ALWAYS WINS on the
    local PC. On the DGX (no mic competing) step_sleep_ms=0 = full throttle.
  * Checkpoints every N steps to checkpoints/latest.pt; RESUMES from it on restart.
    The SAME Eran continues -- the checkpoint is portable PC <-> DGX (identical model dims).
  * Logs step/loss to eran.log + metrics.jsonl, and a compact heartbeat the fleet can poll.
  * RE-READS the voice corpus periodically so the growing 24/7 collection keeps teaching.
  * Periodically appends a fresh generated sample to watch.log ("watch it learn").

DGX-4 fast path (all OFF by default so the local run is byte-for-byte unchanged):
  * amp = "bf16" | "fp16" | "off"   (mixed precision via torch.autocast)
  * compile = true                  (torch.compile the model)
  * allow_tf32 = true               (TF32 matmul on Ampere+/Blackwell)
  * grad_accum_steps = N            (large effective batch without the VRAM)
  * Distributed Data Parallel across all GPUs when launched under torchrun
    (WORLD_SIZE>1); single-process otherwise. See dgx4_launch.sh.

Run (local, default config):  python -s train.py
Run (DGX 4, 4 GPUs):          torchrun --standalone --nproc_per_node=4 train.py --config config.dgx4.json

The -s is REQUIRED locally so it ignores the shadowing user-site CPU torch and uses
Python312's cu121 torch.

לזכרה של עלמה ז"ל
"""

import os
import sys
import json
import time
import math
import socket
import argparse
import datetime
from contextlib import nullcontext

# UTF-8 console so Hebrew samples don't crash logging on cp1252
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tokenizer import tokenizer
from model import build_model
import data as voice_data


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def log_line(log_path, msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def append_metric(metrics_path, obj):
    try:
        with open(metrics_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        pass


def write_fleet_status(path, obj):
    """Best-effort heartbeat the fleet router can poll (router.py --eran-status).

    Atomic write, never raises -- a metrics file must never be able to kill Eran.
    """
    if not path:
        return
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def encode_corpus(text):
    ids = tokenizer.encode(text)
    return torch.tensor(ids, dtype=torch.long)


def get_batch(data_ids, block_size, batch_size, device):
    n = data_ids.size(0)
    ix = torch.randint(0, n - block_size - 1, (batch_size,))
    x = torch.stack([data_ids[i:i + block_size] for i in ix])
    y = torch.stack([data_ids[i + 1:i + 1 + block_size] for i in ix])
    return x.to(device, non_blocking=True), y.to(device, non_blocking=True)


def get_lr(step, tr):
    warmup = tr["warmup_steps"]
    decay = tr["lr_decay_steps"]
    lr = tr["learning_rate"]
    min_lr = tr["min_lr"]
    if step < warmup:
        return lr * (step + 1) / max(1, warmup)
    if step > decay:
        return min_lr
    ratio = (step - warmup) / max(1, (decay - warmup))
    coeff = 0.5 * (1.0 + math.cos(math.pi * ratio))
    return min_lr + coeff * (lr - min_lr)


def write_watch_sample(gen_model, cfg, device, step, loss):
    watch_path = cfg["watch_path"]
    gen_model.eval()
    try:
        start = torch.tensor([[tokenizer.bos_id]], dtype=torch.long, device=device)
        out = gen_model.generate(start, max_new_tokens=200, temperature=0.9, top_k=40)
        text = tokenizer.decode(out[0].tolist())
    except Exception as e:
        text = f"<generate error: {e}>"
    finally:
        gen_model.train()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = (
        f"\n===== PROTO-ERAN watch @ {ts}  step={step}  loss={loss:.4f} =====\n"
        f"{text}\n"
    )
    try:
        with open(watch_path, "a", encoding="utf-8") as f:
            f.write(block)
    except Exception:
        pass


def setup_ddp():
    """Return (ddp, rank, local_rank, world_size, master). No-op when not under torchrun."""
    if int(os.environ.get("WORLD_SIZE", "1")) <= 1:
        return False, 0, 0, 1, True
    import torch.distributed as dist
    dist.init_process_group(backend="nccl")
    rank = int(os.environ["RANK"])
    local_rank = int(os.environ["LOCAL_RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    torch.cuda.set_device(local_rank)
    return True, rank, local_rank, world_size, (rank == 0)


def main():
    ap = argparse.ArgumentParser(description="ERAN continuous trainer")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"),
                    help="path to config json (default: config.json)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    tr = cfg["train"]
    gp = cfg["gpu"]
    os.makedirs(cfg["checkpoint_dir"], exist_ok=True)
    os.makedirs(os.path.dirname(cfg["metrics_path"]), exist_ok=True)
    log_path = cfg["log_path"]
    ckpt_path = os.path.join(cfg["checkpoint_dir"], "latest.pt")
    fleet_status_path = cfg.get("fleet_status_path")

    # --- distributed (DGX) or single-process (PC) ---
    ddp, rank, local_rank, world_size, master = setup_ddp()

    # seed differs per rank so each GPU samples a different slice of the corpus
    torch.manual_seed(cfg["seed"] + rank)

    # --- device + (conditional) HARD VRAM CAP (mic always wins on the PC) ---
    vram_fraction = float(gp.get("vram_fraction", 1.0))
    if (gp["device"] == "cuda") and torch.cuda.is_available():
        device = f"cuda:{local_rank}" if ddp else "cuda"
        # cap ONLY on a shared box; 0 or >=1 means "dedicated, no cap" (DGX)
        if 0.0 < vram_fraction < 1.0:
            torch.cuda.set_per_process_memory_fraction(vram_fraction, local_rank)
        dev_name = torch.cuda.get_device_name(local_rank)
    else:
        device = "cpu"
        dev_name = "CPU (cuda not available)"
    device_is_cuda = device.startswith("cuda")

    # --- precision knobs (DGX fast path; all default-off so PC run is unchanged) ---
    if device_is_cuda and bool(gp.get("allow_tf32", False)):
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    amp = str(tr.get("amp", "off")).lower()
    if amp in ("bf16", "fp16") and device_is_cuda:
        amp_dtype = torch.bfloat16 if amp == "bf16" else torch.float16
        amp_ctx = torch.autocast(device_type="cuda", dtype=amp_dtype)
    else:
        amp = "off"
        amp_ctx = nullcontext()
    scaler = torch.cuda.amp.GradScaler(enabled=(amp == "fp16"))

    grad_accum = max(1, int(tr.get("grad_accum_steps", 1)))

    if master:
        log_line(log_path, f"PROTO-ERAN trainer start. device={device} ({dev_name}) "
                           f"ddp={ddp} world_size={world_size} vram_fraction={vram_fraction} "
                           f"amp={amp} compile={bool(gp.get('compile', False))} "
                           f"grad_accum={grad_accum} torch={torch.__version__}")

    # --- VOICE corpus (NOT books) ---
    text = voice_data.build_corpus(verbose=False)
    data_ids = encode_corpus(text)
    if master:
        sample_preview = text[:300].replace("\n", " | ")
        log_line(log_path, f"VOICE corpus loaded: {len(text)} chars / {data_ids.size(0)} byte-tokens. "
                           f"SAMPLE OF TRAINING TEXT (Iddo's voice): {sample_preview}")

    # --- model (blank/random = age zero, or RESUMED -> the same Eran) ---
    raw_model = build_model(cfg["model"]).to(device)
    nparams = raw_model.num_params()
    if master:
        log_line(log_path, f"Model built: {nparams/1e6:.2f}M params.")

    optimizer = torch.optim.AdamW(
        raw_model.parameters(),
        lr=tr["learning_rate"],
        betas=(tr["beta1"], tr["beta2"]),
        weight_decay=tr["weight_decay"],
    )

    # --- RESUME (portable PC <-> DGX; identical model dims) ---
    step = 0
    if os.path.exists(ckpt_path):
        try:
            ck = torch.load(ckpt_path, map_location=device, weights_only=False)
            raw_model.load_state_dict(ck["model"])
            optimizer.load_state_dict(ck["optim"])
            step = int(ck.get("step", 0))
            if master:
                log_line(log_path, f"RESUMED from checkpoint at step {step}.")
        except Exception as e:
            if master:
                log_line(log_path, f"Checkpoint resume failed ({e}); starting fresh at step 0.")

    # gen_model = the raw, uncompiled, unwrapped module (used for sampling + saving)
    gen_model = raw_model
    model = raw_model
    if device_is_cuda and bool(gp.get("compile", False)) and hasattr(torch, "compile"):
        try:
            model = torch.compile(raw_model)
            if master:
                log_line(log_path, "torch.compile enabled.")
        except Exception as e:
            if master:
                log_line(log_path, f"torch.compile unavailable ({e}); running eager.")
    if ddp:
        from torch.nn.parallel import DistributedDataParallel as DDP
        model = DDP(model, device_ids=[local_rank])

    block_size = cfg["model"]["block_size"]
    batch_size = tr["batch_size"]            # per-GPU batch
    sleep_ms = float(gp.get("step_sleep_ms", 0))
    max_steps = int(tr["max_steps"])         # 0 = forever
    log_interval = int(tr["log_interval"])
    ckpt_interval = int(tr["checkpoint_interval"])
    reload_interval = int(tr["reload_corpus_interval"])

    model.train()
    last_watch = 0.0
    t0 = time.time()
    running_loss = None
    hostname = socket.gethostname()

    while True:
        if max_steps and step >= max_steps:
            if master:
                log_line(log_path, f"Reached max_steps={max_steps}; stopping.")
            break

        # periodic corpus reload (the 24/7 collection grows)
        if step > 0 and step % reload_interval == 0:
            try:
                text = voice_data.build_corpus(verbose=False)
                data_ids = encode_corpus(text)
                if master:
                    log_line(log_path, f"Reloaded VOICE corpus: {data_ids.size(0)} byte-tokens (live growth).")
            except Exception as e:
                if master:
                    log_line(log_path, f"Corpus reload failed: {e}")

        lr = get_lr(step, tr)
        for g in optimizer.param_groups:
            g["lr"] = lr

        # --- gradient accumulation (large effective batch on DGX; default 1 on PC) ---
        optimizer.zero_grad(set_to_none=True)
        lval = 0.0
        for micro in range(grad_accum):
            x, y = get_batch(data_ids, block_size, batch_size, device)
            # under DDP, only sync grads on the final micro-step
            sync = (not ddp) or (micro == grad_accum - 1)
            sync_ctx = nullcontext() if sync else model.no_sync()
            with sync_ctx:
                with amp_ctx:
                    _, loss = model(x, y)
                    loss = loss / grad_accum
                scaler.scale(loss).backward()
            lval += loss.item() * grad_accum  # un-scale for reporting

        lval /= grad_accum

        if scaler.is_enabled():
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), tr["grad_clip"])
            scaler.step(optimizer)
            scaler.update()
        else:
            torch.nn.utils.clip_grad_norm_(model.parameters(), tr["grad_clip"])
            optimizer.step()

        running_loss = lval if running_loss is None else 0.9 * running_loss + 0.1 * lval

        # THROTTLE: on the PC sleep keeps GPU ~10-20% so the mic is never starved.
        # On the DGX step_sleep_ms=0 -> no sleep -> full throttle.
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

        if master and step % log_interval == 0:
            dt = time.time() - t0
            t0 = time.time()
            sps = log_interval / dt if dt > 0 else 0.0
            # tokens/s across the whole fleet this interval
            tps = sps * batch_size * block_size * grad_accum * world_size
            vram_mb = (torch.cuda.memory_reserved(local_rank) / 1e6) if device_is_cuda else 0.0
            log_line(log_path, f"step {step:>7} | loss {lval:.4f} | ema {running_loss:.4f} | "
                               f"lr {lr:.2e} | {sps:.1f} steps/s | {tps/1e3:.0f}k tok/s | "
                               f"sleep {sleep_ms:.0f}ms | eran_vram {vram_mb:.0f}MB")
            append_metric(cfg["metrics_path"], {
                "ts": time.time(), "step": step, "loss": lval,
                "ema_loss": running_loss, "lr": lr, "steps_per_s": sps,
                "tokens_per_s": tps, "world_size": world_size,
            })
            write_fleet_status(fleet_status_path, {
                "service": "eran-live",
                "host": hostname,
                "device": dev_name,
                "world_size": world_size,
                "step": step,
                "loss": round(lval, 4),
                "ema_loss": round(running_loss, 4),
                "lr": lr,
                "steps_per_s": round(sps, 2),
                "tokens_per_s": round(tps, 1),
                "vram_mb": round(vram_mb, 0),
                "updated": datetime.datetime.now().isoformat(timespec="seconds"),
            })

        if master and step > 0 and step % ckpt_interval == 0:
            tmp = ckpt_path + ".tmp"
            torch.save({"model": gen_model.state_dict(), "optim": optimizer.state_dict(),
                        "step": step, "cfg": cfg["model"]}, tmp)
            os.replace(tmp, ckpt_path)

        if master:
            now = time.time()
            if now - last_watch >= float(tr["watch_interval_sec"]):
                write_watch_sample(gen_model, cfg, device, step, running_loss)
                last_watch = now

        step += 1

    if ddp:
        import torch.distributed as dist
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
