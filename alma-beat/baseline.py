# -*- coding: utf-8 -*-
"""THE VANILLA CONTROL. Standing rule, Iddo 2026-07-02: "וגם תאמן מודל וונילה
להשוות" -- and if ours loses, say so.

Same 32 inputs, bit for bit. Same decision rule (a head fires when its logit is
>= 0; the bass degree is the loudest head that fired, rest if none did). Same
judge, same trials, same seeds. EXACTLY the same number of free parameters as
the weave has learnable cords -- 32*H + 15*H + 32*15, counted and asserted, not
assumed.

The ONLY thing that differs is what learns: this is REINFORCE with an EMA
baseline on a real log-likelihood -- a true policy gradient, computed by the
chain rule, travelling backwards. It is the "what would anyone normally do" bar,
and it is the one ALMA has to be measured against honestly rather than the one
it is likely to beat.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

BAR = 16
DRUMS = ("kick", "snare", "hat")
NHEAD = 15                 # kick, snare, hat, b0..b11
NIN = 32                   # p0..p15, one, mk, ms, mh, mb0..mb11


def _sig(z: float) -> float:
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


@dataclass
class VHyper:
    hidden: int = 32
    lr: float = 0.02
    seed: int = 0
    gain: float = 1.0          # kept for symmetry; REINFORCE uses raw advantage


class VanillaBeat:
    """A 32 -> H -> 15 policy with a skip path, trained by REINFORCE."""

    def __init__(self, hyper: VHyper):
        self.hyper = hyper
        H = hyper.hidden
        rng = random.Random(hyper.seed)
        a = 1.0 / math.sqrt(5.0)               # same scale as the weave's x->h
        self.W1 = [[rng.uniform(-a, a) for _ in range(H)] for _ in range(NIN)]
        self.W2 = [[rng.uniform(-0.02, 0.02) for _ in range(NHEAD)] for _ in range(H)]
        self.WS = [[rng.uniform(-0.02, 0.02) for _ in range(NHEAD)] for _ in range(NIN)]
        self.baseline = 0.0
        self.beta = 0.05

    def n_params(self) -> int:
        H = self.hyper.hidden
        return NIN * H + H * NHEAD + NIN * NHEAD

    # ------------------------------------------------------------- encoding
    @staticmethod
    def feats(pos: int, mem: dict) -> list[int]:
        f = [0] * NIN
        f[pos] = 1
        f[16] = 1                              # "one"
        for off, lane in enumerate(DRUMS):
            if mem.get(lane):
                f[17 + off] = 1
        d = mem.get("bass", 0)
        if d:
            f[20 + (d - 1)] = 1
        return f

    # ------------------------------------------------------------- one step
    def _forward(self, f: list[int]):
        H = self.hyper.hidden
        on = [i for i, v in enumerate(f) if v]
        hpre = [sum(self.W1[i][j] for i in on) for j in range(H)]
        hid = [math.tanh(z) for z in hpre]
        logit = []
        for k in range(NHEAD):
            z = sum(hid[j] * self.W2[j][k] for j in range(H))
            z += sum(self.WS[i][k] for i in on)
            logit.append(z)
        return on, hpre, hid, logit

    def bar(self, rng: random.Random, record: bool = True):
        mem = {"kick": 0, "snare": 0, "hat": 0, "bass": 0}
        lanes = {"kick": [], "snare": [], "hat": [], "bass": []}
        tape = []
        for pos in range(BAR):
            f = self.feats(pos, mem)
            on, hpre, hid, logit = self._forward(f)
            fired = []
            for k in range(NHEAD):
                p = _sig(logit[k])
                fired.append(1 if rng.random() < p else 0)
            out = {lane: fired[i] for i, lane in enumerate(DRUMS)}
            best, bestm = 0, None
            for d in range(12):
                if fired[3 + d] and (bestm is None or logit[3 + d] > bestm):
                    best, bestm = d + 1, logit[3 + d]
            out["bass"] = best
            for lane in lanes:
                lanes[lane].append(out[lane])
            if record:
                tape.append((on, hid, logit, fired))
            mem = out
        return lanes, tape

    # ------------------------------------------------------------- REINFORCE
    def learn(self, tape, advantage: float) -> float:
        """d/dw [ log pi ] * A, with pi = prod_k Bernoulli(sigmoid(logit_k))."""
        H = self.hyper.hidden
        lr = self.hyper.lr
        moved = 0.0
        for on, hid, logit, fired in tape:
            g = [(fired[k] - _sig(logit[k])) * advantage for k in range(NHEAD)]
            # heads
            for k in range(NHEAD):
                gk = lr * g[k]
                if not gk:
                    continue
                for j in range(H):
                    d = gk * hid[j]
                    self.W2[j][k] += d
                    moved += abs(d)
                for i in on:
                    self.WS[i][k] += gk
                    moved += abs(gk)
            # hidden, through tanh'
            for j in range(H):
                gh = sum(g[k] * self.W2[j][k] for k in range(NHEAD)) * (1.0 - hid[j] ** 2)
                d = lr * gh
                if not d:
                    continue
                for i in on:
                    self.W1[i][j] += d
                    moved += abs(d)
        return moved

    def play_and_learn(self, reward_fn, rng: random.Random) -> dict:
        bar, tape = self.bar(rng)
        _verdict, raw, report = reward_fn(bar)
        adv = float(raw) - self.baseline
        moved = self.learn(tape, adv)
        self.baseline = (1.0 - self.beta) * self.baseline + self.beta * float(raw)
        return {"bar": bar, "report": report, "moved": moved}

    def weights(self) -> list[float]:
        return ([x for row in self.W1 for x in row] +
                [x for row in self.W2 for x in row] +
                [x for row in self.WS for x in row])

    def load(self, ws: list[float]) -> None:
        H = self.hyper.hidden
        n1, n2 = NIN * H, H * NHEAD
        if len(ws) != self.n_params():
            raise ValueError("checkpoint size mismatch")
        it = iter(ws)
        self.W1 = [[next(it) for _ in range(H)] for _ in range(NIN)]
        self.W2 = [[next(it) for _ in range(NHEAD)] for _ in range(H)]
        self.WS = [[next(it) for _ in range(NHEAD)] for _ in range(NIN)]
