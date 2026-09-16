#!/usr/bin/env python
"""PERETS STAGE-1 PROOF - RUN-3 trainer: innovation A/B with honest twin control.

RUN-3 = RUN-2 + GATE-COLLAPSE FIX: RUN-2's per-frame GIST gate collapsed onto
one frame (mean w ~ [0.002, 0.014, 0.14, 0.0001, 0.977], 93.6% inquorate), so
Thousand-Brains voting never engaged and vanilla won. RUN-3 adds (all
config.yaml knobs, zero extra params, param-match untouched):
  1. gate_balance_coeff  - KL(mean gate dist || uniform) load balancer (MoE-style)
  2. gate_entropy_coeff  - optional per-sample gate entropy bonus
  3. aux_frame_ce_coeff  - aux per-frame CE so every frame classifies on its own
  4. seat_threshold 0.5 -> 0.2 so quorum >= 2 is reachable at eval.

Loads the frozen Qwen2.5-0.5B-Instruct backbone (transformers), wires ALMAWARE
innovation #1 - the Multi-Reference-Frame VOTING head (Thousand-Brains voting +
GIST score==weight) - as real PyTorch, trains it on banking77 (77 intents = a
differential-diagnosis hypothesis set), and logs loss every --log-every steps
to stdout AND logs/<run>.log.

--vanilla trains the MANDATORY param-matched control twin (Arm B): same data,
same optimizer/lr/schedule/steps/seed, same frozen backbone - no frames, no
gates, no voting. The A-vs-B table ships even if vanilla wins.

Two phases (spec d, RUN-2):
  phase 1 (extract): ONE no_grad forward pass over banking77, cache pooled
      last-non-pad-token features at tap layers {4,9,14,19,24} (fp16, ~45 MB).
      Cache is shared by both arms and all seeds - extracted once.
  phase 2 (train):   heads-only training on cached features. Seconds-to-minutes.

accelerate/FSDP-READY: everything goes through accelerate.Accelerator, so the
same script scales to the fleet later:
  single-GPU now :  ~/ai/.venv/bin/python train.py [--vanilla] --seed 1
  fleet later    :  ~/ai/.venv/bin/accelerate launch --config_file fsdp_config_example.yaml train.py ...

Honesty tag: REAL. Metrics reported per spec gates G2-G4; UNKNOWN until measured.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F
import yaml
from torch.utils.data import DataLoader, TensorDataset

from accelerate import Accelerator
from accelerate.utils import set_seed

from frames import MultiFrameVotingHead, VanillaHead, build_heads, gate_regularizers
from metrics import basic_metrics, quorum_metrics

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- utils

class TeeLog:
    """Log to stdout + logfile."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(path, "a", buffering=1)
        self.path = path

    def __call__(self, msg: str):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        self.fh.write(line + "\n")


def git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "n/a"


# ------------------------------------------------------------ phase 1: extraction

