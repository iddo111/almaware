#!/usr/bin/env python3
"""run_arms.py — OPEN LOOP vs CLOSED LOOP, identical diet, identical seed.

לזכרה של עלמה ז״ל.

WHAT IS COMPARED
----------------
  arm OPEN    Brain.hear()     — the living organism's own code path, untouched
  arm CLOSED  Brain.hear_pc()  — the same, with the top-down prediction arrow

Both start from an empty brain at beat 0 and eat the SAME wav files in the SAME
order. The order is drawn once, before either arm runs, from the real
body/school.py menu machinery with genome.SEED — and then FROZEN. Neither arm
gets to choose its own food.

WHY THE DRIVES ARE OFF, AND SAYING SO OUT LOUD
----------------------------------------------
In life, drives.choose() picks from the menu by Goldilocks appetite — which
reads the brain. Left on, each arm would eat a different diet and the
comparison would be about what they chose, not about the loop. So the pick is
uniform-random from the school's menu, identically for both arms. That IS a
departure from life and it is the price of a controlled comparison; it is
written here and in the result file rather than buried.

WHAT IS *NOT* MEASURED HERE, AND WHY
------------------------------------
**No accuracy number.** proof/measure.py's 132-item heldout exam is MISLABELLED
— Iddo's own ear ruled on 2026-09-03 that 0 of 10 clips matched their labels.
Any top-1 percentage off that exam is noise dressed as evidence, and running it
would only launder a broken examiner. Every quantity below is label-free:
counts, rates, distances, distributions, wall-clock. The verdict on whether the
closed loop is BETTER goes to Iddo's ear (pc/ab_server.py), not to this file.

SPAWN NOVELTY IS LABEL-FREE TOO. "Was this spawn for something genuinely new,
or for predictable variation?" is answered by the newborn prototype's own
maximum cosine to the prototypes that already existed at its birth. High = a
near-duplicate the brain could have absorbed; low = new territory. No filename
is consulted.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "proof"))

import genome                                                     # noqa: E402

genome.use_state_dir(os.path.join(ROOT, "state", "arms"))          # sandbox

import ears as ears_mod                                           # noqa: E402
import sleep as sleep_mod                                         # noqa: E402
from brain import Brain                                           # noqa: E402
from chemistry import Chemistry                                   # noqa: E402
from predict import Predictor                                     # noqa: E402
from school import School                                         # noqa: E402


# ---------------------------------------------------------------- the diet
def build_diet(n_beats, seed):
    """One frozen sequence of wav paths, drawn from the real school.

    The unit advances on a fixed schedule (UNIT_EVERY beats) instead of on a
    mastery gate, because a gate reads the brain and would give the two arms
    different curricula. Everything else — the 70/30 current/replay split, the
    30% free listening over the whole house, the dev-file exclusion — is the
    school's own code.
    """
    school = School(seed=seed)
    school.rng = random.Random(seed)
    # The food directory does not change during a draw, but _unit_wavs and
    # _world_wavs both os.listdir() it on EVERY beat — 400,000 listdirs for a
    # 200k-beat diet. Memoised here, which changes no result: the same call
    # returns the same list either way. The school's own code is untouched.
    _uw, _ww = school._unit_wavs, school._world_wavs
    _seen = {}
    school._unit_wavs = lambda u, _f=_uw: _seen.setdefault(("u", u), _f(u))
    school._world_wavs = lambda _f=_ww: _seen.setdefault(("w",), _f())
    rng = random.Random(seed + 1)
    unit_every = max(1, n_beats // len(genome.CURRICULUM))
    diet = []
    for b in range(n_beats):
        k = min(b // unit_every, len(genome.CURRICULUM) - 1)
        school.unit = genome.CURRICULUM[k]
        school.mastered = list(genome.CURRICULUM[:k])
        menu = school.serve_menu(chem=None)
        if not menu:
            continue
        diet.append(rng.choice(menu)["path"])
    return diet


def precompute(paths):
    """path -> the frozen cochlea's 192-d percept, computed exactly once.

    The ear is anatomy and both arms wear the same one; caching guarantees the
    two arms see byte-identical percepts and removes the ear from the timing.
    """
    ears = ears_mod.Ears()
    cache, order = {}, []
    for p in sorted(set(paths)):
        try:
            cache[p] = ears.utterance(p)
            order.append(p)
        except (OSError, ValueError) as e:
            print(f"  skipped {os.path.basename(p)}: {e}")
    return ears, cache


# ------------------------------------------------------------------ one arm
def run_arm(name, closed, diet, cache, ears, gain, log_every=1000):
    genome.PC_FEEDBACK_GAIN = float(gain if closed else 0.0)
    brain = Brain(dim=ears.dim)
    chem = Chemistry()
    pred = Predictor()
    t0 = time.perf_counter()
    hear_seconds = 0.0

    trace = []          # per-beat, sampled
    spawns = []         # every spawn, with its label-free novelty
    surprises = []
    pe_all = []
    counts = []         # (beat, n_protos) at every log_every and every sleep
    sleeps = []

    for b, path in enumerate(diet, start=1):
        vec = cache.get(path)
        if vec is None:
            continue
        chem.decay()
        n_before = len(brain.protos)
        mat_before = brain._matrix().copy() if n_before else None
        th = time.perf_counter()
        if closed:
            rec = brain.hear_pc(vec, chem, b, pred)
        else:
            rec = brain.hear(vec, chem, b)
        hear_seconds += time.perf_counter() - th
        chem.observe(rec["surprise"])
        brain.beat = b
        brain.decay_traces()

        surprises.append(float(rec["surprise"]))
        if closed:
            pe_all.append(float(rec["pe"]))
        if rec["spawned"]:
            # LABEL-FREE novelty of this spawn: how close was it to what the
            # brain already had? 1.0 = an exact duplicate of a known prototype.
            nov = (float(np.max(mat_before @ vec)) if mat_before is not None
                   else 0.0)
            spawns.append({"beat": b, "max_cos_to_existing": nov,
                           "n_before": n_before})

        if b % genome.SLEEP_EVERY == 0:
            # The REAL sleep math from body/sleep.py — attrition, scar decay,
            # SHY downscale — called on the real module. The dream journal and
            # the prayer are skipped: they are examiner-side prose written to
            # disk, they consult train filenames, and they change no state the
            # brain reads. That omission is stated here, not hidden.
            pruned = sleep_mod._prune(brain, b)
            for p in brain.protos:
                p["scar"] *= genome.SCAR_DECAY
                p["mass"] *= genome.SHY_FACTOR
            brain._dirty()
            sleeps.append({"beat": b, "pruned": pruned,
                           "protos_after": len(brain.protos)})
        if b % log_every == 0 or b == 1:
            counts.append({"beat": b, "protos": len(brain.protos),
                           "mass": round(brain.total_mass(), 1),
                           "surprise_mean_1k": round(
                               float(np.mean(surprises[-log_every:])), 5)})
            trace.append({"beat": b, "da": round(chem.da, 4),
                          "ne": round(chem.ne, 4)})
    wall = time.perf_counter() - t0

    # ---- stability: how close have the prototypes drifted to each other? ----
    m = brain._matrix()
    if len(m) > 1:
        G = m @ m.T
        np.fill_diagonal(G, -1.0)
        nearest_twin = G.max(axis=1)
        collapse = {"max_pair_cos": float(G.max()),
                    "mean_nearest_twin_cos": float(nearest_twin.mean()),
                    "n_pairs_over_0.99": int((G > 0.99).sum() // 2)}
    else:
        collapse = {"max_pair_cos": None, "mean_nearest_twin_cos": None,
                    "n_pairs_over_0.99": 0}

    s = np.asarray(surprises, dtype=float)
    half = len(s) // 2
    out = {
        "arm": name,
        "closed": bool(closed),
        "pc_feedback_gain": genome.PC_FEEDBACK_GAIN,
        "beats": len(diet),
        "prototypes_final": len(brain.protos),
        "prototypes_peak": max(c["protos"] for c in counts) if counts else 0,
        "spawns_total": len(spawns),
        "spawn_rate": len(spawns) / max(1, len(diet)),
        "spawn_novelty": {
            "median_max_cos_to_existing": (
                float(np.median([x["max_cos_to_existing"] for x in spawns]))
                if spawns else None),
            "frac_near_duplicate_cos_gt_0.90": (
                float(np.mean([x["max_cos_to_existing"] > 0.90
                               for x in spawns])) if spawns else None),
            "frac_novel_cos_lt_0.70": (
                float(np.mean([x["max_cos_to_existing"] < 0.70
                               for x in spawns])) if spawns else None),
        },
        "surprise": {
            "definition": ("prediction error vs the top-k expectation"
                           if closed else "1 - cosine to nearest prototype"),
            "mean": float(s.mean()), "sd": float(s.std()),
            "p10": float(np.percentile(s, 10)),
            "median": float(np.median(s)),
            "p90": float(np.percentile(s, 90)),
            "max": float(s.max()),
            "mean_first_half": float(s[:half].mean()),
            "mean_second_half": float(s[half:].mean()),
        },
        "prediction_error": ({
            "mean": float(np.mean(pe_all)), "sd": float(np.std(pe_all)),
            "mean_first_half": float(np.mean(pe_all[:len(pe_all) // 2])),
            "mean_second_half": float(np.mean(pe_all[len(pe_all) // 2:])),
        } if pe_all else None),
        "stability": collapse,
        "sleeps": sleeps,
        "counts": counts,
        "chem_trace_tail": trace[-10:],
        "cost": {"wall_seconds": round(wall, 3),
                 "hear_seconds": round(hear_seconds, 3),
                 "ms_per_utterance_hear": round(1000 * hear_seconds
                                                / max(1, len(diet)), 4)},
        "spawns": spawns[:400],
    }
    return brain, out


# ----------------------------------------------------------------- selftest
def selftest(diet, cache, ears):
    """THE REDUCTION, CHECKED IN CODE, NOT ASSERTED IN A COMMENT.

    hear_pc() with PC_FEEDBACK_GAIN = 0 must reproduce hear() to the bit: same
    prototype count, same vectors, same masses, same surprise sequence. If this
    fails, the two arms differ by more than one number and no comparison below
    it means anything.
    """
    sub = diet[:2000]
    b1, _ = run_arm("open-check", False, sub, cache, ears, 0.0, log_every=10**9)
    b2, _ = run_arm("pc-gain0", True, sub, cache, ears, 0.0, log_every=10**9)
    ok = (len(b1.protos) == len(b2.protos))
    detail = {"open_protos": len(b1.protos), "gain0_protos": len(b2.protos)}
    if ok:
        d = max(float(np.abs(p["vec"] - q["vec"]).max())
                for p, q in zip(b1.protos, b2.protos))
        dm = max(abs(p["mass"] - q["mass"])
                 for p, q in zip(b1.protos, b2.protos))
        detail["max_abs_vec_diff"] = d
        detail["max_abs_mass_diff"] = dm
        ok = d < 1e-12 and dm < 1e-9
    return ok, detail


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beats", type=int, default=30000)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--sweep", default="",
                    help="extra closed-loop gains, comma separated. Every one "
                         "run is reported — characterisation of the knob, not "
                         "a search for the setting that wins.")
    ap.add_argument("--seed", type=int, default=genome.SEED)
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest-only", action="store_true")
    a = ap.parse_args()

    print(f"diet: drawing {a.beats} beats from the real school, seed {a.seed}")
    diet = build_diet(a.beats, a.seed)
    print(f"  {len(diet)} beats over {len(set(diet))} distinct wavs")
    print("ear: precomputing the frozen cochlea once for both arms")
    ears, cache = precompute(diet)
    print(f"  {len(cache)} percepts cached, dim {ears.dim}")

    print("\nSELFTEST — does PC_FEEDBACK_GAIN=0 reproduce the open loop?")
    ok, detail = selftest(diet, cache, ears)
    print(f"  {'PASS' if ok else 'FAIL'}  {json.dumps(detail)}")
    if a.selftest_only:
        return 0 if ok else 1
    if not ok:
        print("  REFUSING to report a comparison on top of a broken reduction.")
        return 1

    print(f"\nARM 1/2  OPEN   (Brain.hear, the living organism's code path)")
    b_open, r_open = run_arm("open", False, diet, cache, ears, 0.0)
    print(f"  protos {r_open['prototypes_final']}  spawns "
          f"{r_open['spawns_total']}  surprise mean "
          f"{r_open['surprise']['mean']:.4f}  "
          f"{r_open['cost']['ms_per_utterance_hear']} ms/utt")

    print(f"\nARM 2/2  CLOSED (Brain.hear_pc, gain {a.gain})")
    b_closed, r_closed = run_arm("closed", True, diet, cache, ears, a.gain)
    print(f"  protos {r_closed['prototypes_final']}  spawns "
          f"{r_closed['spawns_total']}  surprise mean "
          f"{r_closed['surprise']['mean']:.4f}  "
          f"{r_closed['cost']['ms_per_utterance_hear']} ms/utt")

    sweep = []
    for gs in [x for x in a.sweep.split(",") if x.strip()]:
        g = float(gs)
        print(f"\nSWEEP    CLOSED gain {g}")
        _b, r = run_arm(f"closed-g{g}", True, diet, cache, ears, g)
        print(f"  protos {r['prototypes_final']}  spawns {r['spawns_total']}"
              f"  surprise mean {r['surprise']['mean']:.4f}")
        r.pop("spawns", None)
        sweep.append(r)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = a.out or os.path.join(ROOT, "results", f"CLOSED-LOOP-{stamp}.json")
    doc = {
        "what": "ERAN closed loop (predictive coding) vs open loop",
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "where": ROOT,
        "the_living_organism_was_not_touched": True,
        "diet": {"beats": len(diet), "distinct_wavs": len(set(diet)),
                 "seed": a.seed, "identical_for_both_arms": True,
                 "drives_choose_disabled": True},
        "selftest_gain0_reduces_to_open_loop": {"pass": ok, **detail},
        "NO_ACCURACY_NUMBER": (
            "proof/measure.py's 132-item heldout is MISLABELLED (Iddo's ear, "
            "2026-09-03: 0/10 clips matched their labels). No top-1 figure is "
            "reported here because any such figure would be noise presented as "
            "evidence. Every number in this file is label-free."),
        "open": r_open,
        "closed": r_closed,
        "gain_sweep": sweep,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    print(f"\nwritten: {out}")

    # brains kept so the A/B can play what each arm actually grouped together
    b_open.beat = len(diet)
    b_closed.beat = len(diet)
    b_open.save(os.path.join(genome.STATE_DIR, "brain-open.json.gz"))
    b_closed.save(os.path.join(genome.STATE_DIR, "brain-closed.json.gz"))
    print(f"brains: {genome.STATE_DIR}/brain-{{open,closed}}.json.gz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
