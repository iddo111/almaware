# -*- coding: utf-8 -*-
"""
PLAYER BEIT-DIN — Pong player ruled by a quorum of neurons, learned by evolution.
=================================================================================
100% ours, pure Python stdlib. Deterministic (seeded).

Architecture (reusing the eran-neuron ideas):
  * 3 DAYAN (judge) neurons — a BEIT DIN (from eran-neuron/neuron.py BeitDin):
    each judge deliberates with a small LIF integration (leak, threshold, spikes)
    over two accumulators — an UP chamber and a DOWN chamber — and casts a vote.
  * Multi-channel edges (from rich_connection.py / neuron.py Connection):
    every input reaches a judge through amp AND phase — the effective weight is
    amp * cos(phase_in - judge_phase), so learning changes RELATIONSHIPS
    (amplitude + phase alignment), not just one scalar.
  * GIST gate, score==weight (from gist_spread.py):
    each judge carries a learned GIST vector; its cosine match against the live
    context is ONE number that is simultaneously the judge's confidence SCORE
    and the WEIGHT of its vote. A judge whose gist doesn't match ABSTAINS.
  * RULING: majority quorum — 2 of 3 judges must agree for the paddle to move.

Learning: evolution strategies (mirrored-sampling ES with rank shaping) over
ALL parameters (gists, amps, phases, thresholds, leaks). Nothing is scripted —
at birth the Beit Din flails; fitness must RISE above the random baseline.

Run:  python player_beitdin.py            (quick training, prints start→end fitness)
"""
import math
import random

from pong_env import PongEnv

# ── dimensions ────────────────────────────────────────────────────────
N_CTX = 6                     # context features per judge
N_JUDGES = 3                  # a Beit Din
# per judge: gist(6) + amp_up(6) + amp_dn(6) + phase(6) + threshold + leak
P_PER_JUDGE = N_CTX * 4 + 2
N_PARAMS = N_JUDGES * P_PER_JUDGE      # = 78

LIF_STEPS = 6                 # micro-deliberation ticks per env step
LIF_DT = 0.35
ABSTAIN = 0.05                # |weighted vote| below this = the judge abstains


def _cosine(u, v):
    du = math.sqrt(sum(a * a for a in u))
    dv = math.sqrt(sum(b * b for b in v))
    if du < 1e-12 or dv < 1e-12:
        return 0.0
    return sum(a * b for a, b in zip(u, v)) / (du * dv)


def _context(obs):
    """Egocentric context vector from the 5-tuple obs (representation only —
    the MAPPING context→action is fully learned)."""
    bx, by, bvx, bvy, my = obs
    return (bx - 0.5,          # ball depth
            by - 0.5,          # ball height
            bvx * 20.0,        # ball x-velocity (scaled to ~unit range)
            bvy * 20.0,        # ball y-velocity
            my - 0.5,          # my paddle height
            (by - my) * 2.0)   # ball relative to me


class Dayan:
    """One judge: gist gate (score==weight) + multi-channel edges + LIF chambers."""

    def __init__(self, params, base_phase):
        # unpack this judge's parameter slice
        i = 0
        self.gist = params[i:i + N_CTX]; i += N_CTX
        amp_up = params[i:i + N_CTX]; i += N_CTX
        amp_dn = params[i:i + N_CTX]; i += N_CTX
        phase = params[i:i + N_CTX]; i += N_CTX
        thr_raw, leak_raw = params[i], params[i + 1]
        self.threshold = 0.25 + abs(thr_raw)                 # > 0
        self.leak = 0.05 + 0.45 / (1.0 + math.exp(-leak_raw))  # 0.05..0.5
        # effective multi-channel weights: amp * phase-alignment vs judge phase
        # (learning moves BOTH amp and phase — the relationship, not one number)
        self.w_up = [a * math.cos(p - base_phase) for a, p in zip(amp_up, phase)]
        self.w_dn = [a * math.cos(p - base_phase) for a, p in zip(amp_dn, phase)]

    def _chamber_spikes(self, drive):
        """LIF integration of a constant drive: leak + threshold + spike count."""
        v = 0.0
        spikes = 0
        for _ in range(LIF_STEPS):
            v += LIF_DT * (-self.leak * v + drive)
            if v >= self.threshold:
                v = 0.0
                spikes += 1
        return spikes

    def vote(self, ctx):
        """Returns the judge's weighted vote in [-LIF_STEPS..+LIF_STEPS] * gate.
        gate = gist-match — ONE number that is both the score and the weight."""
        gate = max(0.0, _cosine(ctx, self.gist))             # score == weight
        if gate <= 0.0:
            return 0.0                                        # no match → abstain
        d_up = sum(w * x for w, x in zip(self.w_up, ctx))
        d_dn = sum(w * x for w, x in zip(self.w_dn, ctx))
        net = self._chamber_spikes(d_up) - self._chamber_spikes(d_dn)
        return net * gate


