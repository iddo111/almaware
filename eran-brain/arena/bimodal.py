# -*- coding: utf-8 -*-
"""bimodal.py — is ERAN-CTX's rule-switching a CAPABILITY or a LOTTERY?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

The arena run (2026-08-21) reported ERAN-CTX on Wisconsin-style rule switching
at 4x budget as 81.6 / 80.4 / 37.7 across three seeds. Two near the oracle, one
at chance. Three seeds cannot tell a capability from a coin flip, and the agent
that ran it said so. This file settles it.

WHAT IS HELD IDENTICAL TO THE ARENA RUN
  * the task (tasks.RuleSwitchTask), untouched,
  * the agent (eran_agent.EranAgent, mode="ctx"), untouched,
  * the search (es.train_es / es.train_online), untouched,
  * the hybrid training recipe of run_arena.run_job: ES over the 10 knobs with
    HALF the budget, then an online life with the rest,
  * the budget: 4 x 3,000,000 = 12,000,000 environment steps per seed,
  * the held-out evaluation seeds 7,000,000 + 0..23, opened once per run,
  * the ES only ever sees train seeds 0..4,000,000.

WHAT IS ADDED
  * 24 seeds instead of 3,
  * per-trial instrumentation of the held-out evaluation, so the failure can be
    named rather than reported: prototype count over time, prototype recycling
    and displacement across switches, retrieval margin, the loudness of the
    context channel against the observation, the action histogram, and the
    perseveration curve as a function of trials-since-switch,
  * variants that test one fix at a time, each on the SAME 24 seeds at the SAME
    budget.

VARIANTS
  base       exactly the arena arm.
  chem       exactly the arena arm with chemistry live (settles the NE claim).
  restart    ES restarts from a fresh init 3 times inside the SAME ES half of
             the budget; the start with the best TRAIN fitness is kept. No
             evaluation episode is ever touched by the choice.
  lamcap     the context leak lam is re-parameterised into [0, LAM_MAX] instead
             of [0, 1], bounding the memory horizon.
  taucap     the ELIGIBILITY horizon trace_tau is re-parameterised into
             [1, TAU_MAX] instead of [1, 121]. Same kind of fix as the ctx_gain
             re-parameterisation the arena run already made mid-flight: the
             number of knobs is unchanged at 10, only the range a knob can
             reach. The bound comes from the task, not from the answer: reward
             here arrives on the SAME step as the action, so credit has no gap
             to bridge, and a rule stays alive for at least CRIT_WINDOW = 10
             trials, so any credit smeared further than that necessarily
             crosses a silent switch.
  attrition  sleep-style attrition: at the prototype cap, the least recently
             winning prototype is recycled instead of the spawn being refused.
  transplant a theta tuned on a DONOR seed is transplanted, and only the online
             life and the agent's own rng vary. Separates "the search is a
             lottery" from "the whole run is a lottery".
"""
import argparse
import json
import math
import multiprocessing as mp
import os
import platform
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run_arena as RA                                             # noqa: E402
import es as ES                                                    # noqa: E402
from tasks import RuleSwitchTask                                   # noqa: E402
from eran_agent import EranAgent, N_PARAMS                         # noqa: E402
from decode_audit import AuditedAgent
import range_variants as RV                              # noqa: E402

MULT = 4
RULE_BUDGET = MULT * 3_000_000
SEEDS = tuple(11 * k for k in range(1, 25))        # 11..264, includes 11/22/33
PERSEV_W = RuleSwitchTask.PERSEV_WINDOW            # 20
LAM_MAX = 0.6
TAU_MAX = float(RuleSwitchTask.CRIT_WINDOW)        # 10 trials
N_RESTARTS = 3


# ── agent variants ─────────────────────────────────────────────────────────
class LamCapAgent(EranAgent):
    """HYPOTHESIS (d): the leaky context has the wrong time constant relative to
    the switch period, so the key cannot distinguish the two rules. lam is
    squashed into [0, LAM_MAX] so the context can never integrate longer than
    1/(1-LAM_MAX) trials. Nothing else changes."""

    def set_params(self, theta):
        super().set_params(theta)
        self.p["lam"] = LAM_MAX * self.p["lam"]


