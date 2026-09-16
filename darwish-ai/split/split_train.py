# -*- coding: utf-8 -*-
"""split_train.py - train ONE model on ONE of the three alphabets.

לזכרו של לָאוֹר ז״ל.

joint  = v2 exactly as it is today, the CONTROL (vocab 138)
rhythm = drums + the shared STEP clock                (vocab 14)
pitch  = PITCH + DUR + the shared STEP clock          (vocab 129)

Everything except the alphabet is held fixed: n_layer 4, d 128, n_head 2,
mem_every 2, seq 2048, micro_b 1, accum 8, lr 3e-4, the SAME split.json, and an
explicit seed that controls BOTH the weight init and the data order (poly_train
seeded only the data order, so its single run has no error bar at all).

WHAT THIS TRAINER DOES DIFFERENTLY FROM poly_train.py, and why
---------------------------------------------------------------
1. It saves a checkpoint AT each requested step mark, not "the best so far".
   Best-so-far is early stopping, and early stopping at a different step in each
   arm silently unmatches the compute. A matched-compute claim needs the weights
   at step N, whatever they are.
2. It reports NOTHING comparative. Every number that will be shown to anyone is
   produced by split_eval.py, from checkpoints, through one code path used
   identically for all three alphabets. That is deliberate: the trap in this
   project on 2026-09-05 was comparing CE across two different alphabets and
   calling the smaller number a win. A trainer that prints a headline invites
   exactly that.

POLITENESS: nice 19, --threads default 4, CPU only. eran2's GPU is running
ComfyUI for another track and eran4's is at 96% with WINSTON. A 1.36M model at
seq 2048 does not need a GPU.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "code-midi"))

import midi_data as MD                                             # noqa: E402
import midi_model as MM                                            # noqa: E402
import split_tok as ST                                             # noqa: E402


def configure(alphabet: str, tokdir: str, cache_dir: str, tokens_per_bar: int):
    """Point the house loader and model at one alphabet.

    midi_data.py validates every stream against v1's ids and REFUSES anything
    else. That guard is why the first v2 run failed at cache-build time instead
    of training on a mislabelled corpus - so every constant is redirected here,
    not just VOCAB.
    """
    A = ST.ALPHABETS[alphabet]
    MD.VOCAB = A["vocab"]
    MD.TOKDIR = tokdir
    MD.CACHE_DIR = cache_dir
    MD.TOK_BAR, MD.TOK_PHRASE = A["bar"], A["phrase"]
    MD.TOK_BOS, MD.TOK_EOS = A["bos"], A["eos"]
    MD.TOKENS_PER_BAR = tokens_per_bar
    MD.TOKENS_PER_PHRASE = 16 * tokens_per_bar + 1
    MM.VOCAB = A["vocab"]
    MM.TOK_BAR = A["bar"]
    return A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alphabet", required=True, choices=("joint", "rhythm", "pitch"))
    ap.add_argument("--tokdir", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--marks", default="750,1500",
                    help="comma-separated step counts at which to save weights")
    ap.add_argument("--seq", type=int, default=2048)
    ap.add_argument("--micro-b", type=int, default=1)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--n-layer", type=int, default=4)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--n-head", type=int, default=2)
    ap.add_argument("--mem-every", type=int, default=2)
    ap.add_argument("--tokens-per-bar", type=int, default=17)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--split", default=os.path.join(ROOT, "code-midi", "split.json"))
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass
    torch.set_num_threads(a.threads)

    marks = sorted({int(x) for x in a.marks.split(",") if x.strip()})
    total = max(marks)

    A = configure(a.alphabet, a.tokdir, a.cache, a.tokens_per_bar)
    os.makedirs(a.ckpt, exist_ok=True)
    logf = open(os.path.join(a.ckpt, "train.log"), "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    # Seed BOTH the weights and the data order. poly_train.py fixed only the
    # latter, so its 2.0588 has no error bar and cannot be compared to anything.
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)

    corpus = MD.MidiCorpus(seq_len=a.seq, sampling="token", seed=a.seed,
                           split_path=a.split, tokdir=a.tokdir,
                           cache_dir=a.cache, verbose=True)
    n_train = int(corpus.data["train"]["arr"].shape[0])
    n_held = int(corpus.data["heldout"]["arr"].shape[0])
    tok_per_step = a.micro_b * a.accum * a.seq
    log("alphabet=%s vocab=%d seed=%d tokdir=%s" % (a.alphabet, A["vocab"], a.seed, a.tokdir))
    log("train tokens=%d heldout tokens=%d  dropped_dupes=%d"
        % (n_train, n_held, len(corpus.manifest.get("dropped_as_duplicate", []))))
    log("tokens/optimiser-step=%d  passes over train at %d steps = %.3f"
        % (tok_per_step, total, total * tok_per_step / max(n_train, 1)))

    model = MM.DarwishMIDI(vocab=A["vocab"], n_layer=a.n_layer, d=a.d,
                           n_head=a.n_head, mem_every=a.mem_every)
    n_par = model.n_params()
    log("params %d  seq=%d micro_b=%d accum=%d lr=%s threads=%d"
        % (n_par, a.seq, a.micro_b, a.accum, a.lr, a.threads))

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, betas=(0.9, 0.95),
                            weight_decay=0.01)
    hist = []
    t0 = time.time()
    wall0 = time.time()
    for step in range(1, total + 1):
        opt.zero_grad(set_to_none=True)
        ce_acc = 0.0
        for _ in range(a.accum):
            batch = corpus.train_batch(a.micro_b)
            loss, parts = MM.loss_fn(model, batch)
            (loss / a.accum).backward()
            ce_acc += parts["ce"] / a.accum
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step % 100 == 0:
            log("step=%d train_ce=%.4f sec/100=%.1f" % (step, ce_acc, time.time() - t0))
            t0 = time.time()
        hist.append({"step": step, "train_ce": ce_acc})
        if step in marks:
            path = os.path.join(a.ckpt, "step%d.pt" % step)
            torch.save({"model": model.state_dict(), "step": step,
                        "alphabet": a.alphabet, "seed": a.seed,
                        "config": {"vocab": A["vocab"], "bar_tok": A["bar"],
                                   "bos_tok": A["bos"], "eos_tok": A["eos"],
                                   "phrase_tok": A["phrase"],
                                   "n_layer": a.n_layer, "d": a.d,
                                   "n_head": a.n_head, "mem_every": a.mem_every,
                                   "seq": a.seq, "lr": a.lr, "n_params": n_par,
                                   "tokdir": a.tokdir, "micro_b": a.micro_b,
                                   "accum": a.accum},
                        "train_ce_last100": float(np.mean(
                            [h["train_ce"] for h in hist[-100:]]))},
                       path)
            log("SAVED %s (train_ce over last 100 = %.4f, wall %.0fs)"
                % (path, float(np.mean([h["train_ce"] for h in hist[-100:]])),
                   time.time() - wall0))
    json.dump({"alphabet": a.alphabet, "seed": a.seed, "marks": marks,
               "n_params": n_par, "n_train_tokens": n_train,
               "n_heldout_tokens": n_held, "seq": a.seq,
               "tokens_per_optimiser_step": tok_per_step,
               "wall_seconds": round(time.time() - wall0, 1),
               "train_ce": hist},
              open(os.path.join(a.ckpt, "trainlog.json"), "w"), indent=1)
    log("DONE %s seed=%d in %.0fs" % (a.alphabet, a.seed, time.time() - wall0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