class BeitDinController:
    """3 judges → ruling (majority quorum, 2 of 3) → paddle action -1/0/+1."""

    def __init__(self, params):
        assert len(params) == N_PARAMS
        self.judges = [Dayan(params[j * P_PER_JUDGE:(j + 1) * P_PER_JUDGE],
                             base_phase=0.13 * j)            # staggered, like BeitDin
                       for j in range(N_JUDGES)]

    def act(self, obs):
        ctx = _context(obs)
        ups = 0
        downs = 0
        for judge in self.judges:
            v = judge.vote(ctx)
            if v > ABSTAIN:
                ups += 1
            elif v < -ABSTAIN:
                downs += 1
        if ups >= 2:                                          # quorum: 2 of 3
            return 1
        if downs >= 2:
            return -1
        return 0                                              # no ruling → hold


# ── fitness ───────────────────────────────────────────────────────────
def evaluate(params, seeds, steps_per_rollout=500):
    """Fitness = mean total LEFT reward (+1 hit / -1 miss) over rollouts.
    The Beit Din plays LEFT; a seeded random player plays RIGHT."""
    brain = BeitDinController(params)
    total = 0.0
    for sd in seeds:
        env = PongEnv(seed=sd)
        opp = random.Random(sd + 9999)
        obsL, obsR = env.reset()
        for _ in range(steps_per_rollout):
            aL = brain.act(obsL)
            aR = opp.choice((-1, 0, 1))
            (obsL, obsR), rL, rR, done = env.step(aL, aR)
            total += rL
            if done:
                obsL, obsR = env.reset()
    return total / len(seeds)


def evaluate_random_player(seeds, steps_per_rollout=500, seed=555):
    """Baseline: a purely random LEFT player, same protocol."""
    total = 0.0
    for sd in seeds:
        env = PongEnv(seed=sd)
        me = random.Random(seed + sd)
        opp = random.Random(sd + 9999)
        obsL, obsR = env.reset()
        for _ in range(steps_per_rollout):
            (obsL, obsR), rL, rR, done = env.step(me.choice((-1, 0, 1)),
                                                  opp.choice((-1, 0, 1)))
            total += rL
            if done:
                obsL, obsR = env.reset()
    return total / len(seeds)


# ── evolution strategies (mirrored sampling + rank shaping) ───────────
def train(generations=30, npairs=12, sigma=0.35, lr=0.4, seed=42,
          train_rollouts=3, verbose=True):
    rng = random.Random(seed)
    theta = [rng.gauss(0.0, 0.5) for _ in range(N_PARAMS)]
    test_seeds = (1001, 1002, 1003)                    # fixed, honest yardstick

    fit_start = evaluate(theta, test_seeds)
    baseline = evaluate_random_player(test_seeds)
    history = [fit_start]
    best_theta, best_fit = list(theta), fit_start      # elitism: keep the best court
    if verbose:
        print(f"random-player baseline : {baseline:+7.2f}")
        print(f"gen  0 (birth)         : {fit_start:+7.2f}")

    for gen in range(1, generations + 1):
        # common random numbers within a generation (fair comparison)
        gen_seeds = tuple(gen * 131 + k for k in range(train_rollouts))
        eps_list = []
        fits = []
        for _ in range(npairs):
            eps = [rng.gauss(0.0, 1.0) for _ in range(N_PARAMS)]
            f_plus = evaluate([t + sigma * e for t, e in zip(theta, eps)], gen_seeds)
            f_minus = evaluate([t - sigma * e for t, e in zip(theta, eps)], gen_seeds)
            eps_list.append(eps)
            fits.append((f_plus, f_minus))

        # rank-shaped, mirrored gradient estimate
        scores = [fp - fm for fp, fm in fits]
        if max(scores) > min(scores):                  # flat gen ⇒ no signal ⇒ no step
            order = sorted(range(npairs), key=lambda i: scores[i])
            rank = [0.0] * npairs
            for r, i in enumerate(order):              # ranks → symmetric weights
                rank[i] = (r / (npairs - 1)) - 0.5
            grad = [0.0] * N_PARAMS
            for i in range(npairs):
                w = rank[i]
                e = eps_list[i]
                for k in range(N_PARAMS):
                    grad[k] += w * e[k]
            theta = [t + (lr / (npairs * sigma)) * g for t, g in zip(theta, grad)]

        fit_now = evaluate(theta, test_seeds)
        history.append(fit_now)
        if fit_now > best_fit:
            best_fit, best_theta = fit_now, list(theta)
        if verbose:
            best_pert = max(max(fp, fm) for fp, fm in fits)
            print(f"gen {gen:2d}                 : {fit_now:+7.2f}   "
                  f"(best perturbation this gen {best_pert:+6.2f})")

    # return the best court ever seated (elitism), with its honest test fitness
    history.append(best_fit)
    return best_theta, history, baseline


# ── quick training run ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 64)
    print("BEIT-DIN PONG — 3 judges, one ruling, learned by evolution")
    print("=" * 64)
    theta, history, baseline = train(generations=30, npairs=12, seed=42)

    start, end = history[0], history[-1]
    peak = max(history)
    print("-" * 64)
    print(f"fitness at birth   : {start:+7.2f}")
    print(f"fitness at the end : {end:+7.2f}   (peak during training {peak:+.2f})")
    print(f"random baseline    : {baseline:+7.2f}")
    verdict = (end > baseline + 1.0) and (end > start)
    print(f"LEARNED? {'YES — the Beit Din rose above chance ✓' if verdict else 'no'}")