class TauCapAgent(EranAgent):
    """The mechanism-matched fix. ERAN's own eligibility trace is what pays the
    action head (the same channel the parent's thumb-tap uses). Its horizon
    trace_tau is decoded as 1 + 120*sigmoid, so ES can reach 121 trials. On a
    task where the rule silently changes every ~10 trials, ANY credit horizon
    longer than the rule's own lifetime pays reward earned under the new rule to
    the prototypes that encoded the dead one. Here the range is re-parameterised
    to [1, TAU_MAX]; the knob count is unchanged."""

    def set_params(self, theta):
        super().set_params(theta)
        self.p["trace_tau"] = 1.0 + (TAU_MAX - 1.0) * (
            (self.p["trace_tau"] - 1.0) / 120.0)


class AttritionAgent(EranAgent):
    """HYPOTHESIS (b): prototypes spawned under rule A are never unlearned, the
    code saturates at the cap, and the new rule has nowhere to live. Fix: at the
    cap, recycle the LEAST RECENTLY WINNING prototype instead of refusing the
    spawn. No new hyperparameter: the cap and the spawn rule are unchanged."""

    def __init__(self, *a, **kw):
        cap = int(kw.pop("cap", 256))
        kw["max_protos"] = 10 ** 9          # let act() always reach _spawn
        super().__init__(*a, **kw)
        self.cap = cap

    def hard_reset(self):
        super().hard_reset()
        self.last_win = []
        self.recycles = 0

    def _spawn(self, v):
        cap = getattr(self, "cap", 256)
        if len(self.mass) >= cap:
            i = int(np.argmin(self.last_win))
            self.vecs[i] = v
            self.mass[i] = 1.0
            self.scar[i] = 0.0
            self.n_abs[i] = 0
            self.s_sum[i] = 0.0
            self.s_sq[i] = 0.0
            self.Q[i, :] = 0.0
            self.V[i] = 0.0
            self.elig.pop(i, None)
            self.last_win[i] = self.beat
            self.recycles += 1
            return i
        i = super()._spawn(v)
        self.last_win.append(self.beat)
        return i

    def act(self, obs):
        a = super().act(obs)
        while len(self.last_win) < len(self.mass):
            self.last_win.append(self.beat)
        if self._last_idx is not None and self._last_idx < len(self.last_win):
            self.last_win[self._last_idx] = self.beat
        return a

    def stats(self):
        s = super().stats()
        s["recycles"] = int(getattr(self, "recycles", 0))
        s["cap"] = int(getattr(self, "cap", 256))
        return s


def make_agent(variant, n_obs, n_actions, seed):
    chem = (variant == "chem")
    # single-knob range variants (range_variants.py): ONE decode range changed,
    # every other knob left exactly as eran_agent.decode() has it. Checked
    # first so a variant name can never be silently swallowed by a later
    # branch.
    _rv = RV.make(variant, n_obs, n_actions, seed)
    if _rv is not None:
        return _rv
    if variant == "lamcap":
        return LamCapAgent(n_obs, n_actions, mode="ctx", chemistry=False,
                           seed=seed)
    if variant == "taucap":
        return TauCapAgent(n_obs, n_actions, mode="ctx", chemistry=False,
                           seed=seed)
    if variant == "taucap+chem":
        return TauCapAgent(n_obs, n_actions, mode="ctx", chemistry=True,
                           seed=seed)
    if variant == "attrition":
        return AttritionAgent(n_obs, n_actions, mode="ctx", chemistry=False,
                              seed=seed, cap=256)
    if variant == "audited":
        # THE FULL DECODE AUDIT (decode_audit.py): all 10 ES-tunable knobs
        # re-ranged against the task's own scale, not just trace_tau. See
        # decode_audit.KNOB_BOUNDS for the per-knob reasoning and the
        # evidence (AUC / observed success-fail split) behind each bound.
        return AuditedAgent(n_obs, n_actions, mode="ctx", chemistry=False,
                            seed=seed)
    return EranAgent(n_obs, n_actions, mode="ctx", chemistry=chem, seed=seed)


