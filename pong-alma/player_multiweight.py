# -*- coding: utf-8 -*-
"""player_multiweight.py — Pong player with MULTI-WEIGHT neuromorphic edges.

100% ours. Pure Python 3 stdlib only. Deterministic when seeded.

Idea (straight from D:\\CLAUDE\\eran-neuron — rich_connection.py + neuron.py):
  "מה שמגדיר את היחס בינינו זה לא מספר" — a connection is NOT one scalar.
  Every edge in this net is a MultiWeightEdge carrying THREE channels that
  are COMBINED at transmit time, exactly like neuron.Connection.transmit:
     amp    — amplitude (real, +/-)            (the classic "weight")
     phase  — phase (rad): the delivered value is modulated by
              cos(phase - ctx_phase), an interference-like alignment
              against a context phase driven by the live ball position
     gate   — soft boolean relation in (0,1) via sigmoid (open/closed)
  transmit(signal, ctx_phase) = amp * cos(phase - ctx_phase) * gate * signal
  So one edge behaves DIFFERENTLY depending on where the ball is — a single
  scalar weight cannot do that. That is the multi-weight/rich-connection
  claim, made functional.

Architecture: obs(5) --edges--> hidden(6, tanh) --edges--> 3 logits -> argmax.
  48 edges x 3 channels + 9 biases/phase-refs = 153 learnable parameters.

LEARNING: (1+lambda) evolution strategies — all channels of all edges start
as seeded random noise and change ONLY through mutation + selection on
fitness (common episode seeds for fair comparison). Genuine learner; no
hand-scripted ball tracking anywhere.

Usage:
  python player_multiweight.py                 # quick train + report
  python player_multiweight.py --generations 60 --seed 7
"""

import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pong_env import PongEnv  # the shared env contract (do not re-implement)

OBS_N = 5
HID_N = 6
ACT_N = 3
CHANNELS = 3  # amp, phase, gate  — the multi-weight bundle per edge
N_EDGES = OBS_N * HID_N + HID_N * ACT_N            # 48
PARAM_COUNT = N_EDGES * CHANNELS + HID_N + ACT_N   # 153


def _scale(obs):
    """Raw env obs -> ~[-1,1] inputs (positions recentred, tiny velocity
    numbers brought to the same footing)."""
    bx, by, bvx, bvy, my = obs
    return (2.0 * bx - 1.0, 2.0 * by - 1.0, bvx / 0.025, bvy / 0.04,
            2.0 * my - 1.0)


def _sigmoid(x):
    if x < -30.0:
        return 0.0
    if x > 30.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


class MultiWeightEdge:
    """One connection = a bundle of channels, not a scalar (rich_connection)."""
    __slots__ = ("amp", "phase", "gate_raw")

    def __init__(self, amp, phase, gate_raw):
        self.amp = amp
        self.phase = phase
        self.gate_raw = gate_raw  # squashed to (0,1) at transmit time

    def transmit(self, signal, ctx_phase):
        # channels COMBINED: amplitude x phase-alignment x gate  (a la
        # neuron.Connection.transmit / rich_connection.transmit)
        align = math.cos(self.phase - ctx_phase)
        return self.amp * align * _sigmoid(self.gate_raw) * signal


class MultiWeightPlayer:
    """obs(5) -> 6 hidden (tanh) -> 3 logits, every edge multi-weight."""
    param_count = PARAM_COUNT

    def __init__(self, params=None):
        if params is None:
            params = [0.0] * PARAM_COUNT
        self.set_params(params)

    def set_params(self, vec):
        if len(vec) != PARAM_COUNT:
            raise ValueError("expected %d params, got %d" % (PARAM_COUNT, len(vec)))
        self._p = list(vec)
        i = 0
        self.e1 = []  # HID_N rows of OBS_N edges
        for _ in range(HID_N):
            row = []
            for _ in range(OBS_N):
                row.append(MultiWeightEdge(vec[i], vec[i + 1], vec[i + 2]))
                i += 3
            self.e1.append(row)
        self.e2 = []  # ACT_N rows of HID_N edges
        for _ in range(ACT_N):
            row = []
            for _ in range(HID_N):
                row.append(MultiWeightEdge(vec[i], vec[i + 1], vec[i + 2]))
                i += 3
            self.e2.append(row)
        self.b1 = list(vec[i:i + HID_N]); i += HID_N
        self.b2 = list(vec[i:i + ACT_N]); i += ACT_N

    def get_params(self):
        return list(self._p)

    def act(self, obs):
        x = _scale(obs)
        # context phase driven by the live ball x-position: the SAME edge
        # transmits differently as the ball approaches — multi-weight in action
        # (half-range so far-wall and my-goal-line get DISTINCT phases)
        ctx_phase = 0.5 * math.pi * x[0]       # x[0] = ball_x in [-1,1]
        h = []
        for j in range(HID_N):
            s = self.b1[j]
            row = self.e1[j]
            for k in range(OBS_N):
                s += row[k].transmit(x[k], ctx_phase)
            h.append(math.tanh(s))
        best_i = 0
        best_v = None
        for j in range(ACT_N):
            s = self.b2[j]
            row = self.e2[j]
            for k in range(HID_N):
                s += row[k].transmit(h[k], ctx_phase)
            if best_v is None or s > best_v:
                best_v = s
                best_i = j
        return best_i - 1  # {-1, 0, +1}


