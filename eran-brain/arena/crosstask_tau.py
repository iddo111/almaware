# -*- coding: utf-8 -*-
"""crosstask_tau.py — does the RULE-derived trace_tau cap break the other two
tasks? Measured, not asserted.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

THE CLAIM UNDER TEST. decode_audit.py caps trace_tau at CRIT_WINDOW=10 for a
reason that is correct *for RuleSwitchTask*: reward arrives on the same trial
as the action, a rule lives >=10 trials, and eligibility traces are NOT cleared
at a silent switch, so credit longer than the rule's own life pays post-switch
reward to pre-switch prototypes.

But eran_agent.decode() is shared by all three arena tasks, and in the other
two the same cap removes credit the task structurally requires:

  * DMS at delay 16 -- the reward lands ONLY on the choice step, 16 steps after
    the cue step whose prototype must be credited. Traces ARE cleared per
    episode (es.rollout calls reset_episode), so a long tau cannot leak into
    the next trial; it only means "credit every step of this episode", which is
    exactly what one terminal reward needs.
  * PONG -- measured reward gaps are 20-140 ticks (mean 42.6); the ball crosses
    the field in 40 ticks. The paddle moves that decide a hit happen while the
    ball approaches, tens of ticks before the +1/-1 arrives.

So: same agent, same budget, same seeds, ONE difference -- trace_tau decoded
over [1,121] (original) or squashed to [1,10] (the rule-derived cap). If the
cap costs nothing here, Finding 0 of the audit is wrong and a global table is
fine. If it costs, a global table is a new range bug.
"""
import argparse
import json
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

import es as ES
import run_arena as RA
from eran_agent import EranAgent, N_PARAMS
from tasks import DMSTask, PongTask

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")

TAU_MAX = 10.0            # the rule-derived cap, applied to a non-rule task
SEEDS = (11, 22, 33, 44, 55, 66)
DMS_DELAY = 16
DMS_BUDGET = 1_000_000    # ~= arena's 60,000 DMS trials x 17 steps at delay 16
PONG_BUDGET = 4_000_000   # arena's own pong budget
EVAL_EPISODES = {"dms16": 400, "pong": 5}


class TauCapAgent(EranAgent):
    """trace_tau squashed into [1, TAU_MAX]. Nothing else changes. Identical in
    form to bimodal.TauCapAgent, so this is the SAME intervention the rule arm
    was measured with -- just applied to a different task."""

    def set_params(self, theta):
        super().set_params(theta)
        self.p["trace_tau"] = 1.0 + (TAU_MAX - 1.0) * (
            (self.p["trace_tau"] - 1.0) / 120.0)


def _factory(task):
    if task == "dms16":
        return lambda: DMSTask(DMS_DELAY)
    return lambda: PongTask(200)


def _budget(task):
    return DMS_BUDGET if task == "dms16" else PONG_BUDGET


def _eval(agent, task, seed_lo, n_ep):
    """Held-out evaluation, online (the agent keeps learning), matching the way
    the rule arm is scored. For DMS the number reported is accuracy on the
    choice step; for Pong it is mean reward per episode."""
    factory = _factory(task)
    if task == "dms16":
        n_ok, n = 0, 0
        for i in range(n_ep):
            _, _, last, _ = ES.rollout(agent, factory, seed_lo + i, learn=True)
            n_ok += int(bool(last.get("correct")))
            n += 1
        return {"acc": round(n_ok / max(1, n), 4), "n_trials": n}
    tot = []
    for i in range(n_ep):
        t, n, _, _ = ES.rollout(agent, factory, seed_lo + i, learn=True)
        tot.append(t)
    return {"reward_per_episode": round(float(np.mean(tot)), 3),
            "n_episodes": n_ep}


