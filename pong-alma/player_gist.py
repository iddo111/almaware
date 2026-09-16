# -*- coding: utf-8 -*-
"""player_gist.py — Pong player whose controller is GIST RETRIEVAL.

100% ours. Pure Python 3 stdlib only. Deterministic when seeded.

Idea (straight from D:\\CLAUDE\\eran-neuron\\gist_spread.py — Iddo's principle):
  * The brain works on CONTEXT.  Here the CONTEXT is the live ball-state
    observation (ball_x, ball_y, ball_vx, ball_vy, my_paddle_y).
  * Retrieval runs by context toward the matching GIST: a small library of
    learned prototype vectors, each tied to an ACTION in {-1, 0, +1}.
  * score == weight : the gist-match (positive cosine vs the context) is
    SIMULTANEOUSLY the retrieval score and the weight of that gist —
    one number, exactly as in gist_spread.ConceptNode.match().
  * The BEST-matching gist wins the retrieval, and ITS action is played.

LEARNING (honest — unlike gist_spread's hand-set vectors, these are LEARNED):
  The prototypes AND their action codes start as seeded random noise and are
  optimized by (1+lambda) evolution strategies: mutate, evaluate on common
  episode seeds, keep the fittest. Nothing is hand-scripted: no "follow the
  ball" rule exists anywhere in this policy — behaviour emerges purely from
  selection on fitness.

Usage:
  python player_gist.py                 # quick train + report
  python player_gist.py --generations 60 --seed 7
"""

import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pong_env import PongEnv  # the shared env contract (do not re-implement)

OBS_N = 5          # context dimension = ball-state observation
N_GISTS = 12       # size of the learned gist library
# genome per gist: OBS_N prototype components + 1 action code
PARAM_COUNT = N_GISTS * (OBS_N + 1)


def _scale(obs):
    """Raw env obs -> comparable ~[-1,1] context axes (cosine needs equal
    footing between positions and the tiny velocity numbers)."""
    bx, by, bvx, bvy, my = obs
    return (2.0 * bx - 1.0, 2.0 * by - 1.0, bvx / 0.025, bvy / 0.04,
            2.0 * my - 1.0)


def _cosine(u, v):
    du = math.sqrt(sum(a * a for a in u))
    dv = math.sqrt(sum(b * b for b in v))
    if du < 1e-12 or dv < 1e-12:
        return 0.0
    return sum(a * b for a, b in zip(u, v)) / (du * dv)


class GistPlayer:
    """Context -> gist retrieval -> action.

    score == weight: gate_k = max(0, cosine(context, gist_k)) is both the
    match score and the retrieval weight; argmax-gate gist's action plays.
    """
    param_count = PARAM_COUNT

    def __init__(self, params=None):
        if params is None:
            params = [0.0] * PARAM_COUNT
        self.set_params(params)

    def set_params(self, vec):
        if len(vec) != PARAM_COUNT:
            raise ValueError("expected %d params, got %d" % (PARAM_COUNT, len(vec)))
        self._p = list(vec)
        self.gists = []    # learned prototype vectors (the gist library)
        self.actions = []  # learned action code per gist
        i = 0
        for _ in range(N_GISTS):
            self.gists.append(vec[i:i + OBS_N])
            i += OBS_N
            self.actions.append(vec[i])
            i += 1

    def get_params(self):
        return list(self._p)

    @staticmethod
    def _decode_action(code):
        # continuous learned code -> discrete action {-1, 0, +1}
        if code > 0.33:
            return 1
        if code < -0.33:
            return -1
        return 0

    def act(self, obs):
        # retrieval by context: one number per gist = score = weight
        ctx = _scale(obs)
        best_gate = -1.0
        best_k = 0
        for k in range(N_GISTS):
            gate = max(0.0, _cosine(ctx, self.gists[k]))   # score == weight
            if gate > best_gate:
                best_gate = gate
                best_k = k
        # the best-matching gist's action is played
        return self._decode_action(self.actions[best_k])

    def retrieve(self, obs):
        """Introspection: (winner_index, gate, action) — for viz/debug."""
        ctx = _scale(obs)
        gates = [max(0.0, _cosine(ctx, g)) for g in self.gists]
        k = max(range(N_GISTS), key=lambda i: gates[i])
        return k, gates[k], self._decode_action(self.actions[k])


# ── fitness: self-play (same genome plays both mirrored sides) ──────────
def evaluate(params, seeds, max_ticks=300):
    """Average hits per side per episode. Higher = keeps rallies alive."""
    player = GistPlayer(params)
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


# ── learning: (1+lambda) evolution strategies over the gist library ─────
def train(generations=60, pop=10, episodes=14, sigma=0.35, seed=1, quiet=False):
    rng = random.Random(seed)
    best = [rng.gauss(0.0, 0.5) for _ in range(PARAM_COUNT)]  # random birth
    seeds = [1000 + e for e in range(episodes)]  # common random numbers
    best_fit = evaluate(best, seeds)
    fit0 = best_fit
    if not quiet:
        print("gen %3d  fitness=%.3f  (random newborn gist library)" % (0, best_fit))
    for gen in range(1, generations + 1):
        improved = False
        for _ in range(pop):
            cand = [p + rng.gauss(0.0, sigma) for p in best]
            f = evaluate(cand, seeds)
            if f > best_fit:
                best, best_fit = cand, f
                improved = True
        if not quiet and (improved or gen % 10 == 0):
            print("gen %3d  fitness=%.3f%s" % (gen, best_fit,
                                               "  <- improved" if improved else ""))
    return best, fit0, best_fit


def main():
    ap = argparse.ArgumentParser(description="GIST-retrieval Pong player (ES-learned)")
    ap.add_argument("--generations", type=int, default=60)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--episodes", type=int, default=14)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 64)
    print("PLAYER-GIST — context->gist retrieval controller (score==weight)")
    print("=" * 64)
    print("gists=%d  params=%d  learn=(1+%d)-ES  seed=%d"
          % (N_GISTS, PARAM_COUNT, args.pop, args.seed))

    best, fit0, fit1 = train(args.generations, args.pop, args.episodes,
                             seed=args.seed)

    # held-out seeds = proof the learning generalizes past the training set
    held = evaluate(best, [5000 + e for e in range(10)])
    print("-" * 64)
    print("fitness before learning : %.3f  (avg hits/side/episode)" % fit0)
    print("fitness after  learning : %.3f  (train seeds)" % fit1)
    print("fitness held-out seeds  : %.3f  (10 unseen episodes)" % held)
    print("LEARNED: %s  (gain=%+.3f)" % ("YES" if fit1 > fit0 else "no", fit1 - fit0))

    # show the retrieval in action (one tick, left side)
    env = PongEnv(seed=42)
    obsL, _ = env.reset()
    p = GistPlayer(best)
    k, gate, a = p.retrieve(obsL)
    print("sample retrieval: context=%s -> gist#%d (score==weight=%.3f) -> action=%+d"
          % (tuple(round(x, 3) for x in obsL), k, gate, a))


if __name__ == "__main__":
    main()
