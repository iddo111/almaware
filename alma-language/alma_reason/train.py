# -*- coding: utf-8 -*-
"""Training the dialectic. Two rules, measured against each other and against
three baselines that cost nothing to beat — so that beating them means something.

    python -m alma_reason.train --corpus syllogism --features raw

THE VERDICT IS THE WORLD, NOT A LOSS
------------------------------------
Exactly as in `xor_pain.py`: one number, +1 or -1, delivered once when the run
is over, saying only *that stood* or *that fell*. It is not a gradient, it does
not name a cord, and no cord reaches it. Iddo's argument from 2026-09-10 00:46
is the reason it may be internal at all — when you break your leg no examiner
tells you that you failed.

Here the world is simply: did the seat the weave left standing match the seat
the sources leave standing?

TWO RULES, AND WHY BOTH ARE RUN
-------------------------------
**THREE-FACTOR** (`--rule three-factor`). The loom's own pain-and-pleasure, on
every learned cord. `xor_pain.py` measured its ceiling honestly: it is a
correct reward-modulated perceptron at the OUTPUT layer and it has no credit
assignment at all for a hidden one, because one global scalar cannot tell h0
"you should have fired" while telling h1 the opposite. 0/8 starts learned XOR.

**NODE PERTURBATION** (`--rule perturbation`), the first of the two ways
forward that file named, now built. Each hidden knot gets its own private
jitter spark, seeded straight into its tray on the beat the evidence arrives,
so the noise passes through the `rise` threshold and changes both whether the
knot fires and what it says. The verdict is then correlated with THAT:

    Δw  =  η · (R − R̄) · ξ_i        for every cord landing on hidden knot i
                                      from a feature that was actually present

The noise is private to the knot, so the credit is private too. It is a real
gradient estimator (Williams 1992; the REINFORCE family), it is entirely local,
and — the part that matters here — **nothing travels backwards**. ξ_i is a
spark that went forward in time like every other spark in ALMA. The output
layer stays with the loom's three-factor rule, which is where that rule works.

R̄ is a running mean of the reward, subtracted as a baseline. It is the
learner's own expectation, not the world's opinion, so it does not smuggle
anything past the doctrine above.

THE CONTROL THAT CATCHES A LYING MEASUREMENT
--------------------------------------------
`--shuffle` trains the identical weave on labels that have been shuffled. If
the shuffled run still "learns", the measurement is broken, not the idea. This
exists because `xor_pain.py` records a night lost to a score() that read the
wrong thing and returned the same number for every configuration.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma import Loom                                              # noqa: E402
from alma.loom import STRAND_CEIL, STRAND_FLOOR                    # noqa: E402
from alma.perturb import NodePerturbation                          # noqa: E402

from .build_dataset import (feature_names, load, stratified_split,  # noqa: E402
                            write as write_dataset, OUT)
from .encoding import SEAT_M, SEAT_Q, Argument                      # noqa: E402
from .weave import (DEFAULT_BEATS, DEFAULT_HIDDEN, SEATS, build,    # noqa: E402
                    conclude, learned_strands, seed_argument)

RULES = ("three-factor", "perturbation", "none")


# ------------------------------------------------------------------ measuring

@dataclass
class Score:
    n: int
    right: int
    tp: int = 0       # מתרץ called מתרץ
    tn: int = 0       # מקשן called מקשן
    fp: int = 0       # מקשן called מתרץ
    fn: int = 0       # מתרץ called מקשן
    ties: int = 0     # תיקו — counted as wrong, and counted separately

    @property
    def accuracy(self) -> float:
        return self.right / self.n if self.n else 0.0

    @property
    def balanced(self) -> float:
        """The headline. Raw accuracy is worthless here — 'always מקשן' scores
        90.6% on the syllogism corpus without reading anything."""
        sens = self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0
        spec = self.tn / (self.tn + self.fp) if (self.tn + self.fp) else 0.0
        return (sens + spec) / 2.0

    def line(self, label: str) -> str:
        return (f"{label:24s} balanced {self.balanced*100:5.1f}%   "
                f"raw {self.accuracy*100:5.1f}%  ({self.right}/{self.n})   "
                f"tp {self.tp:3d} fn {self.fn:3d} tn {self.tn:3d} fp {self.fp:3d}"
                f"{f'  ties {self.ties}' if self.ties else ''}")


def evaluate(loom: Loom, weave, items: list[Argument],
             beats: int = DEFAULT_BEATS) -> Score:
    """Learning OFF. This is the real output: no verdict is delivered at all."""
    s = Score(n=len(items), right=0)
    for a in items:
        seed_argument(weave, a)
        c = conclude(loom.run(weave, beats=beats, verdict=None), beats)
        got, want = c.winner, a.winner
        if got == "תיקו":
            s.ties += 1
        if got == want:
            s.right += 1
        if want == SEAT_M:
            s.tp += 1 if got == SEAT_M else 0
            s.fn += 1 if got != SEAT_M else 0
        else:
            s.tn += 1 if got == SEAT_Q else 0
            s.fp += 1 if got != SEAT_Q else 0
    return s


def baseline_scores(items: list[Argument]) -> dict[str, Score]:
    """What costs nothing. Anything that does not beat these means nothing."""
    out = {}
    for name, call in (("always מתרץ", lambda a: SEAT_M),
                       ("always מקשן", lambda a: SEAT_Q)):
        s = Score(n=len(items), right=0)
        for a in items:
            got = call(a)
            s.right += 1 if got == a.winner else 0
            if a.winner == SEAT_M:
                s.tp += got == SEAT_M
                s.fn += got != SEAT_M
            else:
                s.tn += got == SEAT_Q
                s.fp += got != SEAT_Q
        out[name] = s
    rng = random.Random(7)
    s = Score(n=len(items), right=0)
    for a in items:
        got = rng.choice(SEATS)
        s.right += 1 if got == a.winner else 0
        if a.winner == SEAT_M:
            s.tp += got == SEAT_M
            s.fn += got != SEAT_M
        else:
            s.tn += got == SEAT_Q
            s.fp += got != SEAT_Q
    out["coin toss"] = s
    return out


# ------------------------------------------------------------------ training

def present(loom: Loom, weave, a: Argument, beats: int, rule: str,
            sigma: float, eta: float, baseline: float,
            rng: random.Random, hidden: int,
            perturber: NodePerturbation | None = None) -> tuple[float, float]:
    """One trial: state the case, let both seats argue, be judged, learn.

    Returns (reward, |Δw| this trial) — the second so a run can prove the
    weights actually moved rather than assuming it.
    """
    seed_argument(weave, a)

    pert = None
    if rule == "perturbation":
        # The private noise. It is seeded as a SPARK into the hidden knot's own
        # tray on beat 2 — the beat the evidence lands — so it passes through
        # the `rise` threshold and changes whether the knot speaks at all, not
        # only what it says. A jitter on `bias` would never reach the trigger.
        # v0.2: the rule is the holobrain's shared one (alma/perturb.py). The
        # draw order (seat by seat, knot by knot) is unchanged, and
        # tests/test_perturb.py proves the weights come out bit-identical.
        pert = perturber or NodePerturbation(
            [f"{seat}_h{i}" for seat in SEATS for i in range(hidden)],
            sigma=sigma, eta=eta, beat=2, rng=rng, baseline=baseline)
        pert.jitter(weave)

    got = {"winner": None}

    def world(beat, fires_this_beat):
        """The world. It reads only what the weave DID. No cord reaches in here."""
        if fires_this_beat is None:
            return 1.0 if got["winner"] == a.winner else -1.0
        return None

    plastic = any(st.drift for st in learned_strands(weave))
    r = loom.run(weave, beats=beats,
                 verdict=world if (plastic and rule != "none") else None)
    c = conclude(r, beats)
    got["winner"] = c.winner
    reward = 1.0 if c.winner == a.winner else -1.0

    moved = 0.0
    # THREE-FACTOR: the loom already applied it; write the new weights back.
    if r.learned is not None and rule != "none":
        for st, nw in zip(learned_strands(weave), r.learned):
            moved += abs(nw - st.weight)
            st.weight = nw

    # NODE PERTURBATION: correlate the verdict with each knot's OWN noise.
    if pert is not None:
        moved += pert.credit(weave, r, reward)
    return reward, moved


def train(items_train: list[Argument], items_test: list[Argument],
          features: list[str], *, seed: int, rule: str, epochs: int,
          hidden: int, beats: int, sigma: float, eta: float,
          drift_out: float, drift_in: float, scale: float,
          typical_present: int, balance: bool = True,
          verbose: bool = False) -> dict:
    rng = random.Random(seed)
    loom = Loom()
    weave = build(features, seed=seed, hidden=hidden,
                  drift_in=drift_in, drift_out=drift_out,
                  beats=beats, scale=scale, typical_present=typical_present)

    # A CONFIGURATION THAT CANNOT LEARN MUST NOT BE ALLOWED TO REPORT A SCORE.
    # This is here because a hyperparameter sweep once selected drift_in =
    # drift_out = 0 for the three-factor rule — no plastic cord anywhere — and
    # the arm reported a respectable-looking 51.2% with |dw| = 0.0 on all eight
    # seeds, against an arm that had actually run. Silence about that would have
    # made the comparison between the two rules a fiction.
    if rule == "three-factor" and not (drift_in or drift_out):
        raise ValueError("rule='three-factor' with drift_in=drift_out=0: no cord "
                         "in the weave is plastic, so nothing can be learned. "
                         "This configuration cannot produce a number.")
    if rule == "perturbation" and not (eta and sigma) and not drift_out:
        raise ValueError("rule='perturbation' with eta or sigma at 0 and no "
                         "drift_out: nothing can move.")

    before_tr = evaluate(loom, weave, items_train, beats)
    before_te = evaluate(loom, weave, items_test, beats)

    baseline, beta, moved_total = 0.0, 0.05, 0.0
    perturber = None
    if rule == "perturbation":
        perturber = NodePerturbation(
            [f"{seat}_h{i}" for seat in SEATS for i in range(hidden)],
            sigma=sigma, eta=eta, beat=2, rng=rng, beta=beta)
    curve = []
    for ep in range(epochs):
        if balance:
            order = balanced_stream(items_train, rng)
        else:
            order = list(items_train)
            rng.shuffle(order)
        for a in order:
            reward, moved = present(loom, weave, a, beats, rule, sigma, eta,
                                    baseline, rng, hidden, perturber=perturber)
            baseline = (1 - beta) * baseline + beta * reward
            moved_total += moved
        if verbose and (ep + 1) % max(1, epochs // 10) == 0:
            s = evaluate(loom, weave, items_test, beats)
            curve.append((ep + 1, s.balanced))
            print(f"    epoch {ep+1:4d}   test balanced {s.balanced*100:5.1f}%   "
                  f"|dw| so far {moved_total:8.2f}")

    after_tr = evaluate(loom, weave, items_train, beats)
    after_te = evaluate(loom, weave, items_test, beats)
    return {"seed": seed, "rule": rule, "moved": moved_total, "curve": curve,
            "before_train": before_tr, "before_test": before_te,
            "after_train": after_tr, "after_test": after_te, "weave": weave}


def balanced_stream(items: list[Argument], rng: random.Random) -> list[Argument]:
    """One epoch's diet, with the two verdicts equally represented.

    MEASURED, not precautionary: on the first run of this trainer the weave
    went from 60.9% balanced to 49.4% in three epochs — it discovered that
    answering מקשן every time is right 90.6% of the time, which is true and
    useless. A reward of +1 for being right is the world telling the truth; a
    training set that is 91% one verdict is us feeding it badly. So the fix
    belongs in the DIET, never in the verdict: the minority verdict is
    oversampled until the two are equal, and +1/-1 stays exactly what the
    world says.
    """
    by = {SEAT_M: [], SEAT_Q: []}
    for a in items:
        by[a.winner].append(a)
    if not by[SEAT_M] or not by[SEAT_Q]:
        out = list(items)
        rng.shuffle(out)
        return out
    n = max(len(by[SEAT_M]), len(by[SEAT_Q]))
    out = []
    for seat in (SEAT_M, SEAT_Q):
        pool = by[seat]
        out += [pool[rng.randrange(len(pool))] for _ in range(n)]
    rng.shuffle(out)
    return out


def shuffled(items: list[Argument], seed: int) -> list[Argument]:
    """Same items, verdicts dealt out at random. The control on the measurement."""
    rng = random.Random(seed)
    labels = [a.winner for a in items]
    rng.shuffle(labels)
    return [Argument(id=a.id, features=a.features, winner=lab, seat_m=a.seat_m,
                     seat_q=a.seat_q, text=a.text, source=a.source, meta=a.meta)
            for a, lab in zip(items, labels)]


# ---------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train the שקלא וטריא weave.")
    ap.add_argument("--corpus", default="syllogism",
                    choices=("syllogism", "machloket"))
    ap.add_argument("--features", default="raw",
                    help="raw | distrib (syllogism), machloket")
    ap.add_argument("--rule", default="perturbation", choices=RULES)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--hidden", type=int, default=DEFAULT_HIDDEN)
    ap.add_argument("--beats", type=int, default=DEFAULT_BEATS)
    ap.add_argument("--sigma", type=float, default=0.6)
    ap.add_argument("--eta", type=float, default=0.02)
    ap.add_argument("--drift-out", type=float, default=0.03)
    ap.add_argument("--drift-in", type=float, default=0.0)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--no-balance", action="store_true",
                    help="feed the corpus as it is, imbalance and all")
    ap.add_argument("--shuffle", action="store_true",
                    help="train on shuffled labels — the control")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", default="", help="write the numbers here too")
    args = ap.parse_args(argv)

    if not OUT.exists():
        write_dataset()
    fs = args.features if args.corpus == "syllogism" else "machloket"
    items = load(corpus=args.corpus, feature_set=fs)
    if not items:
        print(f"no items for {args.corpus}/{fs}", file=sys.stderr)
        return 2
    names = feature_names(args.corpus, fs)
    typical = int(statistics.mean(len(a.features) for a in items)) + 1
    tr, te = stratified_split(items)
    if args.shuffle:
        tr = shuffled(tr, seed=99)

    print("שקלא וטריא — a dialectic that is a weave, not a prompt")
    print(f"corpus {args.corpus}/{fs}: {len(items)} items, {len(names)} features, "
          f"{typical} typically present")
    print(f"train {len(tr)} / test {len(te)}   rule={args.rule}   "
          f"hidden={args.hidden}/seat   beats={args.beats} "
          f"({(args.beats-2)//2} rounds)   epochs={args.epochs}   "
          f"diet={'balanced' if not args.no_balance else 'as-is'}"
          f"{'   [LABELS SHUFFLED — control]' if args.shuffle else ''}")
    print()
    print("  baselines that cost nothing, on the held-out half:")
    for name, s in baseline_scores(te).items():
        print("    " + s.line(name))
    print()

    t0 = time.time()
    runs = []
    for seed in range(args.seeds):
        if args.verbose:
            print(f"  seed {seed}:")
        r = train(tr, te, names, seed=seed, rule=args.rule, epochs=args.epochs,
                  hidden=args.hidden, beats=args.beats, sigma=args.sigma,
                  eta=args.eta, drift_out=args.drift_out, drift_in=args.drift_in,
                  scale=args.scale, typical_present=typical,
                  balance=not args.no_balance, verbose=args.verbose)
        runs.append(r)
        print(f"  seed {seed:2d}   test balanced "
              f"{r['before_test'].balanced*100:5.1f}% -> "
              f"{r['after_test'].balanced*100:5.1f}%   "
              f"train {r['before_train'].balanced*100:5.1f}% -> "
              f"{r['after_train'].balanced*100:5.1f}%   |dw| {r['moved']:8.2f}")

    before = [r["before_test"].balanced for r in runs]
    after = [r["after_test"].balanced for r in runs]
    print()
    print(f"  UNTRAINED  test balanced  mean {statistics.mean(before)*100:5.1f}%  "
          f"(min {min(before)*100:.1f}, max {max(before)*100:.1f})")
    print(f"  TRAINED    test balanced  mean {statistics.mean(after)*100:5.1f}%  "
          f"(min {min(after)*100:.1f}, max {max(after)*100:.1f})")
    print(f"  {len(runs)} seeds, {time.time()-t0:.1f}s")

    if args.json:
        payload = {
            "corpus": args.corpus, "feature_set": fs, "rule": args.rule,
            "shuffled": args.shuffle, "epochs": args.epochs,
            "hidden": args.hidden, "beats": args.beats, "sigma": args.sigma,
            "balanced_diet": not args.no_balance,
            "eta": args.eta, "drift_in": args.drift_in,
            "drift_out": args.drift_out, "n_train": len(tr), "n_test": len(te),
            "n_features": len(names),
            "baselines": {k: {"balanced": v.balanced, "accuracy": v.accuracy}
                          for k, v in baseline_scores(te).items()},
            "runs": [{"seed": r["seed"], "moved": r["moved"],
                      "before_test_balanced": r["before_test"].balanced,
                      "after_test_balanced": r["after_test"].balanced,
                      "before_train_balanced": r["before_train"].balanced,
                      "after_train_balanced": r["after_train"].balanced,
                      "after_test_accuracy": r["after_test"].accuracy}
                     for r in runs],
            "untrained_mean": statistics.mean(before),
            "trained_mean": statistics.mean(after),
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False,
                                              indent=2), encoding="utf-8")
        print(f"  numbers -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
