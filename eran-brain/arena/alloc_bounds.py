# -*- coding: utf-8 -*-
"""alloc_bounds.py — the theta -> knob decode for AllocWorld, audited BEFORE
the first real run, not after (the lesson of decode_audit.py: two experiments
were burned by ranges that were physically absurd for the task they were
tuned on; this file exists so that mistake cannot repeat here).

DESIGN RULE, copied from decode_audit.py because it worked: the bound and the
argument for it live TOGETHER in KNOB_BOUNDS, decode_audited() is BUILT FROM
that table, and assert_in_bounds() is the guard nobody can quietly bypass.

Ten of the twelve knobs are eran_agent.py's own (lam, eta_q, eta_v, eps0,
eps_decay, eps_floor, strict_scale, trace_tau, ne_gain, ctx_gain); their
ARCHITECTURE is unchanged (same prototype memory, same Q/V action head, same
tolerance/strictness formulas), so every bound below is RE-DERIVED against
AllocWorld's own numbers (alloc_world.py), not copied from RuleSwitchTask's.
Two knobs are new: persist_gain (5HT stickiness) and oxt_gain (OXT plasticity
boost) -- both are UNPRECEDENTED knobs with no prior success/fail evidence, so
their bounds are derived from architecture facts alone and flagged as such.
"""
import math

import numpy as np

from alloc_world import (EPISODE_TICKS, ENERGY_BUDGET, MIN_DELAY, MAX_DELAY,
                         FAST_LO, FAST_HI, SLOW_LO, SLOW_HI, N_ACTIONS)

PARAM_NAMES = ("lam", "eta_q", "eta_v", "eps0", "eps_decay", "eps_floor",
              "strict_scale", "trace_tau", "ne_gain", "ctx_gain",
              "persist_gain", "oxt_gain")
N_PARAMS = len(PARAM_NAMES)

# architecture constants, unchanged from eran_agent.py (kept local so this
# file has no import-time dependency on the agent module, avoiding a circular
# import: alloc_agent imports alloc_bounds, not the other way round).
STRICTNESS_INFANT, STRICTNESS_ADULT = 0.5, 3.0
TOLERANCE_MIN_SD = 0.02
DA_MAX, NE_MAX, OXT_MAX = 2.0, 3.0, 2.0        # oxt ceiling set in alloc_agent.py


