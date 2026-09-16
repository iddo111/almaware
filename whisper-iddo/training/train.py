"""Fine-tune whisper-large-v3-turbo on Iddo's voice.

DESIGN NOTES THAT MATTER (each one is a decision someone will want to audit)

* THE LANGUAGE TOKEN IS IN THE LOSS. Most Whisper fine-tuning recipes mask the
  prefix and train only on text. That is wrong for this speaker. Production
  (alma-mic/stt.py) runs detect_language() and forces the winner, so language ID
  IS the first half of the product, and 53% of his speech is English. Including
  the <|he|>/<|en|> token in the labels trains the LID head on his actual voice.
  When starting from ivrit-ai -- whose own model card says "language detection
  capability has been degraded during training" -- this is the mechanism that
  can repair it.

* MIXED UTTERANCES GET THE MAJORITY SCRIPT. Whisper has one language slot and no
  'mixed' token. Assigning by dominant letter count is the only honest mapping.

* 20% OF SAMPLES KEEP TIMESTAMPS. faster-whisper's default decode path emits
  timestamp tokens. Training 100% on <|notimestamps|> would let that path rot
  and the regression would only show up in production. Clip-level timestamps
  (<|0.00|> .. <|dur|>) are approximately right because every clip is already
  VAD-trimmed.

* FP32 MASTER WEIGHTS, bf16 COMPUTE -- NOT pure bf16. Loading the model in
  bf16 and letting AdamW keep bf16 state looks like the obvious way to fit a
  1.55B-class model in memory, and it silently destroys the run: bf16 resolves
  ~1 part in 256, while an Adam update at lr 1e-5 on a ~0.03 weight is ~3e-4
  relative, so the update rounds to nothing. Measured on this exact model and
  data (probe_precision.py): bf16 master moves 14.80% of parameters after 6
  steps, fp32 master moves 99.98%. The first aborted run confirmed it end to
  end -- WER 28.19 -> 28.33 after a third of an epoch, i.e. no learning at all.
  Weights and optimizer state are fp32; matmuls run in bf16 under autocast.

* SPEC-AUGMENT IS ON. 11.7 h from one speaker in one room is small enough to
  memorise. This is the cheapest regulariser that attacks exactly that.

* SELECTION IS ON WER WITH GUARD RAILS, NEVER ON LOSS. Loss falling while WER
  climbs is the classic Whisper fine-tuning failure. A checkpoint is only
  eligible to be promoted if it also keeps general Hebrew, general English and
  language-ID within tolerance of the base model -- see `eligible()`. A model
  that transcribes Iddo beautifully and destroys his English is a downgrade and
  is refused here rather than shipped.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HEBREW_LETTER, LATIN_LETTER, normalise  # noqa: E402
import evaluate as ev  # noqa: E402
import melgpu  # noqa: E402

ROOT = os.path.expanduser("~/whisper-iddo")


def lang_of(row):
    """Whisper has one language slot; pick the dominant script."""
    if row["lang"] in ("he", "en"):
        return row["lang"]
    t = row["text"]
    return "he" if len(HEBREW_LETTER.findall(t)) >= len(LATIN_LETTER.findall(t)) else "en"


class TrainSet(Dataset):
    """Returns raw audio, not features. Feature extraction happens on the GPU
    (see melgpu.py) because doing it in forked workers deadlocked this box."""

    def __init__(self, rows, blob, tok, ts_frac=0.2, seed=0):
        self.rows, self.blob, self.tok, self.ts_frac = rows, blob, tok, ts_frac
        self.rng = random.Random(seed)
        self.sot = tok.convert_tokens_to_ids("<|startoftranscript|>")
        self.transcribe = tok.convert_tokens_to_ids("<|transcribe|>")
        self.nots = tok.convert_tokens_to_ids("<|notimestamps|>")
        self.eot = tok.convert_tokens_to_ids("<|endoftext|>")
        self.ts0 = tok.convert_tokens_to_ids("<|0.00|>")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        s = r["off"] // 2
        audio = np.asarray(self.blob[s:s + r["n"]], dtype=np.float32) / 32768.0
        lang_id = self.tok.convert_tokens_to_ids(f"<|{lang_of(r)}|>")
        text_ids = self.tok.encode(" " + normalise(r["text"]), add_special_tokens=False)

        if self.rng.random() < self.ts_frac:
            # clip-level timestamps: <|0.00|> text <|dur|>
            end = min(29.98, round(r["dur"] / 0.02) * 0.02)
            end_id = self.ts0 + int(round(end / 0.02))
            labels = [lang_id, self.transcribe, self.ts0] + text_ids + [end_id, self.eot]
        else:
            labels = [lang_id, self.transcribe, self.nots] + text_ids + [self.eot]
        return audio, labels[:448]


def collate(batch):
    wav = torch.from_numpy(melgpu.pad_batch([b[0] for b in batch]))
    L = max(len(b[1]) for b in batch)
    labels = torch.full((len(batch), L), -100, dtype=torch.long)
    for i, (_, lab) in enumerate(batch):
        labels[i, :len(lab)] = torch.tensor(lab)
    return wav, labels


def eligible(cur, base, tol_rel=0.15, tol_lid=0.02):
    """Guard rails against catastrophic forgetting. Returns (ok, reasons).

    A guard set that was not evaluated is reported as a MISSING guard, never
    silently treated as passing -- the whole point is that a checkpoint must
    prove it did not wreck general speech before it can be promoted."""
    bad = []
    for s in ("fleurs_he", "fleurs_en"):
        if s not in cur or s not in base:
            bad.append(f"{s} GUARD NOT EVALUATED")
            continue
        if cur[s]["wer"] > base[s]["wer"] * (1 + tol_rel) + 1e-9:
            bad.append(f"{s} WER {cur[s]['wer']*100:.2f} > base "
                       f"{base[s]['wer']*100:.2f} +{tol_rel:.0%}")
    k = "iddo_tierA"
    if k in cur and k in base and cur[k]["lid_acc"] < base[k]["lid_acc"] - tol_lid:
        bad.append(f"LID {cur[k]['lid_acc']*100:.1f} < base "
                   f"{base[k]['lid_acc']*100:.1f} -{tol_lid*100:.0f}pt")
    return (not bad), bad


def evaluate_all(model, proc, sets, batch=16):
    out = {}
    was = model.training
    model.eval()
    for name in sets:
        rows, blob = ev.load_set(name)
        hyps, lids = ev.run(model, proc, rows, blob, batch=batch)
        out[name] = ev.score(rows, hyps, lids)
    if was:
        model.train()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--encoder-lr-mult", type=float, default=0.25)
    ap.add_argument("--freeze-encoder-epochs", type=float, default=1.0)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--evals-per-epoch", type=int, default=2)
    ap.add_argument("--ts-frac", type=float, default=0.2)
    ap.add_argument("--spec-augment", type=float, default=0.05)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--max-train", type=int, default=0, help="debug: cap train rows")
    ap.add_argument("--eval-sets", default="iddo_tierA,fleurs_he,fleurs_en")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    os.makedirs(args.out, exist_ok=True)

    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    dev = "cuda"
    # fp32 master weights: see the precision note at the top of this file.
    model = WhisperForConditionalGeneration.from_pretrained(
        args.base, dtype=torch.float32).to(dev)
    proc = WhisperProcessor.from_pretrained(args.base)
    tok, fe = proc.tokenizer, proc.feature_extractor
    model.config.forced_decoder_ids = None
    model.generation_config.forced_decoder_ids = None
    if args.spec_augment > 0:
        model.config.apply_spec_augment = True
        model.config.mask_time_prob = args.spec_augment
        model.config.mask_feature_prob = 0.0
    model.config.use_cache = False
    model.gradient_checkpointing_enable()

    # ---- data
    import common
    pk = common.PackedAudio(ROOT)
    rows = pk.split("train")
    random.Random(args.seed).shuffle(rows)
    if args.max_train:
        rows = rows[:args.max_train]
    ds = TrainSet(rows, pk.blob, tok, ts_frac=args.ts_frac, seed=args.seed)
    dl = DataLoader(ds, batch_size=args.bs, shuffle=True, num_workers=args.workers,
                    collate_fn=collate, drop_last=True, pin_memory=True,
                    persistent_workers=args.workers > 0)
    mel = melgpu.GpuMel(fe, dev)
    d = melgpu.verify(fe, dev)          # refuse to train on a wrong mel
    print(f"gpu mel verified against WhisperFeatureExtractor: max|diff|={d:.2e}")

    steps_per_epoch = len(dl) // args.accum
    total_steps = int(steps_per_epoch * args.epochs)
    eval_every = max(1, steps_per_epoch // args.evals_per_epoch)
    freeze_until = int(steps_per_epoch * args.freeze_encoder_epochs)

    enc_params = [p for n, p in model.named_parameters() if n.startswith("model.encoder")]
    dec_params = [p for n, p in model.named_parameters() if not n.startswith("model.encoder")]
    opt = torch.optim.AdamW(
        [{"params": dec_params, "lr": args.lr},
         {"params": enc_params, "lr": args.lr * args.encoder_lr_mult}],
        betas=(0.9, 0.98), eps=1e-6, weight_decay=0.01)

    def set_encoder_trainable(flag):
        for p in enc_params:
            p.requires_grad_(flag)
    set_encoder_trainable(args.freeze_encoder_epochs <= 0)

    def lr_at(step):
        if step < args.warmup:
            return step / max(1, args.warmup)
        p = (step - args.warmup) / max(1, total_steps - args.warmup)
        return 0.5 * (1 + math.cos(math.pi * min(1.0, p)))

    print(f"train rows      {len(rows)}")
    print(f"steps/epoch     {steps_per_epoch}   total {total_steps}   eval every {eval_every}")
    print(f"encoder frozen  first {freeze_until} steps ({args.freeze_encoder_epochs} epoch)")
    print(f"trainable       enc {sum(p.numel() for p in enc_params)/1e6:.1f}M  "
          f"dec {sum(p.numel() for p in dec_params)/1e6:.1f}M", flush=True)

    # ---- baseline eval (step 0) -- this is what everything is judged against
    t0 = time.time()
    base_res = evaluate_all(model, proc, args.eval_sets.split(","))
    hist = [{"step": 0, "epoch": 0.0, "loss": None, "res": base_res, "encoder": "frozen"}]
    print("[step 0 BASE] " + "  ".join(
        f"{k} WER {v['wer']*100:.2f}/LID {v['lid_acc']*100:.0f}" for k, v in base_res.items()),
        flush=True)

    best = {"metric": base_res["iddo_tierA"]["wer"], "step": 0, "path": None}
    json.dump(base_res, open(os.path.join(args.out, "base_eval.json"), "w"), indent=2)

    step = 0
    micro = 0
    run_loss, run_n = 0.0, 0
    torch.cuda.reset_peak_memory_stats()
    model.train()
    done = False
    ep = 0
    while not done:
        ep += 1
        for wav, labels in dl:
            wav = wav.to(dev, non_blocking=True)
            feats = mel(wav)
            labels = labels.to(dev, non_blocking=True)
            with torch.autocast("cuda", torch.bfloat16):
                out = model(input_features=feats, labels=labels)
            (out.loss / args.accum).backward()
            run_loss += out.loss.item()
            run_n += 1
            micro += 1
            if micro % args.accum:
                continue

            step += 1
            scale = lr_at(step)
            opt.param_groups[0]["lr"] = args.lr * scale
            opt.param_groups[1]["lr"] = args.lr * args.encoder_lr_mult * scale
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)

            if step == freeze_until and freeze_until > 0:
                set_encoder_trainable(True)
                print(f"[step {step}] encoder UNFROZEN "
                      f"(lr x{args.encoder_lr_mult})", flush=True)

            if step % 25 == 0:
                print(f"  step {step}/{total_steps}  loss {run_loss/max(1,run_n):.4f}  "
                      f"lr {opt.param_groups[0]['lr']:.2e}  "
                      f"peak {torch.cuda.max_memory_allocated()/2**30:.1f} GiB  "
                      f"{(time.time()-t0)/60:.1f}m", flush=True)
                run_loss, run_n = 0.0, 0

            if step % eval_every == 0 or step == total_steps:
                res = evaluate_all(model, proc, args.eval_sets.split(","))
                ok, why = eligible(res, base_res)
                cur = res["iddo_tierA"]["wer"]
                epf = step / steps_per_epoch
                hist.append({"step": step, "epoch": round(epf, 3),
                             "loss": out.loss.item(), "res": res,
                             "eligible": ok, "guard": why,
                             "encoder": "frozen" if step < freeze_until else "training",
                             "peak_gib": torch.cuda.max_memory_allocated() / 2**30,
                             "minutes": (time.time() - t0) / 60})
                json.dump(hist, open(os.path.join(args.out, "history.json"), "w"),
                          indent=2, ensure_ascii=False)
                mark = ""
                if ok and cur < best["metric"] - 1e-6:
                    best = {"metric": cur, "step": step,
                            "path": os.path.join(args.out, "best")}
                    model.save_pretrained(best["path"], safe_serialization=True)
                    proc.save_pretrained(best["path"])
                    mark = "  <-- SAVED"
                elif not ok:
                    mark = "  REFUSED: " + "; ".join(why)
                print(f"[step {step} ep {epf:.2f}] " + "  ".join(
                    f"{k} WER {v['wer']*100:.2f}/LID {v['lid_acc']*100:.0f}"
                    for k, v in res.items()) + mark, flush=True)

            if step >= total_steps:
                done = True
                break

    summary = {
        "base": args.base, "out": args.out,
        "args": vars(args),
        "best": best,
        "base_eval": base_res,
        "peak_gib": torch.cuda.max_memory_allocated() / 2**30,
        "wall_minutes": (time.time() - t0) / 60,
        "history": hist,
    }
    json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"),
              indent=2, ensure_ascii=False)
    print(json.dumps({"best": best, "peak_gib": summary["peak_gib"],
                      "wall_minutes": summary["wall_minutes"]}, indent=2))


if __name__ == "__main__":
    main()
