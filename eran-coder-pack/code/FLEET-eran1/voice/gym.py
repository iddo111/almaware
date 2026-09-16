# -*- coding: utf-8 -*-
"""gym.py -- ERAN practises a sound with his own mouth, judged by his own ear.

THE LOOP, and it is the whole point: he aims at a state of his OWN cochlea, his
own tube renders it, his own cochlea judges what actually came out, and the gap
is the learning signal. No labels. No teacher. No backprop through air. It costs
nothing but CPU, so he can practise alone all night.

WHAT IS DIFFERENT FROM 2026-08-23, and each difference is deliberate:

  1. THE EAR. The first learning ran in eran2's 28-float `gist`, a space where
     the child's 62 prototypes do not live. This runs in the organism's OWN
     192-d frozen cochlea (body/ears.py, the one that scored 79.55% on the
     sealed heldout), via utterance_from_samples -- the door ears.py line 279
     was built for and that nothing had ever walked through.
  2. THE RESULT IS WRITTEN DOWN. organs/babble.py had no open(), no json.dump
     and no --out; the converged 34-number shape of the first learning event in
     this project's history existed only in RAM and died with the process. This
     writes the areas, the target, the f0, the seed, the step count, the full
     history and the wav, every run, before it exits. That never happens again.
  3. f0 IS FENCED, NOT SEARCHED. Measured: six climbs chose 125, 192, 235, 244,
     101 and 191 Hz with no convergence -- the level-free 8-slice ear does not
     constrain pitch at all, so a free f0 is a random number generator that
     happens to control how old ERAN sounds. It produced the frog once already.
  4. THERE IS A BLIND CONTROL. Same seed, same RNG stream, same perturbations --
     but it accepts every candidate instead of only the better ones. If guided
     does not beat blind, nothing was learned and this file must say so. A
     search without its control is a demo, not a result.

THE LEARNING RULE is one line and unchanged from the run that worked:
    take = (d < best)
isotropic Gaussian perturbation of all 34 areas at once, sigma fixed, clipped to
the physical fence [0.15, 4.0]. (1+1) hill climbing: one parent, one child, greedy.

SACRED AUDIO LAW: writes wavs, never plays them. The heldout is never opened --
Ears() is built with exam=False and body/ears.py refuses any 'heldout' path.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import earlink                                   # noqa: E402
import mouth34                                   # noqa: E402
from ears import write_wav                       # noqa: E402

OUT_DIR = os.path.expanduser("~/eran-voice-out")


def climb(ears, target, unit, steps=350, sigma=0.30, seed=0, f0=220.0,
          seconds=0.6, guided=True, free_terminations=False):
    """One (1+1) hill climb. Returns everything it learned, nothing thrown away."""
    rng = np.random.default_rng(seed)

    def render(areas, gr, lr):
        y = mouth34.say(areas, f0=f0, seconds=seconds, seed=0,
                        glottal_reflect=gr, lip_reflect=lr)
        if y is None:
            return None, float("inf")
        return y, earlink.distance(ears.utterance_from_samples(y), target)

    areas = np.clip(rng.uniform(0.4, 3.0, mouth34.N_SECTIONS),
                    mouth34.AREA_MIN, mouth34.AREA_MAX)
    gr, lr = mouth34.GLOTTAL_REFLECT, mouth34.LIP_REFLECT
    best_y, best = render(areas, gr, lr)
    start = best
    history = [best]
    accepted = 0
    refused = 0
    t0 = time.perf_counter()

    for _ in range(steps):
        cand = np.clip(areas + rng.normal(0, sigma, areas.size),
                       mouth34.AREA_MIN, mouth34.AREA_MAX)
        cgr, clr = gr, lr
        if free_terminations:
            # terminations are anatomy too, but they are bounded away from |1|
            cgr = float(np.clip(gr + rng.normal(0, 0.02), 0.50, 0.99))
            clr = float(np.clip(lr + rng.normal(0, 0.02), -0.99, -0.50))
        y, d = render(cand, cgr, clr)
        if y is None:
            refused += 1
            history.append(best)
            continue
        take = (d < best) if guided else True
        if take:
            areas, gr, lr, best, best_y = cand, cgr, clr, d, y
            accepted += 1
        history.append(best if guided else d)

    return {
        "unit": unit,
        "guided": bool(guided),
        "seed": int(seed),
        "steps": int(steps),
        "sigma": float(sigma),
        "f0_hz": float(f0),
        "seconds": float(seconds),
        "free_terminations": bool(free_terminations),
        "start": float(start),
        "final": float(best),
        "accepted": int(accepted),
        "refused_unstable": int(refused),
        "areas": [float(x) for x in areas],
        "glottal_reflect": float(gr),
        "lip_reflect": float(lr),
        "max_k_interior": mouth34.max_k_interior(areas),
        "history": [float(h) for h in history],
        "wall_s": round(time.perf_counter() - t0, 2),
    }, best_y


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unit", default="ah")
    ap.add_argument("--steps", type=int, default=350)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--sigma", type=float, default=0.30)
    ap.add_argument("--f0", type=float, default=220.0,
                    help="FENCED, never searched. A baby is 200-500 Hz.")
    ap.add_argument("--seconds", type=float, default=0.6)
    ap.add_argument("--free-terminations", action="store_true")
    ap.add_argument("--no-control", action="store_true",
                    help="skip the blind arm (you should not)")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--out-dir", default=OUT_DIR)
    a = ap.parse_args(argv)

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = os.path.expanduser(a.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    ears = earlink.open_ear()
    target, stats = earlink.target_for(ears, a.unit, a.corpus)
    print("EAR      frozen cochlea repr=%s dim=%d  (exam=%s)"
          % (ears.repr, ears.dim, ears.exam))
    print("TARGET   %s from %d real clips of Iddo  [%s]"
          % (a.unit, stats["n_clips"], stats["corpus"]))
    print("STANDARD a REAL clip sits %.4f from this centroid (best %.4f); "
          "within-class spread %.4f"
          % (stats["real_to_centroid_mean"], stats["real_to_centroid_min"],
             stats["within_class_spread"]))
    print("MOUTH    34 sections, f0 %.0f Hz FENCED, %.2f s, sigma %.2f, %d steps"
          % (a.f0, a.seconds, a.sigma, a.steps))
    print("")

    guided, blind = [], []
    best_overall, best_audio = None, None
    for s in range(a.seeds):
        r, y = climb(ears, target, a.unit, steps=a.steps, sigma=a.sigma, seed=s,
                     f0=a.f0, seconds=a.seconds, guided=True,
                     free_terminations=a.free_terminations)
        guided.append(r)
        print("  guided seed %d   %.4f -> %.4f   accepted %3d/%d   %.1fs"
              % (s, r["start"], r["final"], r["accepted"], r["steps"], r["wall_s"]))
        if best_overall is None or r["final"] < best_overall["final"]:
            best_overall, best_audio = r, y
        if not a.no_control:
            rb, _ = climb(ears, target, a.unit, steps=a.steps, sigma=a.sigma,
                          seed=s, f0=a.f0, seconds=a.seconds, guided=False,
                          free_terminations=a.free_terminations)
            blind.append(rb)
            print("  blind  seed %d   %.4f -> %.4f   (control: accepts everything)"
                  % (s, rb["start"], rb["final"]))

    gf = [r["final"] for r in guided]
    bf = [r["final"] for r in blind] if blind else []
    print("")
    print("GUIDED   mean %.4f   best %.4f" % (float(np.mean(gf)), float(min(gf))))
    if bf:
        print("BLIND    mean %.4f   best %.4f" % (float(np.mean(bf)), float(min(bf))))
        print("VERDICT  guided beats blind by %.4f (%.1f%%)"
              % (float(np.mean(bf) - np.mean(gf)),
                 100.0 * (np.mean(bf) - np.mean(gf)) / max(np.mean(bf), 1e-9)))
    print("REAL     an actual recording of Iddo saying %s: %.4f"
          % (a.unit, stats["real_to_centroid_mean"]))

    wav = os.path.join(out_dir, "gym-%s-%s.wav" % (a.unit, ts))
    write_wav(wav, best_audio)
    posture_dir = os.path.join(os.path.dirname(_HERE), "voice", "postures")
    if not os.path.isdir(posture_dir):
        posture_dir = os.path.join(_HERE, "postures")
    os.makedirs(posture_dir, exist_ok=True)
    posture = os.path.join(posture_dir, "%s-best.json" % a.unit)

    payload = {
        "what": ("ERAN's own vocal tract, searched by (1+1) hill climbing in "
                 "ERAN's own frozen 192-d cochlea, against real recordings of "
                 "Iddo. Not synthesis of a template, not TTS: these 34 numbers "
                 "are a tube shape his own search chose, and the wav is what "
                 "that tube does when air goes through it."),
        "utc": ts,
        "host": os.uname().nodename,
        "unit": a.unit,
        "ear": {"repr": ears.repr, "dim": ears.dim, "n_bands": ears.n_bands,
                "slices": len(ears.slices) and __import__("genome").EAR_SLICES,
                "exam": ears.exam},
        "target_stats": stats,
        "f0_hz_fenced": a.f0,
        "wav": wav,
        "best": best_overall,
        "guided": guided,
        "blind": blind,
        "summary": {
            "guided_mean": float(np.mean(gf)), "guided_best": float(min(gf)),
            "blind_mean": float(np.mean(bf)) if bf else None,
            "blind_best": float(min(bf)) if bf else None,
            "real_clip_to_centroid_mean": stats["real_to_centroid_mean"],
            "within_class_spread": stats["within_class_spread"],
        },
    }
    js = os.path.join(out_dir, "GYM-%s-%s.json" % (a.unit, ts))
    with open(js, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    with open(posture, "w", encoding="utf-8") as f:
        json.dump({"unit": a.unit, "utc": ts, "f0_hz": a.f0,
                   "areas": best_overall["areas"],
                   "glottal_reflect": best_overall["glottal_reflect"],
                   "lip_reflect": best_overall["lip_reflect"],
                   "distance": best_overall["final"]}, f, indent=1)

    print("")
    print("wav      %s" % wav)
    print("json     %s" % js)
    print("posture  %s" % posture)
    return 0


if __name__ == "__main__":
    sys.exit(main())
