# -*- coding: utf-8 -*-
"""
KESHEV-LORA / train_lora.py  --  fine-tune a personal Whisper LoRA on CLEAN data,
then MERGE + CONVERT it to the CTranslate2 format the live decoder (:8738) actually serves.

WHERE THIS RUNS
---------------
On a FLEET GPU, NOT on the Windows PC (the PC's torch is CPU-only, and project law
forbids training on the PC). It needs: torch(+cuda), transformers, peft, soundfile,
and the `ct2-transformers-converter` CLI (ships with ctranslate2). eran3 is OFF LIMITS
(coder training, ~7 days). See README for how to stage data to eran4/eran1.

THE HONEST DESIGN
-----------------
* Base model = ivrit-ai/whisper-large-v3-turbo  (exactly what :8738 serves).
* Trains ONLY on the train split of data/manifest.jsonl. The eval split
  (script_he.is_eval) is NEVER seen here -- that is the whole point of the gate.
* LoRA r=16 on q_proj/v_proj (small, matches the proven prior run).
* After training it MERGES the adapter into the base weights and runs
  ct2-transformers-converter with int8_float16 (the serving compute type), producing
  data/lora-ct2/ -- a drop-in faster-whisper model dir, same shape as the baseline.
* The baseline CT2 dir is downloaded/located separately (see --baseline-ct2 in eval_gate).

Serving reality: faster-whisper cannot load a PEFT adapter. A LoRA only reaches the
mic after it is merged into the base and converted to CT2. This script does that so the
gate compares the SAME artifact that would be deployed -- not an un-servable adapter.

USAGE
-----
    PYTHONIOENCODING=utf-8 python train_lora.py \
        --data ./data --out ./data/lora-adapter --ct2-out ./data/lora-ct2 \
        --epochs 6 --batch 4 --rank 16 --lr 1e-3
"""
from __future__ import annotations
import argparse, json, math, os, subprocess, sys, time

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from script_he import is_eval  # noqa: E402  single source of truth for the split

BASE = "ivrit-ai/whisper-large-v3-turbo"
MIN_SEC, MAX_SEC = 0.35, 30.0


