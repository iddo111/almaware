# -*- coding: utf-8 -*-
"""poly_train.py — train the same 1.36M model on the v2 alphabet, as a control.

לזכרו של לָאוֹר ז״ל.

WHAT MAKES THIS A CONTROL RATHER THAN A DEMO
---------------------------------------------
Everything except the alphabet is held fixed against `ckpt-midi-small/best.pt`:

    n_layer 4, d 128, n_head 2, mem_every 2, seq 8192,
    micro_b 1, accum 8, lr 3e-4, and the SAME split.json --
    the same 271 train tracks and the same 30 heldout tracks, by name.

Only `vocab` (108 -> 138), the bar token (104 -> 1) and the token files
(`tokens-midi/` -> `tokens-poly/`) differ. So a difference in the numbers is
attributable to the representation and to nothing else.

THE ONE NUMBER THAT IS NOT COMPARABLE, AND WHAT REPLACES IT
------------------------------------------------------------
**Cross-entropy per token cannot be compared across two different alphabets.**
v2 spends ~5x more tokens on the same second of music, so it is predicting more,
easier things. A lower CE/token would prove nothing, and a higher one would
condemn nothing.

The comparable quantity is the INFORMATION RATE OF THE MUSIC:

    bits per second of music = (CE_nats / ln 2) * tokens_per_second

That asks the only fair question -- given one second of Darwish, how surprised
is the model? -- and it is what this trainer reports alongside raw CE. It also
reports CE against each alphabet's OWN unigram entropy, which measures how much
context the model is using and is likewise alphabet-independent.

POLITENESS, because the fleet is loaded
----------------------------------------
`--sleep` duty-cycles between steps and the process runs at nice 19. eran4's
GPU is at 96% with WINSTON's training and dmidi-life, and Iddo asked for those
to stay alive, so the default device here is CPU: a 1.36M model at seq 2048 is
a rounding error on 20 cores and touches nobody's GPU.
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
sys.path.insert(0, os.path.join(HERE, "code-midi"))

import midi_data as MD                                          # noqa: E402
import midi_model as MM                                         # noqa: E402


def configure(vocab: int, bar_tok: int, tokdir: str, cache_dir: str,
              bos: int | None = None, eos: int | None = None,
              phrase: int | None = None, tokens_per_bar: int | None = None):
    """Point the house data loader and model at one alphabet.

    midi_data.py validates every token stream against v1's ids -- BOS 106,
    EOS 107, vocab 108 -- and REFUSES a file that does not match. That is a good
    guard, not a bug: it is exactly what caught the first v2 run at cache-build
    time instead of letting a mislabelled corpus train silently. But it means
    every one of those constants has to be redirected, not just VOCAB.
    """
    MD.VOCAB = vocab
    MD.TOKDIR = tokdir
    MD.CACHE_DIR = cache_dir
    MD.TOK_BAR = bar_tok
    if bos is not None:
        MD.TOK_BOS = bos
    if eos is not None:
        MD.TOK_EOS = eos
    if phrase is not None:
        MD.TOK_PHRASE = phrase
    if tokens_per_bar is not None:
        MD.TOKENS_PER_BAR = tokens_per_bar
        MD.TOKENS_PER_PHRASE = 16 * tokens_per_bar + 1
    MM.VOCAB = vocab
    MM.TOK_BAR = bar_tok


def unigram_entropy_nats(corpus, split="train", cap=4_000_000) -> float:
    arr = corpus.data[split]["arr"]
    n = min(len(arr), cap)
    counts = np.bincount(np.asarray(arr[:n]), minlength=MD.VOCAB).astype(np.float64)
    p = counts / counts.sum()
    p = p[p > 0]
    return float(-(p * np.log(p)).sum())


def tokens_per_second(tokdir: str, split_path: str, split="train") -> float:
    """Measured from the token files themselves, not assumed."""
    names = json.load(open(split_path, encoding="utf-8"))[split]
    tot_tok = tot_sec = 0.0
    for n in names:
        p = os.path.join(tokdir, n)
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        tot_tok += d["n_tokens"]
        tot_sec += d["seconds"]
    return tot_tok / max(tot_sec, 1e-9)


@torch.no_grad()
def heldout_ce(model, corpus, b, windows, device) -> float:
    model.eval()
    tot, n = 0.0, 0
    for batch in corpus.heldout_batches(b=b, max_windows=windows, device=device):
        _, parts = MM.loss_fn(model, batch)
        tot += parts["ce"]
        n += 1
    model.train()
    return tot / max(n, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", type=int, required=True)
    ap.add_argument("--bar-tok", type=int, required=True)
    ap.add_argument("--bos-tok", type=int, default=None)
    ap.add_argument("--eos-tok", type=int, default=None)
    ap.add_argument("--phrase-tok", type=int, default=None)
    ap.add_argument("--tokens-per-bar", type=int, default=None)
    ap.add_argument("--tokdir", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--steps", type=int, default=7400)
    ap.add_argument("--seq", type=int, default=2048)
    ap.add_argument("--micro-b", type=int, default=1)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--n-layer", type=int, default=4)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--n-head", type=int, default=2)
    ap.add_argument("--mem-every", type=int, default=2)
    ap.add_argument("--eval-every", type=int, default=250)
    ap.add_argument("--eval-windows", type=int, default=24)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--split", default=os.path.join(HERE, "code-midi", "split.json"))
    ap.add_argument("--log", default=None)
    # --- instrumentation added 2026-09-06 for the LONGER-TRAINING run.
    # All three default to OFF, so omitting them reproduces the original
    # trainer exactly: no snapshot is written, no seed is set, and the
    # curve file is simply an incremental copy of what train.log already
    # prints. NONE of them touch the loss, the optimiser or the data order.
    ap.add_argument("--snap-every", type=int, default=0,
                    help="also save snap_XXXXXX.pt every N steps (0=off). "
                         "Needed because best.pt alone cannot show WHERE a "
                         "run stopped improving or started overfitting.")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed torch so the weight init is reproducible. "
                         "The original v2 run left this unseeded.")
    ap.add_argument("--curve", default=None,
                    help="write the eval history to this JSON after EVERY "
                         "eval (default <ckpt>/curve.json), so a long run "
                         "can be read while it is still running.")
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass
    torch.set_num_threads(a.threads)

    configure(a.vocab, a.bar_tok, a.tokdir, a.cache,
              a.bos_tok, a.eos_tok, a.phrase_tok, a.tokens_per_bar)
    os.makedirs(a.ckpt, exist_ok=True)
    logf = open(a.log or os.path.join(a.ckpt, "train.log"), "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    corpus = MD.MidiCorpus(seq_len=a.seq, sampling="token", seed=1337,
                           split_path=a.split, tokdir=a.tokdir,
                           cache_dir=a.cache, verbose=True)
    uni = unigram_entropy_nats(corpus)
    tps = tokens_per_second(a.tokdir, a.split)
    log(f"alphabet vocab={a.vocab} bar_tok={a.bar_tok} tokdir={a.tokdir}")
    log(f"unigram entropy {uni:.4f} nats = {uni/math.log(2):.4f} bits/token   "
        f"uniform ln(V) = {math.log(a.vocab):.4f}")
    log(f"measured tokens/second of music = {tps:.3f}")

    if a.seed is not None:
        torch.manual_seed(a.seed)
        np.random.seed(a.seed)
        log(f"torch/np seeded with {a.seed} (weight init reproducible)")
    device = torch.device(a.device)
    model = MM.DarwishMIDI(vocab=a.vocab, n_layer=a.n_layer, d=a.d,
                           n_head=a.n_head, mem_every=a.mem_every).to(device)
    n_par = model.n_params()
    log(f"params {n_par:,}  seq={a.seq} micro_b={a.micro_b} accum={a.accum} "
        f"lr={a.lr} device={a.device} threads={a.threads}")

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, betas=(0.9, 0.95),
                            weight_decay=0.01)
    hist = []
    best = float("inf")
    t0 = time.time()
    for step in range(1, a.steps + 1):
        opt.zero_grad(set_to_none=True)
        ce_acc = 0.0
        for _ in range(a.accum):
            batch = corpus.train_batch(a.micro_b, device=device)
            loss, parts = MM.loss_fn(model, batch)
            (loss / a.accum).backward()
            ce_acc += parts["ce"] / a.accum
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if a.sleep:
            time.sleep(a.sleep)

        if step % 50 == 0:
            log(f"step={step} ce={ce_acc:.4f} sec/50={time.time()-t0:.1f}")
            t0 = time.time()
        if step % a.eval_every == 0 or step == a.steps:
            h = heldout_ce(model, corpus, max(a.micro_b, 2), a.eval_windows, device)
            bits_s = (h / math.log(2)) * tps
            hist.append({"step": step, "train_ce": ce_acc, "heldout_ce": h,
                         "heldout_ppl": math.exp(h), "bits_per_second": bits_s,
                         "nats_below_unigram": uni - h})
            log(f"EVAL step={step} heldout_ce={h:.4f} ppl={math.exp(h):.3f} "
                f"bits/s_of_music={bits_s:.2f} below_unigram={uni-h:.4f}")
            payload = {"model": model.state_dict(), "step": step,
                       "best_held": min(best, h), "history": hist,
                       "config": {"vocab": a.vocab, "bar_tok": a.bar_tok,
                                  "n_layer": a.n_layer, "d": a.d,
                                  "n_head": a.n_head, "mem_every": a.mem_every,
                                  "seq": a.seq, "lr": a.lr,
                                  "unigram_nats": uni, "tokens_per_second": tps,
                                  "n_params": n_par}}
            if h < best:
                best = h
                payload["best_held"] = best
                torch.save(payload, os.path.join(a.ckpt, "best.pt"))
            if a.snap_every and step % a.snap_every == 0:
                # A snapshot is saved WHETHER OR NOT it improved. That is the
                # point: an overfitting run's later checkpoints are exactly the
                # ones best.pt throws away, and they are the evidence.
                torch.save(payload,
                           os.path.join(a.ckpt, f"snap_{step:06d}.pt"))
            json.dump({"steps_requested": a.steps, "unigram_nats": uni,
                       "tokens_per_second": tps, "vocab": a.vocab,
                       "n_params": n_par, "seed": a.seed,
                       "tokens_per_step": a.micro_b * a.accum * a.seq,
                       "history": hist},
                      open(a.curve or os.path.join(a.ckpt, "curve.json"), "w"),
                      indent=1)
    log(f"DONE best_heldout_ce={best:.4f} ppl={math.exp(best):.3f} "
        f"bits/s={best/math.log(2)*tps:.2f}")
    json.dump({"best_heldout_ce": best, "unigram_nats": uni,
               "tokens_per_second": tps, "vocab": a.vocab, "n_params": n_par,
               "history": hist},
              open(os.path.join(a.ckpt, "result.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
