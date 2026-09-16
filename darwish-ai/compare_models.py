# -*- coding: utf-8 -*-
"""compare_models.py — the v1 control against v2, on the four measures asked for,
plus the one that is the whole point: does harmony EXIST in the output.

לזכרו של לָאוֹר ז״ל.

THE COMPARISON IS ONLY HONEST IF THE UNITS ARE
-----------------------------------------------
Cross-entropy per token is NOT comparable between two alphabets. v2 spends ~3.3x
more tokens on the same second of music, so it is predicting more things, each
easier. A lower CE/token would prove nothing. Three quantities ARE comparable
and all three are reported:

    nats below the alphabet's OWN unigram entropy   (how much context is used)
    bits per SECOND of music                        (the real information rate)
    everything measured on the DECODED SCORE        (notes, not tokens)

The last one is the important one. Pitch-class entropy, melodic interval,
simultaneous-pitch count and vertical-interval content are all properties of
music, so they can be compared between two models, and against the CORPUS,
which is the only target that matters.

HARMONY IS NOT ASSERTED HERE, IT IS COUNTED
--------------------------------------------
`poly_max` and `poly_mean_sounding` say how many pitches sound together.
`vertical_interval_pct` says WHICH intervals they form. A model emitting random
simultaneous pitches would score well on the first and produce a flat histogram
on the second; a model that learned harmony puts its mass on 3, 4, 5, 7, 8, 9
semitones. Both are printed, for the model AND for the corpus, side by side.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "code-midi"))

import poly_tok as PT                                            # noqa: E402
import poly_sample as PS                                         # noqa: E402
import roundtrip as RT                                           # noqa: E402


def v1_score_from_tokens(toks, key_pc=0) -> PT.Score:
    """Decode a 108-token v1 stream into the same Score type, so both models
    are measured with one ruler. v1 has no octave and no duration, so every
    note is one sixteenth long in the same octave — that IS the finding."""
    return RT.v1_decode(toks, 143.55, key_pc)


def sample_v1(ckpt, n=3000, temp=1.1, seed=17, device="cpu"):
    import torch
    import midi_model as MM
    ck = torch.load(ckpt, map_location=device, weights_only=False)
    cfg = ck["config"]
    MM.VOCAB = cfg["vocab"]
    MM.TOK_BAR = cfg.get("bar_tok", 104)
    model = MM.DarwishMIDI(vocab=cfg["vocab"], n_layer=cfg["n_layer"], d=cfg["d"],
                           n_head=cfg["n_head"], mem_every=cfg["mem_every"]).to(device)
    model.load_state_dict(ck["model"])
    model.eval()
    g = torch.Generator(device="cpu").manual_seed(seed)
    toks = [106]                                    # v1 BOS
    ent, win = [], []
    with torch.no_grad():
        for _ in range(n):
            ctx = torch.tensor([toks[-2048:]], dtype=torch.long, device=device)
            logits, _, _ = model(ctx)
            p = torch.softmax(logits[0, -1].float() / temp, dim=-1)
            pe = p[p > 0]
            win.append(float(-(pe * pe.log2()).sum()))
            if len(win) >= 250:
                ent.append(round(float(np.mean(win)), 3)); win = []
            nxt = int(torch.multinomial(p.cpu(), 1, generator=g).item())
            if nxt == 107:                          # v1 EOS
                break
            toks.append(nxt)
    if win:
        ent.append(round(float(np.mean(win)), 3))
    return toks, ent, ck


def score_report(sc: PT.Score, toks, vocab) -> dict:
    prof = sc.polyphony_profile()
    vi = PS.vertical_intervals(sc)
    tot = sum(vi.values()) or 1
    counts = np.bincount(np.asarray(toks), minlength=vocab).astype(float)
    p = counts / counts.sum()
    p = p[p > 0]
    return {
        "n_tokens": len(toks),
        "distinct_tokens": len(set(toks)),
        "vocab": vocab,
        "token_entropy_bits": round(float(-(p * np.log2(p)).sum()), 4),
        "n_steps": sc.n_steps,
        "n_notes": len(sc.notes),
        "n_drums": len(sc.drums),
        "poly_max": prof["max"],
        "poly_mean_sounding": prof["mean_sounding"],
        "poly_frac_steps_2plus": prof["frac_steps_poly"],
        "pc_entropy_bits": round(RT.entropy_bits(RT.pc_hist(sc)), 4),
        "bass_interval": round(RT.mean_abs_interval_voice(sc, *RT.BASS_BAND), 3),
        "lead_interval": round(RT.mean_abs_interval_voice(sc, *RT.LEAD_BAND), 3),
        "vertical_interval_pct": {str(k): round(100.0 * v / tot, 2)
                                  for k, v in sorted(vi.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1-ckpt", required=True)
    ap.add_argument("--v2-ckpt", required=True)
    ap.add_argument("--v1-ref-ckpt", default=None,
                    help="the pre-existing 7400-step v1 checkpoint, as a reference point")
    ap.add_argument("--v1-result", default=None)
    ap.add_argument("--v2-result", default=None)
    ap.add_argument("--corpus-stats", default=None)
    # MATCHED MUSIC, NOT MATCHED TOKENS. v2 spends ~3.3x more tokens on the
    # same second of music, so generating the same NUMBER of tokens from both
    # would compare 32 bars of v2 against 105 bars of v1 -- and then call the
    # difference a property of the model. The budgets below are set from the
    # measured tokens-per-bar of each alphabet so both produce ~the same
    # amount of MUSIC.
    ap.add_argument("--n1", type=int, default=560, help="v1 tokens (~32 bars)")
    ap.add_argument("--n2", type=int, default=1800, help="v2 tokens (~32 bars)")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default=os.path.join(HERE, "model_compare.json"))
    a = ap.parse_args()

    rep = {"v1": [], "v2": []}
    for s in range(a.seeds):
        toks, ent, ck = sample_v1(a.v1_ckpt, a.n1, 1.1, 17 + s * 101, a.device)
        r = score_report(v1_score_from_tokens(toks), toks, 108)
        r.update({"seed": 17 + s * 101, "entropy_by_window": ent})
        rep["v1"].append(r)

        m, cfg, ck2 = PS.load(a.v2_ckpt, a.device)
        t2, e2 = PS.generate(m, n_tokens=a.n2, temperature=1.1, top_k=0,
                             seed=17 + s * 101, device=a.device, grammar=True)
        r2 = score_report(PT.decode(t2, 143.55, 0), t2, PT.VOCAB)
        r2.update({"seed": 17 + s * 101, "entropy_by_window": e2})
        rep["v2"].append(r2)

    def mean_of(rows, k):
        v = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        return round(float(np.mean(v)), 4) if v else None

    keys = ["n_tokens", "distinct_tokens", "token_entropy_bits", "n_steps",
            "n_notes", "n_drums", "poly_max", "poly_mean_sounding",
            "poly_frac_steps_2plus", "pc_entropy_bits", "bass_interval",
            "lead_interval"]
    rep["mean"] = {v: {k: mean_of(rep[v], k) for k in keys} for v in ("v1", "v2")}

    for v in ("v1", "v2"):
        agg = {}
        for r in rep[v]:
            for k, val in r["vertical_interval_pct"].items():
                agg[k] = agg.get(k, 0.0) + val / len(rep[v])
        rep["mean"][v]["vertical_interval_pct"] = {k: round(x, 2)
                                                   for k, x in sorted(agg.items(), key=lambda z: int(z[0]))}

    if a.v1_ref_ckpt and os.path.exists(a.v1_ref_ckpt):
        rep["v1_ref"] = []
        for s in range(a.seeds):
            toks, ent, ck = sample_v1(a.v1_ref_ckpt, a.n1, 1.1, 17 + s * 101, a.device)
            r = score_report(v1_score_from_tokens(toks), toks, 108)
            r.update({"seed": 17 + s * 101, "entropy_by_window": ent,
                      "train_step": ck.get("step"), "best_held": ck.get("best_held")})
            rep["v1_ref"].append(r)
        rep["mean"]["v1_ref"] = {k: mean_of(rep["v1_ref"], k) for k in keys}
        agg = {}
        for r in rep["v1_ref"]:
            for k, val in r["vertical_interval_pct"].items():
                agg[k] = agg.get(k, 0.0) + val / len(rep["v1_ref"])
        rep["mean"]["v1_ref"]["vertical_interval_pct"] = {
            k: round(x, 2) for k, x in sorted(agg.items(), key=lambda z: int(z[0]))}

    for tag, path in (("v1_train", a.v1_result), ("v2_train", a.v2_result)):
        if path and os.path.exists(path):
            rep[tag] = json.load(open(path, encoding="utf-8"))
    if a.corpus_stats and os.path.exists(a.corpus_stats):
        rep["corpus"] = json.load(open(a.corpus_stats, encoding="utf-8"))

    json.dump(rep, open(a.out, "w", encoding="utf-8"), indent=1)

    print(f"\n{'measure':32s} {'v1 (108)':>14s} {'v2 (138)':>14s} {'corpus':>14s}")
    print("-" * 78)
    has_ref = "v1_ref" in rep["mean"]
    cor = rep.get("corpus", {})
    pairs = [
        ("tokens generated", "n_tokens", None),
        ("distinct tokens used", "distinct_tokens", None),
        ("token entropy (bits)", "token_entropy_bits", None),
        ("steps of music", "n_steps", None),
        ("notes", "n_notes", None),
        ("MAX SIMULTANEOUS PITCHES", "poly_max", "poly_max_median"),
        ("mean simultaneous pitches", "poly_mean_sounding", "poly_mean"),
        ("frac steps with 2+ pitches", "poly_frac_steps_2plus", "poly_frac_2plus"),
        ("pitch-class entropy (bits)", "pc_entropy_bits", "pc_entropy_bits"),
        ("bass interval (semitones)", "bass_interval", "bass_interval"),
        ("lead interval (semitones)", "lead_interval", "lead_interval"),
    ]
    for label, k, ck_ in pairs:
        c = cor.get(ck_) if ck_ else None
        c = f"{c:.3f}" if isinstance(c, (int, float)) else "-"
        ref = str(rep["mean"]["v1_ref"][k]) if has_ref else "-"
        print(f"{label:32s} {str(rep['mean']['v1'][k]):>14s} "
              f"{str(rep['mean']['v2'][k]):>14s} {ref:>14s} {c:>14s}")

    for tag, label in (("v1_train", "v1 control"), ("v2_train", "v2")):
        t = rep.get(tag)
        if t:
            ce, uni, tps = t["best_heldout_ce"], t["unigram_nats"], t["tokens_per_second"]
            print(f"\n{label:12s} heldout CE {ce:.4f} nats  ppl {math.exp(ce):.3f}  "
                  f"unigram {uni:.4f}  below-unigram {uni-ce:.4f}  "
                  f"bits/s-of-music {ce/math.log(2)*tps:.2f}  params {t['n_params']:,}")

    print("\nVERTICAL INTERVALS (%% of simultaneous pairs, mod 12) — harmony, or noise?")
    print(f"{'semitones':>10s} " + " ".join(f"{i:>5d}" for i in range(12)))
    for v in (["v1", "v2"] + (["v1_ref"] if has_ref else [])):
        d = rep["mean"][v]["vertical_interval_pct"]
        print(f"{v:>10s} " + " ".join(f"{d.get(str(i), 0.0):5.1f}" for i in range(12)))
    if cor.get("vertical_interval_pct"):
        d = cor["vertical_interval_pct"]
        print(f"{'corpus':>10s} " + " ".join(f"{d.get(str(i), 0.0):5.1f}" for i in range(12)))
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
