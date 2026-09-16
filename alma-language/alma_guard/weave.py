# -*- coding: utf-8 -*-
"""THE NETWORK. A classifier woven out of knots, threads and strands.

Nothing here is a rule about attacks. The shape is given; every weight is random
and small at the start, and every weight that ends up meaning something was moved
by `alma/loom.py` step 3 and 3b - a cord thickening when it helped its knot speak
and the world answered with pleasure, thinning when it helped and the world
answered with pain - or, since v0.2, by node perturbation (`alma/perturb.py`).

THE SHAPE (v0.1, `hidden=0`, kept bit for bit)
----------------------------------------------
    x0 .. x{W-1}   one knot per feature bucket. `pass`, `trigger any`.
                   Seeded with 1.0 when the feature is PRESENT, and not seeded
                   at all when it is absent - so an absent feature is a SILENT
                   knot. That silence is the whole of credit assignment in ALMA
                   (see encoding.py: the Hebbian term ignores spark size and
                   reads only whether a cord landed and whether its knot spoke).
    one            a knot seeded 1.0 on every message. Its cord is the learnable
                   bias. xor_pain.py found the same need: without an always-on
                   knot, a message with no active features puts nothing into the
                   weave and there is nothing for a verdict to land on.
    out0 .. outK   one head per class. `sum`, `trigger rise 0.0`: the head speaks
                   only when the evidence that reached it totals >= 0. Firing IS
                   the prediction; the value it speaks is the margin.
    say0 .. sayK   `fringe`. The hem: what the weave says out loud.

THE HIDDEN LAYER (v0.2, `hidden=H`)
-----------------------------------
    x_i  --(delay 1)-->   h0 .. h{H-1}   `sum`, `rise θ_j`, thresholds all above 0
    one  --(delay 1)-->   h_j            each hidden knot's own leaning
    h_j  --(delay k+1)--> out_k          the reading, staggered per head
    x_i  --(delay k+2)--> out_k          the v0.1 direct cords (`skip=True`), at the
    one  --(delay k+2)--> out_k          SAME distance as the hidden path - xor_pain.py
                                         paid once for a bias cord that arrived early

With `rule="perturbation"` the x->h and one->h cords carry `drift=0` and are
owned by node perturbation: each hidden knot gets a private jitter spark on
beat 2 and the verdict is correlated with it (`alma/perturb.py`). Every cord
into a head keeps the loom's three-factor rule, which is the correct rule at
an output. With `rule="three-factor"` every cord drifts - that arm is the
ablation that shows the wall, not a contender.

The initial x->h weights are uniform(±h_init/√typical), so a hidden knot's
net input has a spread of about h_init/√3 whatever the message length; each
starts life as a random hyperplane through the bag of features. `sigma` and
`eta` are stated in those units (see `GuardWeave.__init__`).

TIME-MULTIPLEXED CREDIT - the one real design invention of v0.1
---------------------------------------------------------------
A verdict in ALMA is ONE scalar and it reaches EVERY eligible cord at once. With
four heads wired at the same distance, a single verdict would tell all four heads
the same thing on the same beat, and one-vs-rest would be impossible. So head k's
cords are k+1 beats long (k+2 from the inputs when there is a hidden layer), and
on the beat it lands it is the only head holding a trace. One scalar verdict per
beat therefore addresses exactly one head. Nothing travels backwards.

WHAT IS GIVEN AND WHAT IS NOT
-----------------------------
GIVEN:     the shape - knots, heads, thresholds (`rise`), delays.
NOT GIVEN: every cord's weight. Random and small at the start.
NOT GIVEN: any gradient. Nothing travels backwards.
NOT GIVEN: any knowledge of what an attack looks like. Grep this file.
"""
from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma import Loom, Weave                                       # noqa: E402
from alma.loom import Strand, Thread                               # noqa: E402
from alma.perturb import NodePerturbation                          # noqa: E402

RULES = ("three-factor", "perturbation")


