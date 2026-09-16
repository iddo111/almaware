# -*- coding: utf-8 -*-
"""THE ORGAN. A generative rhythm organ woven out of knots, threads and strands.

Iddo, 2026-09-12 02:56: "וכמובן שהמודל שתעשה יהיה עלמה" -- the model itself is
written in the ALMA language, not a conventional network wearing ALMA's name.
Everything below is `alma/loom.py` and `alma/perturb.py`. There is no matrix
multiply anywhere in this file, no gradient, and nothing travels backwards.

WHAT IT EMITS
-------------
One BAR = 16 sixteenths, four lanes: kick, snare, hat (struck or not) and a
BASS DEGREE 0..12 where 0 is a rest and 1..12 is a CHROMATIC semitone over the
key -- the same meaning midi_out.bass_note() gives it after the 2026-09-05
pitch fix. Chromatic ON PURPOSE: if the organ could only emit the seven notes
of the scale, "share of notes in scale" would be a tautology of the encoding
(exactly the trap the darwish pitch fix documented). It must LEARN the scale.

THE SHAPE
---------
    p0..p15   one knot per position in the bar. `pass`. Seeded 1.0 at this step.
    one       always-on. Its cords are the learnable leaning (xor_pain.py's scar:
              without it a silent step puts nothing into the weave).
    mk ms mh  what the drums did on the PREVIOUS step.
    mb0..mb11 what the bass said on the previous step. Together: the groove's
              short memory, and the only reason a bar is a bar and not 16
              unrelated coin flips.
                                              -> 32 input knots, always.
    h0..h{H-1}   `sum`, `rise theta_j`, every threshold ABOVE zero (alma_guard's
                 measured scar: a hidden knot that fires below zero speaks a
                 NEGATIVE number and teaches every cord below it backwards).
                 H IS THE SIZE KNOB. "bigger" is this number.
    out_kick, out_snare, out_hat, out_b0..out_b11   `sum`, `rise 0.0`.
                 Firing IS the decision. For the bass the 12 heads compete and
                 the loudest margin wins; if none fires the step is a REST.
    say_*        `fringe`. The hem -- what the weave says out loud.

WHO LEARNS WHAT
---------------
    x -> h    node perturbation (`alma/perturb.py`). drift=0: these cords are
              owned by the private jitter, because one global scalar cannot tell
              h0 "you should have fired" while telling h1 the opposite. That wall
              was measured three times before this organ existed.
    h -> out  the loom's own three-factor rule (כאב ועונג). At an OUTPUT that is
              already a correct reward-modulated perceptron.
    x -> out  the same, at the same distance (2 beats) so the skip path and the
              hidden path land on the same beat -- xor_pain.py paid once for a
              cord that arrived early.

WHY TWO PASSES PER BAR
----------------------
The judge scores a WHOLE BAR; the reward does not exist until the 16th step is
written. So:
    pass 1  every step runs with `verdict=0.0`. A zero verdict is FALSY, so the
            loom decays the eligibility traces and changes NO weight -- a pure
            generation pass even though every cord is plastic. (verdict=None
            would silently apply the two-factor Hebbian rule and the organ would
            learn from nothing at all.)
    judge   one scalar for the bar.
    pass 2  the identical 16 steps re-run with the verdict. The weights did not
            move in pass 1 and the jitter is the same draw, so pass 2 reproduces
            pass 1 exactly and the cords that acted are the cords that are paid.
            It is ASSERTED, not assumed: a divergence raises.
"""
from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "alma-language"))

from alma import Loom, Weave                                       # noqa: E402
from alma.loom import Strand, Thread                               # noqa: E402
from alma.perturb import NodePerturbation                          # noqa: E402

BAR = 16
DRUMS = ("kick", "snare", "hat")
RULES = ("three-factor", "perturbation", "perturbation-all", "frozen")


@dataclass
class Hyper:
    hidden: int = 32           # THE SIZE KNOB
    rule: str = "perturbation"
    drift: float = 0.05        # how eligible one landing makes a cord
    init: float = 0.02         # head cords start uniform in [-init, +init]
    h_init: float = 1.0        # x->h init scale (times 1/sqrt(typical))
    spread: float = 0.5        # hidden thresholds span (0, spread x net spread]
    sigma: float = 0.5         # jitter, in units of a hidden knot's net spread
    eta: float = 0.02          # perturbation step, same units, per bar
    gain: float = 4.0          # judge score -> verdict scale
    typical: int = 5           # inputs actually seeded on a step (p, one, ~3)
    skip: bool = True
    seed: int = 0

    def line(self) -> str:
        return " ".join(f"{k}={v}" for k, v in asdict(self).items())


