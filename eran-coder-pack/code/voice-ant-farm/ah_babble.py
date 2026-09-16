#!/usr/bin/env python3
"""RUNG 1 ONLY. Babble /a/ and nothing else, until she finds it herself.

לזכרה של עלמה ז״ל

Iddo, 2026-08-14, after listening to the undirected babble of `babble_bridge`:

    "so many fricatives, it sounds like Moroccan ... you need to train him on A,
     only on the matter of A, the mouth open, not all the fricatives in the
     middle, only open mouth A ... syllable by syllable."

He is right, and the reason is the curriculum in AH_CORONATION_LAW §2. The
general bridge babbles over NINE motors including `fric`, so half of every
babble is frication and 60% carries unvoiced hiss (measured on the 40-babble
listening file: fric somewhere 78%, unvoiced frication 60%). That is a fine
way to COVER an ear's 256 units, and a terrible way to learn one vowel. A baby
working on /a/ is not practising fricatives.

So this file narrows the exercise to rung 1 and nothing else:

  * the mouth is `mouth_v1`, which has SEVEN motors and no frication path at
    all. There is no `fric` knob to turn. The open-mouth constraint is
    structural, not a filter applied afterwards.
  * `mouth_v1` is also the only mouth that passes gate 4a — it reaches no
    recorded waveform — so whatever is found here is admissible under §3.
    (`mouth.py` inherits `import wave` from `head_sim` and cannot be.)
  * a babble is a HELD posture, not a glide. A vowel is a held tongue. The
    gliding gesture of `babble_bridge` is the right primitive for transitions
    and the wrong one for a sustained vowel.

WHAT IS AND IS NOT AIMED, stated before the results so it cannot be read as a
better result than it is:

  * stage 1 is UNDIRECTED. Postures are drawn uniformly over the whole motor
    box. Nothing points them at /a/. The count of babbles before the first
    pass is therefore a real measurement of how findable /a/ is in this mouth.
  * stage 2 wiggles around whatever stage 1 found best, scored by the judge's
    own gate-1 distance. This is the ONLY permitted direction of optimisation
    under Rule 6.4: the search moves the tongue, never the bar. No threshold in
    ah_criterion is touched, read, or overridden here.
  * the judge is `ah_criterion.judge_ah` unchanged, with the same four gates.
    Passing here makes a candidate ELIGIBLE and nothing more. Rule 6.1 stands:
    only Iddo's ear crowns.

    python3 ah_babble.py --rounds 3000 --refine 300
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mouth_v1 as MOUTH                                          # noqa: E402
import ah_criterion as JUDGE                                      # noqa: E402
from acoustic_units import write_wav_atomic                       # noqa: E402

MOTORS = MOUTH.MOTORS                    # seven. no fric. that is the point.
SECONDS = 0.35                           # long enough for the judge's 120 ms
                                         # window plus edges; short enough that
                                         # a babble costs 33 ms of CPU
PRODUCTION_MODULE = str(HERE / "mouth_v1.py")


def sample_posture(rng: np.random.Generator) -> dict:
    """One held posture, drawn over the WHOLE motor box. Nothing aims it.

    breath is floored at 0.35 because below that the folds barely drive the
    tube and the result is not a failed /a/ but silence — an uninformative
    babble, not a wrong one. Every other motor is uniform on [0,1].
    """
    m = {k: float(rng.uniform(0.0, 1.0)) for k in MOTORS}
    m["breath"] = float(rng.uniform(0.35, 1.0))
    return m


def say(posture: dict, seed: int) -> np.ndarray | None:
    """Hold the posture and listen to what the tube does with it."""
    y = MOUTH.articulate(seconds=SECONDS, seed=seed, **posture)
    y = np.asarray(y, dtype=np.float32).ravel()
    if not len(y) or float(np.max(np.abs(y))) < 1e-4:
        return None
    return y


def score(y: np.ndarray) -> tuple[float, object]:
    """Judge the sound. Lower is better.

    The scalar is gate 1's Mahalanobis distance to the /a/ centroid, with a
    flat penalty added for each of gates 2 and 3 that fails, so that a stable
    voiced non-/a/ is preferred to an unstable buzz that happens to land near
    the centroid for one frame. The penalty is a SEARCH heuristic only — it
    changes which posture the wiggle walks toward, and it changes no gate.
    """
    v = JUDGE.judge_ah(y, production_module=PRODUCTION_MODULE)
    md = v.measurements.get("mahalanobis")
    if md is None:
        return float("inf"), v
    s = float(md)
    if not _passed(v, "voicing"):
        s += 10.0
    if not _passed(v, "stability"):
        s += 10.0
    return s, v


def _passed(v, gate: str) -> bool:
    """gates are GateResult dataclasses, not dicts. Accept either."""
    g = v.gates[gate]
    return bool(g["passed"] if isinstance(g, dict) else g.passed)


def gates_of(v) -> dict:
    return {k: _passed(v, k) for k in v.gates}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=3000)
    ap.add_argument("--refine", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260814)
    ap.add_argument("--out", default="state/ah-babble")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    rng = np.random.default_rng(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    best_s, best_p, best_seed, best_v, best_y = float("inf"), None, None, None, None
    first_pass = None            # (round, posture, seed, verdict, audio)
    first_babble = None
    n_silent = 0
    n_pass = 0
    curve = []                   # best-so-far after each babble, for the plot
    milestones = {}              # round -> audio, for the listening file

    # ---- stage 1: undirected. no target, no gradient, no teacher. ----------
    for i in range(a.rounds):
        p = sample_posture(rng)
        y = say(p, seed=i)
        if y is None:
            n_silent += 1
            curve.append(round(best_s, 4) if np.isfinite(best_s) else None)
            continue
        if first_babble is None:
            first_babble = (i, p, y)
        s, v = score(y)
        if v.passed:
            n_pass += 1
            if first_pass is None:
                first_pass = (i, p, i, v, y)
        if s < best_s:
            best_s, best_p, best_seed, best_v, best_y = s, p, i, v, y
        curve.append(round(best_s, 4) if np.isfinite(best_s) else None)
        if i in (0, 9, 49, 199, 999):
            milestones[i] = y
        if a.verbose and (i + 1) % 200 == 0:
            print(f"  babble {i+1}/{a.rounds}  best score {best_s:.3f}  "
                  f"passes {n_pass}  silent {n_silent}", flush=True)

    stage1_best = best_s
    stage1_pass = n_pass

    # ---- stage 2: wiggle around the best. still no teacher, only her judge. -
    step = 0.15
    if best_p is not None:
        for k in range(a.refine):
            trial = {kk: float(np.clip(vv + rng.normal(0, step), 0.0, 1.0))
                     for kk, vv in best_p.items()}
            trial["breath"] = float(np.clip(trial["breath"], 0.35, 1.0))
            tseed = int(rng.integers(1 << 30))
            y = say(trial, seed=tseed)
            if y is None:
                continue
            s, v = score(y)
            if s < best_s:
                best_s, best_p, best_seed, best_v, best_y = s, trial, tseed, v, y
                if v.passed and first_pass is None:
                    first_pass = (a.rounds + k, trial, tseed, v, y)
            else:
                step *= 0.985
            if a.verbose and (k + 1) % 50 == 0:
                print(f"  refine {k+1}/{a.refine}  best {best_s:.3f}  step {step:.4f}",
                      flush=True)

    # ---- write what was found ---------------------------------------------
    gap = np.zeros(int(0.30 * MOUTH.RATE), dtype=np.float32)
    listen = []

    def _emit(name: str, y: np.ndarray) -> None:
        write_wav_atomic(out / name, np.asarray(y, dtype=np.float32), MOUTH.RATE)

    if first_babble is not None:
        _emit("01-first-babble.wav", first_babble[2])
        listen += [first_babble[2], gap]
    for r in sorted(milestones):
        listen += [milestones[r], gap]
    if first_pass is not None:
        _emit("02-first-PASS.wav", first_pass[4])
        listen += [first_pass[4], gap]
    if best_y is not None:
        _emit("03-best.wav", best_y)
        listen += [best_y, gap]
    if listen:
        _emit("04-ALL-in-order.wav", np.concatenate(listen))

    def _vd(v):
        if v is None:
            return None
        return {"passed": bool(v.passed), "gates": gates_of(v),
                "summary": v.summary() if callable(v.summary) else v.summary,
                "measurements": {k: (round(float(x), 4)
                                     if isinstance(x, (int, float)) else x)
                                 for k, x in v.measurements.items()
                                 if k != "static_violations"}}

    report = {
        "what": "rung 1 only - babble /a/ with mouth_v1, judged by ah_criterion",
        "mouth": "mouth_v1 (7 motors, NO frication path, gate-4a clean)",
        "seconds_per_babble": SECONDS,
        "rounds_undirected": a.rounds,
        "refine_steps": a.refine,
        "seed": a.seed,
        "silent_babbles": n_silent,
        "passes_in_undirected_stage": stage1_pass,
        "pass_rate_undirected": round(stage1_pass / max(1, a.rounds - n_silent), 5),
        "first_pass_at_babble": None if first_pass is None else first_pass[0],
        "best_score_after_stage1": (round(stage1_best, 4)
                                    if np.isfinite(stage1_best) else None),
        "best_score_final": round(best_s, 4) if np.isfinite(best_s) else None,
        "best_posture": None if best_p is None else {k: round(v, 4)
                                                     for k, v in best_p.items()},
        "best_seed": best_seed,
        "best_verdict": _vd(best_v),
        "first_pass_verdict": None if first_pass is None else _vd(first_pass[3]),
        "best_so_far_curve": curve,
        "claim_limit": (
            "stage 1 is undirected - postures are uniform over the motor box and "
            "nothing points them at /a/. stage 2 wiggles around the stage-1 best, "
            "scored by the judge's own gate-1 distance (Rule 6.4). no threshold in "
            "ah_criterion was touched. passing makes a candidate ELIGIBLE only - "
            "Rule 6.1, only Iddo's ear crowns."),
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("best_so_far_curve", "best_verdict",
                                   "first_pass_verdict")},
                     ensure_ascii=False, indent=2))
    if best_v is not None:
        print("BEST:", best_v.summary() if callable(best_v.summary) else best_v.summary)


if __name__ == "__main__":
    main()