@dataclass
class Hyper:
    """Everything tunable, in one place, so RESULTS.md can print it."""
    width: int = 2048          # feature buckets == feature knots
    drift: float = 0.05        # how eligible one landing makes a cord
    init: float = 0.02         # head cords start uniform in [-init, +init]
    r_ok: float = 0.10         # pleasure when the head was right
    r_miss: float = 4.00       # pain when it stayed silent and should have spoken
    r_fa: float = 1.00         # pain when it spoke and should have stayed silent
    epochs: int = 30
    seed: int = 0
    # ---- v0.2
    hidden: int = 0            # hidden knots; 0 is the v0.1 one-layer weave exactly
    rule: str = "three-factor" # who owns the x->h cords: see the module docstring
    sigma: float = 0.5         # jitter, in units of a hidden knot's initial net spread
    eta: float = 0.02          # perturbation step, in the same units, per trial
    h_init: float = 1.0        # x->h init scale (times 1/sqrt(typical))
    spread: float = 0.5        # hidden thresholds span (0, spread × net spread]
    typical: int = 0           # typical count of present features; 0 = unknown
    skip: bool = True          # hidden weaves keep the v0.1 direct cords too

    def line(self) -> str:
        s = (f"width={self.width} drift={self.drift} init={self.init} "
             f"r_ok={self.r_ok} r_miss={self.r_miss} r_fa={self.r_fa} "
             f"epochs={self.epochs} seed={self.seed}")
        if self.hidden:
            s += (f" hidden={self.hidden} rule={self.rule} sigma={self.sigma} "
                  f"eta={self.eta} h_init={self.h_init} spread={self.spread} "
                  f"typical={self.typical} skip={self.skip}")
        return s