def load_train_rows(data_dir):
    """Return TRAIN-split rows only. Eval rows are never returned from here."""
    man = os.path.join(data_dir, "manifest.jsonl")
    if not os.path.exists(man):
        sys.exit(f"[train] no manifest at {man} -- record clips first (python record.py).")
    rows, held = [], 0
    with open(man, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            r["_id"] = r.get("prompt_id", 0)
            if is_eval({"id": r["_id"], "block": r.get("block", "")}):
                held += 1
                continue
            wav = os.path.join(data_dir, "clips", os.path.basename(r["wav"]))
            if not os.path.exists(wav):
                continue
            if not (r.get("text") or "").strip():
                continue
            rows.append({"wav": wav, "text": r["text"].strip(), "lang": r.get("lang", "he")})
    print(f"[train] train_clips={len(rows)}  held_out_for_eval={held}", flush=True)
    if len(rows) < 20:
        print("[train] WARNING: very few training clips. Expect a weak/failing LoRA;\n"
              "        a second recording session is the realistic path (see FINDINGS.md).",
              flush=True)
    return rows


# ------------------------------------------------------------------ dataset
def make_dataset(rows, fe, tok):
    import numpy as np, soundfile as sf, torch

    class DS(torch.utils.data.Dataset):
        def __len__(self):
            return len(rows)

        def __getitem__(self, i):
            r = rows[i]
            audio, sr = sf.read(r["wav"], dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if sr != 16000 or not (MIN_SEC <= len(audio) / sr <= MAX_SEC):
                return None
            feats = fe(audio, sampling_rate=16000).input_features[0]
            labels = tok(r["text"]).input_ids
            if len(labels) > 448:
                return None
            return {"input_features": feats, "labels": labels}
    return DS()


def make_collate(fe, tok):
    def collate(batch):
        batch = [b for b in batch if b is not None]
        if not batch:
            return None
        x = fe.pad([{"input_features": b["input_features"]} for b in batch], return_tensors="pt")
        y = tok.pad([{"input_ids": b["labels"]} for b in batch], return_tensors="pt")
        x["labels"] = y["input_ids"].masked_fill(y.attention_mask.ne(1), -100)
        return x
    return collate


# ------------------------------------------------------------------ train
def train(a):
    import torch
    from transformers import (WhisperForConditionalGeneration, WhisperProcessor,
                              WhisperTokenizer)
    from peft import LoraConfig, get_peft_model

    if not torch.cuda.is_available():
        print("[train] no CUDA. This must run on a fleet GPU, not the PC. Aborting.",
              file=sys.stderr)
        sys.exit(3)

    torch.manual_seed(0)
    proc = WhisperProcessor.from_pretrained(a.base, language="hebrew", task="transcribe")
    tok = WhisperTokenizer.from_pretrained(a.base, language="hebrew", task="transcribe")
    rows = load_train_rows(a.data)

    model = WhisperForConditionalGeneration.from_pretrained(a.base)
    model.config.forced_decoder_ids = None
    model = get_peft_model(model, LoraConfig(
        r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, bias="none",
        target_modules=["q_proj", "v_proj"]))
    model.print_trainable_parameters()
    model.to("cuda").train()

    dl = torch.utils.data.DataLoader(
        make_dataset(rows, proc.feature_extractor, tok), batch_size=a.batch, shuffle=True,
        num_workers=a.workers, collate_fn=make_collate(proc.feature_extractor, tok))
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)
    total = a.epochs * max(1, math.ceil(len(rows) / a.batch))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, s / max(1, a.warmup)) * max(0.05, 1 - s / max(1, total)))

    step, t0 = 0, time.time()
    for ep in range(a.epochs):
        for batch in dl:
            if batch is None:
                continue
            batch = {k: v.to("cuda") for k, v in batch.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            step += 1
            if step % 5 == 0:
                print(f"[train] ep{ep} {step}/{total} loss {loss.item():.4f} "
                      f"lr {sched.get_last_lr()[0]:.2e}", flush=True)
    os.makedirs(a.out, exist_ok=True)
    model.save_pretrained(a.out)
    with open(os.path.join(a.out, "run_config.json"), "w", encoding="utf-8") as f:
        json.dump({"base": a.base, "train_clips": len(rows), "epochs": a.epochs,
                   "batch": a.batch, "rank": a.rank, "lr": a.lr,
                   "split": "script_he.is_eval (vocab_eval or id%5==0 -> eval)"}, f, indent=2)
    print(f"[train] adapter saved -> {a.out}", flush=True)
    return proc


# ------------------------------------------------------------------ merge + ct2
def merge_and_convert(a, proc=None):
    """Merge the adapter into the base, then convert to CTranslate2 int8_float16."""
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    from peft import PeftModel

    if proc is None:
        proc = WhisperProcessor.from_pretrained(a.base, language="hebrew", task="transcribe")
    print("[merge] loading base + adapter ...", flush=True)
    base = WhisperForConditionalGeneration.from_pretrained(a.base, torch_dtype=torch.float16)
    merged = PeftModel.from_pretrained(base, a.out).merge_and_unload()

    merged_dir = a.out + "-merged-hf"
    os.makedirs(merged_dir, exist_ok=True)
    merged.save_pretrained(merged_dir, safe_serialization=True)
    proc.save_pretrained(merged_dir)          # tokenizer.json + preprocessor_config.json
    print(f"[merge] merged HF model -> {merged_dir}", flush=True)

    if os.path.isdir(a.ct2_out):
        import shutil
        shutil.rmtree(a.ct2_out)
    cmd = ["ct2-transformers-converter", "--model", merged_dir,
           "--output_dir", a.ct2_out, "--quantization", "int8_float16",
           "--copy_files", "tokenizer.json", "preprocessor_config.json"]
    print("[ct2] " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    print(f"[ct2] CTranslate2 LoRA model ready -> {a.ct2_out}", flush=True)
    print("[ct2] this dir is what eval_gate.py loads as --lora-ct2, and what would be\n"
          "      deployed IF (and only if) the gate says PASS.", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "lora-adapter"))
    ap.add_argument("--ct2-out", dest="ct2_out", default=os.path.join(HERE, "data", "lora-ct2"))
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--warmup", type=int, default=15)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--skip-train", action="store_true", help="only merge+convert an existing adapter")
    ap.add_argument("--skip-convert", action="store_true", help="train only, no CT2 conversion")
    a = ap.parse_args()

    proc = None
    if not a.skip_train:
        proc = train(a)
    if not a.skip_convert:
        merge_and_convert(a, proc)
    print("[done] train_lora.py finished. Run eval_gate.py to decide PASS/FAIL.", flush=True)


if __name__ == "__main__":
    main()
