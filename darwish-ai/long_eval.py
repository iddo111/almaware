# -*- coding: utf-8 -*-
"""long_eval.py - score a LIST of v2 checkpoints on the metrics that have teeth.

לזכרו של לָאוֹר ז״ל.

WHY THIS EXISTS SEPARATELY FROM THE TRAINER
--------------------------------------------
The trainer's in-loop eval uses 16 heldout windows out of 723, i.e. 2.2% of the
heldout music. That is fine for picking `best.pt` and for the SHAPE of a curve,
and it is what the original v2 run used, so it is kept identical. It is NOT a
number to report. This script re-scores every checkpoint on the FULL heldout
stream - all 723 non-overlapping windows, every heldout target token scored
exactly once - and that is the headline.

THE FOUR MEASURES, AND WHY THESE FOUR
--------------------------------------
1. BITS PER SECOND OF HELDOUT MUSIC = (CE_nats / ln2) * tokens_per_second.
   NOT cross-entropy per token. CE/token is not comparable across alphabets and
   was mistaken for a result twice on 2026-09-05.

2. VERTICAL-INTERVAL PEARSON against the heldout histogram. NOT cosine.
   The heldout histogram runs 3.5%..12.6% across the twelve interval classes,
   which is nearly flat, so a FLAT 12-bin histogram already scores cosine
   0.9355 against it. v2's celebrated "cosine 0.987" therefore sat barely above
   a histogram that knows nothing. Pearson's floor for that same flat histogram
   is 0.0. Both are printed, with both floors, so the cosine can be retired in
   the open rather than quietly.

3. EVENT DENSITY - drums and notes per 512 sixteenths - against the same
   heldout tracks. Joint v2 emitted 390 drums + 885 notes where heldout has
   ~538 + ~548: too few drums and far too many notes. This is audible in a way
   that CE is not.

4. ENTROPY SLOPE across generation. The v1 scar was mode collapse: bass entropy
   decayed [3.25 ... 0.99] during generation. A negative slope is a failure no
   matter what the other three numbers say.

Generation settings are pinned to split_gen.py's (512 sixteenths of music,
temperature 1.1, 5 seeds, same grammar, EOS suppressed and counted) so the
numbers land on the same ruler as the 2026-09-06 joint-v2 measurements.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import time
from collections import Counter

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "code-midi"))

import poly_tok as PT                                            # noqa: E402
import poly_sample as PS                                         # noqa: E402
import midi_data as MD                                           # noqa: E402
import midi_model as MM                                          # noqa: E402


# --------------------------------------------------------------- full heldout

def full_heldout_ce(model, corpus, device, batch=4):
    """Every heldout target token scored exactly once, no subsampling."""
    n_tok = int(corpus.data["heldout"]["arr"].shape[0])
    all_windows = (n_tok - 1) // corpus.seq_len
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for b in corpus.heldout_batches(b=batch, max_windows=all_windows,
                                        device=device):
            _, parts = MM.loss_fn(model, b)
            tot += parts["ce"]
            n += 1
    model.train()
    return tot / max(n, 1), all_windows


def fixed_train_ce(model, corpus, device, n_windows, batch=4):
    """CE on a FIXED, deterministic sample of TRAIN windows.

    THIS IS THE OVERFITTING DIAGNOSTIC, and it needs its own function because
    the trainer's `train_ce` cannot serve as one. That number is the loss of a
    SINGLE step's eight micro-batches, and `MidiCorpus` is constructed with a
    hard-coded seed=1337, so BOTH long runs see the identical batch order.
    Measured 2026-09-06: their train_ce oscillates in lockstep -- 1.697/1.703
    at step 5000, 1.820/1.821 at 5500, 1.707/1.712 at 6000. That is the DATA
    moving, not the models, and a gap built on it is noise.

    Here the same windows are scored for every checkpoint, evenly spaced over
    the whole train stream with no RNG, so heldout-minus-train is a real
    generalisation gap: it widens only when the model is memorising.
    """
    arr = corpus.data["train"]["arr"]
    n_tok = int(arr.shape[0])
    n = (n_tok - 1) // corpus.seq_len
    starts = np.arange(n, dtype=np.int64) * corpus.seq_len
    if n > n_windows:
        idx = np.unique(np.linspace(0, n - 1, n_windows).round().astype(int))
        starts = starts[idx]
    need = corpus.seq_len + 1
    model.eval()
    tot, k = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(starts), batch):
            chunk = starts[i:i + batch]
            w = np.stack([np.asarray(arr[s:s + need], dtype=np.int64)
                          for s in chunk])
            b = torch.from_numpy(w).to(device) if device else torch.from_numpy(w)
            _, parts = MM.loss_fn(model, b)
            tot += parts["ce"]
            k += 1
    model.train()
    return tot / max(k, 1), len(starts)


# ------------------------------------------------------------- generation

@torch.no_grad()
def generate_steps(model, n_steps, temperature=1.1, seed=17, ctx_cap=2048,
                   max_tokens=None, ent_window=128, device="cpu"):
    """Joint-alphabet generation to a fixed amount of MUSIC, not of tokens.

    Same grammar as split_gen.py: BOS illegal mid-stream, only a PITCH may
    follow a DUR, EOS suppressed until the step target is reached with the
    suppressed probability mass counted rather than guessed.
    """
    bos, eos, step_tok = PT.TOK_BOS, PT.TOK_EOS, PT.TOK_STEP
    dlo, dhi, plo, phi = PT.DUR_BASE, PT.VOCAB, PT.PITCH_BASE, PT.DUR_BASE
    g = torch.Generator(device="cpu").manual_seed(seed)
    toks = [bos]
    max_tokens = max_tokens or n_steps * 60
    steps = 0
    eos_suppressed = 0.0
    ent_series, win, ent_total = [], [], 0.0
    while steps < n_steps and len(toks) < max_tokens:
        ctx = torch.tensor([toks[-ctx_cap:]], dtype=torch.long, device=device)
        logits, _, _ = model(ctx)
        lg = logits[0, -1].float().cpu() / max(temperature, 1e-6)

        mask = torch.zeros_like(lg)
        mask[bos] = float("-inf")
        if dlo <= toks[-1] < dhi:
            m2 = torch.full_like(lg, float("-inf"))
            m2[plo:phi] = 0.0
            mask = mask + m2
        mask[eos] = float("-inf")
        p = torch.softmax(lg + mask, dim=-1)

        pe = p[p > 0]
        h = float(-(pe * pe.log2()).sum())
        ent_total += h
        win.append(h)
        if len(win) >= ent_window:
            ent_series.append(round(float(np.mean(win)), 3))
            win = []

        eos_suppressed += float(torch.softmax(lg, dim=-1)[eos])
        nxt = int(torch.multinomial(p, 1, generator=g).item())
        toks.append(nxt)
        if nxt == step_tok:
            steps += 1
    if win:
        ent_series.append(round(float(np.mean(win)), 3))
    toks.append(eos)

    slope = 0.0
    if len(ent_series) >= 3:
        x = np.arange(len(ent_series), dtype=float)
        slope = float(np.polyfit(x, np.asarray(ent_series, dtype=float), 1)[0])
    return {"tokens": toks, "steps": steps,
            "hit_token_cap": int(steps < n_steps),
            "eos_suppressed": round(eos_suppressed, 4),
            "entropy_series_bits": ent_series,
            "entropy_mean_bits_per_token": round(ent_total / max(len(toks) - 1, 1), 4),
            "entropy_slope_per_window": round(slope, 5)}


# -------------------------------------------------------------- reference

def _ent_bits(h):
    q = np.asarray(h, dtype=float)
    q = q / max(q.sum(), 1e-12)
    q = q[q > 0]
    return float(-(q * np.log2(q)).sum())


def heldout_reference(tokdir, split_path, per_steps=512):
    """Ground truth from the HELDOUT tracks only. The models saw train.

    Density is expressed per `per_steps` sixteenths so it is directly
    comparable to a generation run of that length.
    """
    names = json.load(open(split_path, encoding="utf-8"))["heldout"]
    vi = Counter()
    poly_mean, poly_max, frac = [], [], []
    pc = np.zeros(12)
    tot_notes = tot_drums = tot_steps = 0
    n = 0
    for nm in names:
        p = os.path.join(tokdir, nm)
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        sc = PT.decode(d["tokens"], bpm=d["bpm"], key_pc=d["key_pc"])
        vi += PS.vertical_intervals(sc)
        pr = sc.polyphony_profile()
        poly_mean.append(pr["mean_sounding"])
        poly_max.append(pr["max"])
        frac.append(pr["frac_steps_poly"])
        for note in sc.notes:
            pc[note.midi % 12] += 1
        tot_notes += len(sc.notes)
        tot_drums += len(sc.drums)
        tot_steps += sc.n_steps
        n += 1
    tot = sum(vi.values()) or 1
    scale = per_steps / max(tot_steps, 1)
    return {"n_tracks": n,
            "total_sixteenths": tot_steps,
            "poly_mean_sounding": round(float(np.mean(poly_mean)), 4),
            "poly_max_median": float(np.median(poly_max)),
            "poly_frac_steps_2plus": round(float(np.mean(frac)), 4),
            "vertical_interval_pct": {str(k): round(100.0 * vi[k] / tot, 3)
                                      for k in range(12)},
            "pc_entropy_bits": round(_ent_bits(pc), 4),
            "notes_per_%d_steps" % per_steps: round(tot_notes * scale, 1),
            "drums_per_%d_steps" % per_steps: round(tot_drums * scale, 1)}


def hist_vec(d):
    return np.array([float(d.get(str(k), 0.0)) for k in range(12)])


def cosine(a, b):
    return float(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))


def pearson(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpts", nargs="+", required=True,
                    help="checkpoint paths or globs, scored in sorted order")
    ap.add_argument("--tokdir", default=os.path.join(HERE, "tokens-poly"))
    ap.add_argument("--cache", default=os.path.join(HERE, "cache-v2"))
    ap.add_argument("--split", default=os.path.join(HERE, "code-midi", "split.json"))
    ap.add_argument("--seq", type=int, default=2048)
    ap.add_argument("--gen-steps", type=int, default=512, help="sixteenths")
    ap.add_argument("--gen-seeds", type=int, default=5)
    ap.add_argument("--temp", type=float, default=1.1)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--no-gen", action="store_true",
                    help="CE only; generation is the slow half")
    ap.add_argument("--out", default=os.path.join(HERE, "long_eval.json"))
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass
    torch.set_num_threads(a.threads)

    paths = []
    for pat in a.ckpts:
        hits = sorted(glob.glob(pat))
        paths.extend(hits if hits else [pat])
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        print("no checkpoints found")
        return 1

    # one alphabet for the whole script
    MD.VOCAB = MM.VOCAB = PT.VOCAB
    MD.TOKDIR, MD.CACHE_DIR = a.tokdir, a.cache
    MD.TOK_BAR = MM.TOK_BAR = PT.TOK_BAR
    MD.TOK_BOS, MD.TOK_EOS = PT.TOK_BOS, PT.TOK_EOS

    corpus = MD.MidiCorpus(seq_len=a.seq, sampling="token", seed=1337,
                           split_path=a.split, tokdir=a.tokdir,
                           cache_dir=a.cache, verbose=False)
    names = json.load(open(a.split, encoding="utf-8"))["train"]
    tt = ts = 0.0
    for nm in names:
        p = os.path.join(a.tokdir, nm)
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            tt += d["n_tokens"]
            ts += d["seconds"]
    tps = tt / max(ts, 1e-9)

    ref = heldout_reference(a.tokdir, a.split, a.gen_steps)
    ref_v = hist_vec(ref["vertical_interval_pct"])
    unif = np.full(12, 100.0 / 12.0)
    floor_cos = round(cosine(unif, ref_v), 4)
    floor_pear = round(pearson(unif, ref_v), 4)
    print("heldout: %d tracks, %d sixteenths, %.1f notes + %.1f drums per %d"
          % (ref["n_tracks"], ref["total_sixteenths"],
             ref["notes_per_%d_steps" % a.gen_steps],
             ref["drums_per_%d_steps" % a.gen_steps], a.gen_steps), flush=True)
    print("FLOOR (flat 12-bin histogram vs heldout): cosine=%.4f pearson=%.4f"
          "  <- read every cosine against this" % (floor_cos, floor_pear),
          flush=True)
    print("tokens/second of music = %.3f" % tps, flush=True)

    rows = []
    for path in paths:
        t0 = time.time()
        model, cfg, ck = PS.load(path, a.device)
        ce, nw = full_heldout_ce(model, corpus, a.device)
        tce, tw = fixed_train_ce(model, corpus, a.device, nw)
        row = {"ckpt": path, "step": ck.get("step"),
               "full_heldout_ce_nats": round(ce, 6),
               "full_heldout_windows": nw,
               "fixed_train_ce_nats": round(tce, 6),
               "fixed_train_windows": tw,
               # widens only when the model is memorising; flat means capacity
               "generalisation_gap_nats": round(ce - tce, 6),
               "bits_per_second_of_music": round(ce / math.log(2) * tps, 4),
               "heldout_ppl": round(math.exp(ce), 4)}
        if not a.no_gen:
            gens = []
            for s in range(a.gen_seeds):
                g = generate_steps(model, a.gen_steps, a.temp, 17 + s * 101,
                                   device=a.device)
                sc = PT.decode(g["tokens"], key_pc=0)
                m = PS.measure(sc, g["tokens"])
                v = hist_vec(m["vertical_interval_pct"])
                gens.append({
                    "seed": 17 + s * 101,
                    "n_notes": m["n_notes"], "n_drums": m["n_drums"],
                    "poly_mean_sounding": m["poly_mean_sounding"],
                    "poly_frac_steps_2plus": m["poly_frac_steps_2plus"],
                    "pc_entropy_bits": m["pc_entropy_bits"],
                    "mean_abs_melodic_interval": m["mean_abs_melodic_interval"],
                    "vi_pearson_vs_heldout": round(pearson(v, ref_v), 4),
                    "vi_cosine_vs_heldout": round(cosine(v, ref_v), 4),
                    "entropy_slope_per_window": g["entropy_slope_per_window"],
                    "entropy_mean_bits_per_token": g["entropy_mean_bits_per_token"],
                    "eos_suppressed": g["eos_suppressed"],
                    "hit_token_cap": g["hit_token_cap"],
                    "n_tokens": m["n_tokens"]})

            def ag(k):
                vals = [x[k] for x in gens if isinstance(x.get(k), (int, float))]
                return {"mean": round(float(np.mean(vals)), 4),
                        "sd": round(float(np.std(vals, ddof=1)) if len(vals) > 1
                                    else 0.0, 4)}
            row["gen"] = {k: ag(k) for k in
                          ("n_notes", "n_drums", "poly_mean_sounding",
                           "poly_frac_steps_2plus", "pc_entropy_bits",
                           "mean_abs_melodic_interval", "vi_pearson_vs_heldout",
                           "vi_cosine_vs_heldout", "entropy_slope_per_window",
                           "entropy_mean_bits_per_token", "eos_suppressed",
                           "hit_token_cap", "n_tokens")}
            row["gen_runs"] = gens
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        g = row.get("gen")
        print("%-42s step=%-6s bits/s=%8.4f gap=%+.4f  %s"
              % (os.path.basename(path), row["step"],
                 row["bits_per_second_of_music"],
                 row["generalisation_gap_nats"],
                 ("drums=%6.1f notes=%6.1f vi_pearson=%+.3f ent_slope=%+.4f"
                  % (g["n_drums"]["mean"], g["n_notes"]["mean"],
                     g["vi_pearson_vs_heldout"]["mean"],
                     g["entropy_slope_per_window"]["mean"])) if g else ""),
              flush=True)

    out = {"heldout_reference": ref,
           "floor_flat_histogram": {"vi_cosine": floor_cos,
                                    "vi_pearson": floor_pear},
           "tokens_per_second": tps, "seq": a.seq,
           "gen_steps_of_music": a.gen_steps, "gen_seeds": a.gen_seeds,
           "temperature": a.temp, "rows": rows}
    json.dump(out, open(a.out, "w"), indent=1)
    print("\nwrote " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
