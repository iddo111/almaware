# -*- coding: utf-8 -*-
"""decode_audit.py — the theta -> knob decode audit, DONE ONCE, IN ONE PLACE.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

WHY THIS FILE EXISTS. Twice this project lost an experiment to the SAME bug
class, not a logic bug — a RANGE bug. The code did exactly what it said; what
it said was physically unreasonable for this task:

  1. ctx_gain — caught mid-run in the agentic arena. An unscaled context
     channel was drowned by the L2-normalised observation; an arm that looked
     broken was fine, the RANGE was wrong.
  2. trace_tau — decoded as 1 + 120*sigmoid(theta), letting the credit
     horizon reach 121 trials on a task whose rule lives ~10-60 trials. This
     one separates 24 held-out seeds PERFECTLY (AUC 1.00): every success
     trace_tau <= 7.51, every failure >= 10.29 (results/ARENA-BIMODAL-
     2026-08-21.json). A 37.5% "lottery" was a 100% capability wearing a bad
     decode.

This file is the audit the second bug demanded: EVERY one of the 10 ES-tuned
knobs in eran_agent.decode(), judged against the RULE-SWITCH TASK'S OWN SCALE
(tasks.RuleSwitchTask: CRIT_WINDOW=10, CRIT_HITS=8, BLOCK_MAX=60, oracle_acc=
0.905), not against "what a sigmoid can reach".

DESIGN RULE, so nobody can widen a range without meeting the argument: the
bound and the reasoning for it live TOGETHER in ``KNOB_BOUNDS`` below, and
``decode_audited`` is BUILT FROM that table, not hand-copied next to it. Widen
a number here and you widen the docstring's argument for it, in the same
diff, in the same place a reviewer is already looking.

EVIDENCE, not just theory. Every bound below cites either (a) a task constant
that makes a larger/smaller value physically meaningless, or (b) the actual
success/failure knob values from the 144-run bimodal probe (per-seed data in
results/ARENA-BIMODAL-2026-08-21.json, variant "base"), or both. Six of the
ten ranges are ORIGINALS kept unchanged, because the evidence says they are
fine — this audit does not invent problems to justify itself.

    knob            AUC(fail>succ)   verdict
    trace_tau        1.00 (0 err)    ABSURD, already known — fixed here (was flagged mid-audit, now permanent)
    strict_scale     0.926 (3 err)   ABSURD — fixed here
    ctx_gain         0.919 (3 err)   ABSURD, already known — TIGHTENED further here
    eta_v            0.874 (4 err)   ABSURD — fixed here
    eps_floor        0.867 (3 err)   ABSURD — fixed here
    lam              0.837 (5 err)   ABSURD — fixed here (same disease as trace_tau: a leak
                                     longer than the rule's own lifetime)
    proto_unique_used 0.789          (a DIAGNOSTIC, not a knob -- not decoded, no fix applies)
    eta_q            0.348           FINE, unchanged (see below)
    ne_gain          0.422           FINE, unchanged
    eps0             0.459           FINE, unchanged
    eps_decay        0.459           FINE, unchanged

AUCs are for the CURRENT (unaudited) decode's base-variant separators; see
results/DECODE-AUDIT-2026-08-22.json for the full table with reasoning.
"""
import math

import numpy as np

# import the task's own constants -- the bounds below are DERIVED from these,
# not chosen by feel. If tasks.RuleSwitchTask ever changes its timing, this
# whole file's reasoning should be re-checked against the new numbers.
from tasks import RuleSwitchTask
from eran_agent import PARAM_NAMES, N_PARAMS, ETA0  # noqa: F401  (re-exported)

CRIT_WINDOW = RuleSwitchTask.CRIT_WINDOW      # 10  -- min trials a rule lives
CRIT_HITS = RuleSwitchTask.CRIT_HITS          # 8   -- hits needed in that window
BLOCK_MAX = RuleSwitchTask.BLOCK_MAX          # 60  -- a block times out here
ORACLE_ACC = 0.905                            # hand-coded win-stay/lose-shift


