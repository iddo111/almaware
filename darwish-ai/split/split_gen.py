# -*- coding: utf-8 -*-
"""split_gen.py - generate from the split pair and from joint v2, and MEASURE.

לזכרו של לָאוֹר ז״ל.

CE says how surprised a model is by Darwish. It does not say whether what the
model EMITS is music. These are the measures that do, all of them against the
HELDOUT tracks as ground truth (not the whole corpus - the models saw train):

    mean / max simultaneous pitches
    fraction of steps that are polyphonic
    vertical-interval histogram, cosine and Pearson against heldout
    pitch-class entropy, melodic interval
    GENERATION ENTROPY across the window, and its slope

The entropy slope is the old scar. v2's stayed flat at 3.6-3.9 bits/token, which
is what a healthy sampler looks like; v1's bass entropy DECAYED during
generation, [3.25 ... 0.99], which is mode collapse. A negative slope here is a
failure regardless of what CE says.

FAIR GENERATION - equal music, not equal tokens
------------------------------------------------
Every arm generates until it has emitted the same number of STEP tokens, i.e.
the same number of sixteenths of music. Comparing 3000 tokens of joint against
3000 tokens of pitch would compare 92 seconds against 132 seconds.

The three arms get the SAME grammar, so the comparison is not smuggling an
advantage: after a DUR only a PITCH may follow (a DUR is the length OF a note),
and BOS may never appear mid-stream. EOS is suppressed until the step target is
reached, and every suppression is COUNTED and reported - a model that keeps
trying to stop is telling you something.

THE SPLIT PAIR IS NOT CONDITIONED ON ITSELF. The rhythm model and the pitch
model are sampled independently and merged on the STEP clock. That is the whole
architecture under test: if the drums and the pitches only cohere because one
saw the other, the split would have bought nothing.
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "code-midi"))

import poly_tok as PT                                              # noqa: E402
import poly_sample as PS                                           # noqa: E402
import split_tok as ST                                             # noqa: E402


ALPH_GRAMMAR = {
    # alphabet -> (bos, eos, step, dur_lo, dur_hi, pitch_lo, pitch_hi)
    "joint":  (PT.TOK_BOS, PT.TOK_EOS, PT.TOK_STEP,
               PT.DUR_BASE, PT.VOCAB, PT.PITCH_BASE, PT.DUR_BASE),
    "pitch":  (ST.P_BOS, ST.P_EOS, ST.P_STEP,
               ST.P_DUR_BASE, ST.P_VOCAB, ST.P_PITCH_BASE, ST.P_DUR_BASE),
    "rhythm": (ST.R_BOS, ST.R_EOS, ST.R_STEP, -1, -1, -1, -1),
}


@torch.no_grad()
def generate_steps(model, alphabet, n_steps, temperature=1.1, seed=17,
                   ctx_cap=2048, max_tokens=None, ent_window=128):
    """Generate until n_steps STEP tokens have been emitted. Same grammar for
    every alphabet; every EOS suppression is counted."""
    bos, eos, step_tok, dlo, dhi, plo, phi = ALPH_GRAMMAR[alphabet]
    g = torch.Generator(device="cpu").manual_seed(seed)
    toks = [bos]
    max_tokens = max_tokens or n_steps * 60
    steps = 0
    eos_suppressed = 0
    ent_series, win, ent_total = [], [], 0.0
    while steps < n_steps and len(toks) < max_tokens:
        ctx = torch.tensor([toks[-ctx_cap:]], dtype=torch.long)
        logits, _, _ = model(ctx)
        lg = logits[0, -1].float() / max(temperature, 1e-6)

        mask = torch.zeros_like(lg)
        mask[bos] = float("-inf")                       # BOS is illegal mid-stream
        if dlo >= 0 and dlo <= toks[-1] < dhi:
            # a DUR sets a length; only the note it is the length OF may follow
            m2 = torch.full_like(lg, float("-inf"))
            m2[plo:phi] = 0.0
            mask = mask + m2
        mask[eos] = float("-inf")                       # length floor, counted below
        p = torch.softmax(lg + mask, dim=-1)

        pe = p[p > 0]
        h = float(-(pe * pe.log2()).sum())
        ent_total += h
        win.append(h)
        if len(win) >= ent_window:
            ent_series.append(round(float(np.mean(win)), 3))
            win = []

        # How much the model WANTED to stop, in probability mass, not a guess.
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
            "eos_suppressed": round(float(eos_suppressed), 4),
            "entropy_series_bits": ent_series,
            "entropy_mean_bits_per_token": round(ent_total / max(len(toks) - 1, 1), 4),
            "entropy_bits_per_musical_step": round(ent_total / max(steps, 1), 3),
            "entropy_slope_per_window": round(slope, 5)}


# ------------------------------------------------------------------ reference

def _ent_bits(h):
    q = np.asarray(h, dtype=float)
    q = q / max(q.sum(), 1e-12)
    q = q[q > 0]
    return float(-(q * np.log2(q)).sum())


def heldout_reference(tokdir, split_path):
    """The ground truth: the HELDOUT tracks only. The models saw train."""
    names = json.load(open(split_path, encoding="utf-8"))["heldout"]
    vi = Counter()
    poly_mean, poly_max, frac, n = [], [], [], 0
    pc = np.zeros(12)
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
        n += 1
    tot = sum(vi.values()) or 1
    return {"n_tracks": n,
            "poly_mean_sounding": round(float(np.mean(poly_mean)), 4),
            "poly_max_median": float(np.median(poly_max)),
            "poly_frac_steps_2plus": round(float(np.mean(frac)), 4),
            "vertical_interval_pct": {str(k): round(100.0 * vi[k] / tot, 3)
                                      for k in range(12)},
            "pc_entropy_bits": round(_ent_bits(pc), 4)}


def hist_vec(d):
    return np.array([float(d.get(str(k), 0.0)) for k in range(12)])


def cosine(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / max(na * nb, 1e-12))


def pearson(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--joint", required=True)
    ap.add_argument("--rhythm", required=True)
    ap.add_argument("--pitch", required=True)
    ap.add_argument("--steps", type=int, default=512, help="sixteenths of music")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--temp", type=float, default=1.1)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--tokdir", default=os.path.join(ROOT, "tokens-poly"))
    ap.add_argument("--split", default=os.path.join(ROOT, "code-midi", "split.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "split_gen.json"))
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass
    torch.set_num_threads(a.threads)

    ref = heldout_reference(a.tokdir, a.split)
    ref_v = hist_vec(ref["vertical_interval_pct"])
    # THE FLOOR THIS METRIC NEEDS. The corpus's vertical-interval histogram runs
    # only 4.6%..12.3% across the twelve classes, so it is close to flat, and a
    # FLAT histogram already scores a high cosine against it. Measured with
    # random-weight models on 2026-09-06: cosine 0.9556. So a cosine of 0.98
    # is not "the model learned harmony" - it is barely above the floor. Pearson
    # is the discriminating statistic here; cosine is reported only because the
    # earlier v2 report used it, and it is reported WITH this floor beside it.
    unif = np.full(12, 100.0 / 12.0)
    ref["floor_uniform_vi_cosine"] = round(cosine(unif, ref_v), 4)
    ref["floor_uniform_vi_pearson"] = round(pearson(unif, ref_v), 4)
    print("heldout reference: %d tracks poly_mean=%.3f frac2+=%.3f"
          % (ref["n_tracks"], ref["poly_mean_sounding"],
             ref["poly_frac_steps_2plus"]), flush=True)
    print("FLOOR for the interval metric - a FLAT histogram scores "
          "cosine=%.4f pearson=%.4f against heldout. Read every cosine below "
          "against that." % (ref["floor_uniform_vi_cosine"],
                             ref["floor_uniform_vi_pearson"]), flush=True)

    mj, cj, _ = PS.load(a.joint)
    mr, cr, _ = PS.load(a.rhythm)
    mp, cp, _ = PS.load(a.pitch)

    rows = {"joint": [], "split": []}
    for s in range(a.seeds):
        seed = 17 + s * 101
        gj = generate_steps(mj, "joint", a.steps, a.temp, seed)
        gr = generate_steps(mr, "rhythm", a.steps, a.temp, seed)
        gp = generate_steps(mp, "pitch", a.steps, a.temp, seed)
        merged = ST.merge_streams(gr["tokens"], gp["tokens"])
        rep = ST.merge_report(gr["tokens"], gp["tokens"])

        for name, toks, meta in (("joint", gj["tokens"],
                                  {k: v for k, v in gj.items() if k != "tokens"}),
                                 ("split", merged,
                                  {"rhythm": {k: v for k, v in gr.items() if k != "tokens"},
                                   "pitch": {k: v for k, v in gp.items() if k != "tokens"},
                                   "merge": rep,
                                   "eos_suppressed": gr["eos_suppressed"] + gp["eos_suppressed"],
                                   "hit_token_cap": max(gr["hit_token_cap"],
                                                        gp["hit_token_cap"]),
                                   "entropy_bits_per_musical_step": round(
                                       gr["entropy_bits_per_musical_step"]
                                       + gp["entropy_bits_per_musical_step"], 3),
                                   "entropy_slope_per_window": round(
                                       (gr["entropy_slope_per_window"]
                                        + gp["entropy_slope_per_window"]) / 2.0, 5)})):
            sc = PT.decode(toks, key_pc=0)
            m = PS.measure(sc, toks)
            m["seed"] = seed
            m.update(meta)
            v = hist_vec(m["vertical_interval_pct"])
            m["vi_cosine_vs_heldout"] = round(cosine(v, ref_v), 4)
            m["vi_pearson_vs_heldout"] = round(pearson(v, ref_v), 4)
            rows[name].append(m)
        print("seed=%d joint poly=%.2f cos=%.3f | split poly=%.2f cos=%.3f "
              "clock_disagree=%d"
              % (seed, rows["joint"][-1]["poly_mean_sounding"],
                 rows["joint"][-1]["vi_cosine_vs_heldout"],
                 rows["split"][-1]["poly_mean_sounding"],
                 rows["split"][-1]["vi_cosine_vs_heldout"],
                 rep["disagreements"]), flush=True)

    def agg(name, key):
        vals = [r[key] for r in rows[name] if isinstance(r.get(key), (int, float))]
        if not vals:
            return None
        return {"mean": round(float(np.mean(vals)), 4),
                "sd": round(float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0, 4),
                "n": len(vals)}

    keys = ["n_tokens", "n_steps", "hit_token_cap", "n_notes", "n_drums",
            "poly_mean_sounding",
            "poly_max", "poly_frac_steps_2plus", "onset_max_simultaneous",
            "pc_entropy_bits", "mean_abs_melodic_interval",
            "vi_cosine_vs_heldout", "vi_pearson_vs_heldout",
            "entropy_bits_per_musical_step", "entropy_slope_per_window",
            "eos_suppressed", "distinct_tokens"]
    summary = {n: {k: agg(n, k) for k in keys} for n in rows}
    out = {"heldout_reference": ref, "steps_of_music": a.steps,
           "temperature": a.temp, "n_seeds": a.seeds,
           "ckpts": {"joint": a.joint, "rhythm": a.rhythm, "pitch": a.pitch},
           "summary": summary, "runs": rows}
    json.dump(out, open(a.out, "w"), indent=1)

    print("\n%-34s %-22s %-22s %s" % ("measure", "joint v2", "split (r+p)", "heldout"))
    tgt = {"poly_mean_sounding": ref["poly_mean_sounding"],
           "poly_frac_steps_2plus": ref["poly_frac_steps_2plus"],
           "poly_max": ref["poly_max_median"],
           "pc_entropy_bits": ref["pc_entropy_bits"],
           "vi_cosine_vs_heldout": ref["floor_uniform_vi_cosine"],
           "vi_pearson_vs_heldout": ref["floor_uniform_vi_pearson"]}
    print("(last column = heldout truth, except the two vi_* rows where it is "
          "the FLAT-histogram FLOOR)")
    for k in keys:
        j, sp = summary["joint"][k], summary["split"][k]
        if j is None or sp is None:
            continue
        print("%-34s %8.4f +/-%-9.4f %8.4f +/-%-9.4f %s"
              % (k, j["mean"], j["sd"], sp["mean"], sp["sd"],
                 ("%.4f" % tgt[k]) if k in tgt else ""))
    print("\nwrote " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
