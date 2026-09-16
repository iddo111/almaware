"""babble.py — sensorimotor babbling. The organism becomes its own teacher.

    pick articulator settings -> hear the resulting sound through its OWN
    frozen cochlea -> compare the percept to a target percept -> keep
    whichever try got closer.

That is babbling: try, hear yourself, keep the better try. It is not
backprop and it never sees a gradient — it is a (1+lambda) evolution
strategy with a decaying mutation step, exactly the search shape asked for.

THE TARGET. This module never touches a filename or a class name. Its
target is always a plain vector — in practice a PROTOTYPE FROM THE
ORGANISM'S OWN BRAIN (state/brain.json.gz): something it has actually heard,
grown through living, never a hand-typed formant. voice/say.py resolves
"which prototype index is the thing called 'ah'" by asking the EXAMINER
(proof/say_judge.py, where labels live) — that resolution happens OUTSIDE
this file. babble() itself only ever sees target_vec, a numpy array.

THE EAR IS FROZEN. hear_posture() calls Ears.utterance_from_samples(), the
exact same code path frames()/pool() that a wav on disk would hit
(body/ears.py) — the child hears itself with its own ears, never a
different instrument. Never change ears.py to make this module's numbers
look better.

CHEMISTRY (optional). If a chemistry.Chemistry is passed: mutation step size
is scaled by chem.plasticity() (ACh * (1+DA) * (1+NE)) — the same knob the
brain's own Hebbian pull uses — and chem.observe(1 - best_sim) is called
every generation, exactly as eran_life.py's heartbeat does for every heard
utterance. Because DA is a smoothed *improvement* signal (chemistry.py:
DA = clip(DA_GAIN * (slow_surprise_ema - fast_surprise_ema), 0, DA_MAX)),
DA rises automatically while similarity is climbing and settles once it
plateaus — no separate reward hack was written for this.

Every generation is logged: {gen, best_sim, params, improved}.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, _HERE)

import genome                                     # noqa: E402
from ears import Ears                             # noqa: E402
import mouth                                       # noqa: E402

MOTORS = mouth.MOTORS       # ("breath","pitch","press","tongue_x","tongue_y","lips","jaw")
BREATH_FLOOR = 0.35          # below this the tube is silent — never search there


def random_posture(rng):
    """A newborn's first guess: every motor uniform in [0,1], breath kept
    above the silence floor so the very first try can be heard at all."""
    m = {k: float(rng.uniform(0.0, 1.0)) for k in MOTORS}
    m["breath"] = float(rng.uniform(BREATH_FLOOR, 1.0))
    return m


def _clip_posture(m):
    out = {k: float(np.clip(v, 0.0, 1.0)) for k, v in m.items()}
    out["breath"] = max(out["breath"], BREATH_FLOOR)
    return out


def hear_posture(ears, posture, seconds, seed):
    """Articulate -> percept, through the FROZEN ear. No file ever touches
    disk: mouth.articulate() returns an array, ears.utterance_from_samples()
    consumes it directly."""
    y = mouth.articulate(seconds=seconds, seed=seed, **posture)
    return ears.utterance_from_samples(y)


def babble(target_vec, ears, gens=400, lam=6, seconds=0.32, seed=0,
          chemistry=None, log_path=None, step0=0.35, step_min=0.02,
          rng_seed_stream=None):
    """(1+lambda) hill-climb toward target_vec (a plain vector — no labels).

    Returns (best_posture, best_sim, log) where log is a list of per-
    generation dicts, already written to log_path if given (one JSON line
    per generation, appended — so a long run can be tailed live).
    """
    target_vec = np.asarray(target_vec, dtype=np.float64)
    tn = np.linalg.norm(target_vec)
    if tn > 0:
        target_vec = target_vec / tn
    rng = np.random.default_rng(seed)

    def draw_seed():
        return int(rng.integers(1, 2 ** 31 - 1))

    best_posture = random_posture(rng)
    best_vec = hear_posture(ears, best_posture, seconds, draw_seed())
    best_sim = float(best_vec @ target_vec)

    log = []
    if log_path:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8") if log_path else None
    try:
        entry0 = {"gen": -1, "best_sim": round(best_sim, 5),
                  "params": {k: round(v, 4) for k, v in best_posture.items()},
                  "improved": True, "note": "initial random posture"}
        log.append(entry0)
        if log_fh:
            log_fh.write(json.dumps(entry0) + "\n")

        for gen in range(gens):
            if chemistry is not None:
                chemistry.decay()
            frac = gen / max(1, gens - 1)
            step = step0 * (1.0 - frac) + step_min * frac
            scale = step
            if chemistry is not None:
                scale *= float(np.clip(chemistry.plasticity(), 0.25, 4.0))

            improved = False
            for _ in range(lam):
                cand = _clip_posture({
                    k: best_posture[k] + rng.normal(0.0, scale) for k in MOTORS
                })
                vec = hear_posture(ears, cand, seconds, draw_seed())
                sim = float(vec @ target_vec)
                if sim > best_sim:
                    best_sim, best_posture = sim, cand
                    improved = True

            if chemistry is not None:
                chemistry.observe(max(0.0, 1.0 - best_sim))

            entry = {"gen": gen, "best_sim": round(best_sim, 5),
                     "params": {k: round(v, 4) for k, v in best_posture.items()},
                     "improved": improved, "step": round(step, 4)}
            if chemistry is not None:
                entry["chem"] = chemistry.snapshot()
            log.append(entry)
            if log_fh:
                log_fh.write(json.dumps(entry) + "\n")
    finally:
        if log_fh:
            log_fh.close()

    return best_posture, best_sim, log


def main(argv=None):
    """Direct, organism-facing entrypoint: --target-proto N is a plain
    integer index into a brain.json.gz — no label is ever resolved here.
    For 'give me the ah prototype' use voice/say.py, which asks the examiner."""
    ap = argparse.ArgumentParser(description="sensorimotor babbling toward a "
                                              "brain prototype (no labels)")
    ap.add_argument("--brain-file", default=None)
    ap.add_argument("--target-proto", type=int, required=True,
                    help="prototype index in the loaded brain — a plain "
                         "integer, never a class name")
    ap.add_argument("--gens", type=int, default=400)
    ap.add_argument("--lam", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=0.32)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--log", default=None)
    a = ap.parse_args(argv)

    from brain import Brain          # noqa: E402 (deferred: only main() needs it)

    ears = Ears()
    brain_path = a.brain_file or genome.BRAIN_FILE
    if not os.path.exists(brain_path):
        print(f"[babble] no brain at {brain_path} — nothing to imitate yet.")
        return 1
    brain = Brain.load(brain_path)
    if not (0 <= a.target_proto < len(brain.protos)):
        print(f"[babble] proto index {a.target_proto} out of range "
              f"(brain has {len(brain.protos)} prototypes)")
        return 1
    target_vec = brain.protos[a.target_proto]["vec"]

    seed = a.seed if a.seed is not None else genome.SEED
    log_path = a.log or os.path.join(genome.STATE_DIR, "babble.jsonl")
    t0 = time.time()
    posture, sim, log = babble(target_vec, ears, gens=a.gens, lam=a.lam,
                               seconds=a.seconds, seed=seed, log_path=log_path)
    dt = time.time() - t0
    print(f"[babble] proto#{a.target_proto}: sim {log[0]['best_sim']:.4f} -> "
          f"{sim:.4f} over {a.gens} generations ({dt:.1f}s)")
    print(f"[babble] posture: {posture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
