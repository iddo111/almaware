"""NODE PERTURBATION — per-knot credit, and nothing travels backwards.

v0.6 of the loom's learning path. One class, `NodePerturbation`, used by the
holobrain's organs (`alma_guard`, `alma_reason`) and by `xor_pain.py`.

THE WALL THIS EXISTS FOR
------------------------
`Loom.run(..., verdict=...)` (v0.5, כאב ועונג) gives every eligible cord the same
scalar on the same beat. At an OUTPUT knot that is a correct reward-modulated
perceptron. At a HIDDEN knot it is no credit assignment at all: one global number
cannot tell h0 "you should have fired" while telling h1 the opposite. That wall
was measured three times — XOR on 2026-09-10 (0/8 starts), the security organ's
4-class head and the reasoning organ's three-factor arm on 2026-09-11.

THE RULE
--------
Each target knot i gets its own private random jitter ξ_i ~ N(0, σ) every trial.
The jitter is an ordinary SPARK, seeded into the knot's own tray on the beat its
evidence lands — so it passes through the `rise` threshold and can change whether
the knot speaks at all. The trial runs. The world answers with one scalar R. Then

    Δw_ij  =  η · (R − R̄) · ξ_i · x_j

for every cord j → i whose source actually spoke x_j on the beat that made its
spark land on i's jitter beat. R̄ is a running mean of R (the learner's own
expectation, not the world's opinion). Because ξ_i is private to knot i, the
credit is private too: it is the REINFORCE / weight-perturbation estimator
(Williams 1992) of ∂E[R]/∂w_ij, and it is local.

WHY THIS DOES NOT BREAK THE FIRST LAW
-------------------------------------
ξ_i went FORWARD in time, like every spark in ALMA. The update reads only three
things that are all local to the cord: what its source said, the noise its own
destination received, and the one scalar the world answered. No error is carried
back through any cord. The loom itself is unchanged; this composes with it:

    np = NodePerturbation(["h0", "h1"], sigma=0.3, eta=0.01, beat=2, rng=rng)
    np.jitter(weave)                       # private noise, as sparks
    result = loom.run(weave, beats=8, verdict=...)
    np.credit(weave, result, reward)       # per-knot credit, then forget the noise

WHAT IT DOES NOT DO
-------------------
* It is a gradient ESTIMATOR, not a gradient: its variance grows with the number
  of knots perturbed at once. Honest numbers live in each organ's RESULTS.md.
* Only `sum`-like knots with a `rise` trigger make sense as targets. A jitter
  spark into a `pass`/`any` knot would make it fire on noise alone.
* It does not touch spark SIZE rules of the Hebbian term; the three-factor rule
  still owns every cord with `drift != 0`. Give the cords this rule owns
  `drift = 0` unless you mean both rules to act on them.
"""
from __future__ import annotations

import random
from collections import defaultdict

from .chords import total
from .loom import STRAND_CEIL, STRAND_FLOOR, Result, Weave


class NodePerturbation:
    """Private jitter per knot per trial; the verdict correlated with it."""

    def __init__(self, knots, *, sigma: float, eta: float,
                 beat: "int | dict[str, int]" = 2,
                 rng: random.Random | None = None, beta: float = 0.05,
                 baseline: float = 0.0,
                 floor: float = STRAND_FLOOR, ceil: float = STRAND_CEIL):
        self.knots = list(knots)
        if not self.knots:
            raise ValueError("node perturbation needs at least one target knot")
        if sigma < 0 or eta < 0:
            raise ValueError("sigma and eta must be >= 0")
        self.sigma = float(sigma)
        self.eta = float(eta)
        self.beats = ({k: int(beat) for k in self.knots} if isinstance(beat, int)
                      else {k: int(beat[k]) for k in self.knots})
        self.rng = rng or random.Random(0)
        self.beta = float(beta)
        self.baseline = float(baseline)
        self.floor, self.ceil = float(floor), float(ceil)
        self._last: dict[str, float] = {}
        self._seeded: list = []

    # ------------------------------------------------------------ the noise

    def jitter(self, weave: Weave) -> dict[str, float]:
        """Draw ξ_i for every target knot (in the order given) and seed it.

        The draw order is part of the contract: it is what lets an organ swap its
        private implementation for this one and get bit-identical weights.
        """
        xi = {}
        for k in self.knots:
            if k not in weave.knots:
                raise ValueError(f"perturbation target '{k}' is not a knot")
            x = self.rng.gauss(0.0, self.sigma)
            xi[k] = x
            weave.seed(k, x, beat=self.beats[k])
            self._seeded.append(weave.seeds[-1])
        self._last = xi
        return xi

    def forget(self, weave: Weave) -> None:
        """Take this trial's noise sparks back out of the weave's seeds."""
        if self._seeded:
            ids = {id(s) for s in self._seeded}
            weave.seeds = [s for s in weave.seeds if id(s) not in ids]
        self._seeded = []

    # ------------------------------------------------------------ the credit

    def index(self, weave: Weave) -> dict[str, dict[tuple[str, int], list]]:
        """target knot -> {(source knot, delay): [strands]}, built once per weave."""
        key = ("_alma_perturb_index", tuple(self.knots))
        cache = getattr(weave, "_alma_perturb_cache", None)
        if cache is not None and cache[0] == key and cache[1] == len(weave.threads):
            return cache[2]
        targets = set(self.knots)
        idx: dict[str, dict[tuple[str, int], list]] = {k: defaultdict(list)
                                                        for k in self.knots}
        for t in weave.threads:
            if t.dst in targets and t.port == "in":
                for st in t.strands:
                    idx[t.dst][(t.src, int(st.delay))].append(st)
        weave._alma_perturb_cache = (key, len(weave.threads), idx)
        return idx

    @staticmethod
    def spoken(result: Result) -> dict[tuple[int, str], float]:
        """(beat, knot) -> what the knot said, for every knot that SPOKE."""
        out = {}
        for f in result.fires:
            if f.spoke is None:
                continue
            v = f.spoke
            out[(f.beat, f.knot)] = float(v) if isinstance(v, (int, float)) else total([v])
        return out

    def credit(self, weave: Weave, result: Result, reward: float,
               xi: dict[str, float] | None = None) -> float:
        """Correlate the world's answer with each knot's OWN noise.

        Returns Σ|Δw| so a run can prove its weights moved instead of assuming it.
        """
        xi = self._last if xi is None else xi
        delta = float(reward) - self.baseline
        said = self.spoken(result)
        moved = 0.0
        if delta and self.eta:
            idx = self.index(weave)
            by_beat: dict[int, list[tuple[str, float]]] = defaultdict(list)
            for (b, k), v in said.items():
                by_beat[b].append((k, v))
            for k, x in xi.items():
                step = self.eta * delta * x
                if not step:
                    continue
                cords = idx[k]
                jb = self.beats[k]
                # only the sources that spoke on a beat whose spark lands on jb
                for (src, d), strands in cords.items():
                    pre = said.get((jb - d, src))
                    if not pre:
                        continue
                    for st in strands:
                        new = st.weight + step * pre
                        new = self.ceil if new > self.ceil else (
                            self.floor if new < self.floor else new)
                        moved += abs(new - st.weight)
                        st.weight = new
        self.baseline = (1.0 - self.beta) * self.baseline + self.beta * float(reward)
        self.forget(weave)
        return moved
