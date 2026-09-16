# -*- coding: utf-8 -*-
"""poly_sample.py — draw music out of the v2 model, and measure the harmony.

לזכרו של לָאוֹר ז״ל.

THE SAMPLING SCAR THIS FILE REFUSES TO REPEAT
----------------------------------------------
On 2026-09-05 the Darwish "mode collapse" was traced to the SAMPLER, not the
weights: `top_k=32` over a 108-token vocabulary strangled the distribution and
bass entropy decayed *during* generation, [3.25 ... 0.99]. With temperature 1.1
and top_k OFF, token entropy came back to 6.261 against the corpus's 6.243.

So: **top_k is off by default here, and it stays off.** The default is
temperature 1.1, which is the setting that was measured to work.

WHAT LANE MASKING IS AND WHY IT IS NOT top_k
---------------------------------------------
v2's vocabulary is lanes, and a lane is a contiguous slice. That makes one
legitimate constraint available that v1 could never have: a DUR token must be
followed by a PITCH token, because a duration with no note is meaningless. That
is a GRAMMAR rule about the encoding, not a probability cut across musical
content -- it can never delete a kick, which is exactly what top_k did. It is
applied only when --grammar is on, and the report says whether it was.

WHAT IS MEASURED ON THE OUTPUT, since the question is whether harmony EXISTS
----------------------------------------------------------------------------
  simultaneous-pitch count   max, and mean over sounding steps
  fraction of sounding steps carrying two or more pitches
  vertical interval histogram  -- WHICH intervals, not just how many notes
  pitch-class entropy, mean absolute melodic interval
  per-window token entropy, to catch entropy decaying during generation

A high polyphony count with a flat interval histogram would be noise wearing
harmony's clothes. Both numbers are printed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "code-midi"))

import poly_tok as PT                                           # noqa: E402


def load(ckpt_path, device="cpu"):
    import midi_model as MM
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    cfg = ck["config"]
    MM.VOCAB = cfg["vocab"]
    MM.TOK_BAR = cfg.get("bar_tok", PT.TOK_BAR)
    model = MM.DarwishMIDI(vocab=cfg["vocab"], n_layer=cfg["n_layer"],
                           d=cfg["d"], n_head=cfg["n_head"],
                           mem_every=cfg["mem_every"]).to(device)
    model.load_state_dict(ck["model"])
    model.eval()
    return model, cfg, ck


@torch.no_grad()
def generate(model, n_tokens=3000, temperature=1.1, top_k=0, seed=17,
             device="cpu", grammar=True, ctx_cap=2048, prompt=None,
             min_tokens=0):
    g = torch.Generator(device="cpu").manual_seed(seed)
    toks = list(prompt) if prompt else [PT.TOK_BOS]
    ent_windows = []
    win_ent = []
    for _ in range(n_tokens):
        ctx = torch.tensor([toks[-ctx_cap:]], dtype=torch.long, device=device)
        logits, _, _ = model(ctx)
        lg = logits[0, -1].float() / max(temperature, 1e-6)

        if grammar and toks and PT.DUR_BASE <= toks[-1] < PT.VOCAB:
            # a DUR sets a length; the only thing that can follow is the note
            # it is the length OF. Grammar, not a probability cut.
            mask = torch.full_like(lg, float("-inf"))
            mask[PT.PITCH_BASE:PT.DUR_BASE] = 0.0
            lg = lg + mask

        p = torch.softmax(lg, dim=-1)
        pe = p[p > 0]
        win_ent.append(float(-(pe * pe.log2()).sum()))
        if len(win_ent) >= 250:
            ent_windows.append(round(float(np.mean(win_ent)), 3))
            win_ent = []

        if top_k and top_k > 0:
            v, ix = torch.topk(p, min(top_k, p.numel()))
            nxt = int(ix[torch.multinomial(v, 1, generator=g).item()])
        else:
            nxt = int(torch.multinomial(p.cpu(), 1, generator=g).item())
        if nxt == PT.TOK_EOS:
            # An untrained or early checkpoint ends the piece almost immediately
            # (measured: EOS at token 77, n_steps 0). min_tokens is a LENGTH
            # floor for the booth, not a musical filter -- it suppresses only
            # EOS, never a pitch or a drum, and every measurement run in this
            # report was taken with min_tokens=0 so the model's own sense of
            # ending is what was measured.
            if len(toks) >= min_tokens:
                break
            continue
        toks.append(nxt)
    if win_ent:
        ent_windows.append(round(float(np.mean(win_ent)), 3))
    return toks, ent_windows


def vertical_intervals(score: PT.Score) -> Counter:
    """WHICH intervals sound together. The question is not only 'how many
    notes at once' -- noise can produce that -- but whether they are musical
    intervals: thirds, fourths, fifths, octaves."""
    by_step: dict[int, set] = {}
    for n in score.notes:
        for s in range(n.step, n.step + n.dur):
            by_step.setdefault(s, set()).add(n.midi)
    c = Counter()
    for s, ms in by_step.items():
        ms = sorted(ms)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                c[(ms[j] - ms[i]) % 12] += 1
    return c


def measure(score: PT.Score, toks) -> dict:
    import roundtrip as RT
    prof = score.polyphony_profile()
    vi = vertical_intervals(score)
    tot = sum(vi.values()) or 1
    lanes = Counter(PT.lane_of(t) for t in toks)
    used = len(set(toks))
    counts = np.bincount(np.asarray(toks), minlength=PT.VOCAB).astype(float)
    p = counts / counts.sum()
    p = p[p > 0]
    return {
        "n_tokens": len(toks),
        "distinct_tokens": used,
        "token_entropy_bits": round(float(-(p * np.log2(p)).sum()), 4),
        "n_notes": prof["n_notes"],
        "n_steps": score.n_steps,
        "poly_max": prof["max"],
        "poly_mean_sounding": prof["mean_sounding"],
        "poly_frac_steps_2plus": prof["frac_steps_poly"],
        "onset_max_simultaneous": prof["onset_max"],
        "pc_entropy_bits": round(RT.entropy_bits(RT.pc_hist(score)), 4),
        "mean_abs_melodic_interval": round(RT.mean_abs_interval(score), 3),
        "vertical_interval_pct": {str(k): round(100.0 * v / tot, 2)
                                  for k, v in sorted(vi.items())},
        "lane_counts": dict(lanes),
        "n_drums": len(score.drums),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--temp", type=float, default=1.1)
    ap.add_argument("--top-k", type=int, default=0)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--min-tokens", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--no-grammar", action="store_true")
    ap.add_argument("--bpm", type=float, default=143.55)
    ap.add_argument("--key-pc", type=int, default=0)
    ap.add_argument("--mid", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass

    model, cfg, _ = load(a.ckpt, a.device)
    toks, ent = generate(model, a.n, a.temp, a.top_k, a.seed, a.device,
                         grammar=not a.no_grammar, min_tokens=a.min_tokens)
    sc = PT.decode(toks, a.bpm, a.key_pc, source=a.ckpt)
    rep = measure(sc, toks)
    rep.update({"ckpt": a.ckpt, "temp": a.temp, "top_k": a.top_k,
                "grammar": not a.no_grammar, "seed": a.seed,
                "entropy_by_window_bits": ent, "vocab": cfg["vocab"]})
    if a.mid:
        PT.score_to_midi(sc, a.mid)
        rep["midi"] = a.mid
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if a.json:
        json.dump(rep, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
