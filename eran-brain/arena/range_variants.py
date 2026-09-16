# -*- coding: utf-8 -*-
"""range_variants.py — ONE knob re-ranged per variant. Nothing else moves.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

WHY THIS FILE EXISTS.
decode_audit.py (2026-08-22 01:00) changed SIX ranges at once and measured the
bundle. The bundle scored 24/24, but a bundle cannot tell you which range
mattered -- and two of its six arguments turn out to be wrong on inspection
(see STRUCTURAL-AUDIT-2026-08-22.md: the eps_floor "hard wall at 0.30" does
not exist, and the strict_scale "can never spawn again" region is not
reachable). A bundled win built partly on wrong arguments is not knowledge.

So: one knob per variant, every variant on the SAME 24 seeds at the SAME
12,000,000-step budget through the SAME harness (bimodal.py), against the
already-recorded base (9/24) and taucap (15/24) from
results/ARENA-BIMODAL-2026-08-21.json.

TWO KINDS OF INTERVENTION, AND WHY BOTH ARE NEEDED.
Re-ranging a knob does two things at once, and they are usually confused:

  (a) it removes a region of the search space, and
  (b) it moves where the ES search STARTS, because theta is initialised at
      N(0,1) and the decode maps theta=0 to the middle of whatever range it
      is given.

At theta=0 the ORIGINAL decode starts every search at trace_tau=61 and
ctx_gain=4.1 -- for the rule task, 6x the rule's own lifetime and a context
loud enough to cut the card-discrimination margin from 0.40 to 0.023. So the
original search does not merely *permit* the absurd region, it *begins* inside
it. A squash-style variant (LamCapAgent, TauCapAgent, and everything here
marked "squash") changes (a) and (b) together and cannot separate them.

`taushift` is the control that separates them: it leaves trace_tau's ceiling
at the original 121 -- the absurd region stays fully reachable -- and only
moves the starting point to 10. If taushift alone recovers most of taucap's
gain, then what was broken was the PRIOR, not the ceiling, and every "cap" in
this project is fixing the right thing for the wrong reason.
"""
import math

import numpy as np

from eran_agent import EranAgent, PARAM_NAMES

IDX = {name: i for i, name in enumerate(PARAM_NAMES)}


