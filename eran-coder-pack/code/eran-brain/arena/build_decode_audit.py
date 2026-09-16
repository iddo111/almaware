# -*- coding: utf-8 -*-
"""build_decode_audit.py — assemble results/DECODE-AUDIT-2026-08-22.json.

Reads:
  * results/ARENA-BIMODAL-2026-08-21.json   (base/chem/taucap/.../transplant,
    already merged, 24 seeds each — the recorded baselines)
  * results/BIMODAL-audited-2026-08-22.json (this audit's rerun, 24 seeds,
    same seeds, same 12,000,000-step budget, produced by bimodal.py
    --variants audited)

Writes results/DECODE-AUDIT-2026-08-22.json: the full knob inventory (every
range, old vs new, the reasoning, the evidence), then the "audited" variant
measured the same way merge_bimodal.py measured everything else, paired
against BOTH base (does the full audit beat doing nothing) and taucap (does
the full audit beat fixing trace_tau alone).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

sys.path.insert(0, HERE)
import merge_bimodal as MB                                        # noqa: E402
from decode_audit import KNOB_BOUNDS, PARAM_NAMES                  # noqa: E402

OLD_RANGES = {
    "lam": (0.0, 1.0), "eta_q": (0.0, 0.6), "eta_v": (0.0, 0.6),
    "eps0": (0.0, 1.0), "eps_decay": (1e-5, 1e-1), "eps_floor": (0.0, 0.5),
    "strict_scale": (0.2, 3.2), "trace_tau": (1.0, 121.0),
    "ne_gain": (0.0, 2.0), "ctx_gain": (0.1, 8.1),
}

UNITS = {
    "lam": "context-leak coefficient (dimensionless, 0..1); horizon = "
           "1/(1-lam) trials",
    "eta_q": "action-head (Q) learning rate, per trial",
    "eta_v": "value-baseline learning rate, per trial",
    "eps0": "exploration probability at birth (0..1)",
    "eps_decay": "exploration decay per environment step",
    "eps_floor": "residual exploration probability, held forever "
                 "(training AND evaluation)",
    "strict_scale": "multiplier on the organism's own age-graded strictness "
                    "k (0.5 infant .. 3.0 adult)",
    "trace_tau": "eligibility-trace horizon, in trials",
    "ne_gain": "noradrenaline jump size per reward-prediction-error event",
    "ctx_gain": "loudness of the leaky-context block inside the L2-"
                "normalised prototype key, relative to the raw observation",
}


def knob_verdict(name, base_separators):
    sep = next((s for s in base_separators if s["variable"] == name), None)
    old_lo, old_hi = OLD_RANGES[name]
    new_lo, new_hi, why = KNOB_BOUNDS[name]
    changed = (round(old_lo, 6), round(old_hi, 6)) != (round(new_lo, 6),
                                                        round(new_hi, 6))
    auc = sep["auc_fail_over_success"] if sep else None
    errs = sep["misclassified"] if sep else None
    if auc is None:
        flag = "not measured"
    else:
        sep_strength = abs(auc - 0.5)
        flag = "ABSURD — fixed" if changed else (
            "flagged (kept wide; see reasoning)" if sep_strength > 0.3
            else "fine, unchanged")
    return {
        "knob": name,
        "unit": UNITS[name],
        "old_range": [old_lo, old_hi],
        "new_range": [round(new_lo, 6), round(new_hi, 6)],
        "changed": changed,
        "base_variant_evidence": {
            "auc_fail_over_success": auc,
            "misclassified_of_24": errs,
            "fail_mean": sep["fail_mean"] if sep else None,
            "success_mean": sep["success_mean"] if sep else None,
        },
        "reasoning": why,
        "verdict": flag,
    }


PONG_ALMA_FINDINGS = [
    {
        "file": "D:\\CLAUDE\\pong-alma\\player_beitdin.py",
        "knob": "Dayan.threshold",
        "expression": "0.25 + abs(thr_raw)",
        "range": "[0.25, +inf) — NO upper bound at all, not even a wide one",
        "task_scale_reasoning": (
            "The judge's LIF chamber integrates for LIF_STEPS=6 ticks at "
            "LIF_DT=0.35 (a 2.1-time-unit budget) starting from v=0. Once "
            "threshold exceeds what that budget can reach for a "
            "plausible drive magnitude (drive is itself an unbounded "
            "amp*ctx term, but empirically O(1) near ES birth), the "
            "chamber can never spike and the judge is permanently mute — "
            "same disease as ctx_gain/trace_tau (an ES-reachable region "
            "makes the knob's own mechanism inert), just with an infinite "
            "rather than merely-too-wide ceiling."),
        "blast_radius": (
            "LOW / contained. The controller needs 2 of 3 judges to agree "
            "(majority quorum); one silenced judge degrades the ensemble "
            "toward the remaining 2 judges' agreement rather than causing "
            "a silent total failure the way trace_tau's 121-trial horizon "
            "did for the WHOLE agent. No documented experiment has been "
            "traced to this range; it is flagged on inspection, not from "
            "a burned run."),
        "action_taken": (
            "FLAGGED, NOT FIXED in this pass. pong-alma's own ES benchmark "
            "(arena.py round-robin) is a separate codebase from the "
            "eran-brain rule-switching rerun this audit was scoped to "
            "measure; changing player_beitdin.py's threshold formula would "
            "need its own re-run of arena.py to verify, which was not "
            "requested. Recommended future bound: threshold in roughly "
            "[0.25, 3-5], derived the same way trace_tau's was — from "
            "LIF_STEPS*LIF_DT and the typical drive scale."),
    },
    {
        "file": "D:\\CLAUDE\\pong-alma\\player_beitdin.py",
        "knob": "Dayan.leak",
        "expression": "0.05 + 0.45/(1+exp(-leak_raw))",
        "range": "[0.05, 0.5] — sigmoid-squashed, already bounded",
        "task_scale_reasoning": (
            "Over LIF_STEPS=6 ticks at dt=0.35, leak=0.5 leaves ~32% of a "
            "constant drive's integral after 6 ticks and leak=0.05 leaves "
            "~90% — both are plausible integration regimes for a 6-tick "
            "window; neither extreme makes the chamber's own dynamics "
            "meaningless."),
        "blast_radius": "none found",
        "action_taken": "no issue found; not fixed, not flagged as absurd.",
    },
    {
        "file": "D:\\CLAUDE\\pong-alma\\player_multiweight.py",
        "knob": "MultiWeightEdge.gate (sigmoid(gate_raw))",
        "expression": "_sigmoid(gate_raw)",
        "range": "(0, 1) — a gate, this IS its natural bound",
        "task_scale_reasoning": "same class as eps0: the decoded quantity "
                                "is itself a probability/gate; (0,1) is "
                                "the type, not a choice.",
        "blast_radius": "none",
        "action_taken": "no issue found.",
    },
    {
        "file": "D:\\CLAUDE\\pong-alma\\player_gist.py / player_multiweight.py",
        "knob": "raw amp / phase / action-code genes (no squash at all)",
        "expression": "used directly as theta components",
        "range": "(-inf, +inf) by construction",
        "task_scale_reasoning": (
            "These are ordinary unbounded network weights / a "
            "quantization code with fixed cutoffs (+-0.33) that is valid "
            "for ANY real input — there is no squashing EXPRESSION here "
            "to have a wrong range in the first place (unlike Dayan."
            "threshold, which does apply a floor-plus-abs transform). Not "
            "an instance of this bug class."),
        "blast_radius": "n/a",
        "action_taken": "reviewed, not applicable to this bug class.",
    },
]


def main():
    base_path = os.path.join(RES, "ARENA-BIMODAL-2026-08-21.json")
    audited_bimodal_path = os.path.join(RES, "BIMODAL-audited-2026-08-22.json")
    baseline = json.load(open(base_path, encoding="utf-8"))
    audited_raw = json.load(open(audited_bimodal_path, encoding="utf-8"))

    base_runs = [r for r in baseline["runs"] if r["variant"] == "base"]
    taucap_runs = [r for r in baseline["runs"] if r["variant"] == "taucap"]
    transplant_runs = [r for r in baseline["runs"] if r["variant"] == "transplant"]
    audited_runs = [r for r in audited_raw["runs"] if r["variant"] == "audited"]
    assert len(audited_runs) == 24, len(audited_runs)

    base_block = baseline["variants"]["base"]
    base_seps = base_block["separators"]

    inventory = [knob_verdict(k, base_seps) for k in PARAM_NAMES]
    n_absurd = sum(1 for row in inventory if row["verdict"].startswith("ABSURD"))

    audited_block = MB.variant_block(audited_runs)
    vs_base = MB.paired(base_runs, audited_runs)
    vs_taucap = MB.paired(taucap_runs, audited_runs)
    vs_transplant = MB.paired(transplant_runs, audited_runs)

    payload = {
        "title": ("DECODE-RANGE AUDIT — every ES-tuned knob in eran_agent.py "
                  "judged against the rule-switch task's own scale, and "
                  "measured over the SAME 24 seeds as the recorded "
                  "baselines"),
        "date": "2026-08-22",
        "context": (
            "Two experiments were lost to the SAME bug class: an unbounded "
            "theta squashed into a knob whose RANGE was physically "
            "unreasonable (ctx_gain caught mid-arena-run; trace_tau found "
            "in the 24-seed bimodal probe, AUC 1.00 separator). This file "
            "is the full audit the second bug demanded: all 10 knobs, "
            "judged and — where absurd — fixed in one file "
            "(arena/decode_audit.py), then re-measured on the identical "
            "protocol (12,000,000 steps/seed, half ES over 10 knobs / half "
            "online life, 24 held-out episodes from seed 7,000,000, "
            "training only ever saw seeds 0..4,000,000)."),
        "chance": 1.0 / 3.0, "oracle_acc": 0.905, "oracle_ttc": 10.0,
        "one_trial_worth_pp": (
            "same as the bimodal probe: ~0.06 pp for a fast (~1,600-trial) "
            "arm, ~0.01 pp for a timing-out (~8,000-trial) arm; seed "
            "spread, not trial count, is the real uncertainty here too, "
            "hence the same 24 seeds."),
        "n_knobs_total": len(PARAM_NAMES),
        "n_knobs_flagged_absurd": n_absurd,
        "n_knobs_fine_unchanged": len(PARAM_NAMES) - n_absurd,
        "inventory": inventory,
        "pong_alma_findings": PONG_ALMA_FINDINGS,
        "rerun": {
            "variant": "audited",
            "n_seeds": 24,
            "budget_steps_per_seed": 12_000_000,
            "same_seeds_as_baseline": True,
            "result": audited_block,
        },
        "comparison_vs_base": vs_base,
        "comparison_vs_taucap": vs_taucap,
        "comparison_vs_transplant": vs_transplant,
        "recorded_baselines": {
            "base": {"n_success": 9, "n_seeds": 24, "success_rate": 0.375,
                     "wilson95": [0.2116, 0.5729]},
            "taucap": {"n_success": 15, "n_seeds": 24, "success_rate": 0.625,
                       "wilson95": [0.427, 0.788]},
            "transplant": {"n_success": 24, "n_seeds": 24, "success_rate": 1.0,
                           "wilson95": [0.862, 1.0]},
        },
        "suspect_past_results": [
            {
                "result": "AGENTIC-ARENA-2026-08-21.json / "
                          "AGENTIC-ARENA-VERDICT-2026-08-21.md — ERAN-CTX "
                          "rule-switching, 3 seeds (81.6% / 80.4% / 37.6%)",
                "why_suspect": (
                    "3 seeds drawn from a decode with 6 of 10 ranges later "
                    "found absurd; this audit's 24-seed base arm (same "
                    "unaudited decode) reproduces exactly that spread "
                    "(9/24 success, bimodal, Sarle 0.686) -- the 3-seed "
                    "report was a lottery sample, not a capability "
                    "measurement."),
                "status": "SUPERSEDED by ARENA-BIMODAL-2026-08-21.json and "
                          "this file.",
            },
            {
                "result": "ARENA-BIMODAL-VERDICT-2026-08-21.md's own "
                          "'taucap helps, not closes' conclusion (37.5% -> "
                          "62.5%, McNemar p=0.109, 9 failures remaining)",
                "why_suspect": (
                    "The 9 seeds that survived taucap but still failed were "
                    "attributed to 'secondary knobs' (lam/ctx_gain running "
                    "high) without a stated fix. This audit shows ALL 9 "
                    "succeed once lam/ctx_gain/eps_floor/eta_v/strict_scale "
                    "are also bounded (24/24, McNemar +9/-0 vs taucap, "
                    "p=0.0039) -- trace_tau was necessary but not "
                    "sufficient; the 'not closes' framing undersold how "
                    "close the full fix actually gets (100%, matching "
                    "transplant's success rate)."),
                "status": "SUPERSEDED — the gap taucap left open is now "
                          "closed, not just narrowed.",
            },
            {
                "result": "restart variant's negative finding (5/24 = "
                          "20.8%, worse than base) — 'a starved search "
                          "split three ways is starved further'",
                "why_suspect": "not suspect; CONFIRMED and now made moot. "
                              "The verdict's own recommendation was "
                              "'narrower ranges, not restarts' — this file "
                              "is exactly that fix, and a single un-"
                              "restarted ES run inside the audited ranges "
                              "reaches 100% with no extra restarts needed.",
                "status": "diagnosis confirmed; the restart variant itself "
                          "was never re-tested combined with the audited "
                          "ranges (not needed -- audited alone already "
                          "clears every seed).",
            },
        ],
        "scope_boundary": (
            "eran_agent.decode() is SHARED across all three agentic-arena "
            "tasks (DMS, RULE, PONG) — AGENTIC-ARENA-2026-08-21.json's "
            "ERAN-CTX/ERAN-TRACE/ERAN-PROTO numbers on DMS and PONG used "
            "the SAME 6 now-flagged ranges and may carry the same "
            "distortion. This audit's SPECIFIC numeric bounds, however, "
            "are derived from RuleSwitchTask's own constants (CRIT_WINDOW="
            "10 etc.) and are NOT a drop-in fix for DMS or PONG: DMS's "
            "delay sweep runs to 16 steps, so a trace_tau capped at 10 "
            "would be actively wrong there (it would forbid exactly the "
            "credit horizon DMS at delay=16 needs); PONG has a wholly "
            "different, continuous timescale (200-2000 ticks/episode). "
            "Any decode audit for DMS or PONG needs its own task-scale "
            "re-derivation from THEIR constants, following the same METHOD "
            "as this file, not the same NUMBERS."),
    }

    out_local = os.path.join(RES, "DECODE-AUDIT-2026-08-22.json")
    with open(out_local, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"wrote {out_local}")

    print(f"\naudited: {audited_block['n_success']}/24 = "
          f"{audited_block['success_rate']*100:.1f}% Wilson95 "
          f"{[round(x*100,1) for x in audited_block['success_wilson95']]}")
    print(f"vs base:        {vs_base}")
    print(f"vs taucap:      {vs_taucap}")
    print(f"vs transplant:  {vs_transplant}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
