#!/usr/bin/env python3
"""Full-weight fine-tune of Qwen3-14B on the 3-node DGX fabric via DeepSpeed ZeRO-3.

Launched by launch_node.sh -> torchrun on each of eran1/eran2/eran3 (1 rank/node).
Consumes a PRE-TOKENIZED, PRE-PACKED dataset produced by tokenize_pack.py
(a directory of .npy int32 arrays, each row already exactly seq_len tokens).

CRITICAL ORDERING (ZeRO-3): TrainingArguments(deepspeed=...) MUST be built BEFORE
AutoModelForCausalLM.from_pretrained(), so HF registers HfDeepSpeedConfig and
from_pretrained partitions the weights with zero.Init(). Otherwise every rank
loads the FULL model and DeepSpeed's later model.to(device) wedges.
"""
import argparse, os, glob, signal, faulthandler
import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer,
                          TrainingArguments, set_seed)

faulthandler.register(signal.SIGUSR1, all_threads=True)   # kill -USR1 <pid> -> stack to stderr


class PackedDataset(Dataset):
    """Memory-maps the packed .npy shards. Each item is one seq_len window;
    labels == input_ids (causal LM, loss over the whole packed window)."""
    def __init__(self, data_dir, seq_len):
        self.seq_len = seq_len
        self.shards = sorted(glob.glob(os.path.join(data_dir, "*.npy")))
        if not self.shards:
            raise FileNotFoundError(f"no .npy packed shards in {data_dir} -- run tokenize_pack.py first")
        self.arrs, self.index = [], []
        for si, f in enumerate(self.shards):
            a = np.load(f, mmap_mode="r")
            assert a.ndim == 2 and a.shape[1] == seq_len, f"{f} shape {a.shape} != (*,{seq_len})"
            self.arrs.append(a)
            for r in range(a.shape[0]):
                self.index.append((si, r))

    def __len__(self):
        return len(self.index)

    def __getitem__(self, i):
        si, r = self.index[i]
        ids = torch.from_numpy(np.asarray(self.arrs[si][r], dtype=np.int64))
        return {"input_ids": ids, "labels": ids.clone(), "attention_mask": torch.ones_like(ids)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_path", required=True)
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--deepspeed", required=True)
    ap.add_argument("--seq_len", type=int, default=2048)
    ap.add_argument("--micro_batch", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--warmup_ratio", type=float, default=0.03)
    ap.add_argument("--num_epochs", type=float, default=1.0)
    ap.add_argument("--save_steps", type=int, default=200)
    ap.add_argument("--save_total_limit", type=int, default=3)
    ap.add_argument("--log_steps", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    set_seed(args.seed)

    tok = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)

    # ---- TrainingArguments FIRST (registers HfDeepSpeedConfig for zero.Init) ----
    targs = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.micro_batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.num_epochs,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=args.log_steps,
        save_steps=args.save_steps,
        save_total_limit=args.save_total_limit,
        save_strategy="steps",
        report_to=[],
        deepspeed=args.deepspeed,
        dataloader_num_workers=2,
        ddp_timeout=3600,
        max_grad_norm=1.0,
    )

    # ---- now the model: from_pretrained partitions via zero.Init (stage 3) ----
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",   # flash_attn not installed on the fleet
        use_cache=False,              # required with gradient checkpointing
        trust_remote_code=True,
    )
    model.gradient_checkpointing_enable()

    ds = PackedDataset(args.data_dir, args.seq_len)

    trainer = Trainer(model=model, args=targs, train_dataset=ds, processing_class=tok)
    trainer.train(resume_from_checkpoint=_maybe_resume(args.output_dir))
    trainer.save_model(os.path.join(args.output_dir, "latest-hf"))
    tok.save_pretrained(os.path.join(args.output_dir, "latest-hf"))


def _maybe_resume(output_dir):
    ckpts = glob.glob(os.path.join(output_dir, "checkpoint-*"))
    return True if ckpts else None


if __name__ == "__main__":
    main()