def _sig(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


# ─────────────────────────────────────────────────────────────────────────
# THE TABLE. lo/hi are the DECODED (post-squash) bounds -- the physical
# units a person reasons in, not the raw theta. Every row states the
# argument for its own ceiling/floor; a row with "UNCHANGED" still states why
# the ORIGINAL range survives the audit, so silence is never the reason a
# range stays wide.
# ─────────────────────────────────────────────────────────────────────────
KNOB_BOUNDS = {

    # lam -- the leaky context's decay. WAS sig(t) => [0, 1), i.e. a memory
    # horizon 1/(1-lam) that can reach ~1e13 trials as lam -> 1. SAME DISEASE
    # AS trace_tau: this leak is folded into the KEY the organism uses to
    # spawn/match prototypes, so a horizon longer than a rule's own lifetime
    # (CRIT_WINDOW=10) mixes pre- and post-switch history into one
    # "conjunction" that can never be rule-specific. Bound so the worst case
    # horizon equals the rule's own minimum lifetime, exactly the anchor
    # already used for trace_tau below.
    #   evidence: base-variant AUC 0.837 (5/24 misclassified); ALL 4 failing
    #   seeds with lam >= 0.91 have horizon >= 11 trials (seeds 66/77/33/99 in
    #   ARENA-BIMODAL-2026-08-21.json). Best observed SUCCESS is lam=0.591
    #   (horizon 2.44) -- 0.9 gives real headroom above every success while
    #   removing the region where failures cluster.
    "lam": (0.0, 1.0 - 1.0 / CRIT_WINDOW,
            "context horizon 1/(1-lam) capped at CRIT_WINDOW=10 trials -- a "
            "leak that outlives the rule it's supposed to help recognise is "
            "not memory, it is noise smeared across a rule boundary."),

    # eta_q -- action-head (Q) learning rate. WAS 0.6*sig(t) => [0, 0.6].
    # UNCHANGED: no task-scale absurdity found. Q is clipped to [-20,20]
    # regardless, and 0.6 < 1 cannot make a single-trial update overshoot
    # into oscillation the way a rate >= 1 could. Evidence AGAINST a problem:
    # base-variant AUC 0.348 -- if anything HIGHER eta_q associates with
    # SUCCESS (succ mean 0.331 vs fail mean 0.253), the opposite of "the ES
    # exploits an absurd range".
    "eta_q": (0.0, 0.6,
              "unchanged: Q is hard-clipped to +/-20 elsewhere, rate<1 cannot "
              "overshoot, and AUC 0.348 on 24 seeds shows no failure mode "
              "lives here (higher eta_q trends WITH success, not failure)."),

    # eta_v -- value-baseline learning rate. WAS 0.6*sig(t) => [0, 0.6]. V is
    # meant to average a prototype's reward under the CURRENT rule; an
    # effective averaging window shorter than a handful of trials makes V
    # chase single +/-1 rewards instead of estimating anything. Anchor: keep
    # the implied window >= ~3 trials (a fraction of the rule's own 10-trial
    # minimum), i.e. eta_v <= 1/3.
    #   evidence: base AUC 0.874 (4/24 err); every SUCCESS seed has eta_v <=
    #   0.295 (best observed), several FAILURES sit far above that (up to
    #   0.570). 0.35 sits just above the best success with a small margin,
    #   removing the >0.4 tail where half the failures live.
    "eta_v": (0.0, 1.0 / 3.0,
              "value learning rate capped so its implied averaging window "
              "(1/eta_v) stays >= ~3 trials -- a value estimate that "
              "overwrites itself in 1-2 trials cannot represent 'this "
              "prototype's worth under the rule that's been live for 10'."),

    # eps0 -- exploration probability AT BIRTH. WAS sig(t) => [0, 1].
    # UNCHANGED: it decodes to a PROBABILITY, and 1 is the only physically
    # possible ceiling for a probability. Nothing to bound further.
    "eps0": (0.0, 1.0,
             "unchanged: this IS a probability; [0,1] is not a choice, it is "
             "the type."),

    # eps_decay -- per-step exploration decay. WAS 10**(-1-4*sig(t)) =>
    # [1e-5, 1e-1] per env-step. UNCHANGED: life budgets here are millions of
    # steps (half of 12,000,000 = 6,000,000 to the online life alone); even
    # the SLOWEST decay (1e-5/step) reaches the floor within ~1e5 steps, ~2%
    # of that budget, and the FASTEST (1e-1/step) reaches it within ~10
    # steps -- both ends are "reachable" and neither strands the agent in a
    # regime that cannot recover before the budget runs out.
    #   evidence: base AUC 0.459 -- indistinguishable from chance.
    "eps_decay": (1e-5, 1e-1,
                  "unchanged: both extremes resolve within a small fraction "
                  "of the 6,000,000-step online-life budget, and AUC 0.459 "
                  "(24 seeds) is chance-level -- no failure mode traced here."),

    # eps_floor -- exploration rate maintained FOREVER (training AND eval;
    # act() applies self.eps regardless of frozen_eval). WAS 0.5*sig(t) =>
    # [0, 0.5]. Physical ceiling: to have any chance of hitting the block's
    # own criterion (CRIT_HITS/CRIT_WINDOW = 8/10 = 80% accuracy in a
    # 10-trial window), the EXPECTED accuracy with residual random actions
    # among 3 choices must clear 80%: 1 - (2/3)*eps_floor >= 0.80 =>
    # eps_floor <= 0.30. That is a hard mathematical ceiling -- ABOVE it the
    # rule can in expectation never be relearned even once, guaranteeing a
    # BLOCK_MAX=60 timeout every single block. The old range's max (0.5)
    # sits inside that dead zone.
    #   evidence: base AUC 0.867 (3/24 err); every SUCCESS <= 0.219, several
    #   FAILURES already sit at or above the 0.30 hard limit. New ceiling
    #   0.25 keeps a safety margin below the 0.30 mathematical wall while
    #   sitting just above the best observed success.
    "eps_floor": (0.0, 0.25,
                  "capped below the CRIT_HITS/CRIT_WINDOW=8/10 hard limit "
                  "(residual random actions among 3 choices make the 80% "
                  "criterion mathematically unreachable once eps_floor>0.30; "
                  "0.25 keeps a margin and still clears every observed "
                  "success, whose max was 0.219)."),

    # strict_scale -- multiplies the organism's own age-graded strictness k
    # (STRICTNESS_INFANT=0.5 .. STRICTNESS_ADULT=3.0, already a sensible
    # built-in curve). WAS 0.2 + 3.0*sig(t) => [0.2, 3.2], so the COMBINED
    # multiplier on the tolerance's sd term could reach 3.0*3.2 = 9.6 --
    # spawn threshold pushed ~9.6 sd below the mean similarity, i.e. a
    # tolerance far below any cosine similarity ever seen, meaning the
    # organism can no longer spawn a new prototype for the rest of its life
    # regardless of how surprising the input is. New ceiling keeps the
    # combined multiplier under ~4.5 (0.2..1.5 * 0.5..3.0), well inside a
    # range where TOLERANCE_MIN_SD=0.02 keeps the tolerance a plausible
    # cosine value rather than an unreachable one.
    #   evidence: base AUC 0.926 (3/24 err, second-strongest separator after
    #   trace_tau); every SUCCESS <= 1.180, FAILURES range 0.860-2.396. 1.5
    #   sits just above the best success and well below the failure tail.
    "strict_scale": (0.2, 1.5,
                      "combined with the organism's own age curve (0.5..3.0) "
                      "the effective sd-multiplier is capped near 4.5 instead "
                      "of 9.6 -- beyond that the spawn tolerance falls below "
                      "any plausible cosine similarity and the organism can "
                      "never differentiate a new rule from an old one again."),

    # trace_tau -- THE mechanism this whole audit started from. WAS
    # 1 + 120*sig(t) => [1, 121] trials of eligibility. Reward here arrives
    # on the SAME step as the action (no gap to bridge), and a rule lives at
    # least CRIT_WINDOW=10 trials, so ANY credit horizon longer than 10
    # necessarily pays a reward earned under the new rule back to prototypes
    # that acted under the dead one, on other cards. Bound: exactly
    # CRIT_WINDOW.
    #   evidence: base AUC 1.00, ZERO misclassifications on 24 seeds -- every
    #   success <= 7.51, every failure >= 10.29. This is the fix already
    #   proven by the "taucap" variant (37.5% -> 62.5%, +11.6pp SE 4.2,
    #   McNemar +8/-2 p=0.109); this file makes it the PERMANENT range.
    "trace_tau": (1.0, float(CRIT_WINDOW),
                  "eligibility horizon capped at CRIT_WINDOW=10 -- credit "
                  "cannot span longer than the rule it's paying for without "
                  "smearing reward across a silent rule change. AUC 1.00, "
                  "0 misclassifications on 24 held-out seeds."),

    # ne_gain -- chemistry's NE jump size on a reward-prediction-error event.
    # WAS 2.0*sig(t) => [0, 2]. UNCHANGED: this is already bounded well
    # inside the architectural ceiling NE_MAX=3.0 (a single jump can add at
    # most 2.0, needing >1 event to saturate), and the chemistry arm was
    # measured to do NOTHING on this task either way (verdict: -2.9 +/- 2.2
    # pp vs no-chemistry, indistinguishable from zero). AUC 0.422 -- chance.
    "ne_gain": (0.0, 2.0,
                "unchanged: already inside the NE_MAX=3.0 architectural cap, "
                "and chemistry was measured to do nothing on this task "
                "(-2.9+/-2.2pp, indistinguishable from zero); AUC 0.422."),

    # ctx_gain -- how loud the leaky-context block is inside the L2-
    # normalised key, next to the raw observation block. WAS 0.1 + 8.0*sig(t)
    # => [0.1, 8.1]. This is the ORIGINAL bug (caught mid-arena: too LOW
    # drowns the context). This audit finds the fix's own ceiling is STILL
    # too generous in the other direction: the observation for RuleSwitchTask
    # is a handful of one-hot bits (norm ~1.4-2.0); at gain 8.1 the context
    # block's norm can reach ~4-8x the observation's, so the CURRENT card
    # (colour/shape) is what gets drowned instead. Ceiling lowered to keep
    # the context block within roughly 1.5x the observation's own scale at
    # its most generous.
    #   evidence: base AUC 0.919 (3/24 err); every SUCCESS <= 1.354 (mean
    #   0.852), FAILURES range 0.691-7.384 with 12/15 above 1.576. 3.0 keeps
    #   more than 2x headroom above the best success while removing the
    #   4-7.4 tail where the observation is functionally invisible.
    "ctx_gain": (0.1, 3.0,
                 "context loudness capped so it cannot out-shout the CURRENT "
                 "card by more than ~1.5x its own scale -- the mirror image "
                 "of the original bug (context too quiet); every observed "
                 "success used <=1.354, so 3.0 is generous headroom, not a "
                 "tight squeeze."),
}

# sanity: every PARAM_NAMES entry must have a bound, and vice versa.
assert set(KNOB_BOUNDS) == set(PARAM_NAMES), (
    set(KNOB_BOUNDS) ^ set(PARAM_NAMES))


def decode_audited(theta):
    """theta (10,) -> dict of physically-bounded knobs. Built FROM
    KNOB_BOUNDS so the table above is the only place a range can change."""
    t = np.asarray(theta, dtype=np.float64)
    lam_lo, lam_hi, _ = KNOB_BOUNDS["lam"]
    eq_lo, eq_hi, _ = KNOB_BOUNDS["eta_q"]
    ev_lo, ev_hi, _ = KNOB_BOUNDS["eta_v"]
    e0_lo, e0_hi, _ = KNOB_BOUNDS["eps0"]
    ed_lo, ed_hi, _ = KNOB_BOUNDS["eps_decay"]
    ef_lo, ef_hi, _ = KNOB_BOUNDS["eps_floor"]
    ss_lo, ss_hi, _ = KNOB_BOUNDS["strict_scale"]
    tt_lo, tt_hi, _ = KNOB_BOUNDS["trace_tau"]
    ng_lo, ng_hi, _ = KNOB_BOUNDS["ne_gain"]
    cg_lo, cg_hi, _ = KNOB_BOUNDS["ctx_gain"]

    out = {
        "lam":          lam_lo + (lam_hi - lam_lo) * _sig(t[0]),
        "eta_q":        eq_lo + (eq_hi - eq_lo) * _sig(t[1]),
        "eta_v":        ev_lo + (ev_hi - ev_lo) * _sig(t[2]),
        "eps0":         e0_lo + (e0_hi - e0_lo) * _sig(t[3]),
        "eps_decay":    10.0 ** (math.log10(ed_lo)
                                  + (math.log10(ed_hi) - math.log10(ed_lo))
                                  * _sig(t[4])),
        "eps_floor":    ef_lo + (ef_hi - ef_lo) * _sig(t[5]),
        "strict_scale": ss_lo + (ss_hi - ss_lo) * _sig(t[6]),
        "trace_tau":    tt_lo + (tt_hi - tt_lo) * _sig(t[7]),
        "ne_gain":      ng_lo + (ng_hi - ng_lo) * _sig(t[8]),
        "ctx_gain":     cg_lo + (cg_hi - cg_lo) * _sig(t[9]),
    }
    assert_in_bounds(out)
    return out


def assert_in_bounds(knobs, eps=1e-9):
    """THE GUARD (item 6). Every decoded value must sit inside the interval
    KNOB_BOUNDS declares for it. A range nobody can justify in a comment
    should not exist -- so if this ever fires, the fix is to either correct
    the decode formula or write the argument for a wider bound INTO
    KNOB_BOUNDS, not to loosen this check."""
    for name, v in knobs.items():
        lo, hi = KNOB_BOUNDS[name][0], KNOB_BOUNDS[name][1]
        if not (lo - eps <= v <= hi + eps):
            raise AssertionError(
                f"decode_audited: knob '{name}'={v!r} outside its declared "
                f"sensible interval [{lo}, {hi}] (see KNOB_BOUNDS reasoning "
                f"in decode_audit.py). Widen the bound only by editing the "
                f"comment that justifies it.")


# ── the agent that uses the audited decode instead of eran_agent.decode ────
from eran_agent import EranAgent  # noqa: E402


class AuditedAgent(EranAgent):
    """EranAgent, mode='ctx', with EVERY ES-tunable knob run through
    decode_audited() instead of eran_agent.decode(). Nothing else about the
    organism changes -- same prototype memory, same action head, same
    learning rule. This is the full audit as a single drop-in agent, so it
    can be measured with the exact same harness (bimodal.py/es.py/tasks.py)
    as every other variant."""

    def set_params(self, theta):
        self.theta = np.asarray(theta, dtype=np.float64)
        self.p = decode_audited(self.theta)


if __name__ == "__main__":
    # quick human-readable dump of the table, and the self-test (also in
    # test_decode_bounds.py) so `python decode_audit.py` alone is a useful
    # smoke test.
    print(f"{'knob':<14}{'old range':<18}{'new range':<18}reasoning")
    OLD = {"lam": (0, 1), "eta_q": (0, 0.6), "eta_v": (0, 0.6), "eps0": (0, 1),
           "eps_decay": (1e-5, 1e-1), "eps_floor": (0, 0.5),
           "strict_scale": (0.2, 3.2), "trace_tau": (1, 121),
           "ne_gain": (0, 2), "ctx_gain": (0.1, 8.1)}
    for k in PARAM_NAMES:
        lo, hi, why = KNOB_BOUNDS[k]
        olo, ohi = OLD[k]
        changed = " (CHANGED)" if (round(olo, 6), round(ohi, 6)) != \
            (round(lo, 6), round(hi, 6)) else " (unchanged)"
        print(f"{k:<14}[{olo:g},{ohi:g}]{changed:<18}[{lo:g},{hi:g}]")
    import test_decode_bounds as T
    T.run()
    print("\ndecode_audit.py self-test: PASS")
