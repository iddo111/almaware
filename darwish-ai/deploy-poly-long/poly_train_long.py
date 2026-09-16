# -*- coding: utf-8 -*-
"""poly_train_long.py — CONTINUE the polyphonic model past step 30000, guarded.

לזכרו של לָאוֹר ז״ל. Iddo's ruling 2026-09-12 02:54: "דרוויש זוועה. איך ממשיכים -
בוא תן לו להתאמן, אחרי סוכות נבדוק" (Darwish sounds awful; let it train, check
after Sukkot). This file is what runs unattended for that month.

WHAT THIS ADDS OVER poly_train.py, AND WHY EACH PIECE EXISTS
--------------------------------------------------------------
poly_train.py is untouched and still the source of truth for the model, the
loss and the eval methodology (same DarwishMIDI, same loss_fn, same
heldout_ce). This file only adds what an unattended month needs and poly_train
never had to do because it ran once, watched, and stopped at a fixed step
count:

  1. RESUME.  poly_train.py always starts a fresh model at step 0. This script
     resumes from a checkpoint's WEIGHTS and its saved `step`, so systemd can
     kill and restart this process at any point (reboot, OOM, a `systemctl
     stop`) and it picks up training instead of re-learning from nothing. The
     optimizer's own state (AdamW moments) is NOT saved by poly_train.py's
     checkpoint format, so a resume restarts AdamW's moments at zero -- a
     small, honest discontinuity, not hidden: it is named in the log.

  2. MEMORY GUARD.  This fleet is carrying live resident models (Maverick
     400B llama-server + rpc-server shards) with single-digit GB of headroom
     on every box tonight. Before every step this reads /proc/meminfo
     MemAvailable and, if it is below --mem-guard-gb, PAUSES (sleeps, keeps
     re-checking) instead of stepping. It never kills anything and never
     raises its own priority; it just yields. Measured 2026-09-12: eran1
     ~3.4GB, eran3 ~3.4GB, eran4 ~1.9GB available -- all under a 15GB bar, so
     the very first thing this script does on this fleet, tonight, is wait.
     That is the correct, intended behaviour, not a bug: see the deliverable
     doc for why 15GB and what runs when the guard is open.

  3. PERIODIC RENDER.  Every --render-every steps (default = --eval-every)
     this draws ONE short sample from the model IN ITS CURRENT STATE (temp
     1.1, top_k off -- the exact sampling settings poly_sample.py's own
     scar-note prescribes) and writes it as a dated .mid + .json report to
     --render-dir/YYYYMMDD/. So after Sukkot there is a ROW of samples across
     the month, not one final guess, and each one's report includes the same
     scale-consistency numbers Iddo's ear ruling was measured in.

  4. THE SCALE METRIC, LOGGED NOT ENFORCED.  Iddo's verdict was "no scale".
     This file computes, on every rendered sample, the fraction of PITCH
     tokens whose key-relative degree (idx % 12) falls outside natural minor
     {0,2,3,5,7,8,10} and outside freygish/Phrygian-dominant {0,1,4,5,7,8,10}
     -- the same measurement claude-cli-SONNET-rescale made on tonight's
     Chai arrangement (41.7% / 35.6%). It is logged into curve.json next to
     heldout_ce every eval, so the after-Sukkot review has TWO numbers, not
     one: did it get less surprised, and did it get less chromatic. Nothing
     in the sampler is constrained by this number -- it is a thermometer,
     not a thermostat. See the deliverable doc for why a hard scale filter
     or a mode-conditioning token was NOT built tonight.

  5. CURRICULUM: split_curated.json, not split.json.  A title survey of all
     323 corpus files (2026-09-12) found the existing make_split.py name-filter
     (which already excludes Bassel Darwish/house, Yinon Darwish/vocal-pop and
     2 speech clips -- 22 files, documented in split.json's own
     excluded_reason) missed 33 more non-target files that the same broad
     "darwish" harvest pulled in under sports-commentary and podcast titles:
     squash and cricket match commentary, a business podcast, a political
     panel, a table-tennis clip, and a rap battle. Two of the 33 were sitting
     in the HELDOUT set itself. split_curated.json removes all 33 from TRAIN
     only; HELDOUT is left byte-identical to split.json on purpose, so
     heldout_ce here stays comparable to ckpt-poly-long-s1337/s2026's own
     history (1.7375 / 1.7182) even though 2 of those 30 heldout files are
     now known to be non-music. That wrinkle is named, not hidden.

WHAT THIS DELIBERATELY DOES NOT DO
------------------------------------
No mode/key-conditioning token was added to the vocabulary tonight. The
tokenizer already encodes pitch KEY-RELATIVE (poly_tok.py's `degree`), so a
mode signal would need a NEW token type inserted periodically through every
track (once at BOS is invisible to the sliding-window sampler, which starts
most windows mid-track) -- that means re-tokenizing all 323 files and
re-validating the 30000-step checkpoint against a changed alphabet. That is a
real architecture change, not a training-run setting, and it risks the
already-trained weights for an untested payoff. Left for after Sukkot, once
we know whether curation + longer training + more context move the number.

House style follows poly_train.py exactly for everything not listed above.
"""
from __future__ import annotations