def _sig(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


KNOB_BOUNDS = {

    # lam -- leaky-context decay. Horizon 1/(1-lam) must reach at least the
    # reward delay (MIN_DELAY..MAX_DELAY = 3..9 ticks) to be worth anything,
    # but must stay well under the FASTEST stream-L rule lifetime (FAST_LO=15
    # ticks) or the same disease decode_audit.py found: a leak that outlives
    # the rule it should help recognise smears pre- and post-switch history
    # into one indistinguishable "conjunction". MAX_DELAY (9) already sits
    # comfortably under FAST_LO (15), so anchoring on MAX_DELAY satisfies both
    # constraints at once.
    "lam": (0.0, 1.0 - 1.0 / MAX_DELAY,
           f"context horizon 1/(1-lam) capped at MAX_DELAY={MAX_DELAY} ticks -- "
           f"long enough to matter for bridging the reward delay, short "
           f"enough (< FAST_LO={FAST_LO}) to never span a fast-regime switch."),

    # eta_q -- action-head learning rate. UNCHANGED reasoning from
    # decode_audit.py: Q is hard-clipped to +/-20 regardless, and rate<1
    # cannot overshoot into oscillation the way rate>=1 could. No task-scale
    # absurdity: this is an architectural fact, not a RuleSwitchTask fact.
    "eta_q": (0.0, 0.6,
             "unchanged: Q is hard-clipped to +/-20 elsewhere and a rate<1 "
             "cannot overshoot into oscillation -- an architectural fact, "
             "not specific to the task that decode_audit.py measured it on."),

    # eta_v -- value-baseline learning rate. Same logic as decode_audit.py:
    # cap so the implied averaging window (1/eta_v) covers at least a few
    # ENGAGEMENTS of a stream (not ticks -- V is indexed by prototype, keyed
    # on which stream/cue was engaged). With stochastic reward (correct pays
    # only 80% of the time), a window under ~3 engagements cannot separate
    # signal from the 20% mislabel rate.
    "eta_v": (0.0, 1.0 / 3.0,
             "value learning rate capped so its implied averaging window "
             "(1/eta_v) stays >= ~3 engagements -- below that a value "
             "estimate chases the 20% chance a correct response still pays "
             "-1 (or an incorrect one pays +1) instead of estimating the "
             "stream's true worth."),

    # eps0 -- exploration probability at birth. UNCHANGED: this decodes to a
    # PROBABILITY; [0,1] is the type, not a choice.
    "eps0": (0.0, 1.0,
            "unchanged: this IS a probability; [0,1] is the type, not a "
            "choice."),

    # eps_decay -- per-tick exploration decay. Budget here (run_chem.py) is
    # matched-order-of-magnitude to the bimodal probe's per-seed budget
    # (millions of steps); even the slowest decay in this range (1e-5/tick)
    # reaches the floor within ~1e5 ticks, a small fraction of any budget in
    # the low millions, and the fastest (1e-1/tick) reaches it within ~10
    # ticks -- both ends are reachable inside the budget, same as the
    # RuleSwitchTask finding (AUC 0.459 there, chance-level).
    "eps_decay": (1e-5, 1e-1,
                 "unchanged: both extremes resolve within a small fraction "
                 "of a multi-million-tick budget; the RuleSwitchTask audit "
                 "found this range chance-level (AUC 0.459) and nothing "
                 "about AllocWorld's structure changes that argument."),

    # eps_floor -- exploration maintained FOREVER (train AND eval). THIS
    # TASK'S OWN HAZARD, distinct from RuleSwitchTask: exploring here means a
    # UNIFORM random pick among ALL N_ACTIONS=7 (which stream AND which
    # response), not just a random response within a fixed stream. At
    # eps_floor=f, a fraction f of ticks are pure noise over the entire
    # allocation decision -- exactly the decision this whole experiment
    # measures. Above eps_floor~0.3, noise dominates enough of the record
    # that no modulator's effect on ALLOCATION (which stream to engage) can
    # be measured over the signal; capped there with margin.
    "eps_floor": (0.0, 0.3,
                 "capped so uniform noise over the FULL 7-way allocation "
                 "decision (not just a response bit, unlike RuleSwitchTask) "
                 "cannot dominate enough of the record to erase every "
                 "modulator's effect on which stream gets attended."),

    # strict_scale -- multiplies the organism's own age-graded strictness k
    # (STRICTNESS_INFANT..STRICTNESS_ADULT = 0.5..3.0), same architecture as
    # eran_agent.py. UNCHANGED reasoning: combined multiplier capped near 4.5
    # instead of 9.6, keeping the spawn tolerance inside a plausible cosine
    # range (TOLERANCE_MIN_SD=0.02) rather than an unreachable one -- an
    # architecture fact, independent of which task is running.
    "strict_scale": (0.2, 1.5,
                    "unchanged: combined with the organism's own age curve "
                    "(0.5..3.0) the effective sd-multiplier is capped near "
                    "4.5, not 9.6 -- an architecture fact about when the "
                    "spawn tolerance becomes physically unreachable, not a "
                    "task-specific one."),

    # trace_tau -- THE mechanism decode_audit.py named. Reward here is
    # delayed 3-9 ticks (MIN_DELAY..MAX_DELAY) and STOCHASTIC, so credit must
    # bridge a real gap -- unlike RuleSwitchTask, where reward arrived on the
    # SAME step and any horizon > 1 was pure liability. Floor: must reach at
    # least MAX_DELAY (9) or a reward arriving at the delay's tail end pays
    # nothing (the originating prototype's eligibility has already decayed
    # away). A little slack above MAX_DELAY is allowed because OTHER
    # streams' engagements and REST ticks also decay the SAME global
    # eligibility dict in between (the world does not pause the other two
    # streams while one waits for its reward) -- so the horizon needs some
    # margin over the raw delay to survive a realistic mix of engagements.
    # Ceiling: FAST_LO (15) -- the fastest a stream-L rule can live -- for
    # exactly the reason decode_audit.py gave: beyond that, credit can be
    # paid to a prototype that encoded a rule already dead.
    "trace_tau": (float(MAX_DELAY), float(FAST_LO),
                 f"floor = MAX_DELAY={MAX_DELAY} ticks (must survive the "
                 f"reward's own worst-case delay, including the extra decay "
                 f"contributed by other streams' engagements in between); "
                 f"ceiling = FAST_LO={FAST_LO} (the fastest a stream-L rule "
                 f"lives) -- same disease decode_audit.py found, credit "
                 f"beyond a rule's own lifetime pays a dead hypothesis."),

    # ne_gain -- NE jump size per RPE event. UNCHANGED: architectural ceiling
    # NE_MAX=3.0 (below), unrelated to which task is running; a single jump
    # of up to 2.0 needs >1 event to saturate regardless of task structure.
    "ne_gain": (0.0, 2.0,
               "unchanged: already inside the architectural ceiling "
               f"NE_MAX={NE_MAX} -- a task-independent fact about the "
               "chemistry's own saturation curve."),

    # ctx_gain -- MEASURED against THIS task's own observation, not copied
    # from RuleSwitchTask's. 5,000-tick empirical rollout (random policy,
    # alloc_bounds' own measurement, see build log): median ||obs|| = 3.25,
    # median ||leaky-context|| (lam=0.8) = 1.97 -- ratio 1.65. Capping so the
    # context block cannot out-shout the CURRENT tick's observation by more
    # than ~1.5x (same margin decode_audit.py used) gives
    # ctx_gain_max ~= 1.5 * 1.65 ~= 2.5. AllocWorld's own obs carries 6 pure-
    # noise distractor dims that RuleSwitchTask never had, which is exactly
    # why this task needed its OWN measurement instead of reusing 3.0.
    "ctx_gain": (0.1, 2.5,
                "measured on THIS task (median ||obs||=3.25, median "
                "||leaky-ctx||=1.97 at lam=0.8, 5,000-tick random-policy "
                "rollout): capped at ~1.5x that ratio so context cannot "
                "out-shout the current tick, mirroring decode_audit.py's "
                "margin but computed fresh because AllocWorld's 6 noise "
                "distractor dims change the observation's own scale."),

    # persist_gain -- NEW KNOB (5HT stickiness bonus toward repeating the
    # last-engaged stream, scaled by chem.patience() in [0,1]). NO PRIOR
    # SUCCESS/FAIL EVIDENCE EXISTS for this knob (first time it is used) --
    # this bound is architecture-only and should be revisited once seeds
    # exist. Ceiling reasoning: the bonus is added directly to Q-scores
    # before argmax; Q is clipped to +/-20 but REALISTIC achieved spreads
    # within this budget are far smaller (eta_q<=0.6, |rpe|<=~2.5 per
    # update, a few hundred updates per stream at best) -- gaps of a few
    # units are plausible, gaps of 20 are not. Capping the maximum bonus
    # (persist_gain since patience<=1) at 2.0 lets stickiness matter (a
    # bonus on the same order as a real learned gap) without being able to
    # override an arbitrarily large learned preference by fiat.
    "persist_gain": (0.0, 2.0,
                    "NEW KNOB, no prior evidence -- architecture-only bound: "
                    "capped so the maximum stickiness bonus (patience<=1) "
                    "sits on the same order as a realistic learned Q gap "
                    "under this budget, not able to override a strong "
                    "learned preference by fiat."),

    # oxt_gain -- NEW KNOB (OXT's plasticity multiplier: (1+oxt_gain*oxt) on
    # top of the DA/NE plasticity gate). NO PRIOR EVIDENCE. Ceiling reasoning:
    # parity with DA and NE's own architectural ceilings -- DA_MAX=2.0 caps
    # the DA term at (1+2.0)=3x, NE_MAX=3.0 caps the NE term at (1+3.0)=4x.
    # oxt_gain*OXT_MAX should land in the same order, not dwarf the other two
    # modulators by construction: 1.5*2.0=3.0 -> (1+3.0)=4x, matching NE's
    # own ceiling.
    "oxt_gain": (0.0, 1.5,
                "NEW KNOB, no prior evidence -- capped for PARITY with the "
                "existing DA_MAX=2.0 ((1+2.0)=3x) and NE_MAX=3.0 "
                "((1+3.0)=4x) architectural ceilings: 1.5*OXT_MAX(2.0)=3.0 "
                "-> (1+3.0)=4x, the same order, so OXT cannot dwarf the "
                "other three modulators purely by its own range."),
}

assert set(KNOB_BOUNDS) == set(PARAM_NAMES), (set(KNOB_BOUNDS) ^ set(PARAM_NAMES))


def decode_audited(theta):
    t = np.asarray(theta, dtype=np.float64)
    out = {}
    for i, name in enumerate(PARAM_NAMES):
        lo, hi, _why = KNOB_BOUNDS[name]
        if name == "eps_decay":
            out[name] = 10.0 ** (math.log10(lo) + (math.log10(hi) - math.log10(lo))
                                 * _sig(t[i]))
        else:
            out[name] = lo + (hi - lo) * _sig(t[i])
    assert_in_bounds(out)
    return out


def assert_in_bounds(knobs, eps=1e-9):
    for name, v in knobs.items():
        lo, hi = KNOB_BOUNDS[name][0], KNOB_BOUNDS[name][1]
        if not (lo - eps <= v <= hi + eps):
            raise AssertionError(
                f"decode_audited: knob '{name}'={v!r} outside its declared "
                f"interval [{lo}, {hi}] (see KNOB_BOUNDS in alloc_bounds.py). "
                f"Widen the bound only by editing the comment that justifies it.")


if __name__ == "__main__":
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"{'knob':<14}{'range':<22}reasoning")
    for k in PARAM_NAMES:
        lo, hi, why = KNOB_BOUNDS[k]
        print(f"{k:<14}[{lo:g},{hi:g}]{'':<10}{why[:70]}...")

    # self-test, same structure as test_decode_bounds.py
    n_checked = 0
    for edge in (-1e6, -30.0, -1.0, 0.0, 1.0, 30.0, 1e6):
        theta = np.full(N_PARAMS, edge, dtype=np.float64)
        assert_in_bounds(decode_audited(theta)); n_checked += 1
    for i in range(N_PARAMS):
        for edge in (-30.0, 30.0):
            theta = np.zeros(N_PARAMS, dtype=np.float64)
            theta[i] = edge
            assert_in_bounds(decode_audited(theta)); n_checked += 1
    rng = np.random.default_rng(20260822)
    for _ in range(2000):
        theta = rng.normal(0.0, rng.uniform(0.1, 50.0), N_PARAMS)
        assert_in_bounds(decode_audited(theta)); n_checked += 1
    for name, (lo, hi, why) in KNOB_BOUNDS.items():
        assert hi >= lo, f"{name}: hi < lo"
        assert isinstance(why, str) and len(why) > 20, f"{name}: no real reasoning"
    print(f"\nalloc_bounds.py self-test: {n_checked} theta vectors checked, "
         f"{len(KNOB_BOUNDS)} knobs bounded, all inside declared intervals. PASS")
