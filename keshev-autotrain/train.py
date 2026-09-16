# -*- coding: utf-8 -*-
"""KESHEV AUTOTRAIN / train.py -- the two training paths. שני המסלולים.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

    --mode lora   a cheap personal adaptation (r=16 on q/v proj). Minutes.
    --mode full   a full fine-tune of the decoder stack, for when there is
                  enough gold data to justify it. Hours.

Both paths are RESUMABLE (--resume picks up the newest checkpoint), both write a
VERSIONED output directory, and both go through guards.py: fleet-only, nice 19,
a memory floor that refuses to start and pauses mid-run.

WHERE IT RUNS
-------------
On a fleet box. `guards.require_fleet()` refuses Windows outright -- training on
the PC is forbidden by project law and this script will not be the exception.

THE SPLIT IS SACRED
-------------------
The frozen evaluation set (the reserved Cafe-Claude sessions 2026-06-25 and
2026-07-01) is excluded here by PREFIX, the same rule cafe_eval.py enforces on
the other side. If the eval set ever enters the training pool the number stops
meaning anything, and a meaningless number is worse than no number -- it is a
green light you cannot trust.

LABEL QUALITY IS CARRIED, NOT FLATTENED
---------------------------------------
Each row carries `source`:
    correction -> HIS correction. Gold. He told the model it was wrong.
    confirmed  -> he sent it verbatim. Real, but the model already agreed.
    asr        -> the model's own output. WEAK, circular. This is what sank the
                  previous LoRA (0/13 names, CER 28.5% vs 18.0%).
`--gold-only` trains on corrections+confirmed alone. `--weight-gold N` repeats
gold rows N times instead of discarding the rest. The default is gold-only for
LoRA, because a small adaptation on circular labels is exactly the known failure.
"""
from __future__ import annotations
import argparse, glob, json, os, random, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guards

EVAL_PREFIXES = ("20260625", "20260701")       # frozen. never trained on.
BASE = "ivrit-ai/whisper-large-v3-turbo"


def load_manifest(path, gold_only, weight_gold):
    rows, skipped = [], {"frozen": 0, "empty": 0, "missing": 0, "weak": 0}
    root = os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            wav = d.get("wav") or ""
            if os.path.basename(wav).startswith(EVAL_PREFIXES):
                skipped["frozen"] += 1              # the split is sacred
                continue
            text = (d.get("truth") or d.get("text") or "").strip()
            if not text:
                skipped["empty"] += 1
                continue
            p = wav if os.path.isabs(wav) else os.path.join(root, wav)
            if not os.path.exists(p):
                skipped["missing"] += 1
                continue
            src = d.get("source", "asr")
            gold = src in ("correction", "confirmed")
            if gold_only and not gold:
                skipped["weak"] += 1
                continue
            row = {"wav": p, "text": text, "source": src}
            rows.append(row)
            if gold and weight_gold > 1:
                rows.extend([dict(row) for _ in range(weight_gold - 1)])
    return rows, skipped