# ── instrumented held-out evaluation ───────────────────────────────────────
def diag_rollout(agent, factory, seed, learn):
    """One held-out episode with per-trial recording. The agent/task interaction
    is byte-for-byte es.rollout; only observation of it is added."""
    task = factory()
    obs = task.reset(seed)
    agent.reset_episode()
    rows = []
    q_snaps = []
    used_block = set()
    done = False
    steps = 0
    while not done:
        o = np.asarray(obs, dtype=np.float64)
        # retrieval diagnostics on the key the agent is ABOUT to use
        v = agent._key(obs)
        if len(agent.vecs):
            sims = agent.vecs @ v
            att = sims - np.asarray(agent.scar)
            order = np.argsort(att)[::-1]
            sim1 = float(sims[order[0]])
            marg = float(att[order[0]] - att[order[1]]) if len(order) > 1 else 1.0
        else:
            sim1, marg = 0.0, 0.0
        ctx_norm = float(agent.p["ctx_gain"] * np.linalg.norm(agent.ctx))
        obs_norm = float(np.linalg.norm(o))

        col, shape = task.col, task.shape
        rule, prev_rule, since = task.rule, task.prev_rule, task.since_switch

        a = agent.act(obs)
        idx = agent._last_idx
        nproto = len(agent.mass)
        if idx is not None:
            used_block.add(int(idx))

        obs, r, done, info = task.step(a)
        if learn:
            agent.learn(r, done)

        rows.append((int(a), int(col), int(shape), int(rule),
                     -1 if prev_rule is None else int(prev_rule),
                     int(since), int(nproto),
                     -1 if idx is None else int(idx),
                     sim1, marg, ctx_norm, obs_norm))

        if info.get("switch"):
            q_snaps.append((int(nproto),
                            np.argmax(agent.Q, axis=1).copy(),
                            set(used_block)))
            used_block = set()

        steps += 1
        if steps > 5000:
            break
    return task, rows, q_snaps


def aggregate(rows, q_snaps):
    """Turn per-trial records into the diagnostics that can name a mechanism."""
    a = np.array([r[0] for r in rows])
    col = np.array([r[1] for r in rows])
    shp = np.array([r[2] for r in rows])
    rule = np.array([r[3] for r in rows])
    prule = np.array([r[4] for r in rows])
    since = np.array([r[5] for r in rows])
    npro = np.array([r[6] for r in rows])
    idx = np.array([r[7] for r in rows])
    sim1 = np.array([r[8] for r in rows])
    marg = np.array([r[9] for r in rows])
    cn = np.array([r[10] for r in rows])
    on = np.array([r[11] for r in rows])

    correct_now = np.where(rule == 0, col, shp)
    ok = (a == correct_now)
    old_correct = np.where(prule == 0, col, np.where(prule == 1, shp, -1))
    has_prev = (prule >= 0)
    opp = has_prev & (since < PERSEV_W) & (old_correct != correct_now)
    pers = opp & (a == old_correct)

    # error / perseveration as a function of trials since the switch
    err_curve, pers_curve = [], []
    for t in range(PERSEV_W):
        m = (since == t)
        err_curve.append(round(float(1.0 - ok[m].mean()), 4) if m.any() else None)
        mo = m & opp
        pers_curve.append(round(float(pers[mo].mean()), 4) if mo.any() else None)

    # action degeneracy (hypothesis c)
    hist = np.bincount(a, minlength=3).astype(float)
    hist /= max(1.0, hist.sum())

    # retrieval degeneracy
    valid = idx >= 0
    if valid.any():
        ucounts = np.bincount(idx[valid])
        top1 = float(ucounts.max() / ucounts.sum())
        uniq = int((ucounts > 0).sum())
    else:
        top1, uniq = 1.0, 0

    # prototype displacement across switches: of the prototypes that actually
    # WON during a block, how many changed their preferred action by the next
    # switch? This is the direct test of "are pre-switch prototypes displaced,
    # or do they just accumulate?"
    disp = []
    for k in range(1, len(q_snaps)):
        n_prev, am_prev, used_prev = q_snaps[k - 1]
        n_cur, am_cur, used_cur = q_snaps[k]
        common = [i for i in used_prev if i < len(am_prev) and i < len(am_cur)]
        if common:
            ch = float(np.mean([am_prev[i] != am_cur[i] for i in common]))
            disp.append(round(ch, 4))

    return {
        "acc": round(float(ok.mean()), 4),
        "n_trials": int(len(rows)),
        "action_hist": [round(float(x), 4) for x in hist],
        "action_max_share": round(float(hist.max()), 4),
        "persev_rate": round(float(pers[opp].mean()), 4) if opp.any() else None,
        "persev_opportunities": int(opp.sum()),
        "err_curve_by_since_switch": err_curve,
        "persev_curve_by_since_switch": pers_curve,
        "n_proto_eval_start": int(npro[0]),
        "n_proto_eval_end": int(npro[-1]),
        "n_proto_at_switch": [int(s[0]) for s in q_snaps],
        "proto_top1_share": round(top1, 4),
        "proto_unique_used": uniq,
        "proto_displacement_per_switch": disp,
        "proto_displacement_mean": (round(float(np.mean(disp)), 4)
                                    if disp else None),
        "mean_sim_top1": round(float(sim1.mean()), 4),
        "mean_attraction_margin": round(float(marg.mean()), 5),
        "mean_ctx_over_obs": round(float((cn / np.maximum(on, 1e-9)).mean()), 4),
    }