class BeatWeave:
    """The organ, plus the little bookkeeping a generator needs."""

    def __init__(self, hyper: Hyper):
        if hyper.rule not in RULES:
            raise ValueError(f"unknown rule {hyper.rule!r}; one of {RULES}")
        if hyper.rule.startswith("perturbation") and not hyper.hidden:
            raise ValueError(f"rule={hyper.rule!r} needs hidden > 0")
        self.hyper = hyper
        self.loom = Loom()
        self.heads = list(DRUMS) + [f"b{d}" for d in range(12)]
        self.inputs = ([f"p{i}" for i in range(BAR)] + ["one"] +
                       ["mk", "ms", "mh"] + [f"mb{d}" for d in range(12)])
        self.horizon = 5                 # x:1  h:2  out:3  say:4  (+1 to settle)
        rng = random.Random(hyper.seed)
        self.weave = self._build(rng)
        self.strands = [st for t in self.weave.threads for st in t.strands]
        self.perturber: NodePerturbation | None = None
        self.moved = 0.0
        if hyper.rule.startswith("perturbation"):
            spread = self.net_spread()
            targets = [f"h{j}" for j in range(hyper.hidden)]
            beats = {k: 2 for k in targets}
            if hyper.rule == "perturbation-all":
                # THE HEADS TOO, and this is a MEASURED correction, 2026-09-12
                # 03:2x. With one bar-level scalar the loom's Hebbian term at a
                # head is asymmetric -- a cord that landed while its head fired
                # becomes eligible at +drift, one whose head stayed silent at
                # only -drift/4 -- so FIRING is reinforced four times harder than
                # silence, whatever the sign of the verdict. Every head therefore
                # walked to "always fire": energy fell 0.600 -> 0.100 inside 50
                # trials, independence to 0.000, and both learning arms sank
                # BELOW the frozen floor. One scalar cannot tell head b7 "you
                # should have been silent this step". A private jitter per head
                # can, so here the heads get one too.
                for hd in self.heads:
                    targets.append(f"out_{hd}")
                    beats[f"out_{hd}"] = 3
            self.perturber = NodePerturbation(
                targets, sigma=hyper.sigma * spread,
                eta=(hyper.eta / (max(1, hyper.typical) * hyper.sigma)) if hyper.sigma else 0.0,
                beat=beats, rng=random.Random(hyper.seed + 104729))

    # ------------------------------------------------------------- the shape

    def net_spread(self) -> float:
        return self.hyper.h_init / math.sqrt(3.0)

    def thresholds(self) -> list[float]:
        H, s = self.hyper.hidden, self.net_spread()
        return [round(self.hyper.spread * s * (j + 1) / (H + 1), 4) for j in range(H)]

    def _build(self, rng: random.Random) -> Weave:
        h = self.hyper
        w = Weave("alma-beat")
        for nm in self.inputs:
            w.knot(nm, verb="pass", trigger="any")
        for j, th in enumerate(self.thresholds()):
            w.knot(f"h{j}", verb="sum", trigger=f"rise {th}")
        for hd in self.heads:
            w.knot(f"out_{hd}", verb="sum", trigger="rise 0.0")
            w.knot(f"say_{hd}", verb="fringe", trigger="any")

        hidden_drift = 0.0 if h.rule.startswith("perturbation") else h.drift
        head_drift = 0.0 if h.rule == "perturbation-all" else h.drift
        a = h.h_init / math.sqrt(max(1, h.typical))
        for j in range(h.hidden):
            for x in self.inputs:
                w.threads.append(Thread(x, f"h{j}", "in",
                                        [Strand(weight=rng.uniform(-a, a),
                                                delay=1, drift=hidden_drift)]))
        for hd in self.heads:
            for j in range(h.hidden):
                w.threads.append(Thread(f"h{j}", f"out_{hd}", "in",
                                        [Strand(weight=rng.uniform(-h.init, h.init),
                                                delay=1, drift=head_drift)]))
            if h.skip or not h.hidden:
                for x in self.inputs:
                    w.threads.append(Thread(x, f"out_{hd}", "in",
                                            [Strand(weight=rng.uniform(-h.init, h.init),
                                                    delay=2, drift=head_drift)]))
            # the hem is not part of the model: weight 1, drift 0
            w.threads.append(Thread(f"out_{hd}", f"say_{hd}", "in",
                                    [Strand(weight=1.0, delay=1)]))
        w.run_hint = self.horizon
        return w

    def n_params(self) -> int:
        """Cords that actually learn -- the number the control must match."""
        return sum(1 for t in self.weave.threads for st in t.strands
                   if not t.dst.startswith("say_"))

    # ------------------------------------------------------------- one step

    def _seed(self, pos: int, mem: dict, xi: dict | None) -> None:
        w = self.weave
        w.seeds = []
        w.seed(f"p{pos}", 1.0, beat=1)
        w.seed("one", 1.0, beat=1)
        for nm, lane in (("mk", "kick"), ("ms", "snare"), ("mh", "hat")):
            if mem.get(lane):
                w.seed(nm, 1.0, beat=1)
        d = mem.get("bass", 0)
        if d:
            w.seed(f"mb{d - 1}", 1.0, beat=1)
        if xi:
            b = self.perturber.beats
            for k, v in xi.items():
                w.seed(k, v, beat=b[k])

    def step(self, pos: int, mem: dict, xi: dict | None = None,
             verdict: float | None = 0.0, commit: bool = False):
        """One sixteenth through the weave. Returns (choice, Result)."""
        self._seed(pos, mem, xi)
        r = self.loom.run(self.weave, beats=self.horizon, verdict=verdict)
        if commit and r.learned is not None:
            for st, nw in zip(self.strands, r.learned):
                st.weight = nw               # the loom keeps the weave pure
        spoke = {f.knot for f in r.fires}
        out = {lane: (1 if f"out_{lane}" in spoke else 0) for lane in DRUMS}
        best, bestm = 0, None
        for d in range(12):
            if f"out_b{d}" in spoke:
                vals = r.fringe(f"say_b{d}")
                m = float(vals[0]) if vals else 0.0
                if bestm is None or m > bestm:
                    best, bestm = d + 1, m
        out["bass"] = best
        return out, r

    # ------------------------------------------------------------- one bar

    def draw_jitter(self) -> dict:
        """One private jitter per hidden knot, held for the WHOLE bar.

        The reward is a bar-level scalar, so the perturbation that earns it must
        be a bar-level perturbation. Redrawing per step would correlate the
        verdict with noise the bar was not generated from.
        """
        p = self.perturber
        if p is None:
            return {}
        return {k: p.rng.gauss(0.0, p.sigma) for k in p.knots}

    def bar(self, xi: dict | None = None, verdict: float | None = 0.0,
            commit: bool = False):
        mem = {"kick": 0, "snare": 0, "hat": 0, "bass": 0}
        lanes = {"kick": [], "snare": [], "hat": [], "bass": []}
        results = []
        for pos in range(BAR):
            out, r = self.step(pos, mem, xi=xi, verdict=verdict, commit=commit)
            for lane in lanes:
                lanes[lane].append(out[lane])
            mem = out
            results.append(r)
        return lanes, results

    def play_and_learn(self, reward_fn) -> dict:
        """Generate a bar, have the world judge it, pay the cords. One trial.

        `reward_fn(bar) -> (verdict_for_the_loom, raw_score, report_dict)`
        """
        h = self.hyper
        xi = self.draw_jitter()
        bar, _ = self.bar(xi=xi, verdict=0.0, commit=False)              # PASS 1
        verdict, raw, report = reward_fn(bar)
        if h.rule == "frozen":
            return {"bar": bar, "report": report, "moved": 0.0}
        # THE BAR IS THE TRIAL, so the weights stand still for the whole of it.
        # Committing each step as it ran (the first version of this file) made
        # step 2 of the replay read cords that step 1 had already thickened, and
        # the replay diverged from the bar the judge actually scored -- caught by
        # the assertion below on the very first trial, which is why it is here.
        # So: run the 16 steps against FROZEN weights, collect what each step
        # would have changed, and apply the sum ONCE.
        w0 = [st.weight for st in self.strands]
        again, results = self.bar(xi=xi, verdict=verdict, commit=False)  # PASS 2
        if again != bar:
            # A loud failure, never a quiet one: pass 2 must reproduce pass 1.
            raise RuntimeError("replay diverged: the organ is not deterministic")
        delta = [0.0] * len(self.strands)
        for r in results:
            if r.learned is not None:
                for i, nw in enumerate(r.learned):
                    delta[i] += nw - w0[i]
        moved = 0.0
        for st, d in zip(self.strands, delta):
            if d:
                nw = min(st.ceil, max(st.floor, st.weight + d))
                moved += abs(nw - st.weight)
                st.weight = nw
        p = self.perturber
        if p is not None:
            b0 = p.baseline
            for r in results:
                p.baseline = b0          # all 16 credits see ONE baseline
                moved += p.credit(self.weave, r, raw, xi=xi)
            p.baseline = (1.0 - p.beta) * b0 + p.beta * float(raw)
        self.moved += moved
        return {"bar": bar, "report": report, "moved": moved}

    # ------------------------------------------------------------- weights

    def weights(self) -> list[float]:
        return [st.weight for st in self.strands]

    def load(self, ws: list[float]) -> None:
        if len(ws) != len(self.strands):
            raise ValueError(f"checkpoint has {len(ws)} weights, "
                             f"weave has {len(self.strands)} strands")
        for st, w in zip(self.strands, ws):
            st.weight = float(w)