def newest_checkpoint(outdir):
    cks = sorted(glob.glob(os.path.join(outdir, "checkpoint-*")),
                 key=lambda p: int(p.rsplit("-", 1)[-1]) if p.rsplit("-", 1)[-1].isdigit() else -1)
    return cks[-1] if cks else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["lora", "full"], required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True, help="versioned output dir")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--limit", type=int, default=0, help="cap rows (a small proof run)")
    ap.add_argument("--gold-only", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--weight-gold", type=int, default=1)
    ap.add_argument("--floor-gb", type=float, default=guards.DEFAULT_FLOOR_GB)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--runlog", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "logs", "runs.jsonl"))
    a = ap.parse_args()

    guards.require_fleet()
    guards.be_nice(19)
    avail = guards.require_headroom(a.floor_gb)

    gold_only = a.gold_only if a.gold_only is not None else (a.mode == "lora")
    rows, skipped = load_manifest(a.manifest, gold_only, a.weight_gold)
    random.Random(2026).shuffle(rows)
    if a.limit:
        rows = rows[:a.limit]
    ngold = sum(1 for r in rows if r["source"] in ("correction", "confirmed"))
    print("[train] mode=%s rows=%d (gold=%d) gold_only=%s skipped=%s"
          % (a.mode, len(rows), ngold, gold_only, skipped), flush=True)
    if not rows:
        print("[train] REFUSED: no usable rows. Nothing was trained, nothing was swapped.\n"
              "        (an empty pool is a healthy outcome, not a failure)", flush=True)
        guards.log_run(a.runlog, mode=a.mode, rows=0, outcome="no-data", avail_gb=avail)
        return 2

    t0 = time.time()
    import torch, numpy as np, soundfile as sf
    from transformers import (WhisperProcessor, WhisperForConditionalGeneration,
                              Seq2SeqTrainer, Seq2SeqTrainingArguments)

    proc = WhisperProcessor.from_pretrained(a.base, language="he", task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(a.base, dtype=torch.bfloat16)
    model.config.forced_decoder_ids = None
    model.generation_config.forced_decoder_ids = None

    if a.mode == "lora":
        from peft import LoraConfig, get_peft_model
        model = get_peft_model(model, LoraConfig(
            r=a.rank, lora_alpha=a.rank * 2, lora_dropout=0.05, bias="none",
            target_modules=["q_proj", "v_proj"]))
        model.print_trainable_parameters()
        lr = a.lr or 1e-3
    else:
        model.model.encoder.requires_grad_(False)     # keep the ear, retrain the mouth
        lr = a.lr or 1e-5

    fe, tok = proc.feature_extractor, proc.tokenizer

    class DS(torch.utils.data.Dataset):
        def __len__(self):
            return len(rows)

        def __getitem__(self, i):
            r = rows[i]
            audio, sr = sf.read(r["wav"], dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            feats = fe(audio, sampling_rate=sr, return_tensors="pt").input_features[0]
            labels = tok(r["text"], return_tensors="pt").input_ids[0]
            return {"input_features": feats, "labels": labels}

    def collate(batch):
        x = torch.stack([b["input_features"] for b in batch])
        maxlen = max(b["labels"].shape[0] for b in batch)
        lab = torch.full((len(batch), maxlen), -100, dtype=torch.long)
        for i, b in enumerate(batch):
            lab[i, :b["labels"].shape[0]] = b["labels"]
        return {"input_features": x, "labels": lab}

    os.makedirs(a.out, exist_ok=True)
    targs = Seq2SeqTrainingArguments(
        output_dir=a.out, per_device_train_batch_size=a.batch,
        num_train_epochs=a.epochs, learning_rate=lr, bf16=True,
        logging_steps=10, save_steps=50, save_total_limit=3,
        report_to=[], remove_unused_columns=False, dataloader_num_workers=0)

    class MemGuard(__import__("transformers").TrainerCallback):
        """The floor, mid-run. Stops cleanly so the checkpoint survives."""
        def on_step_end(self, args_, state, control, **kw):
            if state.global_step % 10 == 0 and not guards.pause_if_low(a.floor_gb):
                control.should_training_stop = True
            return control

    trainer = Seq2SeqTrainer(model=model, args=targs, train_dataset=DS(),
                             data_collator=collate, callbacks=[MemGuard()])

    ck = newest_checkpoint(a.out) if a.resume else None
    if ck:
        print("[train] resuming from %s" % ck, flush=True)
    res = trainer.train(resume_from_checkpoint=ck)

    final = os.path.join(a.out, "final")
    trainer.save_model(final)
    proc.save_pretrained(final)
    dt = time.time() - t0
    loss = float(getattr(res, "training_loss", float("nan")))
    print("[train] DONE in %.1fs  loss=%.4f  -> %s" % (dt, loss, final), flush=True)
    guards.log_run(a.runlog, mode=a.mode, rows=len(rows), gold=ngold, epochs=a.epochs,
                   loss=loss, seconds=round(dt, 1), out=final, avail_gb=avail,
                   outcome="trained")
    print("[train] NOTE: nothing was deployed. A model becomes live only by\n"
          "        beating the frozen set in evaluate.py, and then only by his word.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
