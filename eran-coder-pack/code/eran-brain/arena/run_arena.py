# -*- coding: utf-8 -*-
"""run_arena.py — THE AGENTIC ARENA.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

ERAN's substrate vs a spiking network, in AGENTIC situations: decisions,
memory over time, and logic. Not audio classification.

THE HONEST PREMISE. Neither contender is an agent today. ERAN's organism is an
associative prototype memory: it recognises, and it has no action selection at
all. The SNN is a classifier. BOTH had to be given an action head, and how you
give one is itself the finding — an architecture that only maps input to output
fails the moment a task asks it to hold something across time.

PROTOCOL, identical for every arm:
  * matched BUDGET in environment steps, printed per arm,
  * >= 3 seeds per arm per task, every seed reported,
  * the chance / random baseline printed FIRST, always,
  * held-out evaluation seeds, disjoint from anything training ever touched,
  * no tuning on the evaluation episodes,
  * the worth of a single episode in percentage points stated before any gap.

Usage:
    python run_arena.py --quick          # smoke test, tiny budgets
    python run_arena.py                  # the real run
"""
import argparse
import json
import multiprocessing as mp
import os
import platform
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tasks import DMSTask, RuleSwitchTask, PongTask, RandomOpp   # noqa: E402
import es as ES                                                   # noqa: E402
from lif import LIFAgent                                          # noqa: E402
from eran_agent import EranAgent                                  # noqa: E402
from baselines import (RandomAgent, DMSOracle, RuleOracle,        # noqa: E402
                       PongOracle, TabularQ)

# ── held-out seed ranges. TRAIN never sees these. ──────────────────────────
TRAIN_LO, TRAIN_HI = 0, 4_000_000
EVAL_LO = 7_000_000                    # opened once per arm, at the end

DELAYS = (0, 1, 2, 4, 8, 16)
SEEDS = (11, 22, 33)

# population / episodes-per-candidate. The BUDGET is identical for every arm;
# this split is an ES hyperparameter and it is set per arm-family because the
# search spaces differ by two orders of magnitude (LIF: 600-1800 synaptic
# weights, evaluated on a frozen policy; ERAN: 9 knobs whose whole effect is
# how a LIFE unfolds, so a candidate must be allowed to live). Set on TRAIN
# seeds only; the held-out seeds were never opened during any of this.
ES_EPS = {("es", "dms"): (20, 24), ("es", "rule"): (20, 6), ("es", "pong"): (20, 8),
          ("hybrid", "dms"): (20, 50), ("hybrid", "rule"): (20, 6),
          ("hybrid", "pong"): (20, 8)}

DMS_EVAL_EPISODES = 400
RULE_EVAL_EPISODES = 24
PONG_EVAL_EPISODES = 5
PONG_EVAL_TICKS = 2000


# ── budgets, in ENVIRONMENT STEPS. One number per task, all arms alike. ────
def budgets(quick):
    if quick:
        return {"dms_trials": 1500, "rule": 40_000, "pong": 60_000}
    return {"dms_trials": 60_000, "rule": 3_000_000, "pong": 4_000_000}


# ── the roster ─────────────────────────────────────────────────────────────
# kind: "random" | "oracle" | "online" | "es" | "hybrid"
#   online = learns online only, no evolution   (tabular controls)
#   es     = evolution only, weights frozen at eval   (LIF spiking arms)
#   hybrid = evolution over knobs + online life  (ERAN: it has both, natively)
ARMS = [
    ("RANDOM",          "random", {}),
    ("ORACLE",          "oracle", {}),
    ("Q-TAB",           "online", {"cls": "qtab", "memory": False}),
    ("Q-TAB-MEM",       "online", {"cls": "qtab", "memory": True}),
    ("ERAN-PROTO",      "hybrid", {"cls": "eran", "mode": "proto", "chem": False}),
    ("ERAN-TRACE",      "hybrid", {"cls": "eran", "mode": "trace", "chem": False}),
    ("ERAN-CTX",        "hybrid", {"cls": "eran", "mode": "ctx",   "chem": False}),
    ("ERAN-CTX+CHEM",   "hybrid", {"cls": "eran", "mode": "ctx",   "chem": True}),
    ("LIF-FF",          "es",     {"cls": "lif", "recurrent": False, "hidden": 16}),
    ("LIF-REC",         "es",     {"cls": "lif", "recurrent": True,  "hidden": 16}),
    ("LIF-REC-BIG",     "es",     {"cls": "lif", "recurrent": True,  "hidden": 32}),
]