def run_job(job):
    task, arm, seed = job
    t0 = time.time()
    np.random.seed(seed)
    factory = _factory(task)
    probe = factory()
    cls = TauCapAgent if arm == "tau10" else EranAgent
    agent = cls(probe.n_obs, probe.n_actions, mode="ctx", chemistry=False,
                seed=seed)
    budget = _budget(task)
    pop, eps_gen = RA.ES_EPS[("hybrid", "dms" if task == "dms16" else "pong")]

    _, es_hist, used_es, gens = ES.train_es(
        agent, factory, budget // 2, seed=seed, pop=pop, eps_per_gen=eps_gen,
        train_seed_lo=RA.TRAIN_LO, train_seed_hi=RA.TRAIN_HI,
        hard_reset_each=True)
    agent.hard_reset()
    life_curve, used_life = ES.train_online(
        agent, factory, budget - used_es, seed=seed + 5,
        train_seed_lo=RA.TRAIN_LO, train_seed_hi=RA.TRAIN_HI)

    res = {"task": task, "arm": arm, "seed": int(seed),
           "budget_steps": int(budget),
           "steps_used": int(used_es + used_life),
           "generations": int(gens),
           "trace_tau": round(float(agent.p["trace_tau"]), 3),
           "knobs": {k: round(float(v), 5) for k, v in agent.p.items()}}
    res.update(_eval(agent, task, RA.EVAL_LO, EVAL_EPISODES[task]))
    res["wall_s"] = round(time.time() - t0, 1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="dms16,pong")
    ap.add_argument("--procs", type=int, default=3)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    jobs = [(t, arm, s) for t in a.tasks.split(",")
            for arm in ("orig", "tau10") for s in SEEDS]
    print("=" * 78)
    print("CROSS-TASK trace_tau CAP TEST — is the rule-derived cap safe "
          "for DMS and Pong?")
    print("=" * 78)
    print(f"arms: orig trace_tau in [1,121]  vs  tau10 in [1,{TAU_MAX:g}] "
          f"(the rule-derived cap)")
    print(f"seeds {list(SEEDS)}  |  DMS delay {DMS_DELAY} budget {DMS_BUDGET:,} "
          f"|  Pong budget {PONG_BUDGET:,}")
    print("-" * 78)
    with Pool(a.procs) as pool:
        rows = []
        for r in pool.imap_unordered(run_job, jobs):
            rows.append(r)
            score = r.get("acc", r.get("reward_per_episode"))
            print(f"{r['task']:<7}{r['arm']:<7}seed={r['seed']:<4}"
                  f"tau={r['trace_tau']:>7.2f}  score={score}  "
                  f"({r['wall_s']}s)", flush=True)

    print("-" * 78)
    summary = {}
    for task in a.tasks.split(","):
        key = "acc" if task == "dms16" else "reward_per_episode"
        s = {}
        for arm in ("orig", "tau10"):
            v = [r[key] for r in rows if r["task"] == task and r["arm"] == arm]
            taus = [r["trace_tau"] for r in rows
                    if r["task"] == task and r["arm"] == arm]
            s[arm] = {"mean": round(float(np.mean(v)), 4),
                      "sd": round(float(np.std(v, ddof=1)), 4),
                      "n": len(v), "values": v,
                      "trace_tau_mean": round(float(np.mean(taus)), 2)}
        # paired by seed
        d = [next(r[key] for r in rows if r["task"] == task
                  and r["arm"] == "tau10" and r["seed"] == sd)
             - next(r[key] for r in rows if r["task"] == task
                    and r["arm"] == "orig" and r["seed"] == sd)
             for sd in SEEDS]
        s["paired_delta_tau10_minus_orig"] = {
            "mean": round(float(np.mean(d)), 4),
            "se": round(float(np.std(d, ddof=1)) / math.sqrt(len(d)), 4),
            "per_seed": [round(float(x), 4) for x in d]}
        summary[task] = s
        pd = s["paired_delta_tau10_minus_orig"]
        print(f"{task:<8} orig {s['orig']['mean']:.4f} (tau~"
              f"{s['orig']['trace_tau_mean']:.1f})   tau10 "
              f"{s['tau10']['mean']:.4f} (tau~{s['tau10']['trace_tau_mean']:.1f})"
              f"   paired delta {pd['mean']:+.4f} +/- {pd['se']:.4f}")

    payload = {"title": "Cross-task trace_tau cap test",
               "date": "2026-08-22",
               "question": ("does the CRIT_WINDOW=10 cap, correct for "
                            "RuleSwitchTask, cost anything on DMS-16 and Pong, "
                            "which share the same decode()?"),
               "tau_cap": TAU_MAX, "seeds": list(SEEDS),
               "summary": summary, "runs": rows}
    os.makedirs(RESULTS, exist_ok=True)
    out = os.path.join(RESULTS, "CROSSTASK-TAU-2026-08-22.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
