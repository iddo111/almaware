"""MURPHY — a small beit din, written in ALMA, whose whole job is catching a lie a
measurement tells about itself.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"מודל מרפי על שם אתה יודע מי... בית דין קטן וחכם שמוצא באגים ובעיות"*,
then *"הייתי עושה אותו מודל קטן וחכם בשפת עלמה ברמה הכי גבוהה שיש"*, *"ולאמן אותו - לא
שווה כלום בלי אימון חזק"*, and *"וגם שידע ללמוד לבד — שניהם."*

Then, the same night: *"תחבר את מרפי לכל סקריפט אימון בפרויקט - שאף ריצה לא תדווח בלי
פסק שלו. ותוסיף לו עד לזה ששפט את עצמו."*

## What Murphy reads, and why it is not source code

Murphy does not read code. **He reads the trace a run leaves behind** — the losses, the
metric, the floor it was measured against, and now also WHO DID THE JUDGING — and rules
on one question:

    is this number evidence, or is the experiment fooling itself?

That is the right target because it is what actually went wrong all day on 2026-08-30,
four times, and every one of the four was visible in the numbers alone:

  * an encoder whose loss hit 0.0007 by step 250 while its metric sat at chance
  * a hinge term pinned at 0.18 for 9,000 steps — a constraint that could never be met
  * a metric of 5.8% where the RAW INPUT scores 66.9% — worse than no model at all
  * a hand scoring 86% while drawing dot-clouds no person would call a letter

None of those needed cleverness. Each needed **a floor the claim could fall through**.

## The two witnesses added on Iddo's instruction, and what they cost

The fourth failure above is the one the first seven witnesses could only catch by
accident. They caught it because that run happened to have no holdout — a bookkeeping
tell, not the actual fault. **The actual fault was that the hand was optimising the eye's
opinion, the eye's opinion was then reported as the score, and no person ever looked at
the sheet.** Two things, so two witnesses:

  * `circularity` — the judge of the metric was inside the loop that was trained, and
    nothing outside that loop agreed.
  * `unlooked`    — the run MADE something, and nobody ever looked at what it made.

**Neither is answerable from the numbers.** No amount of staring at losses and accuracies
reveals who held the ruler. So the trace had to grow four fields, and this is stated
plainly rather than hidden: `judge_in_loop`, `artifact`, `looked_at`, `independent`.
Murphy cannot ask a question the trace refuses to answer, and `watch()` therefore prints
which questions went unanswered — an under-declared run is visibly under-declared.

Looking DISCHARGES circularity, and that is not a softening: a person's eyes are the
cheapest judge that is not the model. It is the whole difference between the two Winston
runs of that day — 86.4% in dot-clouds nobody had seen, and cos 0.445 in real lines on a
sheet that had been opened and looked at.

## Why he is a weave and not a function

He is written in ALMA because the shape of the job is the shape of the language. Each
suspicion is a KNOT that stays silent until the evidence crosses its own line (`rise`);
the STRANDS carry how much each suspicion counts; a `pool` gathers them; a `fringe`
speaks the verdict. By ALMA's third law the layout IS the program — so Murphy's opinion
is legible as a diagram, not buried in an if-tree.

## Trained twice, because Iddo asked for both

  * **STRONG** — his weights are fitted against thousands of generated runs whose truth
    is known by construction, by perturbation search. No gradient, and none is needed.
  * **BY HIMSELF** — ALMA's own `drift` is left on afterwards: a cord that helped a
    verdict land thickens, a cord that spoke into silence thins. Local, forward-only,
    already in the language. Nothing was imported to get it.

**Training may not cost him a real catch.** `--train` re-runs `real_traps.py` with the
fitted weights and REFUSES TO SAVE them if they miss one of the real runs. A lesson
learned on generated data that loses a real failure is not a lesson.

## The acceptance test he must pass

`real_traps.py` holds the real failures of 2026-08-30 and the sound runs from the same
day. **A Murphy that cannot catch those is decoration**, and the file says so out loud
rather than reporting an average that hides it.

    python murphy.py --train 4000
    python real_traps.py

## Using him from a training script — one import, one line

    from murphy import watch
    watch({"chance": ..., "baseline": ..., "held_out": True,
           "judge_in_loop": False, "artifact": None, "looked_at": False,
           "claimed_success": True, "steps": [{"step": s, "metric": m, "terms": {...}}]},
          name="the eye, invariance")
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "alma-language"))

from alma.loom import Loom, Strand, Weave                       # noqa: E402

# The nine suspicions. Each is a question a careful colleague asks about a result. The
# first seven are answerable from the numbers alone; the last two are not, and needed
# the trace to grow — see the module docstring, this is said out loud on purpose.
SUSPICIONS = (
    ("collapse",     "the loss fell to nothing almost immediately"),
    ("flat",         "the metric never moved"),
    ("at_chance",    "the metric is where guessing would put it"),
    ("below_floor",  "the raw input scores HIGHER than the model"),
    ("frozen_term",  "a loss term never changed — a constraint that cannot be met"),
    ("no_holdout",   "nothing was held out; the score is memory"),
    ("no_floor",     "no baseline was measured, so nothing could have refuted it"),
    ("circularity",  "the judge was the model itself, and nothing outside it agreed"),
    ("unlooked",     "it made something and no person ever looked at what it made"),
)
NAMES = [s for s, _ in SUSPICIONS]

# The four fields the last two witnesses need, and which no number can supply.
#
#   judge_in_loop  was the thing that produced the metric part of the thing being trained
#   artifact       what the run MADE, if anything ("drawings", "audio", ...) or None
#   looked_at      the artifact was actually EXAMINED -- by a person, or by an instrument
#                  that inspects the artifact itself and not the score -- and it stood up
#                  to the look. `hand_eye.py` sets this from its pen audit, which counts
#                  connected components and stub segments on the raster: a machine that
#                  can see a dot-cloud. A look that FAILS is not a look that passed.
#   independent    some check that does not run through the judge and could have failed
DECLARED = ("judge_in_loop", "artifact", "looked_at", "independent")


# ────────────────────────────────────────────────────────── reading a trace

def _in_loop(trace: dict):
    """Was the thing that produced the metric part of the thing being trained?

    Answered directly by `judge_in_loop`, or inferred when the trace names both the judge
    and what the objective was computed by. **Returns None when the trace never said** —
    and None is not innocence, it is an unanswered question, reported as such.
    """
    if "judge_in_loop" in trace and trace["judge_in_loop"] is not None:
        return bool(trace["judge_in_loop"])
    j, o = trace.get("judge"), trace.get("objective_by")
    if j is not None and o is not None:
        return str(j).strip().lower() == str(o).strip().lower()
    return None


def undeclared(trace: dict) -> list:
    """The questions this trace refused to answer. A witness cannot testify to those."""
    st = trace.get("steps") or []
    miss = []
    if _in_loop(trace) is None:
        miss.append("judge_in_loop (who produced the metric)")
    if "artifact" not in trace:
        miss.append("artifact (what the run MADE, if anything)")
    if "looked_at" not in trace:
        miss.append("looked_at (did a person open it and look)")
    if trace.get("baseline") is None:
        miss.append("baseline (the raw-input floor)")
    if "held_out" not in trace:
        miss.append("held_out")
    if trace.get("chance") is None:
        miss.append("chance")
    if not any(s.get("terms") for s in st):
        miss.append("terms (the loss, term by term)")
    if len(st) < 2:
        miss.append("steps (fewer than two: nothing could have moved)")
    return miss


def evidence(trace: dict) -> dict:
    """Turn a run's trace into nine numbers in [0,1]: how loud each suspicion is.

    `trace` wants: steps [{step, metric, terms:{name:value}}], whatever floors the
    experiment actually established — `chance`, `baseline` (the raw-input score),
    `held_out` (bool) — and who held the ruler: `judge_in_loop`, `artifact`, `looked_at`,
    `independent`. Missing floors are not treated as innocent: their ABSENCE is itself
    one of the things Murphy is looking for.
    """
    st = trace.get("steps") or []
    m = [s["metric"] for s in st]
    chance = trace.get("chance")
    base = trace.get("baseline")
    out = {}
    if not m:
        # A run that logged nothing. Every witness that reads numbers is mute, but the
        # ones that read the PAPERWORK are not, and a run with no trace at all is the
        # least defensible kind there is -- so it still gets asked those.
        for k in ("collapse", "flat", "at_chance", "below_floor", "frozen_term"):
            out[k] = 0.0
        out["no_holdout"] = 0.0 if trace.get("held_out") else 1.0
        out["no_floor"] = 0.0 if base is not None else 1.0
        loop, looked = _in_loop(trace), bool(trace.get("looked_at"))
        out["circularity"] = 0.0 if not loop else (
            0.35 if (looked or trace.get("independent")) else 1.0)
        out["unlooked"] = 1.0 if (trace.get("artifact") and not looked) else 0.0
        return out

    # a loss that vanishes at once solved something other than the task
    has_terms = any(s.get("terms") for s in st)
    if has_terms:
        first = [s.get("terms", {}) for s in st[:max(1, len(st) // 10)]]
        losses = [sum(s.get("terms", {}).values()) for s in st]
        l0 = max(losses[0], 1e-9)
        early = min(sum(t.values()) for t in first) if first else l0
        out["collapse"] = _clip(1.0 - early / l0) if l0 > 0 else 0.0
    else:
        out["collapse"] = 0.0                 # no terms declared: he cannot ask

    rng = (max(m) - min(m)) if len(m) > 1 else None
    out["flat"] = _clip(1.0 - rng / 0.05) if rng is not None else 0.0
    out["at_chance"] = _clip(1.0 - abs(m[-1] - chance) / 0.05) if chance else 0.0
    out["below_floor"] = _clip((base - m[-1]) / 0.1) if base is not None else 0.0

    # a term with no variance is either satisfied and inert, or unsatisfiable and pinned.
    # Only the SECOND is a fault, and the difference is whether it is sitting at zero.
    worst = 0.0
    if has_terms:
        for k in st[0].get("terms", {}):
            v = [s.get("terms", {}).get(k, 0.0) for s in st]
            if len(v) > 2 and max(v) > 1e-4:
                spread = (max(v) - min(v)) / max(abs(sum(v) / len(v)), 1e-9)
                worst = max(worst, _clip(1.0 - spread / 0.05))
    out["frozen_term"] = worst

    # `held_out` may be True, False, or a STRING giving the reason no holdout is possible.
    # Winston's table hand is the honest case: 22 rows and 22 letters, no sample to hold
    # out, and the score is by construction a score on what it memorised. Refusing that
    # answer would force the author to write True and lie. So the excuse is ADMISSIBLE --
    # and `watch()` reads it aloud in every ruling, so it is on the record rather than
    # quietly banked.
    out["no_holdout"] = 0.0 if trace.get("held_out") else 1.0
    out["no_floor"] = 0.0 if base is not None else 1.0

    # ---- the two that no number can answer -----------------------------------------
    # CIRCULARITY. The fault is not "a frozen model scored it" -- that is ordinary and
    # fine. The fault is that the thing being trained was optimising the judge's opinion
    # and the judge's opinion was then reported as the result, with NOTHING OUTSIDE THE
    # LOOP agreeing. Two things discharge it, and both are outside opinions: a person who
    # actually looked, or a check that does not run through the judge. That is exactly
    # the difference between Winston's two runs of 2026-08-30 -- same hand, same eye,
    # 86.4% in dot-clouds nobody had seen, and cos 0.445 in lines on a sheet that had.
    loop = _in_loop(trace)
    looked = bool(trace.get("looked_at"))
    indep = bool(trace.get("independent"))
    if not loop:                                  # False, or None = never declared
        out["circularity"] = 0.0
    elif looked or indep:
        out["circularity"] = 0.35                 # noted, and below any sane line
    else:
        out["circularity"] = 1.0

    # UNLOOKED. Only a run that MAKES something can be guilty of this: an accuracy over a
    # fixed corpus has no output to open. A run that draws, speaks, or generates does,
    # and the whole dot-cloud disaster is one sentence long -- the metric was happy and
    # the deliverable did not exist. Note the honest weakness: this witness depends on
    # the run DECLARING that it makes an artifact. `watch()` names the omission out loud,
    # and the three scripts wired to Murphy declare it in code so it cannot be skipped.
    out["unlooked"] = 1.0 if (trace.get("artifact") and not looked) else 0.0
    return out


def _clip(x):
    return float(min(1.0, max(0.0, x)))


# ────────────────────────────────────────────────────────────── the weave

def build(weights=None, lines=None, drift: float = 0.0) -> Weave:
    """Murphy, as a weave. Nine witnesses, a bench that gathers them, one ruling.

    Every suspicion knot uses `rise` — ALMA's own trigger for *do not speak until the
    evidence crosses this line*. That is the beit din's manner: a witness who is unsure
    stays silent rather than adding noise to the count. The line itself is learned.
    """
    w = weights or [1.0] * len(NAMES)
    ln = lines or [0.5] * len(NAMES)
    v = Weave("murphy")
    for i, (name, _) in enumerate(SUSPICIONS):
        v.knot(name, verb="pass", trigger="rise %.4f" % max(0.02, ln[i]))
    v.knot("bench", verb="pool")           # the suspicions gather here and accumulate
    # THE GATE, and it is the whole correction. Murphy first scored 7 of 8 on the real
    # runs of 2026-08-30, and the one he missed was a run that sat at chance and SAID SO.
    # Same numbers, opposite verdict: at chance under "this is learning" is a lie, and at
    # chance under "this failed" is a report. **The fault is never in the number; it is in
    # the distance between the number and the claim.** So the bench may only rule when a
    # success was actually asserted -- ALMA's `gate` verb, used for the thing it is named
    # after: evidence held back until the key turns.
    v.knot("claim", verb="pass")
    v.knot("ruling", verb="gate")
    for i, name in enumerate(NAMES):
        v.thread(name, "bench", strands=[Strand(weight=w[i], drift=drift)])
    v.thread("bench", "ruling", port="in", strands=[Strand(weight=1.0, delay=2)])
    v.thread("claim", "ruling", port="key", strands=[Strand(weight=1.0, delay=3)])
    v.knot("said", verb="fringe")
    v.thread("ruling", "said", strands=[Strand(weight=1.0)])
    v.run_hint = 8
    return v


def rule(trace: dict, weights=None, lines=None, drift: float = 0.0, weave=None):
    """Run Murphy over one trace. Returns (suspicion score, which witnesses spoke).

    `weave` lets a caller tie the same bench once and put many cases in front of it —
    which is the whole of the training loop, and it is 4x faster. Nothing carries over
    between cases: the seeds are cleared here, and the loom keeps every pool and tray on
    its own stack frame, so the same bench hearing a thousand runs hears each one fresh.
    """
    ev = evidence(trace)
    v = weave if weave is not None else build(weights, lines, drift)
    v.seeds = []
    for name in NAMES:
        v.seed(name, ev[name], beat=1)
    # A run that claims nothing cannot be fooling anybody. Default is to assume a claim
    # was made, because that is the common case and the safer default for a watchdog.
    v.seed("claim", 1.0 if trace.get("claimed_success", True) else 0.0, beat=1)
    r = Loom().run(v)
    spoke = [f.knot for f in r.fires if f.knot in NAMES]
    said = r.fringe("said")
    return (max(said) if said else 0.0), spoke, ev


# ──────────────────────────────────────────── the one line a training script calls

WHY = dict(SUSPICIONS)


def load(path: str = None) -> tuple:
    """Murphy's fitted cords, if they are for THIS bench. Nine names, or none.

    A `murphy.json` written before a witness existed describes a different court, and
    silently reusing seven weights for nine witnesses would be its own quiet lie.
    """
    p = path or os.path.join(HERE, "murphy.json")
    try:
        cfg = json.load(open(p))
    except Exception:
        return None, None
    if list(cfg.get("names", [])) != NAMES:
        return None, None
    return cfg.get("weights"), cfg.get("lines")


def watch(trace: dict, name: str = "", cut: float = 1.0, weights=None, lines=None,
          quiet: bool = False) -> dict:
    """Put one run in front of Murphy and print the ruling. ASCII only, on purpose.

    Iddo, 2026-08-30: *"שאף ריצה לא תדווח בלי פסק שלו."* So this is deliberately one
    import and one call at the end of a training script. It prints the verdict, every
    witness that spoke and why, and — this part matters as much — every question the
    trace never answered, because a witness that was never given the field cannot speak
    and its silence must not read as acquittal.

    Returns {"fooling": bool, "score": float, "spoke": [...], "evidence": {...},
             "undeclared": [...]} so a caller can act on it as well as read it.
    """
    if weights is None and lines is None:
        weights, lines = load()
    score, spoke, ev = rule(trace, weights, lines)
    spoke = list(dict.fromkeys(spoke))
    fooling = score >= cut
    miss = undeclared(trace)
    if not quiet:
        bar = "-" * 72
        print("\n" + bar)
        print("MURPHY  |  %s%s" % (name or "this run",
                                   "" if weights else "   (equal weights)"))
        if spoke:
            print("  witnesses that spoke:")
            for k in spoke:
                print("     %-12s %.2f   %s" % (k, ev[k], WHY[k]))
        else:
            print("  witnesses that spoke:  none -- every suspicion stayed below its line")
        print("  RULING: %s" % ("FOOLING ITSELF  (%.2f >= %.2f)" % (score, cut) if fooling
                                else "sound  (%.2f < %.2f)" % (score, cut)))
        if not trace.get("claimed_success", True):
            print("          (no success was claimed, so the bench could not rule -- a run"
                  " that fails and says so is a report, not a lie)")
        if isinstance(trace.get("held_out"), str):
            print("  nothing was held out, and the run's reason is ON THE RECORD:")
            print("     \"%s\"" % trace["held_out"])
        if miss:
            print("  the trace never answered: %s" % "; ".join(miss))
            print("  -> a question Murphy cannot ask is not a question that came back clean.")
        print(bar, flush=True)
    return {"fooling": fooling, "score": score, "spoke": spoke,
            "evidence": ev, "undeclared": miss}


# ─────────────────────────────────────────────────── runs whose truth is known

def _declare(rng: random.Random, trace: dict, fault: str) -> None:
    """Who judged this run, and what did it make.

    THE TRAP THIS AVOIDS is the one Murphy already fell into once: the first generated
    benchmark was one he could not fail because a single flag separated the classes. So
    these four fields are drawn for EVERY run first, and the fault is imposed afterwards
    on exactly one axis. `judge_in_loop` is true in half the sound runs; `looked_at` is
    false in plenty of them too. Only the CONJUNCTION carries the label, which is the
    thing that has to be learned and cannot be read off a flag.
    """
    trace["judge_in_loop"] = rng.random() < 0.5
    trace["artifact"] = rng.choice([None, None, "drawings", "audio", "samples"])
    trace["independent"] = rng.random() < 0.5
    if fault == "circular":
        trace["judge_in_loop"] = True
        trace["independent"] = False
        trace["looked_at"] = False
    elif fault == "unlooked":
        trace["judge_in_loop"] = False
        trace["artifact"] = rng.choice(["drawings", "audio", "samples"])
        trace["looked_at"] = False
    elif trace["judge_in_loop"] or trace["artifact"]:
        trace["looked_at"] = True          # honest on every axis except its own fault
    else:
        trace["looked_at"] = rng.random() < 0.5     # nothing to look at either way


def make_run(rng: random.Random, fooling: bool) -> dict:
    """A synthetic experiment whose verdict is known BY CONSTRUCTION — and HARD.

    The first version of this was a benchmark Murphy could not fail: every fooling run
    was missing a holdout or a baseline, and every sound one had both, so an untrained
    Murphy scored 99.8% by reading two flags and training changed nothing. **The model
    built to catch experiments that cannot fail was first measured by one.** The lesson
    is the model's own, and it is why this generator works to be difficult:

      * a fooling run almost always HAS a holdout and a baseline. It fails in exactly
        ONE subtle way, and looks respectable in every other.
      * a sound run is often ALARMING to look at — converged flat and early, carrying an
        inert regulariser, sitting only just above its floor, self-judged but inspected.
        Suspicious is not the same as wrong, and a Murphy that cannot tell them apart is
        a nuisance, not a judge.
      * three of the sound looks are in here to COST him, and they are built to trip a
        witness AT FULL STRENGTH — `pretrained_flat` holds the metric exactly constant,
        `solved_instantly` drops the whole loss to nothing on step one, `pinned_but_fine`
        carries a term pinned at a nonzero constant. Each is a real thing an honest run
        does (a frozen model measured five times; a linear probe that converges at once;
        a fixed penalty sitting at its target), and each makes equal weights say FOOLING.
        That is the lesson there is to learn and it is a true one: **a flat metric, a
        vanished loss and a pinned term are only faults IN COMPANY** — when the number
        they accompany is a number guessing would have produced. Untrained Murphy scores
        badly here on purpose. A benchmark he cannot fail teaches him nothing, and he of
        all models does not get to be measured by one.
    """
    n = rng.randint(8, 24)
    chance = rng.choice([0.045, 0.1, 0.25, 0.5])
    base = round(rng.uniform(chance + 0.05, 0.85), 3)
    trace = {"chance": chance, "baseline": base, "held_out": True, "steps": []}
    l0 = rng.uniform(0.5, 3.0)

    if not fooling:
        # sound, but deliberately awkward to look at
        look = rng.choice(["normal", "normal", "converged_flat", "inert_term",
                           "just_above", "fast_drop", "self_judged_but_looked",
                           "pretrained_flat", "solved_instantly", "pinned_but_fine"])
        hard = look in ("pretrained_flat", "solved_instantly", "pinned_but_fine")
        if look == "just_above":
            end = rng.uniform(base + 0.005, base + 0.03)
        elif hard:
            end = rng.uniform(base + 0.10, min(0.99, base + 0.16))   # clearly above floor
        else:
            end = rng.uniform(base + 0.05, min(0.99, base + 0.3))
        # a metric that never moved but sits WELL ABOVE its floor is a model that was
        # already right. Flatness on its own proves nothing; it is only a fault when the
        # number it is flat at is a number guessing would have produced.
        start = (end if look == "pretrained_flat"
                 else end - 0.004 if look == "converged_flat"
                 else end - rng.uniform(0.05, 0.4))
        jitter = 0.0 if look == "pretrained_flat" else 0.006
        for i in range(n):
            f = i / (n - 1)
            terms = {"main": l0 * (1 - 0.7 * f) + rng.gauss(0, 0.02),
                     "reg": rng.uniform(0.05, 0.4) * (1 - 0.5 * f)}
            if look == "inert_term":
                terms["reg"] = 0.0                    # satisfied and silent -- NOT a fault
            if look == "fast_drop":
                terms["main"] = l0 * (0.02 if i > 0 else 1.0)   # solved it early, honestly
            if look == "solved_instantly":
                # a linear probe on a good representation converges on step one. The loss
                # really is gone and the task really is solved -- the metric ends well
                # above the floor. Identical in the numbers to the collapse that killed
                # I-JEPA attempt 1, and the opposite verdict.
                terms = {"main": l0 if i == 0 else l0 * 1e-4}
            if look == "pinned_but_fine":
                terms["reg"] = 0.12                   # a fixed penalty, sitting on target
            trace["steps"].append({"step": (i + 1) * 250,
                                   "metric": max(0.0, start + (end - start) * f
                                                 + rng.gauss(0, jitter)),
                                   "terms": terms})
        _declare(rng, trace, "none")
        if look == "self_judged_but_looked":
            trace["judge_in_loop"] = True             # the eye judging the hand...
            trace["looked_at"] = True                 # ...on a sheet somebody opened
        trace["_mode"] = "sound:" + look
        return trace

    # fooling -- and respectable everywhere except in one place
    mode = rng.choice(["collapse", "flat", "below_floor", "frozen",
                       "no_holdout", "no_floor", "circular", "unlooked"])
    if mode == "below_floor":
        end = rng.uniform(chance + 0.05, base - 0.03)      # good-looking, still below
    elif mode in ("collapse", "flat", "frozen"):
        end = chance + rng.uniform(0.0, 0.02)
    else:
        end = rng.uniform(base + 0.05, base + 0.25)
    start = end - (0.003 if mode == "flat" else rng.uniform(0.02, 0.2))
    for i in range(n):
        f = i / (n - 1)
        terms = {"main": l0 * (1 - 0.6 * f), "reg": rng.uniform(0.05, 0.4) * (1 - 0.4 * f)}
        if mode == "collapse":
            terms["main"] = l0 * (0.0004 if i > 0 else 1.0)
        if mode == "frozen":
            terms["reg"] = 0.18                    # pinned: a hinge that can never close
        trace["steps"].append({"step": (i + 1) * 250,
                               "metric": max(0.0, start + (end - start) * f
                                             + rng.gauss(0, 0.004)),
                               "terms": terms})
    if mode == "no_holdout":
        trace["held_out"] = False
    if mode == "no_floor":
        trace["baseline"] = None
    _declare(rng, trace, mode)
    trace["_mode"] = mode
    return trace


def dataset(n: int, seed: int = 1933):
    rng = random.Random(seed)
    return [(make_run(rng, i % 2 == 0), i % 2 == 0) for i in range(n)]


# ───────────────────────────────────────────────────────── the strong training

def score(data, weights, lines, cut=1.0):
    v = build(weights, lines)
    ok = 0
    for trace, fooling in data:
        s, _, _ = rule(trace, weave=v)
        ok += int((s >= cut) == fooling)
    return ok / len(data)


def by_mode(data, weights, lines, cut=1.0):
    """Where he is wrong, mode by mode. An average is where a miss goes to hide."""
    v = build(weights, lines)
    tally = {}
    for trace, fooling in data:
        s, _, _ = rule(trace, weave=v)
        k = trace.get("_mode", "?")
        a, b = tally.get(k, (0, 0))
        tally[k] = (a + int((s >= cut) == fooling), b + 1)
    return tally


def train(steps: int, n_data: int, sigma: float, seed: int, quiet=False):
    """Perturbation search over the cords and the lines. No gradient anywhere.

    Measured on Winston earlier today: with sigma small enough to stay in the linear
    range, this estimates the true gradient at cosine +0.76, and at sigma 0.15 it drops
    to +0.05 because the tremor leaves the range where the estimate means anything. Small
    tremors. It is the same lesson twice.
    """
    rng = random.Random(seed)
    data = dataset(n_data, seed)
    hold = dataset(max(200, n_data // 2), seed + 7717)
    w = [1.0] * len(NAMES)
    ln = [0.5] * len(NAMES)
    best = score(data, w, ln)
    for step in range(1, steps + 1):
        dw = [rng.gauss(0, sigma) for _ in w]
        dl = [rng.gauss(0, sigma) for _ in ln]
        up_w = [max(0.0, a + b) for a, b in zip(w, dw)]
        up_l = [min(0.98, max(0.02, a + b)) for a, b in zip(ln, dl)]
        s = score(data, up_w, up_l)
        if s > best:                       # one number came back: better, or not
            w, ln, best = up_w, up_l, s
        if not quiet and (step % max(1, steps // 8) == 0 or step == steps):
            print("  step %5d  train %.1f%%   held-out %.1f%%"
                  % (step, 100 * best, 100 * score(hold, w, ln)), flush=True)
    return w, ln, best, score(hold, w, ln)


def real_score(weights, lines):
    """How many of the REAL runs of 2026-08-30 he still gets. Lazy import on purpose."""
    from real_traps import CASES                                # noqa: E402
    ok = 0
    for _, fooling, _, trace in CASES:
        s, _, _ = rule(trace, weights, lines)
        ok += int((s >= 1.0) == fooling)
    return ok, len(CASES)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train Murphy.")
    ap.add_argument("--train", type=int, default=300, help="perturbation steps")
    ap.add_argument("--data", type=int, default=600, help="generated runs to fit on")
    ap.add_argument("--sigma", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=1933)
    ap.add_argument("--out", default=os.path.join(HERE, "murphy.json"))
    a = ap.parse_args(argv)

    print("MURPHY - %d witnesses, fitted on %d runs whose truth is known"
          % (len(NAMES), a.data))
    flat_w, flat_l = [1.0] * len(NAMES), [0.5] * len(NAMES)
    bench = dataset(400, a.seed + 1)
    before = score(bench, flat_w, flat_l)
    print("  untrained (every witness counts the same): %.1f%%" % (100 * before))
    print("  where the untrained bench is wrong:")
    for k, (ok, tot) in sorted(by_mode(bench, flat_w, flat_l).items()):
        if ok < tot:
            print("     %-28s %d/%d" % (k, ok, tot))
    w, ln, tr, te = train(a.train, a.data, a.sigma, a.seed)

    # THE GATE ON HIS OWN TRAINING. A lesson learned on generated runs that costs him one
    # of the real failures of 2026-08-30 is not a lesson, and it does not get saved.
    r_new, n_real = real_score(w, ln)
    r_old, _ = real_score(flat_w, flat_l)
    print("\nthe real runs of 2026-08-30:  untrained %d/%d   trained %d/%d"
          % (r_old, n_real, r_new, n_real))
    if r_new < n_real:
        print("REFUSING TO SAVE. He gained %.1f%% on generated runs and lost a REAL one. "
              "%s is left as it was." % (100 * (te - before), a.out))
        return 1

    json.dump({"names": NAMES, "weights": w, "lines": ln,
               "train": tr, "heldout": te, "real_traps": [r_new, n_real],
               "note": "weights are ALMA strand weights; lines are `rise` triggers"},
              open(a.out, "w"), indent=1)
    print("\nheld-out runs Murphy has never seen: %.1f%%  (untrained %.1f%%)"
          % (100 * te, 100 * before))
    print("what he learned to weigh:")
    for name, wi, li in sorted(zip(NAMES, w, ln), key=lambda t: -t[1]):
        print("   %-12s cord %.2f   speaks above %.2f" % (name, wi, li))
    print("-> %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