# ── fitness: self-play (same genome plays both mirrored sides) ──────────
def evaluate(params, seeds, max_ticks=300):
    """Average hits per side per episode. Higher = keeps rallies alive."""
    player = MultiWeightPlayer(params)
    total_hits = 0.0
    for sd in seeds:
        env = PongEnv(seed=sd)
        obsL, obsR = env.reset()
        done = False
        ticks = 0
        while not done and ticks < max_ticks:
            aL = player.act(obsL)
            aR = player.act(obsR)
            (obsL, obsR), rL, rR, done = env.step(aL, aR)
            if rL > 0:
                total_hits += 1
            if rR > 0:
                total_hits += 1
            ticks += 1
    return total_hits / (2.0 * len(seeds))


# ── learning: (1+lambda) evolution strategies over ALL edge channels ────
def train(generations=200, pop=10, episodes=14, sigma=0.30, seed=1, quiet=False):
    rng = random.Random(seed)
    best = [rng.gauss(0.0, 0.5) for _ in range(PARAM_COUNT)]  # random birth
    seeds = [1000 + e for e in range(episodes)]  # common random numbers
    best_fit = evaluate(best, seeds)
    fit0 = best_fit
    if not quiet:
        print("gen %3d  fitness=%.3f  (random newborn multi-weight net)" % (0, best_fit))
    for gen in range(1, generations + 1):
        improved = False
        for _ in range(pop):
            # per-gene mutation: touch ~35% of the channels — finer steps on
            # a 153-dim landscape than mutating every gene at once
            cand = [p + (rng.gauss(0.0, sigma) if rng.random() < 0.35 else 0.0)
                    for p in best]
            f = evaluate(cand, seeds)
            if f > best_fit:
                best, best_fit = cand, f
                improved = True
        if not quiet and (improved or gen % 10 == 0):
            print("gen %3d  fitness=%.3f%s" % (gen, best_fit,
                                               "  <- improved" if improved else ""))
    return best, fit0, best_fit


def main():
    ap = argparse.ArgumentParser(
        description="Multi-weight neuromorphic Pong player (ES-learned)")
    ap.add_argument("--generations", type=int, default=200)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--episodes", type=int, default=14)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 64)
    print("PLAYER-MULTIWEIGHT — rich multi-channel edges (amp/phase/gate)")
    print("=" * 64)
    print("edges=%d x %d channels  params=%d  learn=(1+%d)-ES  seed=%d"
          % (N_EDGES, CHANNELS, PARAM_COUNT, args.pop, args.seed))

    best, fit0, fit1 = train(args.generations, args.pop, args.episodes,
                             seed=args.seed)

    # held-out seeds = proof the learning generalizes past the training set
    held = evaluate(best, [5000 + e for e in range(10)])
    print("-" * 64)
    print("fitness before learning : %.3f  (avg hits/side/episode)" % fit0)
    print("fitness after  learning : %.3f  (train seeds)" % fit1)
    print("fitness held-out seeds  : %.3f  (10 unseen episodes)" % held)
    print("LEARNED: %s  (gain=%+.3f)" % ("YES" if fit1 > fit0 else "no", fit1 - fit0))

    # show one edge's multi-weight behaviour: same edge, ball far vs near
    p = MultiWeightPlayer(best)
    e = p.e1[0][0]
    far = e.transmit(1.0, 0.5 * math.pi * -1.0)   # ball at far wall
    near = e.transmit(1.0, 0.5 * math.pi * 1.0)   # ball at my goal line
    print("sample edge (amp=%.2f phase=%.2f gate=%.2f): unit signal -> "
          "%.3f when ball far, %.3f when ball near  <- one edge, many weights"
          % (e.amp, e.phase, _sigmoid(e.gate_raw), far, near))


if __name__ == "__main__":
    main()
