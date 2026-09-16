# -*- coding: utf-8 -*-
"""split_eval.py - the measurement. One code path for all three alphabets.

לזכרו של לָאוֹר ז״ל.

THE TRAP THIS FILE EXISTS TO AVOID
-----------------------------------
On 2026-09-05 v2 was declared a winner over v1 because its heldout CE was 2.059
against v1's 2.705. THAT COMPARISON WAS INVALID: v2's tokens are more numerous
and each carries less, so a lower CE per token proves nothing. Cross-alphabet CE
is not a quantity. Two things are:

  (A) TOTAL NATS TO DESCRIBE THE SAME MUSIC.
      split_tok.merge_streams is a bijection, so the rhythm stream plus the
      pitch stream describe EXACTLY the same Score as the joint stream. The
      total number of nats a model family spends on the heldout corpus is
      therefore directly comparable:

          joint  = nats(joint model on the joint stream)
          split  = nats(rhythm model) + nats(pitch model)

      Divided by the seconds of heldout music this is BITS PER SECOND OF MUSIC,
      and it is the headline. The split pays for the STEP/BAR/PHRASE clock
      TWICE - once in each stream - and that cost is included in full. Nothing
      is netted out.

  (B) PER-LANE CE ON THE SAME TARGET SYMBOLS.
      Every drum token of the heldout corpus appears once in the joint stream
      and once in the rhythm stream. -log p of that same symbol, under each
      model, averaged over the same count, is like-for-like. Same for the pitch
      and duration tokens against the pitch model.

FLOORS, printed beside every number because a number without its floor is
inadmissible here:
      uniform            ln(V)
      unigram            the marginal, FITTED ON TRAIN, scored on heldout
      lane-marginal      the within-lane marginal, fitted on train
      bigram             p(t | previous t), add-alpha, fitted on train
A model that does not clear the bigram floor has learned nothing worth the name.

SCORING PROTOCOL - strided, full coverage, zero RNG
----------------------------------------------------
Windows of seq_len with stride seq_len/2; only the second half of each window is
scored, so every target token except the first seq_len/2 gets at least
seq_len/2 tokens of context, and every target token in the heldout stream is
scored EXACTLY ONCE. A final end-aligned window mops up the tail, so coverage is
100.00% and not "about all of it". No sampling, no seeds, no variance.

CONTEXT-MATCHED VARIANT
-----------------------
At a fixed seq_len the three alphabets do not cover the same amount of MUSIC per
window - the rhythm stream is denser in music per token. --context-match rescales
each alphabet's eval window so all three see the same number of seconds of music,
which separates "the split helps because capacity is freed" from "the split helps
because the window reaches further". Both numbers are reported; neither is hidden.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "code-midi"))

import midi_data as MD                                             # noqa: E402
import midi_model as MM                                            # noqa: E402
import split_tok as ST                                             # noqa: E402


# ------------------------------------------------------------------ helpers

def lane_ids(alphabet: str):
    """[vocab] -> integer lane id, plus the name table."""
    lanes = ST.ALPHABETS[alphabet]["lanes"]
    names = sorted(lanes)
    out = np.zeros(ST.ALPHABETS[alphabet]["vocab"], dtype=np.int64)
    for k, name in enumerate(names):
        lo, hi = lanes[name]
        out[lo:hi] = k
    return out, names


def window_plan(n: int, seq: int):
    """(start, first_scored_offset) covering targets 1..n-1 exactly once."""
    stride = max(seq // 2, 1)
    starts = list(range(0, max(n - seq - 1, 0) + 1, stride))
    if not starts:
        raise ValueError("heldout stream shorter than one window")
    if starts[-1] != n - seq - 1 and n - seq - 1 > starts[-1]:
        starts.append(n - seq - 1)
    plan, covered = [], 0                    # covered = last scored abs target
    for s in starts:
        lo_abs = max(s + 1, covered + 1)
        hi_abs = s + seq
        if lo_abs > hi_abs:
            continue
        plan.append((s, lo_abs - (s + 1), hi_abs - (s + 1) + 1))
        covered = hi_abs
    return plan, covered


# ------------------------------------------------------------------ floors

def fit_floors(train_arr: np.ndarray, vocab: int, alpha: float = 0.1):
    n = int(train_arr.shape[0])
    a = np.asarray(train_arr, dtype=np.int64)
    uni = np.bincount(a, minlength=vocab).astype(np.float64) + alpha
    uni /= uni.sum()
    big = np.bincount(a[:-1] * vocab + a[1:],
                      minlength=vocab * vocab).astype(np.float64).reshape(vocab, vocab)
    big += alpha
    big /= big.sum(axis=1, keepdims=True)
    return {"unigram": uni, "bigram": big, "n_train": n}


def floor_scores(floors, lane_of, n_lanes, held, plan, vocab):
    """CE of the unigram / lane-marginal / bigram floors on the scored positions."""
    uni, big = floors["unigram"], floors["bigram"]
    log_uni, log_big = np.log(uni), np.log(big)
    # lane marginal: p(token | its own lane), from the train unigram
    lane_mass = np.zeros(n_lanes)
    for v in range(vocab):
        lane_mass[lane_of[v]] += uni[v]
    log_lane = np.log(uni / np.maximum(lane_mass[lane_of], 1e-300))

    tot = {"unigram": 0.0, "lane_marginal": 0.0, "bigram": 0.0}
    per_lane = {k: np.zeros(n_lanes) for k in tot}
    counts = np.zeros(n_lanes)
    n_scored = 0
    for s, off, end in plan:
        tgt = np.asarray(held[s + 1 + off: s + 1 + end], dtype=np.int64)
        prv = np.asarray(held[s + off: s + end], dtype=np.int64)
        lz = lane_of[tgt]
        n_scored += tgt.size
        counts += np.bincount(lz, minlength=n_lanes)
        for key, vals in (("unigram", log_uni[tgt]),
                          ("lane_marginal", log_lane[tgt]),
                          ("bigram", log_big[prv, tgt])):
            tot[key] += float(-vals.sum())
            per_lane[key] += np.bincount(lz, weights=-vals, minlength=n_lanes)
    return {"n_scored": n_scored,
            "counts": counts.tolist(),
            "total_nats": {k: tot[k] for k in tot},
            "ce": {k: tot[k] / max(n_scored, 1) for k in tot},
            "per_lane_nats": {k: per_lane[k].tolist() for k in per_lane}}


# ------------------------------------------------------------------ model

@torch.no_grad()
def score(ckpt_path, held, seq, plan, lane_of, n_lanes, threads=4, batch=2,
          lane_slices=None):
    """Total and per-lane nats, plus the LANE-RESTRICTED per-lane nats.

    Why the second one exists. The joint model must spend part of every drum
    prediction deciding "is the next token a drum at all, or a pitch"; the
    rhythm model never faces that question, because its stream contains no
    pitches. So a raw drum-lane CE comparison flatters the split for a reason
    that has nothing to do with drums. The lane-restricted number renormalises
    BOTH models over the target's own lane:

        -log( p(t) / sum_{u in lane(t)} p(u) )
          = -logit[t] + logsumexp(logits over that lane)

    and therefore asks only the question Iddo actually asked: GIVEN that a note
    sounds here, which note? Both numbers are reported. The raw one is what the
    stream costs; the restricted one is what the model knows about pitch.
    """
    torch.set_num_threads(threads)
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    cfg = ck["config"]
    MM.VOCAB = cfg["vocab"]
    MM.TOK_BAR = cfg["bar_tok"]
    model = MM.DarwishMIDI(vocab=cfg["vocab"], n_layer=cfg["n_layer"], d=cfg["d"],
                           n_head=cfg["n_head"], mem_every=cfg["mem_every"])
    model.load_state_dict(ck["model"])
    model.eval()

    tot = 0.0
    per_lane = np.zeros(n_lanes)
    per_lane_restricted = np.zeros(n_lanes)
    counts = np.zeros(n_lanes)
    n_scored = 0
    lane_bounds = None
    if lane_slices:
        names = sorted(lane_slices)
        lane_bounds = [lane_slices[k] for k in names]
    for i in range(0, len(plan), batch):
        chunk = plan[i:i + batch]
        w = np.stack([np.asarray(held[s: s + seq + 1], dtype=np.int64)
                      for s, _, _ in chunk])
        t = torch.from_numpy(w)
        inp, tgt = t[:, :-1], t[:, 1:]
        logits, _, _ = model(inp)
        lg = logits.float()
        nll = F.cross_entropy(lg.reshape(-1, cfg["vocab"]),
                              tgt.reshape(-1), reduction="none").view(tgt.shape)
        rest = None
        if lane_bounds is not None:
            lse_all = torch.logsumexp(lg, dim=-1)
            lse_lane = torch.stack(
                [torch.logsumexp(lg[..., lo:hi], dim=-1) for lo, hi in lane_bounds],
                dim=-1)
            z_t = torch.from_numpy(lane_of[tgt.numpy()])
            picked = lse_lane.gather(-1, z_t.unsqueeze(-1)).squeeze(-1)
            rest = nll - lse_all + picked
        for b, (s, off, end) in enumerate(chunk):
            v = nll[b, off:end].numpy().astype(np.float64)
            z = lane_of[tgt[b, off:end].numpy()]
            tot += float(v.sum())
            per_lane += np.bincount(z, weights=v, minlength=n_lanes)
            counts += np.bincount(z, minlength=n_lanes)
            n_scored += v.size
            if rest is not None:
                vr = rest[b, off:end].numpy().astype(np.float64)
                per_lane_restricted += np.bincount(z, weights=vr, minlength=n_lanes)
    return {"ckpt": os.path.basename(ckpt_path), "step": int(ck["step"]),
            "seed": int(ck.get("seed", -1)), "alphabet": ck.get("alphabet", "?"),
            "n_params": cfg.get("n_params"),
            "n_scored": n_scored, "total_nats": tot,
            "ce": tot / max(n_scored, 1),
            "per_lane_nats": per_lane.tolist(),
            "per_lane_nats_lane_restricted": per_lane_restricted.tolist(),
            "per_lane_counts": counts.tolist()}


# ------------------------------------------------------------------ main

def load_split_arrays(alphabet, tokdir, cache_dir, split_path, seq):
    A = ST.ALPHABETS[alphabet]
    MD.VOCAB = A["vocab"]
    MD.TOK_BAR, MD.TOK_PHRASE = A["bar"], A["phrase"]
    MD.TOK_BOS, MD.TOK_EOS = A["bos"], A["eos"]
    fp, manifest = MD.build_cache(split_path, tokdir, cache_dir, verbose=False)
    held = np.load(os.path.join(cache_dir, "%s.heldout.tokens.npy" % fp), mmap_mode="r")
    train = np.load(os.path.join(cache_dir, "%s.train.tokens.npy" % fp), mmap_mode="r")
    secs = sum(m["seconds"] for m in manifest["splits"]["heldout"]["tracks"])
    tracks = [m["file"] for m in manifest["splits"]["heldout"]["tracks"]]
    return held, train, secs, tracks, manifest, A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True,
                    help="JSON: {alphabet: {seed: {step: ckpt_path}}}")
    ap.add_argument("--tokdirs", required=True,
                    help="JSON: {alphabet: tokdir}")
    ap.add_argument("--caches", required=True, help="JSON: {alphabet: cache_dir}")
    ap.add_argument("--seq", type=int, default=2048)
    ap.add_argument("--context-match", action="store_true")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--split", default=os.path.join(ROOT, "code-midi", "split.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "split_eval.json"))
    ap.add_argument("--only-alphabet", default=None,
                    help="score only this alphabet's checkpoints (floors are still "
                         "computed for all three, so a partial file merges cleanly)")
    ap.add_argument("--only-seed", default=None)
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass

    runs = json.loads(a.runs)
    tokdirs = json.loads(a.tokdirs)
    caches = json.loads(a.caches)

    ctx = {}
    for alph in ("joint", "rhythm", "pitch"):
        held, train, secs, tracks, manifest, A = load_split_arrays(
            alph, tokdirs[alph], caches[alph], a.split, a.seq)
        lo, names = lane_ids(alph)
        ctx[alph] = {"held": held, "train": train, "seconds": secs,
                     "tracks": tracks, "lane_of": lo, "lane_names": names,
                     "vocab": A["vocab"], "n_held": int(held.shape[0]),
                     "n_train": int(train.shape[0])}

    # The three alphabets must describe the SAME heldout music, or nothing below
    # is comparable. Assert it rather than trust it.
    t0 = ctx["joint"]["tracks"]
    for alph in ("rhythm", "pitch"):
        if ctx[alph]["tracks"] != t0:
            raise SystemExit("heldout track lists differ between joint and %s: "
                             "%d vs %d tracks" % (alph, len(t0), len(ctx[alph]["tracks"])))
        if abs(ctx[alph]["seconds"] - ctx["joint"]["seconds"]) > 1.0:
            raise SystemExit("heldout seconds differ: %s" % alph)
    seconds = ctx["joint"]["seconds"]

    # window length per alphabet
    seqs = {k: a.seq for k in ctx}
    if a.context_match:
        tps = {k: ctx[k]["n_held"] / seconds for k in ctx}
        ref = max(tps.values())                    # densest alphabet keeps --seq
        for k in ctx:
            seqs[k] = max(256, int(round(a.seq * tps[k] / ref)))

    out = {"seconds_of_heldout_music": round(seconds, 1),
           "heldout_tracks": len(t0),
           "seq_len": seqs, "context_matched": bool(a.context_match),
           "heldout_tokens": {k: ctx[k]["n_held"] for k in ctx},
           "train_tokens": {k: ctx[k]["n_train"] for k in ctx},
           "lane_names": {k: ctx[k]["lane_names"] for k in ctx},
           "floors": {}, "models": {}}

    for alph in ctx:
        c = ctx[alph]
        plan, covered = window_plan(c["n_held"], seqs[alph])
        c["plan"] = plan
        out.setdefault("coverage", {})[alph] = {
            "scored_targets": covered, "of_possible": c["n_held"] - 1,
            "fraction": round(covered / max(c["n_held"] - 1, 1), 6),
            "n_windows": len(plan)}
        fl = fit_floors(c["train"], c["vocab"])
        fs = floor_scores(fl, c["lane_of"], len(c["lane_names"]),
                          c["held"], plan, c["vocab"])
        fs["uniform_ce"] = math.log(c["vocab"])
        out["floors"][alph] = fs
        print("floors %-7s uniform=%.4f unigram=%.4f lane_marg=%.4f bigram=%.4f "
              "(%d scored)" % (alph, fs["uniform_ce"], fs["ce"]["unigram"],
                               fs["ce"]["lane_marginal"], fs["ce"]["bigram"],
                               fs["n_scored"]), flush=True)

    for alph, by_seed in runs.items():
        if a.only_alphabet and alph != a.only_alphabet:
            continue
        c = ctx[alph]
        out["models"][alph] = {}
        for seed, by_step in by_seed.items():
            if a.only_seed and str(seed) != str(a.only_seed):
                continue
            out["models"][alph][seed] = {}
            for step, path in by_step.items():
                r = score(path, c["held"], seqs[alph], c["plan"],
                          c["lane_of"], len(c["lane_names"]), a.threads,
                          lane_slices=ST.ALPHABETS[alph]["lanes"])
                out["models"][alph][seed][step] = r
                print("%-7s seed=%s step=%-5s ce=%.4f total_nats=%.0f"
                      % (alph, seed, step, r["ce"], r["total_nats"]), flush=True)

    json.dump(out, open(a.out, "w"), indent=1)
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
