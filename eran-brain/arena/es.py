# -*- coding: utf-8 -*-
"""es.py — ONE evolution strategy, used identically by every arm.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Antithetic OpenAI-ES with rank normalisation and COMMON RANDOM NUMBERS: inside
a generation every candidate is evaluated on exactly the same episode seeds, so
the fitness differences are signal and not luck. Nothing here is arm-specific.

BUDGET is counted in ENVIRONMENT STEPS and it is the same for every arm on a
given task. Training stops the moment the budget is spent — mid-generation if
necessary — so no arm can quietly buy an extra generation.

Held-out discipline: the ES only ever sees TRAIN seeds. Evaluation seeds come
from a disjoint range and are opened once, at the end, per arm.
"""
import numpy as np


def rollout(agent, task_factory, seed, learn=True):
    """One episode. Returns (total_reward, n_steps, info-of-last-step, task)."""
    task = task_factory()
    obs = task.reset(seed)
    agent.reset_episode()
    total = 0.0
    steps = 0
    last = {}
    done = False
    while not done:
        a = agent.act(obs)
        obs, r, done, last = task.step(a)
        total += r
        steps += 1
        if learn:
            agent.learn(r, done)
        if steps > 5000:
            break
    return total, steps, last, task


def evaluate(agent, task_factory, seeds, learn=True):
    tot = 0.0
    steps = 0
    for s in seeds:
        t, n, _, _ = rollout(agent, task_factory, s, learn=learn)
        tot += t
        steps += n
    return tot / max(1, len(seeds)), steps


def train_es(agent, task_factory, budget_steps, seed=0,
             pop=24, sigma=0.12, lr=0.06, eps_per_gen=24,
             train_seed_lo=0, train_seed_hi=1_000_000,
             hard_reset_each=True):
    """Evolve ``agent.theta``. Returns (best_theta, history, steps_used, gens).

    ``hard_reset_each``: online agents (ERAN) must start every candidate
    evaluation as a newborn, otherwise a candidate inherits the previous one's
    memory and the fitness is not the candidate's. ES arms have no such state.
    """
    rng = np.random.default_rng(seed)
    theta = np.asarray(agent.theta, dtype=np.float64).copy()
    n = len(theta)
    half = max(1, pop // 2)
    used = 0
    hist = []
    gen = 0
    best_theta, best_fit = theta.copy(), -1e18

    while used < budget_steps:
        gen += 1
        gen_seeds = rng.integers(train_seed_lo, train_seed_hi, eps_per_gen)
        eps = rng.normal(0.0, 1.0, (half, n))
        fits = np.zeros(2 * half)
        for k in range(half):
            for sgn_i, sgn in enumerate((1.0, -1.0)):
                cand = theta + sgn * sigma * eps[k]
                agent.set_params(cand)
                if hard_reset_each and hasattr(agent, "hard_reset"):
                    agent.hard_reset()
                f, st = evaluate(agent, task_factory, gen_seeds, learn=True)
                fits[k * 2 + sgn_i] = f
                used += st
            if used >= budget_steps:
                fits = fits[:(k + 1) * 2]
                eps = eps[:k + 1]
                half = k + 1
                break

        # rank-normalise to [-0.5, 0.5]; robust to reward scale
        order = np.argsort(np.argsort(fits))
        ranks = order / max(1, len(fits) - 1) - 0.5
        grad = np.zeros(n)
        for k in range(len(eps)):
            grad += (ranks[k * 2] - ranks[k * 2 + 1]) * eps[k]
        theta = theta + lr / (len(eps) * sigma + 1e-9) * grad

        mean_fit = float(np.mean(fits))
        hist.append(round(mean_fit, 4))
        if mean_fit > best_fit:
            best_fit, best_theta = mean_fit, theta.copy()
        half = max(1, pop // 2)

    agent.set_params(best_theta)
    if hasattr(agent, "hard_reset"):
        agent.hard_reset()
    return best_theta, hist, used, gen


def train_online(agent, task_factory, budget_steps, seed=0,
                 train_seed_lo=0, train_seed_hi=1_000_000):
    """A purely online arm just LIVES for the budget. Same number of env steps
    as every ES arm gets; no evolution, no gradients."""
    rng = np.random.default_rng(seed)
    used = 0
    curve = []
    acc_win = []
    while used < budget_steps:
        s = int(rng.integers(train_seed_lo, train_seed_hi))
        t, n, last, _ = rollout(agent, task_factory, s, learn=True)
        used += n
        acc_win.append(t)
        if len(acc_win) >= 200:
            curve.append(round(float(np.mean(acc_win)), 4))
            acc_win = []
    return hist_trim(curve), used


def hist_trim(c, k=40):
    if len(c) <= k:
        return c
    step = len(c) / k
    return [c[min(len(c) - 1, int(i * step))] for i in range(k)]