def instrumented_rule_eval(agent, factory, n_episodes, eval_lo):
    """Frozen pass then the online pass, in run_arena's own order. The online
    pass is the headline number for this task: the rule CHANGES inside the
    episode, so an agent that cannot learn during evaluation cannot solve it at
    all. The ES-tuned knobs are frozen in both passes."""
    out = {}
    for label, frozen in (("frozen", True), ("online", False)):
        agent.frozen_eval = frozen
        ttc, ncor, ntr = [], 0, 0
        all_rows, all_snaps = [], []
        for i in range(n_episodes):
            task, rows, snaps = diag_rollout(agent, factory, eval_lo + i,
                                             learn=not frozen)
            rep = task.report()
            ttc.extend(rep["ttc"])
            ncor += rep["n_correct"]
            ntr += rep["n_trials"]
            all_rows.extend(rows)
            all_snaps.extend(snaps)
        out[f"acc_{label}"] = round(ncor / max(1, ntr), 4)
        out[f"ttc_mean_{label}"] = round(float(np.mean(ttc)), 3) if ttc else None
        out[f"ttc_reached_frac_{label}"] = (
            round(float(np.mean([t < RuleSwitchTask.BLOCK_MAX for t in ttc])), 4)
            if ttc else None)
        out[f"n_trials_{label}"] = int(ntr)
        if label == "online":
            out["diag"] = aggregate(all_rows, all_snaps)
            out["persev_rate_online"] = out["diag"]["persev_rate"]
    agent.frozen_eval = False
    return out


# ── ES with restarts, inside the SAME budget ───────────────────────────────
def train_es_multistart(agent, factory, budget, seed, pop, eps_gen, lo, hi,
                        n_starts=N_RESTARTS):
    """HYPOTHESIS: ES lands in a degenerate basin and never leaves. Fix: spend
    the same ES budget on n_starts independent starts and keep the one whose
    TRAIN fitness is best. The selection signal is the mean fitness of the last
    generations, which the ES already paid for -- no extra environment steps and
    no evaluation episode is ever consulted."""
    per = budget // n_starts
    used = 0
    starts = []
    best_score, best_theta = -1e18, None
    for j in range(n_starts):
        agent.set_params(agent.random_params(seed * 1000 + 7 * j))
        agent.hard_reset()
        left = budget - used
        b = min(per, left) if j < n_starts - 1 else left
        if b <= 0:
            break
        th, hist, u, gens = ES.train_es(
            agent, factory, b, seed=seed * 97 + j, pop=pop,
            eps_per_gen=eps_gen, train_seed_lo=lo, train_seed_hi=hi,
            hard_reset_each=True)
        used += u
        score = float(np.mean(hist[-5:])) if hist else -1e18
        starts.append({"start": j, "train_score": round(score, 3),
                       "gens": int(gens), "steps": int(u),
                       "hist_tail": hist[-6:]})
        if score > best_score:
            best_score, best_theta = score, np.asarray(th, float).copy()
        if used >= budget:
            break
    agent.set_params(best_theta)
    agent.hard_reset()
    return best_theta, starts, used, best_score