def _sig(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


# ── the original decode formulas, keyed by knob, as functions of sigmoid s ──
# Kept here explicitly so a "squash" variant and the original differ in ONE
# number that a reader can see side by side.
ORIGINAL = {
    "lam":          (0.0, 1.0,   lambda s: s),
    "eta_q":        (0.0, 0.6,   lambda s: 0.6 * s),
    "eta_v":        (0.0, 0.6,   lambda s: 0.6 * s),
    "eps0":         (0.0, 1.0,   lambda s: s),
    "eps_decay":    (1e-5, 1e-1, lambda s: 10.0 ** (-1.0 - 4.0 * s)),
    "eps_floor":    (0.0, 0.5,   lambda s: 0.5 * s),
    "strict_scale": (0.2, 3.2,   lambda s: 0.2 + 3.0 * s),
    "trace_tau":    (1.0, 121.0, lambda s: 1.0 + 120.0 * s),
    "ne_gain":      (0.0, 2.0,   lambda s: 2.0 * s),
    "ctx_gain":     (0.1, 8.1,   lambda s: 0.1 + 8.0 * s),
}


# ── the single-knob interventions ──────────────────────────────────────────
# Each entry: knob, kind, argument, and the STRUCTURAL argument for it. No
# entry may cite which seeds succeeded -- that is what the first audit did, and
# it is why its numbers could not be believed.
SINGLE_KNOB = {
    "gaincap": dict(
        knob="ctx_gain", kind="squash", lo=0.1, hi=1.5,
        why=("STRUCTURAL: the key is L2-normalised, so ctx_gain sets how much "
             "of the unit key is context rather than the card that must be "
             "classified. Measured on the real stream (STRUCTURAL-PROBE, "
             "rule_tradeoff_competent): card margin falls 0.40 -> 0.023 as "
             "gain goes 0.1 -> 8.1, while the rule signal the context buys "
             "never exceeds 0.004 at ANY (lam, gain). The channel cannot pay "
             "for what it costs above ~1.5, where card margin is still 0.19.")),

    "lamcap": dict(
        knob="lam", kind="squash", lo=0.0, hi=0.9,
        why=("HYPOTHESIS UNDER TEST, NOT A DERIVED BOUND. 1/(1-lam) capped at "
             "CRIT_WINDOW=10. Stated honestly: four structural probes (context "
             "loudness, card/rule margin, within-episode drift, post-switch "
             "addressing recovery) FAILED to find any mechanism by which a "
             "long lam hurts this task -- if anything a saturated context is "
             "a near-constant vector that dilutes less than a short one. The "
             "bound is therefore proposed as a MEASUREMENT, not as a "
             "conclusion; see the audit's open question.")),

    "epsfloorcap": dict(
        knob="eps_floor", kind="squash", lo=0.0, hi=0.15,
        why=("STRUCTURAL: eps is never reset for evaluation (act() applies "
             "self.eps whatever frozen_eval says), so eps_floor is a PERMANENT "
             "tax on the reported score. With 3 actions the best attainable "
             "accuracy is 1-(2/3)*eps_floor; parity with this arena's own "
             "oracle (90.5%) needs eps_floor <= 0.1425. NOTE: this is an "
             "optimality bound, NOT an absurdity bound -- the measured "
             "criterion is still reachable at eps_floor=0.5 (98.3% of blocks, "
             "mean ttc 19.6), which falsifies the earlier audit's claim of a "
             "hard wall at 0.30.")),

    "strictcap": dict(
        knob="strict_scale", kind="squash", lo=0.2, hi=1.5,
        why=("FALSIFICATION TEST. The earlier audit capped this at 1.5 on the "
             "argument that the combined multiplier 3.0*3.2=9.6 pushes the "
             "spawn tolerance below any reachable cosine, so the organism "
             "'can never spawn again'. Measured (STRUCTURAL-PROBE.strictness): "
             "spawning actually dies at effective k ~28 (rule), ~50 (dms16), "
             "~39-50 (pong) -- far ABOVE the reachable maximum of 9.6. The "
             "region the argument describes does not exist. Run to confirm "
             "the cap buys nothing.")),

    "etavcap": dict(
        knob="eta_v", kind="squash", lo=0.0, hi=1.0 / 3.0,
        why=("WEAK STRUCTURAL: V[i] is a per-prototype reward baseline and "
             "1/eta_v is its effective averaging window; above eta_v~0.33 the "
             "baseline is rewritten within ~3 trials, so rpe = r - V tracks "
             "the last reward rather than the prototype's worth under a rule "
             "that lives >=10 trials. Bounded by the rule's own timescale, "
             "not by which seeds happened to win.")),

    "taushift": dict(
        knob="trace_tau", kind="recentre", target=10.0,
        why=("THE CONFOUND CONTROL, and the most informative run here. The "
             "ceiling stays at the original 121 -- the whole 'absurd' region "
             "remains reachable -- and ONLY the starting point moves, from "
             "trace_tau=61 at theta=0 to trace_tau=10. If this recovers most "
             "of taucap's +6/24, the pathology was never the reachable range: "
             "it was that ES begins its search 6x outside the rule's own "
             "lifetime and has to climb out. That would mean the whole 'cap "
             "the range' framing is treating a prior as if it were a bound.")),
}


def _make_class(spec):
    knob = spec["knob"]
    i = IDX[knob]
    if spec["kind"] == "squash":
        lo, hi = spec["lo"], spec["hi"]

        def remap(theta):
            return lo + (hi - lo) * _sig(theta[i])
    elif spec["kind"] == "recentre":
        lo, hi, f = ORIGINAL[knob]
        target = spec["target"]
        # solve for the shift that puts theta=0 at `target`, ceiling untouched
        s_star = (target - lo) / (hi - lo)
        shift = math.log(s_star / (1.0 - s_star))

        def remap(theta, _f=f, _sh=shift):
            return _f(_sig(theta[i] - _sh))
    else:
        raise ValueError(spec["kind"])

    class _V(EranAgent):
        _knob = knob
        _spec = spec

        def set_params(self, theta):
            super().set_params(theta)
            self.p[knob] = float(remap(np.asarray(theta, dtype=np.float64)))

    _V.__name__ = f"Variant_{knob}"
    _V.__doc__ = spec["why"]
    return _V


CLASSES = {name: _make_class(spec) for name, spec in SINGLE_KNOB.items()}



# ── LAYER 2: one change at a time, but measured ON TOP OF the trace_tau fix ──
# WHY THIS LAYER EXISTS. Layer 1 measures each range against the recorded
# `base`, where trace_tau is still decoded over [1,121] and every ES search
# still starts at tau=61. That defect is large enough to mask the others: a
# seed can have a perfectly sensible ctx_gain and still fail because its credit
# horizon is 9x the rule's lifetime.
#
# The question actually asked is the marginal one -- "after the trace_tau fix
# they became the binding constraint". So each variant here is taucap (the
# already-measured 15/24 reference) plus EXACTLY ONE further range change.
# One change at a time, relative to a stated reference.
TAU_CAP = 10.0


def _tau_squash(theta):
    return 1.0 + (TAU_CAP - 1.0) * _sig(theta[IDX["trace_tau"]])


LAYER2 = {
    "tau+gaincap":    dict(knob="ctx_gain", lo=0.1, hi=1.5),
    "tau+lamcap":     dict(knob="lam", lo=0.0, hi=0.9),
    "tau+epsfloorcap": dict(knob="eps_floor", lo=0.0, hi=0.15),
}


def _make_layer2(name, spec):
    knob = spec["knob"]
    i = IDX[knob]
    lo, hi = spec["lo"], spec["hi"]

    class _V2(EranAgent):
        _knob = knob

        def set_params(self, theta):
            super().set_params(theta)
            th = np.asarray(theta, dtype=np.float64)
            self.p["trace_tau"] = float(_tau_squash(th))
            self.p[knob] = float(lo + (hi - lo) * _sig(th[i]))

    _V2.__name__ = f"Variant2_{knob}"
    _V2.__doc__ = (f"taucap (trace_tau -> [1,{TAU_CAP:g}]) PLUS {knob} -> "
                   f"[{lo:g},{hi:g}]. Reference for this arm is taucap (15/24), "
                   f"not base -- the single change under test is {knob}.")
    return _V2


CLASSES.update({n: _make_layer2(n, sp) for n, sp in LAYER2.items()})



# ── LAYER 3: lam, tested where it could still possibly bind ────────────────
# PRE-REGISTERED, and the reason is stated before the run. tau+gaincap reaches
# 21/24; its three remaining failures have lam 0.767 against 0.292 for its
# successes. lamcap ALONE was null (8/24), so if lam matters at all it can only
# matter once the two dominant defects are already gone. This arm is exactly
# that test: taucap + gaincap (the measured 21/24 reference) plus ONE further
# change, lam -> [0, 0.9].
#
# Honest prior: four structural probes found no mechanism for lam, and the
# single-knob arm was null. I expect this to be null too, and the residual lam
# correlation to be the same confounding with ctx_gain seen everywhere else.
# If it is NOT null, the audit's open question has an answer and the follow-up
# is a spawn-dynamics probe over a full lifetime.
LAYER3 = {"tau+gain+lamcap": dict(lo=0.0, hi=0.9)}


def _make_layer3(spec):
    lo, hi = spec["lo"], spec["hi"]
    il, ig = IDX["lam"], IDX["ctx_gain"]

    class _V3(EranAgent):
        def set_params(self, theta):
            super().set_params(theta)
            th = np.asarray(theta, dtype=np.float64)
            self.p["trace_tau"] = float(_tau_squash(th))
            self.p["ctx_gain"] = float(0.1 + (1.5 - 0.1) * _sig(th[ig]))
            self.p["lam"] = float(lo + (hi - lo) * _sig(th[il]))

    _V3.__name__ = "Variant3_lam"
    _V3.__doc__ = ("taucap + gaincap (reference 21/24) PLUS lam -> [0,0.9]. "
                   "The single change under test is lam.")
    return _V3


CLASSES.update({n: _make_layer3(sp) for n, sp in LAYER3.items()})


def make(name, n_obs, n_actions, seed):
    """Return the single-knob variant agent, or None if `name` isn't one."""
    cls = CLASSES.get(name)
    if cls is None:
        return None
    return cls(n_obs, n_actions, mode="ctx", chemistry=False, seed=seed)


def describe():
    rows = []
    for name, spec in SINGLE_KNOB.items():
        knob = spec["knob"]
        olo, ohi, _ = ORIGINAL[knob]
        if spec["kind"] == "squash":
            new = f"[{spec['lo']:g}, {spec['hi']:g}]"
            start = spec["lo"] + (spec["hi"] - spec["lo"]) * 0.5
        else:
            new = f"[{olo:g}, {ohi:g}] (UNCHANGED)"
            start = spec["target"]
        rows.append({
            "variant": name, "knob": knob, "kind": spec["kind"],
            "original_range": f"[{olo:g}, {ohi:g}]", "new_range": new,
            "start_at_theta_zero_before": round(ORIGINAL[knob][2](0.5), 5),
            "start_at_theta_zero_after": round(start, 5),
            "why": spec["why"],
        })
    return rows


if __name__ == "__main__":
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for r in describe():
        print(f"\n{r['variant']:<14} {r['knob']:<13} {r['kind']}")
        print(f"  range {r['original_range']} -> {r['new_range']}")
        print(f"  ES starts at {r['start_at_theta_zero_before']} -> "
              f"{r['start_at_theta_zero_after']}")
    # self-test: every variant must change EXACTLY ONE knob
    from eran_agent import decode
    rng = np.random.default_rng(0)
    bad = []
    for name, cls in CLASSES.items():
        for _ in range(200):
            th = rng.normal(0, 1, len(PARAM_NAMES))
            a = cls(10, 3, mode="ctx", seed=0)
            a.set_params(th)
            base = decode(th)
            diff = [k for k in PARAM_NAMES
                    if abs(base[k] - a.p[k]) > 1e-12]
            if diff != [SINGLE_KNOB[name]["knob"]] and diff != []:
                bad.append((name, diff))
                break
    if bad:
        raise SystemExit(f"NOT single-knob: {bad}")
    print("\nself-test: every variant changes exactly one knob  PASS")