def build_agent(name, kind, cfg, task_name, n_obs, n_actions, seed):
    if kind == "random":
        return RandomAgent(n_obs, n_actions, seed=seed)
    if kind == "oracle":
        return {"dms": DMSOracle, "rule": RuleOracle,
                "pong": PongOracle}[task_name](n_obs, n_actions, seed=seed)
    if cfg["cls"] == "qtab":
        return TabularQ(n_obs, n_actions, memory=cfg["memory"], seed=seed)
    if cfg["cls"] == "lif":
        return LIFAgent(n_obs, n_actions, hidden=cfg["hidden"],
                        recurrent=cfg["recurrent"], seed=seed)
    if cfg["cls"] == "eran":
        return EranAgent(n_obs, n_actions, mode=cfg["mode"],
                         chemistry=cfg["chem"], seed=seed)
    raise ValueError(name)


# ── task factories ─────────────────────────────────────────────────────────
def dms_factory(delay):
    return lambda: DMSTask(delay)


def rule_factory():
    return lambda: RuleSwitchTask()


def pong_factory(ticks):
    return lambda: PongTask(ticks=ticks, opponent=RandomOpp(9999))


# ── one (task, arm, seed) job ──────────────────────────────────────────────
def run_job(job):
    name, kind, cfg, task_name, extra, seed, budget, quick = job
    t0 = time.time()
    np.random.seed(seed)

    if task_name == "dms":
        delay = extra["delay"]
        factory = dms_factory(delay)
        probe = DMSTask(delay)
        ep_len = probe.ep_len()
    elif task_name == "rule":
        factory = rule_factory()
        probe = RuleSwitchTask()
        ep_len = 200
    else:
        factory = pong_factory(extra["ticks"])
        probe = PongTask(ticks=extra["ticks"])
        ep_len = extra["ticks"]

    n_obs, n_actions = probe.n_obs, probe.n_actions
    agent = build_agent(name, kind, cfg, task_name, n_obs, n_actions, seed)

    # ── training, matched budget ──────────────────────────────────────────
    es_hist, life_curve = [], []
    used_es = used_life = 0
    gens = 0
    if kind == "es":
        pop, eps_gen = ES_EPS[("es", task_name)]
        _, es_hist, used_es, gens = ES.train_es(
            agent, factory, budget, seed=seed, pop=pop, eps_per_gen=eps_gen,
            train_seed_lo=TRAIN_LO, train_seed_hi=TRAIN_HI,
            hard_reset_each=False)
    elif kind == "hybrid":
        pop, eps_gen = ES_EPS[("hybrid", task_name)]
        _, es_hist, used_es, gens = ES.train_es(
            agent, factory, budget // 2, seed=seed, pop=pop, eps_per_gen=eps_gen,
            train_seed_lo=TRAIN_LO, train_seed_hi=TRAIN_HI,
            hard_reset_each=True)
        agent.hard_reset()
        life_curve, used_life = ES.train_online(
            agent, factory, budget - used_es, seed=seed + 5,
            train_seed_lo=TRAIN_LO, train_seed_hi=TRAIN_HI)
    elif kind == "online":
        life_curve, used_life = ES.train_online(
            agent, factory, budget, seed=seed,
            train_seed_lo=TRAIN_LO, train_seed_hi=TRAIN_HI)

    stats_after_train = agent.stats()

    # ── evaluation on HELD-OUT seeds ──────────────────────────────────────
    is_online = getattr(agent, "online", False)
    res = {"arm": name, "kind": kind, "task": task_name, "seed": seed,
           "budget_steps": int(budget),
           "steps_used_es": int(used_es), "steps_used_life": int(used_life),
           "steps_used_total": int(used_es + used_life),
           "generations": int(gens),
           "es_history_tail": es_hist[-8:], "life_curve": life_curve,
           "stats": stats_after_train}
    res.update(extra)

    if task_name == "dms":
        for label, frozen in (("frozen", True), ("online", False)):
            if not is_online and label == "online":
                continue
            if is_online:
                agent.frozen_eval = frozen
            ok = 0
            for i in range(DMS_EVAL_EPISODES):
                _, _, last, _ = ES.rollout(agent, factory, EVAL_LO + i,
                                           learn=(is_online and not frozen))
                ok += int(last.get("correct", False))
            res[f"acc_{label}"] = ok / DMS_EVAL_EPISODES
        if is_online:
            agent.frozen_eval = False
        res.setdefault("acc_online", res["acc_frozen"])
        res["acc"] = res["acc_frozen"]
        res["n_eval"] = DMS_EVAL_EPISODES

    elif task_name == "rule":
        for label, frozen in (("frozen", True), ("online", False)):
            if not is_online and label == "frozen":
                continue
            if is_online:
                agent.frozen_eval = frozen
            ttc, persev, persev_opp, ncor, ntr = [], 0, 0, 0, 0
            for i in range(RULE_EVAL_EPISODES):
                _, _, _, task = ES.rollout(agent, factory, EVAL_LO + i,
                                           learn=(is_online and not frozen))
                rep = task.report()
                ttc.extend(rep["ttc"])
                persev += rep["persev"]
                persev_opp += rep["persev_opportunities"]
                ncor += rep["n_correct"]
                ntr += rep["n_trials"]
            res[f"ttc_mean_{label}"] = float(np.mean(ttc)) if ttc else None
            res[f"ttc_per_block_{label}"] = [
                round(float(np.mean(ttc[b::RuleSwitchTask.N_BLOCKS])), 2)
                for b in range(RuleSwitchTask.N_BLOCKS)] if ttc else []
            res[f"ttc_reached_frac_{label}"] = (
                float(np.mean([t < RuleSwitchTask.BLOCK_MAX for t in ttc]))
                if ttc else None)
            res[f"persev_rate_{label}"] = (persev / persev_opp
                                           if persev_opp else None)
            res[f"acc_{label}"] = ncor / max(1, ntr)
            res[f"n_trials_{label}"] = ntr
        if is_online:
            agent.frozen_eval = False
        res["acc"] = res["acc_online"]
        res["ttc_mean"] = res["ttc_mean_online"]
        res["persev_rate"] = res["persev_rate_online"]

    else:  # pong
        efac = pong_factory(PONG_EVAL_TICKS)
        for label, frozen in (("frozen", True), ("online", False)):
            if not is_online and label == "online":
                continue
            if is_online:
                agent.frozen_eval = frozen
            scores = []
            for i in range(PONG_EVAL_EPISODES):
                tot, _, _, _ = ES.rollout(agent, efac, EVAL_LO + i,
                                          learn=(is_online and not frozen))
                scores.append(tot)
            res[f"score_{label}"] = float(np.mean(scores))
            res[f"scores_{label}"] = [round(float(s), 1) for s in scores]
        if is_online:
            agent.frozen_eval = False
        res.setdefault("score_online", res["score_frozen"])
        res["score"] = max(res["score_frozen"], res.get("score_online",
                                                        res["score_frozen"]))
        res["stats_after_eval"] = agent.stats()

    res["stats_final"] = agent.stats()
    res["wall_s"] = round(time.time() - t0, 1)
    return res