# ── one (variant, seed) job ────────────────────────────────────────────────
def run_job(job):
    variant, seed, budget, donor_theta = job
    t0 = time.time()
    np.random.seed(seed)

    factory = RA.rule_factory()
    probe = RuleSwitchTask()
    n_obs, n_actions = probe.n_obs, probe.n_actions
    agent = make_agent(variant, n_obs, n_actions, seed)
    pop, eps_gen = RA.ES_EPS[("hybrid", "rule")]

    res = {"variant": variant, "seed": int(seed), "budget_steps": int(budget),
           "n_es_params": int(N_PARAMS)}

    if variant == "transplant":
        agent.set_params(np.asarray(donor_theta, dtype=np.float64))
        agent.hard_reset()
        used_es, gens, es_hist = 0, 0, []
        res["donor_theta"] = [round(float(x), 6) for x in donor_theta]
    elif variant == "restart":
        _, starts, used_es, best_score = train_es_multistart(
            agent, factory, budget // 2, seed, pop, eps_gen,
            RA.TRAIN_LO, RA.TRAIN_HI)
        res["restarts"] = starts
        res["es_train_score"] = round(best_score, 3)
        es_hist = []
        gens = sum(s["gens"] for s in starts)
    else:
        _, es_hist, used_es, gens = ES.train_es(
            agent, factory, budget // 2, seed=seed, pop=pop,
            eps_per_gen=eps_gen, train_seed_lo=RA.TRAIN_LO,
            train_seed_hi=RA.TRAIN_HI, hard_reset_each=True)
        res["es_train_score"] = (round(float(np.mean(es_hist[-5:])), 3)
                                 if es_hist else None)
        agent.hard_reset()

    if variant != "transplant":
        agent.hard_reset()
    stats_after_es = agent.stats()

    life_seed = seed + 5
    life_curve, used_life = ES.train_online(
        agent, factory, budget - used_es, seed=life_seed,
        train_seed_lo=RA.TRAIN_LO, train_seed_hi=RA.TRAIN_HI)
    stats_after_life = agent.stats()

    res.update({
        "steps_used_es": int(used_es), "steps_used_life": int(used_life),
        "steps_used_total": int(used_es + used_life),
        "generations": int(gens),
        "es_history": ES.hist_trim(es_hist, 60),
        "es_history_tail": es_hist[-8:],
        "life_curve": life_curve,
        "life_final": (round(float(np.mean(life_curve[-5:])), 3)
                       if life_curve else None),
        "life_first": (round(float(np.mean(life_curve[:5])), 3)
                       if life_curve else None),
        "stats_after_es": stats_after_es,
        "stats_after_life": stats_after_life,
        "theta": [round(float(x), 6) for x in agent.theta],
        "knobs": {k: round(float(v), 5) for k, v in agent.p.items()},
        "ctx_horizon_trials": round(1.0 / max(1e-6, 1.0 - agent.p["lam"]), 3),
    })

    res.update(instrumented_rule_eval(agent, factory, RA.RULE_EVAL_EPISODES,
                                      RA.EVAL_LO))
    res["stats_final"] = agent.stats()
    res["acc"] = res["acc_online"]
    res["wall_s"] = round(time.time() - t0, 1)
    return res


# ── summary helpers ────────────────────────────────────────────────────────
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


ORACLE_ACC, ORACLE_TTC, CHANCE = 0.905, 10.0, 1.0 / 3.0
SUCCESS_TTC = 20.0          # a "success" = reaches criterion, blocks not timing out