import argparse
import datetime
import glob
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
import poly_tok as PT                                            # noqa: E402
import poly_sample as PS                                         # noqa: E402

VOCAB, BAR_TOK = 138, 1
NAT_MINOR = {0, 2, 3, 5, 7, 8, 10}
FREYGISH = {0, 1, 4, 5, 7, 8, 10}


def configure(tokdir: str, cache_dir: str, split_path: str):
    MD.VOCAB = VOCAB
    MD.TOKDIR = tokdir
    MD.CACHE_DIR = cache_dir
    MD.TOK_BAR = BAR_TOK
    MD.TOK_BOS = PT.TOK_BOS
    MD.TOK_EOS = PT.TOK_EOS
    MM.VOCAB = VOCAB
    MM.TOK_BAR = BAR_TOK


def mem_available_gb() -> float:
    """Linux MemAvailable, in GiB. These DGX boxes are unified-memory (Grace-
    Blackwell): there is no separate VRAM pool to check, so system RAM
    headroom IS the GPU headroom too."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / (1024 * 1024)
    except Exception:
        pass
    return float("inf")  # non-Linux / unreadable: never block


def wait_for_memory(min_gb: float, log) -> float:
    """Block until MemAvailable >= min_gb. Logs on entry and then only every
    ~10 minutes while waiting, so a long wait does not flood train.log."""
    avail = mem_available_gb()
    if avail >= min_gb or min_gb <= 0:
        return avail
    log(f"MEMGUARD pausing: {avail:.2f} GB available < {min_gb:.1f} GB guard "
        f"({datetime.datetime.now().isoformat(timespec='seconds')})")
    last_log = time.time()
    while avail < min_gb:
        time.sleep(30)
        avail = mem_available_gb()
        if time.time() - last_log > 600:
            log(f"MEMGUARD still waiting: {avail:.2f} GB available < "
                f"{min_gb:.1f} GB ({datetime.datetime.now().isoformat(timespec='seconds')})")
            last_log = time.time()
    log(f"MEMGUARD resuming: {avail:.2f} GB available >= {min_gb:.1f} GB")
    return avail


def scale_fractions(tokens) -> tuple[float, int]:
    """(fraction outside the BETTER-fitting of natural-minor/freygish, n_pitch)."""
    degs = [(t - PT.PITCH_BASE) % 12 for t in tokens
            if PT.PITCH_BASE <= t < PT.DUR_BASE]
    if not degs:
        return 0.0, 0
    n = len(degs)
    out_minor = sum(1 for g in degs if g not in NAT_MINOR) / n
    out_freyg = sum(1 for g in degs if g not in FREYGISH) / n
    return min(out_minor, out_freyg), n


def unigram_entropy_nats(corpus, split="train", cap=4_000_000) -> float:
    arr = corpus.data[split]["arr"]
    n = min(len(arr), cap)
    counts = np.bincount(np.asarray(arr[:n]), minlength=MD.VOCAB).astype(np.float64)
    p = counts / counts.sum()
    p = p[p > 0]
    return float(-(p * np.log(p)).sum())


def tokens_per_second(tokdir: str, split_path: str, split="train") -> float:
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


def render_sample(model, step, device, render_dir, n_tokens, seed):
    """Draw ONE short sample at the model's CURRENT weights. temp=1.1,
    top_k=0, grammar=True -- poly_sample.py's own scar-tested defaults."""
    was_training = model.training
    model.eval()
    toks, ent = PS.generate(model, n_tokens=n_tokens, temperature=1.1, top_k=0,
                            seed=seed, device=device, grammar=True,
                            min_tokens=n_tokens // 2)
    if was_training:
        model.train()
    day = datetime.datetime.now().strftime("%Y%m%d")
    outdir = os.path.join(render_dir, day)
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.join(outdir, f"step_{step:06d}")
    sc = PT.decode(toks, bpm=143.55, key_pc=0, source=f"train-long step {step}")
    PT.score_to_midi(sc, stem + ".mid")
    out_frac, n_pitch = scale_fractions(toks)
    rep = PS.measure(sc, toks)
    rep.update({"step": step, "n_pitch_events": n_pitch,
                "out_of_best_scale_frac": out_frac,
                "entropy_by_window_bits": ent})
    json.dump(rep, open(stem + ".json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return stem + ".mid", out_frac, n_pitch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokdir", default=os.path.join(HERE, "tokens-poly"))
    ap.add_argument("--cache", default=os.path.join(HERE, "code-midi", "cache-poly-curated"))
    ap.add_argument("--split", default=os.path.join(HERE, "code-midi", "split_curated.json"))
    ap.add_argument("--ckpt", required=True, help="output checkpoint dir (resumed from automatically if it already has best.pt)")
    ap.add_argument("--resume", default=None, help="seed checkpoint to load ONLY if --ckpt has no best.pt yet")
    ap.add_argument("--steps", type=int, default=500_000, help="cumulative step ceiling; systemd keeps this running long before it is hit")
    ap.add_argument("--seq", type=int, default=4096, help="context length in tokens (was 2048 for the s1337/s2026 runs)")
    ap.add_argument("--micro-b", type=int, default=1)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--n-layer", type=int, default=4)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--n-head", type=int, default=2)
    ap.add_argument("--mem-every", type=int, default=2)
    ap.add_argument("--eval-every", type=int, default=250)
    ap.add_argument("--eval-windows", type=int, default=24)
    ap.add_argument("--snap-every", type=int, default=2000)
    ap.add_argument("--device", default="cpu", help="cpu on purpose: the original s1337/s2026 runs used cuda, but this fleet is now carrying live resident GPU models this run must never touch")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--mem-guard-gb", type=float, default=15.0)
    ap.add_argument("--render-every", type=int, default=0, help="0 = same as --eval-every")
    ap.add_argument("--render-tokens", type=int, default=1500)
    ap.add_argument("--render-dir", default=os.path.join(HERE, "samples-long"))
    a = ap.parse_args()
    if a.render_every <= 0:
        a.render_every = a.eval_every

    try:
        os.nice(19)
    except Exception:
        pass
    torch.set_num_threads(a.threads)

    configure(a.tokdir, a.cache, a.split)
    os.makedirs(a.ckpt, exist_ok=True)
    os.makedirs(a.render_dir, exist_ok=True)
    logf = open(os.path.join(a.ckpt, "train.log"), "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log(f"=== poly_train_long start {datetime.datetime.now().isoformat(timespec='seconds')} "
        f"pid={os.getpid()} ===")

    corpus = MD.MidiCorpus(seq_len=a.seq, sampling="token", seed=1337,
                           split_path=a.split, tokdir=a.tokdir,
                           cache_dir=a.cache, verbose=True)
    uni = unigram_entropy_nats(corpus)
    tps = tokens_per_second(a.tokdir, a.split)
    log(f"alphabet vocab={VOCAB} bar_tok={BAR_TOK} tokdir={a.tokdir} split={a.split}")
    log(f"unigram entropy {uni:.4f} nats   measured tokens/second of music = {tps:.3f}")
    log(f"context: seq={a.seq} tokens = {a.seq/tps:.1f}s of music "
        f"(previous run: 2048 tokens = {2048/tps:.1f}s)")

    device = torch.device(a.device)
    model = MM.DarwishMIDI(vocab=VOCAB, n_layer=a.n_layer, d=a.d,
                           n_head=a.n_head, mem_every=a.mem_every).to(device)
    n_par = model.n_params()

    start_step = 0
    hist = []
    best = float("inf")
    best_path = os.path.join(a.ckpt, "best.pt")
    if os.path.exists(best_path):
        ck = torch.load(best_path, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        start_step = ck["step"]
        hist = ck.get("history", [])
        best = ck.get("best_held", float("inf"))
        log(f"RESUMED from {best_path} at step {start_step}, best_held={best:.4f}, "
            f"{len(hist)} history rows carried forward. AdamW moments restart at zero.")
    elif a.resume:
        ck = torch.load(a.resume, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        start_step = ck["step"]
        best = ck.get("best_held", float("inf"))
        log(f"SEEDED from {a.resume} at step {start_step}, best_held={best:.4f}. "
            f"Fresh history from here (seed history not carried, seed file untouched).")
    else:
        log("COLD START: no --ckpt/best.pt and no --resume given. New random weights.")

    log(f"params {n_par:,}  seq={a.seq} micro_b={a.micro_b} accum={a.accum} "
        f"lr={a.lr} device={a.device} threads={a.threads} mem_guard={a.mem_guard_gb}GB")

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, betas=(0.9, 0.95),
                            weight_decay=0.01)
    t0 = time.time()
    step = start_step
    while step < a.steps:
        step += 1
        wait_for_memory(a.mem_guard_gb, log)

        opt.zero_grad(set_to_none=True)
        ce_acc = 0.0
        for _ in range(a.accum):
            batch = corpus.train_batch(a.micro_b, device=device)
            loss, parts = MM.loss_fn(model, batch)
            (loss / a.accum).backward()
            ce_acc += parts["ce"] / a.accum
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % 50 == 0:
            log(f"step={step} ce={ce_acc:.4f} sec/50={time.time()-t0:.1f} "
                f"mem_avail={mem_available_gb():.1f}GB")
            t0 = time.time()

        if step % a.eval_every == 0 or step == a.steps:
            h = heldout_ce(model, corpus, max(a.micro_b, 2), a.eval_windows, device)
            bits_s = (h / math.log(2)) * tps
            row = {"step": step, "train_ce": ce_acc, "heldout_ce": h,
                   "heldout_ppl": math.exp(h), "bits_per_second": bits_s,
                   "nats_below_unigram": uni - h,
                   "wall_time": datetime.datetime.now().isoformat(timespec="seconds")}

            if step % a.render_every == 0:
                try:
                    mid_path, out_frac, n_pitch = render_sample(
                        model, step, device, a.render_dir, a.render_tokens,
                        seed=1000 + step)
                    row["sample_mid"] = mid_path
                    row["sample_out_of_scale_frac"] = out_frac
                    row["sample_n_pitch_events"] = n_pitch
                    log(f"RENDER step={step} -> {mid_path}  "
                        f"out_of_best_scale={out_frac*100:.1f}% over {n_pitch} pitch events")
                except Exception as e:
                    log(f"RENDER FAILED step={step}: {e!r}")

            hist.append(row)
            log(f"EVAL step={step} heldout_ce={h:.4f} ppl={math.exp(h):.3f} "
                f"bits/s_of_music={bits_s:.2f} below_unigram={uni-h:.4f}")

            payload = {"model": model.state_dict(), "step": step,
                       "best_held": min(best, h), "history": hist,
                       "config": {"vocab": VOCAB, "bar_tok": BAR_TOK,
                                  "n_layer": a.n_layer, "d": a.d,
                                  "n_head": a.n_head, "mem_every": a.mem_every,
                                  "seq": a.seq, "lr": a.lr,
                                  "unigram_nats": uni, "tokens_per_second": tps,
                                  "n_params": n_par, "split": a.split}}
            if h < best:
                best = h
                payload["best_held"] = best
            # ALWAYS save best.pt (not only on improvement): this is what a
            # systemd restart resumes from, so it must always reflect the
            # last completed eval, improved or not. A separate on-improvement
            # marker is unnecessary here because history[] already shows
            # exactly which step was the best.
            torch.save(payload, best_path)
            if a.snap_every and step % a.snap_every == 0:
                torch.save(payload, os.path.join(a.ckpt, f"snap_{step:06d}.pt"))
            json.dump({"steps_ceiling": a.steps, "unigram_nats": uni,
                       "tokens_per_second": tps, "vocab": VOCAB,
                       "n_params": n_par, "seq": a.seq,
                       "tokens_per_step": a.micro_b * a.accum * a.seq,
                       "history": hist},
                      open(os.path.join(a.ckpt, "curve.json"), "w"), indent=1)

    log(f"DONE at step ceiling {a.steps}, best_heldout_ce={best:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