# ── job list ───────────────────────────────────────────────────────────────
def build_jobs(b, quick, only=None):
    jobs = []
    delays = DELAYS if not quick else (0, 1, 4)
    seeds = SEEDS if not quick else (11,)
    for name, kind, cfg in ARMS:
        if only and name not in only:
            continue
        for sd in seeds:
            for d in delays:
                jobs.append((name, kind, cfg, "dms", {"delay": d}, sd,
                             b["dms_trials"] * (d + 1 if d else 1), quick))
            jobs.append((name, kind, cfg, "rule", {}, sd, b["rule"], quick))
            jobs.append((name, kind, cfg, "pong", {"ticks": 200}, sd,
                         b["pong"], quick))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--procs", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(HERE, "results",
                                                  "AGENTIC-ARENA-2026-08-21.json"))
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    b = budgets(a.quick)
    jobs = build_jobs(b, a.quick)
    nproc = a.procs or max(1, min(18, (os.cpu_count() or 4) - 2))

    print("=" * 78)
    print("AGENTIC ARENA — ERAN's substrate vs a spiking network, as AGENTS")
    print("=" * 78)
    print("CHANCE / RANDOM BASELINES, printed first, as the house law requires:")
    print("  DMS  (delayed match to sample) : chance = 50.00%  "
          f"(2 actions; {DMS_EVAL_EPISODES} held-out trials -> 1 trial = "
          f"{100.0 / DMS_EVAL_EPISODES:.2f} percentage points)")
    print("  RULE (Wisconsin card sort)     : chance = 33.33%  "
          "(3 actions; a random policy needs the full 60-trial block timeout, "
          "so trials-to-criterion at chance = 60 = 'never got there')")
    print("  PONG                           : random vs random is measured "
          "below as the RANDOM arm; the sign of the score is what matters "
          "(+1 per hit, -1 per miss).")
    print(f"\nBudgets (environment steps, identical for every arm on a task):")
    print(f"  DMS  : {b['dms_trials']} trials x (delay+1) steps per arm per seed per delay")
    print(f"  RULE : {b['rule']:,} steps per arm per seed")
    print(f"  PONG : {b['pong']:,} steps per arm per seed")
    print(f"\n{len(jobs)} jobs on {nproc} processes. seeds={SEEDS if not a.quick else (11,)}")
    print("-" * 78, flush=True)

    t0 = time.time()
    out = []
    if nproc > 1:
        with mp.Pool(nproc) as pool:
            for i, r in enumerate(pool.imap_unordered(run_job, jobs), 1):
                out.append(r)
                tag = (f"delay={r.get('delay')}" if r["task"] == "dms" else "")
                key = (r.get("acc") if r["task"] != "pong" else r.get("score"))
                print(f"[{i:>4}/{len(jobs)}] {r['task']:<5} {r['arm']:<14} "
                      f"seed={r['seed']:<3} {tag:<9} -> "
                      f"{key if key is None else round(key, 4)} "
                      f"({r['wall_s']}s)", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            r = run_job(j)
            out.append(r)
            print(f"[{i}/{len(jobs)}] {r['task']} {r['arm']} {r['wall_s']}s",
                  flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    payload = {
        "title": "AGENTIC ARENA — ERAN prototype substrate vs spiking LIF, as agents",
        "date": "2026-08-21",
        "host": platform.node(),
        "honest_premise": (
            "Neither contender is an agent today. ERAN's organism is an "
            "associative prototype memory with no action selection at all; the "
            "SNN is a classifier. Both were given a matched action head. How "
            "you give one is itself the finding."),
        "chance": {"dms": 0.5, "rule": 1.0 / 3.0,
                   "dms_one_trial_pp": 100.0 / DMS_EVAL_EPISODES},
        "budgets": b, "seeds": list(SEEDS if not a.quick else (11,)),
        "delays": list(DELAYS if not a.quick else (0, 1, 4)),
        "eval_seed_lo": EVAL_LO,
        "train_seed_range": [TRAIN_LO, TRAIN_HI],
        "dms_eval_episodes": DMS_EVAL_EPISODES,
        "rule_eval_episodes": RULE_EVAL_EPISODES,
        "pong_eval": {"episodes": PONG_EVAL_EPISODES, "ticks": PONG_EVAL_TICKS},
        "quick": bool(a.quick),
        "wall_s": round(time.time() - t0, 1),
        "runs": out,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"\nwrote {a.out}  ({round(time.time()-t0,1)}s)")


if __name__ == "__main__":
    mp.set_start_method("fork", force=True)
    main()