def extract_features(cfg: dict, device: torch.device, log) -> dict:
    """One frozen forward pass over banking77; cache pooled features at tap layers.

    Returns {"train": path, "test": path}. Cached once, reused by all arms/seeds.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from datasets import load_dataset

    cache = HERE / cfg["cache_dir"]
    cache.mkdir(parents=True, exist_ok=True)
    tag = cfg["base_model"].replace("/", "_")
    paths = {s: cache / f"{tag}_banking77_{s}.pt" for s in ("train", "test")}
    if all(p.exists() for p in paths.values()):
        log(f"[extract] cache hit: {paths['train'].name}, {paths['test'].name}")
        return paths

    log(f"[extract] loading dataset {cfg['dataset']}")
    try:
        ds = load_dataset(cfg["dataset"])
    except Exception as e:  # plain-parquet mirror of the same data
        log(f"[extract] {cfg['dataset']} failed ({type(e).__name__}: {e}); "
            f"falling back to {cfg['dataset_fallback']}")
        ds = load_dataset(cfg["dataset_fallback"])

    log(f"[extract] loading FROZEN backbone {cfg['base_model']} (bf16)")
    tok = AutoTokenizer.from_pretrained(cfg["base_model"])
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], dtype=torch.bfloat16)
    model.to(device).eval()
    for p in model.parameters():
        p.requires_grad_(False)

    taps = list(cfg["tap_layers"])
    bs, seq_len = cfg["extract_batch_size"], cfg["extract_seq_len"]
    for split, path in paths.items():
        texts = list(ds[split]["text"])
        labels = torch.tensor(list(ds[split]["label"]), dtype=torch.long)
        feats = []
        t0 = time.time()
        for i in range(0, len(texts), bs):
            enc = tok(texts[i:i + bs], return_tensors="pt", padding=True,
                      truncation=True, max_length=seq_len).to(device)
            with torch.no_grad():
                out = model(**enc, output_hidden_states=True)
            # hidden_states[k] = output of decoder layer k (index 0 = embeddings).
            # Pool = last non-pad token hidden state.
            last = enc["attention_mask"].sum(1) - 1                       # [B]
            rows = torch.arange(enc["input_ids"].size(0), device=device)
            pooled = torch.stack(
                [out.hidden_states[k][rows, last] for k in taps], dim=1)  # [B, F, H]
            feats.append(pooled.to(torch.float16).cpu())
            if (i // bs) % 20 == 0:
                log(f"[extract] {split} {i}/{len(texts)} ({time.time() - t0:.1f}s)")
        feats = torch.cat(feats)
        torch.save({"features": feats, "labels": labels, "tap_layers": taps}, path)
        log(f"[extract] saved {path.name} features={tuple(feats.shape)} "
            f"in {time.time() - t0:.1f}s")

    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return paths


# --------------------------------------------------------------- phase 2: training

def make_loader(path: Path, batch_size: int, shuffle: bool, limit: int = 0) -> DataLoader:
    blob = torch.load(path, map_location="cpu", weights_only=True)
    feats, labels = blob["features"].float(), blob["labels"]
    if limit:
        feats, labels = feats[:limit], labels[:limit]
    return DataLoader(TensorDataset(feats, labels), batch_size=batch_size,
                      shuffle=shuffle, drop_last=False)


def cosine_with_warmup(optimizer, warmup: int, total: int):
    def lr_lambda(step):
        if step < warmup:
            return step / max(1, warmup)
        prog = (step - warmup) / max(1, total - warmup)
        return 0.5 * (1.0 + math.cos(math.pi * min(1.0, prog)))
    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


@torch.no_grad()
def evaluate(model, loader, accelerator: Accelerator, arm: str, cfg: dict) -> dict:
    model.eval()
    all_logits, all_labels, all_w = [], [], []
    for feats, labels in loader:
        logits, _z, w = model(feats, return_votes=True)
        all_logits.append(accelerator.gather_for_metrics(logits))
        all_labels.append(accelerator.gather_for_metrics(labels))
        if w is not None:
            all_w.append(accelerator.gather_for_metrics(w))
    logits = torch.cat(all_logits)
    labels = torch.cat(all_labels)
    results = basic_metrics(logits, labels)
    if arm == "A" and all_w:
        results["quorum"] = quorum_metrics(
            logits, labels, torch.cat(all_w),
            seat_threshold=cfg["seat_threshold"], quorum=cfg["quorum"])
    model.train()
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Perets Stage-1 RUN-2 trainer (A/B)")
    ap.add_argument("--vanilla", action="store_true",
                    help="train the param-matched vanilla control twin (Arm B); "
                         "default = innovation (Arm A)")
    ap.add_argument("--seed", type=int, default=1, help="seed (spec: 1,2,3 per arm)")
    ap.add_argument("--epochs", type=int, default=None, help="override config epochs")
    ap.add_argument("--log-every", type=int, default=None, help="override config log_every")
    ap.add_argument("--config", type=str, default=str(HERE / "config.yaml"))
    ap.add_argument("--extract-only", action="store_true",
                    help="run phase 1 (feature extraction) then exit")
    ap.add_argument("--smoke", action="store_true",
                    help="tiny run: 256 train samples, 1 epoch (pipeline check only)")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    if args.epochs is not None:
        cfg["epochs"] = args.epochs
    if args.log_every is not None:
        cfg["log_every"] = args.log_every
    if args.smoke:
        cfg["epochs"] = 1

    arm = "B" if args.vanilla else "A"
    run_name = f"arm{arm}_seed{args.seed}" + ("_smoke" if args.smoke else "")
    accelerator = Accelerator()
    set_seed(args.seed)
    log = TeeLog(HERE / "logs" / f"{run_name}.log") if accelerator.is_main_process \
        else (lambda msg: None)

    log(f"=== PERETS STAGE-1 RUN-2 | arm {arm} "
        f"({'vanilla control' if arm == 'B' else 'multi-frame voting innovation'}) "
        f"| seed {args.seed} | git {git_hash()} ===")
    log(f"device={accelerator.device} n_proc={accelerator.num_processes} "
        f"torch={torch.__version__}")

    # ---- phase 1: extraction (main process only; cache shared) ----
    t_start = time.time()
    if accelerator.is_main_process:
        paths = extract_features(cfg, accelerator.device, log)
    accelerator.wait_for_everyone()
    tag = cfg["base_model"].replace("/", "_")
    paths = {s: HERE / cfg["cache_dir"] / f"{tag}_banking77_{s}.pt"
             for s in ("train", "test")}
    if args.extract_only:
        log(f"[extract] done in {time.time() - t_start:.1f}s; exiting (--extract-only)")
        return

    # ---- build BOTH heads (param-match hard assert), keep the requested arm ----
    arm_a, arm_b, pa, pb, rel = build_heads(
        hidden=cfg["hidden_size"], n_classes=cfg["n_classes"],
        tap_layers=tuple(cfg["tap_layers"]), frame_proj=cfg["frame_proj"],
        vanilla_proj=cfg["vanilla_proj"], max_rel_mismatch=cfg["max_param_mismatch"])
    log(f"[params] Arm A={pa:,} Arm B={pb:,} rel diff={rel:.4%} (<0.5% gate OK)")
    model = arm_b if args.vanilla else arm_a

    train_loader = make_loader(paths["train"], cfg["batch_size"], shuffle=True,
                               limit=256 if args.smoke else 0)
    test_loader = make_loader(paths["test"], 256, shuffle=False,
                              limit=256 if args.smoke else 0)

    total_steps = cfg["epochs"] * len(train_loader)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["lr"],
                                  weight_decay=cfg["weight_decay"])
    scheduler = cosine_with_warmup(optimizer, cfg["warmup_steps"], total_steps)
    model, optimizer, train_loader, test_loader, scheduler = accelerator.prepare(
        model, optimizer, train_loader, test_loader, scheduler)

    # ---- RUN-3 gate-collapse fix knobs (Arm A only; pure loss terms, 0 params) ----
    gate_balance_coeff = float(cfg.get("gate_balance_coeff", 0.0))
    gate_entropy_coeff = float(cfg.get("gate_entropy_coeff", 0.0))
    aux_frame_ce_coeff = float(cfg.get("aux_frame_ce_coeff", 0.0))
    if arm == "A":
        log(f"[gate-fix] balance(KL->uniform) coeff {gate_balance_coeff} | "
            f"entropy-bonus coeff {gate_entropy_coeff} | "
            f"aux per-frame CE coeff {aux_frame_ce_coeff} | "
            f"seat_threshold {cfg['seat_threshold']} quorum {cfg['quorum']}")

    # ---- train ----
    log(f"[train] {cfg['epochs']} epochs x {len(train_loader)} steps/epoch "
        f"= {total_steps} steps | batch {cfg['batch_size']} | lr {cfg['lr']} "
        f"cosine warmup {cfg['warmup_steps']}")
    model.train()
    step, t0, run_loss, run_n = 0, time.time(), 0.0, 0
    last_w = None
    for epoch in range(1, cfg["epochs"] + 1):
        for feats, labels in train_loader:
            logits, z, w = model(feats, return_votes=True)
            loss = F.cross_entropy(logits, labels)
            if w is not None:  # Arm A: RUN-3 gate-collapse fix
                kl_u, ent = gate_regularizers(w)
                if gate_balance_coeff:
                    loss = loss + gate_balance_coeff * kl_u      # keep frames seated on average
                if gate_entropy_coeff:
                    loss = loss - gate_entropy_coeff * ent       # per-sample entropy bonus
                if aux_frame_ce_coeff:
                    # aux per-frame CE: every frame must classify on its own,
                    # so no frame goes dead and every vote carries real evidence
                    n_b, n_f, n_c = z.shape
                    aux_ce = F.cross_entropy(z.reshape(n_b * n_f, n_c),
                                             labels.repeat_interleave(n_f))
                    loss = loss + aux_frame_ce_coeff * aux_ce
                last_w = w.detach()
            accelerator.backward(loss)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            step += 1
            run_loss += loss.item()
            run_n += 1
            if step % cfg["log_every"] == 0 or step == total_steps:
                gate_msg = ""
                if last_w is not None:
                    mw = [round(v, 3) for v in last_w.mean(0).tolist()]
                    gate_msg = f" gate w/frame {mw}"
                log(f"[train] step {step}/{total_steps} epoch {epoch} "
                    f"loss {run_loss / run_n:.4f} "
                    f"lr {scheduler.get_last_lr()[0]:.2e} "
                    f"elapsed {time.time() - t0:.1f}s{gate_msg}")
                run_loss, run_n = 0.0, 0

    # ---- eval + results ----
    results = evaluate(model, test_loader, accelerator, arm, cfg)
    wall = time.time() - t_start
    peak_gb = (torch.cuda.max_memory_allocated() / 2**30
               if torch.cuda.is_available() else 0.0)
    log(f"[eval] acc {results['accuracy']:.4f} macroF1 {results['macro_f1']:.4f} "
        f"nll {results['nll']:.4f} ece {results['ece']:.4f}")
    if "quorum" in results:
        q = results["quorum"]
        log(f"[quorum] mean w/frame {q['mean_w_per_frame']} "
            f"seated hist {q['seated_frames_hist']} "
            f"inquorate {q['inquorate_rate']:.4f} "
            f"selective acc(quorate) {q['selective_accuracy_quorate']:.4f}")
    log(f"[done] wall {wall:.1f}s | peak GPU mem {peak_gb:.2f} GB "
        f"(G4 gate: <=15 min/arm, <=8 GB)")

    if accelerator.is_main_process:
        out = {
            "run": run_name, "arm": arm, "seed": args.seed,
            "innovation": None if arm == "B" else
                "multi_reference_frame_voting (thousand-brains + GIST score==weight)",
            "base_model": cfg["base_model"], "dataset": cfg["dataset"],
            "tap_layers": cfg["tap_layers"],
            "params": {"arm_A": pa, "arm_B": pb, "rel_diff": rel},
            "metrics": results, "wall_seconds": wall, "peak_gpu_gb": peak_gb,
            "git": git_hash(),
            "config": {k: cfg[k] for k in
                       ("batch_size", "lr", "weight_decay", "warmup_steps", "epochs")},
            "gate_fix": {                       # RUN-3 gate-collapse fix knobs
                "gate_balance_coeff": gate_balance_coeff,
                "gate_entropy_coeff": gate_entropy_coeff,
                "aux_frame_ce_coeff": aux_frame_ce_coeff,
                "seat_threshold": cfg["seat_threshold"], "quorum": cfg["quorum"]},
        }
        rdir = HERE / "results"
        rdir.mkdir(exist_ok=True)
        rpath = rdir / f"{run_name}.json"
        json.dump(out, open(rpath, "w"), indent=2)
        log(f"[results] wrote {rpath}")


if __name__ == "__main__":
    main()
