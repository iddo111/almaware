# -*- coding: utf-8 -*-
"""structural_probe.py — measure what each ES knob MEANS, per task, from the
task's own mechanics. No accuracy is read anywhere in this file.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

WHY THIS FILE EXISTS, AND WHY IT READS NO RESULTS.
The first decode audit (decode_audit.py, 2026-08-22 01:00) set several bounds
by looking at which knob values the *succeeding seeds* happened to use --
"1.5 sits just above the best success", "3.0 keeps 2x headroom above the best
success". Those bounds were then scored on THE SAME 24 seeds. That is
selection on the outcome: it cannot help but produce a high success rate, and
the number it produces is not evidence about the range.

This file is the replacement evidence base. Every quantity here is derived
from tasks.py + eran_agent.py mechanics ONLY:

  * how loud the context channel actually is inside the L2-normalised key,
    measured by running the real update on real observations (probe_ctx);
  * how much of a DMS cue physically survives `delay` blank steps (probe_dms_cue);
  * how long credit must reach in each task to connect an action to its
    reward, measured from the environment's own timing (probe_credit_horizon);
  * whether a PERFECT greedy policy can still pass RuleSwitchTask's own
    8-of-10 criterion at a given residual exploration rate (probe_eps_floor);
  * where the spawn tolerance falls below any cosine the task can produce, so
    the organism can never differentiate again (probe_strict);
  * which regions of the joint decode are DEGENERATE -- a knob that provably
    does nothing (probe_degenerate).

Run:  python structural_probe.py            (writes results/STRUCTURAL-PROBE-*.json)
"""
import json
import math
import os
import random as _random

import numpy as np

from tasks import DMSTask, RuleSwitchTask, PongTask
from eran_agent import (EranAgent, decode, PARAM_NAMES, TOLERANCE_MIN_SD,
                        TOLERANCE_WARMUP, STRICTNESS_INFANT, STRICTNESS_ADULT,
                        CRITICAL_PERIOD_BEATS)

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")

# the three arena tasks, at the settings run_arena.py actually uses
DMS_DELAYS = (0, 1, 2, 4, 8, 16)          # run_arena.DELAYS
RULE = RuleSwitchTask
PONG_TICKS = 200                           # run_arena PongTask(ticks=200)


def _task(name, **kw):
    if name == "dms":
        return DMSTask(kw.get("delay", 0))
    if name == "rule":
        return RuleSwitchTask()
    if name == "pong":
        return PongTask(PONG_TICKS)
    raise ValueError(name)


