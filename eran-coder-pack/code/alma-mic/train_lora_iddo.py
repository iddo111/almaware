#!/usr/bin/env python3
"""ALMA-MIC personal Whisper LoRA — train on Iddo's own (wav, text) pairs.

Runs ONLY on the DGX fleet (eran4). Data: voice_corpus/ streamed from the PC
over the LAN. PRIVACY: this script never prints transcript text — numbers only.

Subcommands:
  train  — LoRA (peft, r=16, q/v proj) on ivrit-ai/whisper-large-v3-turbo
  eval   — WER on the held-out slice: base model vs base+LoRA (honest A/B)

Split rule (deterministic, permanent): sort all corpus entries by wav filename;
every 20th (idx % 20 == 0) is HELDOUT forever. Training may only use the rest.
"""
from __future__ import annotations
import argparse, json, math, os, re, sys, time
import numpy as np
import soundfile as sf
import torch

BASE = "ivrit-ai/whisper-large-v3-turbo"
LANGNAME = {"he": "hebrew", "en": "english"}
MAX_SEC = 30.0
MIN_SEC = 0.35


def load_manifest(data_dir):
    """-> (train_rows, heldout_rows); rows = dict(wav=abs_path, text, lang)."""
    rows, skipped = [], {"missing": 0, "lang": 0, "empty": 0}
    with open(os.path.join(data_dir, "corpus.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("lang") not in LANGNAME:
                skipped["lang"] += 1
                continue
            if not (r.get("text") or "").strip():
                skipped["empty"] += 1
                continue
            p = os.path.join(data_dir, os.path.basename(r["wav"]))
            if not os.path.exists(p):
                skipped["missing"] += 1
                continue
            rows.append({"wav": p, "text": r["text"].strip(), "lang": r["lang"]})
    rows.sort(key=lambda r: os.path.basename(r["wav"]))
    held = [r for i, r in enumerate(rows) if i % 20 == 0]
    train = [r for i, r in enumerate(rows) if i % 20 != 0]
    print(f"[data] usable={len(rows)} train_pool={len(train)} heldout={len(held)} skipped={skipped}", flush=True)
    return train, held


class Corpus(torch.utils.data.Dataset):
    def __init__(self, rows, fe, toks):
        self.rows, self.fe, self.toks = rows, fe, toks

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        audio, sr = sf.read(r["wav"], dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000 or not (MIN_SEC <= len(audio) / sr <= MAX_SEC):
            return None
        feats = self.fe(audio, sampling_rate=16000).input_features[0]
        labels = self.toks[r["lang"]](r["text"]).input_ids
        if len(labels) > 448:
            return None
        return {"input_features": feats, "labels": labels}


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


def build(base):
    from transformers import WhisperProcessor, WhisperTokenizer
    proc = WhisperProcessor.from_pretrained(base, language="hebrew", task="transcribe")
    toks = {k: WhisperTokenizer.from_pretrained(base, language=v, task="transcribe")
            for k, v in LANGNAME.items()}
    return proc, toks


def load_overlay(path):
    """jsonl of {wav, text[, lang]} -> {basename: text}. Used for teacher labels
    (training) and for Iddo's human-verified gold references (eval)."""
    m = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            t = (r.get("text") or "").strip()
            if t:
                m[os.path.basename(r["wav"])] = t
    return m


def cmd_train(a):
    from transformers import WhisperForConditionalGeneration
    from peft import LoraConfig, get_peft_model
    torch.manual_seed(0)
    proc, toks = build(a.base)
    train_pool, _ = load_manifest(a.data)
    if a.labels:  # distillation: replace pseudo-labels with a stronger teacher's
        lab = load_overlay(a.labels)
        before = len(train_pool)
        train_pool = [dict(r, text=lab[os.path.basename(r["wav"])])
                      for r in train_pool if os.path.basename(r["wav"]) in lab]
        print(f"[train] teacher labels: {len(train_pool)}/{before} rows relabeled "
              f"(dropped {before - len(train_pool)} without teacher text)", flush=True)
    train_pool.sort(key=lambda r: os.path.basename(r["wav"]), reverse=True)  # newest first
    rows = train_pool[: a.slice] if a.slice else train_pool
    print(f"[train] slice={len(rows)} epochs={a.epochs} batch={a.batch} r={a.rank} base={a.base}", flush=True)

    model = WhisperForConditionalGeneration.from_pretrained(a.base)
    model.config.forced_decoder_ids = None
    model = get_peft_model(model, LoraConfig(
        r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, bias="none",
        target_modules=["q_proj", "v_proj"]))
    model.print_trainable_parameters()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(dev).train()

    dl = torch.utils.data.DataLoader(
        Corpus(rows, proc.feature_extractor, toks), batch_size=a.batch, shuffle=True,
        num_workers=a.workers, collate_fn=make_collate(proc.feature_extractor, toks["he"]),
        drop_last=False)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)
    total = a.epochs * math.ceil(len(rows) / a.batch)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, s / max(1, a.warmup)) * max(0.05, 1 - s / max(1, total)))

    step, t0 = 0, time.time()
    for ep in range(a.epochs):
        for batch in dl:
            if batch is None:
                continue
            batch = {k: v.to(dev) for k, v in batch.items()}
            with torch.autocast(device_type=dev, dtype=torch.bfloat16, enabled=dev == "cuda"):
                loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            step += 1
            if step % 10 == 0:
                print(f"[train] ep{ep} step {step}/{total} loss {loss.item():.4f} "
                      f"lr {sched.get_last_lr()[0]:.2e} {step * a.batch / (time.time() - t0):.1f} samp/s", flush=True)
        os.makedirs(a.out, exist_ok=True)
        model.save_pretrained(a.out)
        print(f"[train] epoch {ep} done, adapter saved -> {a.out}", flush=True)
    with open(os.path.join(a.out, "run_config.json"), "w", encoding="utf-8") as f:
        json.dump({"base": a.base, "slice": len(rows), "epochs": a.epochs, "batch": a.batch,
                   "rank": a.rank, "lr": a.lr, "labels": a.labels or "corpus.jsonl (pseudo)",
                   "split_rule": "sorted-by-name idx%20==0 heldout"},
                  f, indent=2)
    print("[train] DONE", flush=True)