class GuardWeave:
    """A weave plus the small amount of bookkeeping a classifier needs."""

    def __init__(self, heads: list[str], hyper: Hyper, default: str = "benign"):
        if hyper.rule not in RULES:
            raise ValueError(f"unknown rule {hyper.rule!r}; one of {RULES}")
        if hyper.rule == "perturbation" and not hyper.hidden:
            raise ValueError(
                "rule='perturbation' needs a hidden layer (hidden > 0). At the heads "
                "the loom's three-factor rule is already the correct rule "
                "(xor_pain.py); perturbation exists for the knots it cannot reach.")
        self.heads = list(heads)
        self.hyper = hyper
        self.default = default
        self.loom = Loom()
        H = hyper.hidden
        # head k fires on beat out_beat0 + k; say_k records one beat later
        self.out_beat0 = 3 if H else 2
        self.horizon = len(self.heads) + (4 if H else 3)
        rng = random.Random(hyper.seed)
        self.weave = self._build(rng)
        self.strands = [st for t in self.weave.threads for st in t.strands]
        self.perturber: NodePerturbation | None = None
        self.moved = 0.0
        if hyper.rule == "perturbation":
            typ = max(1, hyper.typical)
            spread = self.net_spread()
            self.perturber = NodePerturbation(
                [f"h{j}" for j in range(H)],
                sigma=hyper.sigma * spread,
                # Σ_j Δw_ij over ~typ present cords moves net_i by
                # eta_raw·δ·ξ·typ; with ξ ~ sigma·spread that is eta·spread·δ
                eta=(hyper.eta / (typ * hyper.sigma)) if hyper.sigma else 0.0,
                beat=2, rng=random.Random(hyper.seed + 104729))

    # -------------------------------------------------------------- shape

    def net_spread(self) -> float:
        """Typical spread of a hidden knot's net input at initialisation."""
        return self.hyper.h_init / math.sqrt(3.0)

    def thresholds(self) -> list[float]:
        """Hidden thresholds, all ABOVE zero, spread over (0, spread × net spread].

        Found by running the XOR toy (tests/test_v02.py), 2026-09-11 18:3x: with
        thresholds straddling zero the weave stayed at chance. A hidden knot that
        fires below zero SPEAKS A NEGATIVE NUMBER, and the loom's Hebbian term at the
        head reads only whether a cord landed and whether the head fired - never the
        sign of what landed - so every cord from a negative-speaking knot was taught
        backwards. With every threshold positive, every hidden knot that speaks says
        something positive, and the head's three-factor rule is a proper
        reward-modulated perceptron again (xor_pain.py uses 0.5 / 1.5 for the same
        reason, without having written it down).
        """
        H, s = self.hyper.hidden, self.net_spread()
        return [round(self.hyper.spread * s * (j + 1) / (H + 1), 4) for j in range(H)]

    def _build(self, rng: random.Random) -> Weave:
        h = self.hyper
        w = Weave("alma-guard")
        for i in range(h.width):
            w.knot(f"x{i}", verb="pass", trigger="any")
        w.knot("one", verb="pass", trigger="any")
        if h.hidden:
            for j, th in enumerate(self.thresholds()):
                w.knot(f"h{j}", verb="sum", trigger=f"rise {th}")
        for k in range(len(self.heads)):
            w.knot(f"out{k}", verb="sum", trigger="rise 0.0")
            w.knot(f"say{k}", verb="fringe", trigger="any")

        def cord(delay: int, drift: float | None = None, init: float | None = None) -> Strand:
            a = h.init if init is None else init
            return Strand(weight=rng.uniform(-a, a), delay=delay,
                          drift=h.drift if drift is None else drift)

        if not h.hidden:
            # v0.1, byte for byte: same draws, same order, same cords
            for k in range(len(self.heads)):
                d = k + 1                   # THE STAGGER. See the module docstring.
                for i in range(h.width):
                    w.threads.append(Thread(f"x{i}", f"out{k}", "in", [cord(d)]))
                w.threads.append(Thread("one", f"out{k}", "in", [cord(d)]))
                # the hem is not part of the model: weight 1, drift 0
                w.threads.append(Thread(f"out{k}", f"say{k}", "in",
                                        [Strand(weight=1.0, delay=1)]))
            w.run_hint = len(self.heads) + 3
            return w

        a = h.h_init / math.sqrt(max(1, h.typical))
        hd = 0.0 if h.rule == "perturbation" else h.drift
        for i in range(h.width):
            for j in range(h.hidden):
                w.threads.append(Thread(f"x{i}", f"h{j}", "in", [cord(1, hd, a)]))
        for j in range(h.hidden):
            w.threads.append(Thread("one", f"h{j}", "in", [cord(1, hd, a)]))
        for k in range(len(self.heads)):
            d = k + 1                       # THE STAGGER, from the hidden layer
            for j in range(h.hidden):
                w.threads.append(Thread(f"h{j}", f"out{k}", "in", [cord(d)]))
            if h.skip:
                for i in range(h.width):
                    w.threads.append(Thread(f"x{i}", f"out{k}", "in", [cord(d + 1)]))
            w.threads.append(Thread("one", f"out{k}", "in", [cord(d + 1)]))
            w.threads.append(Thread(f"out{k}", f"say{k}", "in",
                                    [Strand(weight=1.0, delay=1)]))
        w.run_hint = self.horizon
        return w

    # -------------------------------------------------------------- running

    def _seed(self, feats: dict[int, float]) -> None:
        self.weave.seeds = []
        for b in feats:
            if 0 <= b < self.hyper.width:
                self.weave.seed(f"x{b}", 1.0, beat=1)
        self.weave.seed("one", 1.0, beat=1)

    def present(self, feats: dict[int, float], label: str | None,
                learn: bool) -> tuple[str, dict[int, float]]:
        """One message through the weave. Returns (prediction, per-head margin).

        When `learn`, the world answers on each head's own beat. The closure can
        read only what the weave DID - no cord reaches into it, so the learner
        does not get to decide whether it was right.
        """
        h = self.hyper
        self._seed(feats)
        n = len(self.heads)
        ob = self.out_beat0
        pert = self.perturber if learn else None
        if pert is not None:
            pert.jitter(self.weave)             # private noise, one spark per hidden knot

        def world(beat, fires_this_beat):
            if fires_this_beat is None:
                return None                     # every head was settled on its beat
            k = beat - ob                       # head k fires on beat ob+k
            if not (0 <= k < n):
                return None
            spoke = any(f.knot == f"out{k}" for f in fires_this_beat)
            want = (label == self.heads[k])
            if spoke == want:
                return h.r_ok
            return -h.r_miss if want else -h.r_fa

        r = self.loom.run(self.weave, beats=self.horizon,
                          verdict=world if learn else None)
        if learn and r.learned is not None:
            for st, nw in zip(self.strands, r.learned):
                st.weight = nw                  # the loom keeps the weave pure

        # read what the RUN did, never what the callback saw (xor_pain.py's scar)
        spoke = {f.knot for f in r.fires}
        margin: dict[int, float] = {}
        for k in range(n):
            if f"out{k}" in spoke:
                vals = r.fringe(f"say{k}")
                margin[k] = float(vals[0]) if vals else 0.0
        if not margin:
            pred = self.default
        else:
            pred = self.heads[max(margin, key=lambda k: margin[k])]

        if pert is not None:
            # ONE scalar for the whole trial, with the same asymmetry as the heads
            if pred == label:
                reward = h.r_ok
            elif label != self.default and pred == self.default:
                reward = -h.r_miss
            else:
                reward = -h.r_fa
            self.moved += pert.credit(self.weave, r, reward)
        return pred, margin

    def predict(self, feats: dict[int, float]) -> tuple[str, dict[int, float]]:
        return self.present(feats, None, learn=False)

    # -------------------------------------------------------------- weights

    def weights(self) -> list[float]:
        return [st.weight for st in self.strands]

    def load(self, ws: list[float]) -> None:
        if len(ws) != len(self.strands):
            raise ValueError(f"model has {len(ws)} weights, weave has "
                             f"{len(self.strands)} strands")
        for st, w in zip(self.strands, ws):
            st.weight = float(w)