# ───────────────────────────────────────────────────────────────────────────
# 1. CONTEXT LOUDNESS.  key = [obs | ctx_gain * ctx], then L2-normalised.
#    The physically meaningful quantity is not lam or ctx_gain separately but
#    the SHARE of the unit key that the context block occupies. Measured by
#    running eran_agent's own update on the real observation stream.
# ───────────────────────────────────────────────────────────────────────────
def probe_ctx(seed=1234, steps=4000):
    """For a grid of lam, measure ||ctx|| / ||obs|| on each task's real stream,
    with a random policy. ctx_gain then scales this linearly, so the context's
    share of the unit key is  share = g*R / sqrt(1 + (g*R)^2)  where R is the
    measured ||ctx||/||obs||."""
    out = {}
    lams = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
            0.95, 0.99, 0.999, 0.9999]
    for tname in ("rule", "dms16", "pong"):
        rng = np.random.default_rng(seed)
        if tname == "dms16":
            task, kw = _task("dms", delay=16), {}
        else:
            task = _task(tname)
        obs_stream = []
        obs = task.reset(seed)
        for _ in range(steps):
            obs_stream.append(np.asarray(obs, dtype=np.float64))
            a = int(rng.integers(task.n_actions))
            obs, r, done, info = task.step(a)
            if done:
                obs = task.reset(int(rng.integers(1_000_000)))
        obs_stream = np.array(obs_stream)
        obs_norm = float(np.mean(np.linalg.norm(obs_stream, axis=1)))

        per_lam = {}
        for lam in lams:
            ctx = np.zeros(obs_stream.shape[1])
            norms = []
            for o in obs_stream:
                # eran_agent updates ctx AFTER forming the key, so the norm we
                # care about is the one the NEXT key sees.
                norms.append(float(np.linalg.norm(ctx)))
                ctx = lam * ctx + (1.0 - lam) * o
            # discard the burn-in: first 10 horizons or 10% of stream
            burn = min(len(norms) // 10, int(10.0 / max(1e-9, 1.0 - lam)) + 1)
            tail = norms[burn:] or norms
            R = float(np.mean(tail)) / obs_norm
            per_lam[str(lam)] = {
                "ctx_over_obs": round(R, 6),
                "horizon_1_over_1_minus_lam": round(1.0 / max(1e-9, 1.0 - lam), 3),
                # share of the unit key taken by the context block, per gain
                "share_at_gain": {str(g): round((g * R) / math.sqrt(1.0 + (g * R) ** 2), 4)
                                  for g in (0.1, 0.5, 1.0, 2.0, 3.0, 4.0, 8.1)},
            }
        out[tname] = {"obs_norm_mean": round(obs_norm, 4),
                      "n_obs": int(obs_stream.shape[1]),
                      "per_lam": per_lam}
    return out


# ───────────────────────────────────────────────────────────────────────────
# 2. DMS CUE SURVIVAL.  The whole point of mode="ctx" on DMS is that the cue,
#    seen at t=0 and gone from t=1, must still be readable in ctx at the
#    choice step t=delay. Measure the cue block's share of the key there.
# ───────────────────────────────────────────────────────────────────────────
def probe_dms_cue(seed=7, episodes=200):
    """At the CHOICE step, how much of the unit key is the remembered cue?
    Reported against the discrimination the prototype must make: two keys that
    differ only in which cue was shown differ by exactly this component."""
    out = {}
    cue_slot = 3
    N = DMSTask.N_ITEMS
    for delay in DMS_DELAYS:
        if delay == 0:
            continue                       # cue is present in the observation
        row = {}
        for lam in (0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99):
            rng = np.random.default_rng(seed)
            fracs = []
            for ep in range(episodes):
                task = DMSTask(delay)
                obs = task.reset(int(rng.integers(1_000_000)))
                ctx = np.zeros(task.n_obs)
                for t in range(delay + 1):
                    o = np.asarray(obs, dtype=np.float64)
                    if t == delay:
                        # key the agent forms ON the choice step
                        cue_energy = float(ctx[cue_slot:cue_slot + N].sum())
                        fracs.append(cue_energy)
                        break
                    ctx = lam * ctx + (1.0 - lam) * o
                    obs, r, done, info = task.step(int(rng.integers(2)))
            row[str(lam)] = round(float(np.mean(fracs)), 6)
        out[str(delay)] = row
    # the lam whose horizon matches the delay, for reference
    out["_lam_matching_delay"] = {str(d): round(1.0 - 1.0 / d, 4)
                                  for d in DMS_DELAYS if d > 0}
    return out


# ───────────────────────────────────────────────────────────────────────────
# 3. CREDIT HORIZON.  trace_tau is an eligibility horizon in STEPS. How many
#    steps actually separate an action from the reward it caused, per task?
# ───────────────────────────────────────────────────────────────────────────
def probe_credit_horizon(seed=3, episodes=40):
    out = {}

    # RULE: reward is on the SAME trial as the action. Nothing to bridge.
    # What matters instead is how long a RULE lives, because credit that
    # outlives the rule pays the new rule's reward to the old rule's cards.
    rng = np.random.default_rng(seed)
    lives = []
    for ep in range(episodes):
        t = RuleSwitchTask()
        t.reset(int(rng.integers(1_000_000)))
        done = False
        since = 0
        while not done:
            _, _, done, info = t.step(int(rng.integers(3)))
            since += 1
            if info.get("switch"):
                lives.append(since)
                since = 0
    out["rule"] = {
        "action_to_reward_steps": 0,
        "rule_lifetime_trials_random_policy": {
            "mean": round(float(np.mean(lives)), 2),
            "min": int(np.min(lives)), "max": int(np.max(lives))},
        "rule_lifetime_floor_CRIT_WINDOW": RULE.CRIT_WINDOW,
        "rule_lifetime_ceiling_BLOCK_MAX": RULE.BLOCK_MAX,
        "traces_reset_between_rules": False,
        "note": ("elig is cleared only by reset_episode(); a rule EPISODE is "
                 "all 6 blocks, so traces cross every silent switch."),
    }

    # DMS: reward lands only on the choice step; the cue step is `delay` steps
    # earlier. Credit must reach the whole episode. Traces DO reset per episode.
    out["dms"] = {
        "action_to_reward_steps_by_delay": {str(d): d for d in DMS_DELAYS},
        "episode_len_by_delay": {str(d): (1 if d == 0 else d + 1)
                                 for d in DMS_DELAYS},
        "traces_reset_between_episodes": True,
        "note": ("reset_episode() clears elig, so a tau longer than the "
                 "episode cannot leak into the next trial; it only means "
                 "'every step of THIS episode is credited', which is what "
                 "a single terminal reward requires."),
    }

    # PONG: reward is +1/-1 the tick the ball reaches the goal line. The
    # actions that decided it are the paddle moves during the ball's approach.
    env_ticks_per_crossing = 1.0 / 0.025          # ball_speed from pong_env
    rng = np.random.default_rng(seed)
    gaps, gap = [], 0
    task = PongTask(PONG_TICKS)
    obs = task.reset(seed)
    for ep in range(episodes):
        obs = task.reset(int(rng.integers(1_000_000)))
        done = False
        gap = 0
        while not done:
            obs, r, done, info = task.step(int(rng.integers(3)))
            gap += 1
            if r != 0:
                gaps.append(gap)
                gap = 0
    out["pong"] = {
        "ball_full_crossing_ticks": round(env_ticks_per_crossing, 1),
        "serve_to_left_paddle_ticks": round(env_ticks_per_crossing / 2.0, 1),
        "observed_ticks_between_reward_events": {
            "mean": round(float(np.mean(gaps)), 2),
            "p10": round(float(np.percentile(gaps, 10)), 1),
            "p90": round(float(np.percentile(gaps, 90)), 1),
            "min": int(np.min(gaps)), "max": int(np.max(gaps))},
        "traces_reset_between_episodes": True,
        "note": ("the paddle moves that decide a hit happen while the ball "
                 "crosses the field; credit shorter than that cannot reach "
                 "them."),
    }
    return out


# ───────────────────────────────────────────────────────────────────────────
# 4. eps_floor vs RuleSwitchTask's OWN criterion.  Assume a PERFECT greedy
#    policy. Residual eps-random actions alone decide whether the 8-of-10
#    criterion is reachable inside BLOCK_MAX=60. This is a best-case bound:
#    if a perfect policy cannot pass, no policy can.
# ───────────────────────────────────────────────────────────────────────────
def _block_ttc(p, rng, crit_window, crit_hits, block_max):
    """Exactly RuleSwitchTask.step's criterion logic, on a Bernoulli(p) stream."""
    window = []
    for since in range(1, block_max + 1):
        window.append(1 if rng.random() < p else 0)
        if len(window) > crit_window:
            window.pop(0)
        if len(window) == crit_window and sum(window) >= crit_hits:
            return since
    return block_max


def probe_eps_floor(trials=4000, seed=5):
    out = {}
    for tname, n_act in (("rule", 3), ("dms", 2), ("pong", 3)):
        row = {}
        for eps in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
            # greedy is perfect; a random action is right with prob 1/n_act
            p = (1.0 - eps) + eps / n_act
            entry = {"best_case_accuracy": round(p, 4)}
            if tname == "rule":
                rng = _random.Random(seed)
                ttcs = []
                reached = 0
                for _ in range(trials):
                    t = _block_ttc(p, rng, RULE.CRIT_WINDOW, RULE.CRIT_HITS,
                                   RULE.BLOCK_MAX)
                    ttcs.append(t)
                    reached += int(t < RULE.BLOCK_MAX)
                entry.update({
                    "mean_ttc_perfect_policy": round(float(np.mean(ttcs)), 2),
                    "frac_blocks_reaching_criterion": round(reached / trials, 4),
                    "passes_experiment_success_test_ttc_lt_20":
                        bool(float(np.mean(ttcs)) < 20.0),
                })
            row[str(eps)] = entry
        out[tname] = row
    out["_note"] = ("success in bimodal.py is mean trials-to-criterion < 20. "
                    "The rule rows are a BEST CASE: perfect greedy knowledge, "
                    "only eps-noise. Where the best case already fails, the "
                    "region is unusable regardless of learning.")
    return out


# ───────────────────────────────────────────────────────────────────────────
# 5. strict_scale vs the cosines the task can actually produce.
#    spawn happens iff sim < tolerance(i) = mean_i - k*sd_i, with
#    k = strictness() = (0.5..3.0 over the critical period) * strict_scale
#    and sd floored at TOLERANCE_MIN_SD. Measure the real mean/sd of absorbed
#    similarities, and the real cosine between DIFFERENT task states.
# ───────────────────────────────────────────────────────────────────────────
def probe_strict(seed=11, steps=6000):
    out = {}
    for tname in ("rule", "dms16", "pong"):
        if tname == "dms16":
            task = DMSTask(16)
        else:
            task = _task(tname)
        rng = np.random.default_rng(seed)
        # a mid-range agent so keys are formed exactly as in the real run
        ag = EranAgent(task.n_obs, task.n_actions, mode="ctx", seed=seed)
        ag.p = dict(ag.p)
        ag.p.update({"lam": 0.3, "ctx_gain": 1.0, "eps0": 1.0, "eps_floor": 1.0,
                     "strict_scale": 0.7, "trace_tau": 5.0})
        ag.hard_reset()
        obs = task.reset(seed)
        sims_absorbed = []
        keys = []
        for i in range(steps):
            v = ag._key(obs)
            if len(ag.vecs):
                s = float(np.max(ag.vecs @ v))
                sims_absorbed.append(s)
            if len(keys) < 400:
                keys.append(v.copy())
            a = ag.act(obs)
            obs, r, done, info = task.step(a)
            ag.learn(r, done)
            if done:
                obs = task.reset(int(rng.integers(1_000_000)))
                ag.reset_episode()
        K = np.array(keys)
        C = K @ K.T
        off = C[~np.eye(len(K), dtype=bool)]
        # per-prototype absorbed stats, as tolerance() computes them
        tol_rows = []
        for i in range(len(ag.mass)):
            n = ag.n_abs[i]
            if n < TOLERANCE_WARMUP:
                continue
            mean = ag.s_sum[i] / n
            var = max(0.0, ag.s_sq[i] / n - mean * mean)
            sd = max(var ** 0.5, TOLERANCE_MIN_SD)
            tol_rows.append((mean, sd))
        means = np.array([m for m, s in tol_rows]) if tol_rows else np.array([1.0])
        sds = np.array([s for m, s in tol_rows]) if tol_rows else np.array([TOLERANCE_MIN_SD])
        # at which effective k does tolerance drop below the LOWEST cosine the
        # task can produce -> nothing is ever surprising enough to spawn again
        min_cos = float(np.min(off))
        p01_cos = float(np.percentile(off, 1))
        k_dead_min = float(np.median((means - min_cos) / sds))
        k_dead_p01 = float(np.median((means - p01_cos) / sds))
        out[tname] = {
            "n_prototypes": int(len(ag.mass)),
            "absorbed_sim_mean_median": round(float(np.median(means)), 5),
            "absorbed_sim_sd_median": round(float(np.median(sds)), 5),
            "sd_is_at_floor_frac": round(float(np.mean(sds <= TOLERANCE_MIN_SD + 1e-12)), 3),
            "cosine_between_distinct_keys": {
                "min": round(min_cos, 5), "p01": round(p01_cos, 5),
                "median": round(float(np.median(off)), 5)},
            "k_at_which_spawn_dies_vs_min_cos": round(k_dead_min, 3),
            "k_at_which_spawn_dies_vs_p01_cos": round(k_dead_p01, 3),
            "k_reachable_now": {
                "infant": round(STRICTNESS_INFANT * 3.2, 3),
                "adult": round(STRICTNESS_ADULT * 3.2, 3),
                "adult_at_strict_scale_1_5": round(STRICTNESS_ADULT * 1.5, 3)},
        }
    out["_note"] = ("k_at_which_spawn_dies is the effective strictness k where "
                    "mean - k*sd falls below the lowest cosine the task can "
                    "produce. Above it the organism can never spawn again, "
                    "whatever it sees. Compare with k_reachable_now.adult.")
    return out


# ───────────────────────────────────────────────────────────────────────────
# 6. DEGENERATE REGIONS of the joint decode: places where a knob provably has
#    no effect at all, so ES spends search on a dimension that does nothing.
# ───────────────────────────────────────────────────────────────────────────
def probe_degenerate(n=400_000, seed=17):
    rng = np.random.default_rng(seed)
    th = rng.normal(0.0, 1.0, (n, len(PARAM_NAMES)))
    ks = [decode(t) for t in th[:20_000]]
    eps0 = np.array([k["eps0"] for k in ks])
    epsf = np.array([k["eps_floor"] for k in ks])
    epsd = np.array([k["eps_decay"] for k in ks])
    lam = np.array([k["lam"] for k in ks])
    tau = np.array([k["trace_tau"] for k in ks])
    gain = np.array([k["ctx_gain"] for k in ks])
    settle = (eps0 - epsf) / epsd
    return {
        "sampling": "theta ~ N(0,1)^10, the ES init distribution",
        "n_sampled": int(len(ks)),
        "frac_eps0_below_eps_floor": round(float(np.mean(eps0 < epsf)), 4),
        "note_eps0": ("where eps0 < eps_floor the eps schedule clamps on step 1 "
                      "and eps0 has NO effect: a dead search dimension."),
        "frac_eps_settles_after_1e5_steps": round(float(np.mean(settle > 1e5)), 4),
        "frac_trace_tau_gt_CRIT_WINDOW": round(float(np.mean(tau > RULE.CRIT_WINDOW)), 4),
        "frac_lam_horizon_gt_CRIT_WINDOW": round(
            float(np.mean(1.0 / np.maximum(1e-9, 1.0 - lam) > RULE.CRIT_WINDOW)), 4),
        "frac_ctx_gain_gt_3": round(float(np.mean(gain > 3.0)), 4),
        "median_at_theta_zero": {k: round(float(v), 5)
                                 for k, v in decode(np.zeros(len(PARAM_NAMES))).items()},
        "note_prior": ("median_at_theta_zero is where EVERY ES search STARTS. "
                       "A re-parameterisation moves this as well as the "
                       "ceiling -- the two effects are not separable by a "
                       "rescale-style variant."),
    }


# ───────────────────────────────────────────────────────────────────────────
def main():
    out = {
        "title": "Structural probe of the arena decode ranges",
        "date": "2026-08-22",
        "principle": ("every number here comes from tasks.py / eran_agent.py / "
                      "pong_env.py mechanics. No run accuracy is read."),
        "task_constants": {
            "rule": {"n_actions": RULE.n_actions, "CRIT_WINDOW": RULE.CRIT_WINDOW,
                     "CRIT_HITS": RULE.CRIT_HITS, "BLOCK_MAX": RULE.BLOCK_MAX,
                     "N_BLOCKS": RULE.N_BLOCKS, "n_obs": RULE.n_obs},
            "dms": {"n_actions": DMSTask.n_actions, "N_ITEMS": DMSTask.N_ITEMS,
                    "n_obs": DMSTask.n_obs, "delays": list(DMS_DELAYS)},
            "pong": {"n_actions": PongTask.n_actions, "n_obs": PongTask.n_obs,
                     "ticks": PONG_TICKS, "ball_speed": 0.025,
                     "paddle_speed": 0.05, "paddle_half": 0.10},
        },
    }
    print("probe 1/10  context loudness ...", flush=True)
    out["ctx_loudness"] = probe_ctx()
    print("probe 2/10  DMS cue survival ...", flush=True)
    out["dms_cue_survival"] = probe_dms_cue()
    print("probe 3/10  credit horizon ...", flush=True)
    out["credit_horizon"] = probe_credit_horizon()
    print("probe 4/10  eps_floor vs criterion ...", flush=True)
    out["eps_floor_vs_criterion"] = probe_eps_floor()
    print("probe 5/10  strictness vs task cosines ...", flush=True)
    out["strictness"] = probe_strict()
    print("probe 6/10  degenerate regions ...", flush=True)
    out["degenerate_regions"] = probe_degenerate()
    print("probe 7/10  discrimination margin ...", flush=True)
    out["margin"] = probe_margin()
    print("probe 8/10  rule ctx trade-off (random + competent policy) ...", flush=True)
    out["rule_tradeoff"] = probe_rule_tradeoff()
    out["rule_tradeoff_competent"] = probe_rule_tradeoff(p_correct=0.85)
    print("probe 9/10  within-episode key drift ...", flush=True)
    out["key_drift"] = probe_key_drift()
    print("probe 10/10 post-switch addressing recovery ...", flush=True)
    out["switch_recovery"] = probe_switch_recovery()

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "STRUCTURAL-PROBE-2026-08-22.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print("wrote", path)
    return out




# ───────────────────────────────────────────────────────────────────────────
# 7. DISCRIMINATION MARGIN.  The single quantity that decides whether a
#    prototype memory can work at all: how much closer is a key to another key
#    of the SAME required-response class than to one of a DIFFERENT class?
#    lam and ctx_gain do not act independently -- they jointly set how much of
#    the unit key is trial-specific rather than a constant carried over from
#    the stationary observation mean. Measured on the real stream.
# ───────────────────────────────────────────────────────────────────────────
def _margin(keys, labels):
    K = np.array(keys)
    lab = np.array(labels)
    C = K @ K.T
    n = len(K)
    eye = np.eye(n, dtype=bool)
    same = (lab[:, None] == lab[None, :]) & ~eye
    diff = (lab[:, None] != lab[None, :])
    if same.sum() == 0 or diff.sum() == 0:
        return None
    w = float(C[same].mean())
    b = float(C[diff].mean())
    return {"within": round(w, 5), "between": round(b, 5),
            "margin": round(w - b, 5)}


def probe_margin(seed=21, steps=1500):
    """margin(lam, ctx_gain) per task, where the label is the thing the task
    forces the agent to tell apart."""
    grid_lam = (0.0, 0.3, 0.5, 0.7, 0.9, 0.95, 0.99)
    grid_gain = (0.1, 0.5, 1.0, 2.0, 3.0, 4.1, 8.1)
    out = {}

    for tname in ("rule", "dms16", "pong"):
        rows = {}
        for lam in grid_lam:
            for gain in grid_gain:
                rng = np.random.default_rng(seed)
                if tname == "dms16":
                    task = DMSTask(16)
                elif tname == "rule":
                    task = RuleSwitchTask()
                else:
                    task = PongTask(PONG_TICKS)
                ag = EranAgent(task.n_obs, task.n_actions, mode="ctx", seed=seed)
                ag.p = dict(ag.p)
                ag.p.update({"lam": lam, "ctx_gain": gain})
                ag.ctx = np.zeros(task.n_obs)
                obs = task.reset(seed)
                keys, labels = [], []
                for i in range(steps):
                    v = ag._key(obs)
                    o = np.asarray(obs, dtype=np.float64)
                    if tname == "rule":
                        # the class the agent must resolve: which action the
                        # card demands. Both rules are live across the episode,
                        # so the card identity (colour,shape) IS the class.
                        keys.append(v.copy())
                        labels.append(int(task.col) * 10 + int(task.shape))
                    elif tname == "dms16":
                        if task.t == task._choice_step():
                            # at the choice step the ONLY thing separating a
                            # correct from an incorrect response is the cue
                            # seen 16 steps ago -> label by (visible pair,
                            # which side matches)
                            keys.append(v.copy())
                            labels.append(int(task.cA) * 100 + int(task.cB) * 10
                                          + int(task.match_is_A))
                    else:
                        # pong: the action that matters is decided by whether
                        # the ball is above or below the paddle
                        d = task.env.by - task.env.yL
                        keys.append(v.copy())
                        labels.append(0 if d < -0.05 else (2 if d > 0.05 else 1))
                    a = int(rng.integers(task.n_actions))
                    ag.ctx = lam * ag.ctx + (1.0 - lam) * o
                    obs, r, done, info = task.step(a)
                    if done:
                        obs = task.reset(int(rng.integers(1_000_000)))
                        ag.ctx = np.zeros(task.n_obs)
                    if len(keys) >= 500:
                        break
                m = _margin(keys, labels)
                if m is not None:
                    rows[f"lam={lam},gain={gain}"] = m
        out[tname] = rows
    out["_note"] = ("margin = mean cosine(same class) - mean cosine(different "
                    "class), on the L2-normalised key the organism actually "
                    "matches on. margin -> 0 means the prototype memory is "
                    "physically unable to separate the classes the task "
                    "scores, whatever it learns.")
    return out


# ───────────────────────────────────────────────────────────────────────────
# 8. THE TRADE-OFF ctx_gain ACTUALLY SITS ON (rule task).
#    Probe 7 labels keys by CARD, so it rewards ctx_gain -> 0: with no context
#    the key is a clean one-hot card. But a clean card is exactly what CANNOT
#    solve RuleSwitchTask, because the same card demands a different action
#    under each rule, and which rule is live is knowable ONLY from the recent
#    feedback the context carries. So there are TWO margins pulling opposite
#    ways, and the honest bound is where the WEAKER of them is strongest.
#      card margin : same card vs different card          (falls with gain)
#      rule margin : same card, rule A vs rule B          (rises with gain)
#    Both are measured on the real key, with no accuracy read.
# ───────────────────────────────────────────────────────────────────────────
def probe_rule_tradeoff(seed=31, steps=20000, cap=1200, p_correct=None):
    """p_correct=None -> random policy. p_correct=0.85 -> a NEAR-CRITERION
    agent, which is the regime evaluation actually scores: there the
    prev_reward channel carries a real switch signal (a burst of -1 right
    after the silent flip) that a random policy never produces."""
    grid_lam = (0.0, 0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99)
    grid_gain = (0.1, 0.25, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 4.1, 8.1)
    out = {}
    for lam in grid_lam:
        for gain in grid_gain:
            rng = np.random.default_rng(seed)
            task = RuleSwitchTask()
            ag = EranAgent(task.n_obs, task.n_actions, mode="ctx", seed=seed)
            ag.p = dict(ag.p)
            ag.p.update({"lam": lam, "ctx_gain": gain})
            ag.ctx = np.zeros(task.n_obs)
            obs = task.reset(seed)
            keys, card, rule = [], [], []
            for i in range(steps):
                v = ag._key(obs)
                o = np.asarray(obs, dtype=np.float64)
                keys.append(v.copy())
                card.append(int(task.col) * 10 + int(task.shape))
                rule.append(int(task.rule))
                if p_correct is None or rng.random() > p_correct:
                    a = int(rng.integers(task.n_actions))
                else:
                    a = task.col if task.rule == 0 else task.shape
                ag.ctx = lam * ag.ctx + (1.0 - lam) * o
                obs, r, done, info = task.step(a)
                if done:
                    obs = task.reset(int(rng.integers(1_000_000)))
                    ag.ctx = np.zeros(task.n_obs)
                if len(keys) >= cap:
                    break
            K = np.array(keys); cd = np.array(card); rl = np.array(rule)
            C = K @ K.T
            n = len(K); eye = np.eye(n, dtype=bool)
            same_card = (cd[:, None] == cd[None, :]) & ~eye
            diff_card = (cd[:, None] != cd[None, :])
            same_rule = (rl[:, None] == rl[None, :])
            # card margin: can the key tell two DIFFERENT cards apart?
            card_margin = float(C[same_card].mean() - C[diff_card].mean())
            # rule margin: for the SAME card, can it tell the two RULES apart?
            m_sr = same_card & same_rule
            m_dr = same_card & ~same_rule
            rule_margin = (float(C[m_sr].mean() - C[m_dr].mean())
                           if m_sr.sum() and m_dr.sum() else None)
            out[f"lam={lam},gain={gain}"] = {
                "card_margin": round(card_margin, 5),
                "rule_margin": round(rule_margin, 5) if rule_margin is not None else None,
                "weaker_of_the_two": (round(min(card_margin, rule_margin), 5)
                                      if rule_margin is not None else None),
            }
    out["_note"] = ("RuleSwitchTask needs BOTH margins positive at once: a key "
                    "that cannot separate cards cannot act, and a key that "
                    "cannot separate rules cannot switch. ctx_gain trades one "
                    "against the other, so the structurally defensible band is "
                    "where the weaker margin is largest -- a bound derived "
                    "from the task, with no run accuracy consulted.")
    return out



# ───────────────────────────────────────────────────────────────────────────
# 9. WITHIN-EPISODE KEY DRIFT (the real test for lam's top end).
#    reset_episode() zeroes ctx, so the context spends the first ~1/(1-lam)
#    trials RAMPING UP from zero. If that ramp is long compared with the
#    episode, the key for one and the same card is not the same vector at
#    trial 10 as at trial 300: the prototype spawned early stops matching.
#    A memory horizon is only usable if the key it produces is STATIONARY
#    inside the episode it has to work in.
# ───────────────────────────────────────────────────────────────────────────
def probe_key_drift(seed=41, episodes=12):
    grid_lam = (0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999)
    out = {}
    for gain in (1.0, 3.0):
        rows = {}
        for lam in grid_lam:
            rng = np.random.default_rng(seed)
            early, late = {}, {}
            ep_lens = []
            for ep in range(episodes):
                task = RuleSwitchTask()
                ag = EranAgent(task.n_obs, task.n_actions, mode="ctx", seed=seed)
                ag.p = dict(ag.p); ag.p.update({"lam": lam, "ctx_gain": gain})
                ag.ctx = np.zeros(task.n_obs)
                obs = task.reset(int(rng.integers(1_000_000)))
                done, t = False, 0
                while not done:
                    v = ag._key(obs); o = np.asarray(obs, dtype=np.float64)
                    cid = int(task.col) * 10 + int(task.shape)
                    (early if t < 20 else late).setdefault(cid, []).append(v.copy())
                    a = task.col if task.rule == 0 else task.shape
                    if rng.random() > 0.85:
                        a = int(rng.integers(3))
                    ag.ctx = lam * ag.ctx + (1.0 - lam) * o
                    obs, r, done, info = task.step(a)
                    t += 1
                ep_lens.append(t)
            sims = []
            for cid in early:
                if cid not in late:
                    continue
                E = np.array(early[cid]); L = np.array(late[cid][-40:])
                sims.append(float((E @ L.T).mean()))
            rows[str(lam)] = {
                "same_card_cos_early_vs_late": round(float(np.mean(sims)), 5),
                "horizon": round(1.0 / max(1e-9, 1.0 - lam), 1),
            }
        out[f"gain={gain}"] = rows
        out[f"gain={gain}"]["_episode_len_mean"] = round(float(np.mean(ep_lens)), 1)
    out["_note"] = ("cos between keys for the SAME card seen in the first 20 "
                    "trials vs the last 40 of the SAME episode. 1.0 = the key "
                    "is stationary and one prototype serves the whole episode; "
                    "well below 1.0 = the context is still ramping and the "
                    "organism must re-spawn the same card as if it were new.")
    return out



# ───────────────────────────────────────────────────────────────────────────
# 10. POST-SWITCH ADDRESSING RECOVERY (the mechanism probes 7-9 missed).
#     Probes 7-9 measured the key with the rule held fixed, and found no reason
#     for a long lam to hurt. But the observed data says lam separates success
#     from failure at AUC 0.986 even INSIDE the well-behaved ctx_gain band, so
#     the mechanism must be something a stationary probe cannot see.
#
#     Here it is. The observation carries prev_action and prev_reward. The
#     instant the rule silently flips, those two channels inverting is the ONLY
#     evidence a switch happened -- and the leaky context SMEARS that evidence
#     over ~1/(1-lam) trials. So for 1/(1-lam) trials after every switch, the
#     key for one and the same card is displaced from where it sat before the
#     switch: the organism looks up a DIFFERENT prototype, carrying a DIFFERENT
#     Q row, exactly during the window in which it must re-learn fastest.
#     If that displacement outlasts CRIT_WINDOW=10 trials, the block cannot be
#     re-learned before it is disturbed again.
#
#     Measured: cosine between the key for a card AFTER a switch and the key
#     for the SAME card in settled conditions, as a function of trials since
#     the switch.
# ───────────────────────────────────────────────────────────────────────────
def probe_switch_recovery(seed=53, episodes=60, gain=1.0):
    grid_lam = (0.0, 0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99)
    out = {}
    HOR = 25
    for lam in grid_lam:
        rng = np.random.default_rng(seed)
        settled = {}          # card -> keys taken >=15 trials after any switch
        after = {t: {} for t in range(HOR)}
        for ep in range(episodes):
            task = RuleSwitchTask()
            ag = EranAgent(task.n_obs, task.n_actions, mode="ctx", seed=seed)
            ag.p = dict(ag.p); ag.p.update({"lam": lam, "ctx_gain": gain})
            ag.ctx = np.zeros(task.n_obs)
            obs = task.reset(int(rng.integers(1_000_000)))
            done = False
            since_switch = 10 ** 6
            while not done:
                v = ag._key(obs); o = np.asarray(obs, dtype=np.float64)
                cid = int(task.col) * 10 + int(task.shape)
                if since_switch >= 15:
                    settled.setdefault(cid, []).append(v.copy())
                if since_switch < HOR:
                    after[since_switch].setdefault(cid, []).append(v.copy())
                # a competent agent: it knows the live rule, which is the
                # regime where the switch signal is strongest
                a = task.col if task.rule == 0 else task.shape
                if rng.random() > 0.85:
                    a = int(rng.integers(3))
                ag.ctx = lam * ag.ctx + (1.0 - lam) * o
                obs, r, done, info = task.step(a)
                since_switch = 0 if info.get("switch") else since_switch + 1
        base = {c: np.array(v).mean(axis=0) for c, v in settled.items()}
        for c in base:
            n = np.linalg.norm(base[c])
            if n > 0:
                base[c] = base[c] / n
        curve = []
        for t in range(HOR):
            sims = []
            for c, vs in after[t].items():
                if c in base:
                    sims.append(float((np.array(vs) @ base[c]).mean()))
            curve.append(round(float(np.mean(sims)), 5) if sims else None)
        ref = curve[HOR - 1] if curve[HOR - 1] else 1.0
        # trials until the key is back within 1% of its settled address
        rec = next((t for t, c in enumerate(curve) if c is not None and c >= 0.99 * ref),
                   None)
        out[str(lam)] = {
            "horizon_1_over_1_minus_lam": round(1.0 / max(1e-9, 1.0 - lam), 1),
            "cos_to_settled_address_by_trials_since_switch": curve,
            "trials_to_recover_addressing": rec,
            "outlasts_CRIT_WINDOW": (rec is not None and rec > RULE.CRIT_WINDOW),
        }
    out["_note"] = ("trials_to_recover_addressing is how long after a silent "
                    "rule flip the organism keeps looking up a displaced "
                    "prototype for the same card. Compare with CRIT_WINDOW=10: "
                    "a displacement that outlasts the window means the block "
                    "cannot be re-learned before the next flip.")
    out["_gain_used"] = gain
    return out


if __name__ == "__main__":
    main()