_norm_re = re.compile(r"[^\w\s]", re.UNICODE)


def norm(s):
    return re.sub(r"\s+", " ", _norm_re.sub("", s.lower())).strip()


@torch.no_grad()
def transcribe_all(model, proc, rows, dev, batch=8):
    out = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        feats, keep = [], []
        for r in chunk:
            audio, sr = sf.read(r["wav"], dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if sr != 16000 or not (MIN_SEC <= len(audio) / sr <= MAX_SEC):
                continue
            feats.append(audio); keep.append(r)
        if not feats:
            continue
        # group by lang so the language token is right
        for lang in ("he", "en"):
            sub = [(f, r) for f, r in zip(feats, keep) if r["lang"] == lang]
            if not sub:
                continue
            x = proc.feature_extractor([f for f, _ in sub], sampling_rate=16000,
                                       return_tensors="pt").input_features.to(dev)
            with torch.autocast(device_type=dev, dtype=torch.bfloat16, enabled=dev == "cuda"):
                ids = model.generate(input_features=x, language=lang, task="transcribe",
                                     max_new_tokens=200)
            for (f, r), t in zip(sub, proc.batch_decode(ids, skip_special_tokens=True)):
                out.append((r["text"], t, r["lang"]))
    return out


def wer_report(pairs, tag):
    import jiwer
    for lang in ("he", "en", None):
        sel = [(a, b) for a, b, l in pairs if lang is None or l == lang]
        if not sel:
            continue
        refs = [norm(a) for a, b in sel]
        hyps = [norm(b) for a, b in sel]
        refs, hyps = zip(*[(r, h) for r, h in zip(refs, hyps) if r])
        w = jiwer.wer(list(refs), list(hyps))
        print(f"[eval] {tag} lang={lang or 'ALL'} n={len(refs)} WER={w:.4f}", flush=True)


def cmd_eval(a):
    from transformers import WhisperForConditionalGeneration
    proc, _ = build(a.base)
    _, held = load_manifest(a.data)
    if a.gold:  # human-verified references override the pseudo-label refs
        g = load_overlay(a.gold)
        n_gold = sum(1 for r in held if os.path.basename(r["wav"]) in g)
        held = [dict(r, text=g.get(os.path.basename(r["wav"]), r["text"])) for r in held]
        if a.gold_only:
            held = [r for r in held if os.path.basename(r["wav"]) in g]
        print(f"[eval] gold refs applied: {n_gold} (gold_only={a.gold_only})", flush=True)
    if a.limit:
        held = held[-a.limit:]  # newest slice of heldout = current mic conditions
    print(f"[eval] heldout clips used: {len(held)}", flush=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    model = WhisperForConditionalGeneration.from_pretrained(a.base).to(dev).eval()
    wer_report(transcribe_all(model, proc, held, dev, a.batch), "BASE")

    if a.lora and os.path.isdir(a.lora):
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.lora).to(dev).eval()
        wer_report(transcribe_all(model, proc, held, dev, a.batch), f"LORA({os.path.basename(a.lora)})")
    print("[eval] DONE", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--data", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--base", default=BASE)
    t.add_argument("--slice", type=int, default=2000)
    t.add_argument("--epochs", type=int, default=2)
    t.add_argument("--batch", type=int, default=8)
    t.add_argument("--rank", type=int, default=16)
    t.add_argument("--lr", type=float, default=1e-3)
    t.add_argument("--warmup", type=int, default=20)
    t.add_argument("--workers", type=int, default=2)
    t.add_argument("--labels", default="", help="teacher jsonl overriding train texts")
    e = sub.add_parser("eval")
    e.add_argument("--data", required=True)
    e.add_argument("--base", default=BASE)
    e.add_argument("--lora", default="")
    e.add_argument("--limit", type=int, default=150)
    e.add_argument("--batch", type=int, default=8)
    e.add_argument("--gold", default="", help="human-verified refs jsonl (swap-in later)")
    e.add_argument("--gold-only", action="store_true", dest="gold_only")
    a = ap.parse_args()
    {"train": cmd_train, "eval": cmd_eval}[a.cmd](a)


if __name__ == "__main__":
    main()