def classify(r):
    """A run SUCCEEDS if it actually learns each rule: mean trials-to-criterion
    under 20 (the oracle's floor is 10, the block times out at 60). Stated
    before any number is read, and applied identically to every variant."""
    t = r.get("ttc_mean_online")
    return (t is not None) and (t < SUCCESS_TTC)


def summarise(runs, label):
    accs = np.array([r["acc_online"] for r in runs])
    ttcs = np.array([r["ttc_mean_online"] for r in runs])
    good = [r for r in runs if classify(r)]
    bad = [r for r in runs if not classify(r)]
    lo, hi = wilson(len(good), len(runs))
    out = {
        "variant": label, "n_seeds": len(runs),
        "n_success": len(good), "n_fail": len(bad),
        "success_rate": round(len(good) / max(1, len(runs)), 4),
        "success_wilson95": [round(lo, 4), round(hi, 4)],
        "acc_mean": round(float(accs.mean()), 4),
        "acc_median": round(float(np.median(accs)), 4),
        "acc_min": round(float(accs.min()), 4),
        "acc_max": round(float(accs.max()), 4),
        "acc_all_sorted": sorted(round(float(x), 4) for x in accs),
        "ttc_all_sorted": sorted(round(float(x), 3) for x in ttcs),
        "acc_success_mean": (round(float(np.mean([r["acc_online"] for r in good])), 4)
                             if good else None),
        "acc_fail_mean": (round(float(np.mean([r["acc_online"] for r in bad])), 4)
                          if bad else None),
        "ttc_success_mean": (round(float(np.mean([r["ttc_mean_online"] for r in good])), 3)
                             if good else None),
        "ttc_fail_mean": (round(float(np.mean([r["ttc_mean_online"] for r in bad])), 3)
                          if bad else None),
    }
    keys = ["lam", "ctx_gain", "trace_tau", "eta_q", "eta_v", "eps_floor",
            "eps_decay", "strict_scale"]
    for k in keys:
        for grp, nm in ((good, "success"), (bad, "fail")):
            v = [r["knobs"][k] for r in grp]
            out[f"{k}_{nm}"] = round(float(np.mean(v)), 4) if v else None
    for k in ("es_train_score", "life_final"):
        for grp, nm in ((good, "success"), (bad, "fail")):
            v = [r[k] for r in grp if r.get(k) is not None]
            out[f"{k}_{nm}"] = round(float(np.mean(v)), 3) if v else None
    for k in ("mean_ctx_over_obs", "mean_attraction_margin", "action_max_share",
              "proto_top1_share", "proto_displacement_mean",
              "n_proto_eval_end", "proto_unique_used"):
        for grp, nm in ((good, "success"), (bad, "fail")):
            v = [r["diag"][k] for r in grp if r["diag"].get(k) is not None]
            out[f"{k}_{nm}"] = round(float(np.mean(v)), 4) if v else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="base")
    ap.add_argument("--seeds", default="")
    ap.add_argument("--procs", type=int, default=14)
    ap.add_argument("--budget", type=int, default=RULE_BUDGET)
    ap.add_argument("--donor", default="")
    ap.add_argument("--tag", default="base")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    seeds = ([int(x) for x in a.seeds.split(",")] if a.seeds else list(SEEDS))
    variants = a.variants.split(",")
    donor = None
    if a.donor:
        donor = json.load(open(a.donor, encoding="utf-8"))

    print("=" * 78)
    print("ARENA BIMODAL PROBE — rule switching, capability or lottery?")
    print("=" * 78)
    print(f"CHANCE = {CHANCE*100:.1f}%   ORACLE = {ORACLE_ACC*100:.1f}% "
          f"(trials-to-criterion {ORACLE_TTC})")
    print(f"Budget {a.budget:,} env steps per seed (= 4x the arena's matched "
          f"rule budget), half to ES over {N_PARAMS} knobs, half to an online life.")
    print(f"Evaluation: {RA.RULE_EVAL_EPISODES} held-out episodes from seed "
          f"{RA.EVAL_LO:,}; training only ever saw {RA.TRAIN_LO}..{RA.TRAIN_HI:,}.")
    print(f"A single held-out trial is worth ~{100.0/1600:.3f} pp for a fast arm "
          f"(~1,600 trials) and ~{100.0/8000:.3f} pp for a timing-out arm "
          f"(~8,000 trials); 1 SE at chance over 1,600 trials = "
          f"{100*math.sqrt(CHANCE*(1-CHANCE)/1600):.2f} pp.")
    print(f"variants={variants}  seeds={len(seeds)}  procs={a.procs}")
    print("-" * 78, flush=True)

    jobs = []
    for v in variants:
        for s in seeds:
            dt = None
            if v == "transplant":
                dt = donor
            jobs.append((v, s, a.budget, dt))

    t0 = time.time()
    out = []
    with mp.Pool(a.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(run_job, jobs), 1):
            out.append(r)
            print(f"[{i:>3}/{len(jobs)}] {r['variant']:<10} seed={r['seed']:<4} "
                  f"acc={r['acc_online']*100:5.1f}%  ttc={r['ttc_mean_online']:5.1f}  "
                  f"lam={r['knobs']['lam']:.3f} ctxg={r['knobs']['ctx_gain']:.2f} "
                  f"tau={r['knobs']['trace_tau']:6.2f}  "
                  f"{'OK ' if classify(r) else 'FAIL'} ({r['wall_s']}s)",
                  flush=True)

    summ = {v: summarise([r for r in out if r["variant"] == v], v)
            for v in variants}
    payload = {
        "title": "ARENA BIMODAL PROBE — ERAN-CTX rule switching over many seeds",
        "date": "2026-08-21", "host": platform.node(),
        "question": ("Is ERAN-CTX's rule-switching result a capability or a "
                     "lottery, what makes it fail, and does the fix hold?"),
        "chance": CHANCE, "oracle_acc": ORACLE_ACC, "oracle_ttc": ORACLE_TTC,
        "success_criterion": f"ttc_mean_online < {SUCCESS_TTC}",
        "budget_steps": a.budget, "budget_multiplier_vs_arena": MULT,
        "seeds": seeds, "variants": variants,
        "eval_seed_lo": RA.EVAL_LO, "eval_episodes": RA.RULE_EVAL_EPISODES,
        "train_seed_range": [RA.TRAIN_LO, RA.TRAIN_HI],
        "n_es_params": N_PARAMS,
        "wall_s": round(time.time() - t0, 1),
        "summary": summ, "runs": out,
    }
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    path = os.path.join(HERE, "results", f"BIMODAL-{a.tag}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)

    print("\n" + "=" * 78)
    for v in variants:
        s = summ[v]
        print(f"{v:<10} n={s['n_seeds']:<3} success {s['n_success']}/{s['n_seeds']} "
              f"= {s['success_rate']*100:.1f}% "
              f"[{s['success_wilson95'][0]*100:.1f}, {s['success_wilson95'][1]*100:.1f}] 95% Wilson"
              f"   acc mean {s['acc_mean']*100:.1f}% "
              f"(succ {(s['acc_success_mean'] or 0)*100:.1f} / fail "
              f"{(s['acc_fail_mean'] or 0)*100:.1f})")
        print(f"           lam succ {s['lam_success']} vs fail {s['lam_fail']} | "
              f"ctx_gain {s['ctx_gain_success']} vs {s['ctx_gain_fail']} | "
              f"trace_tau {s['trace_tau_success']} vs {s['trace_tau_fail']}")
        print(f"           ctx/obs {s['mean_ctx_over_obs_success']} vs "
              f"{s['mean_ctx_over_obs_fail']} | margin "
              f"{s['mean_attraction_margin_success']} vs "
              f"{s['mean_attraction_margin_fail']} | act_max_share "
              f"{s['action_max_share_success']} vs {s['action_max_share_fail']}")
        print(f"           es_train succ {s['es_train_score_success']} vs fail "
              f"{s['es_train_score_fail']} | life_final "
              f"{s['life_final_success']} vs {s['life_final_fail']}")
    print(f"\nwrote {path}  ({round(time.time()-t0,1)}s)")


if __name__ == "__main__":
    mp.set_start_method("fork", force=True)
    main()
