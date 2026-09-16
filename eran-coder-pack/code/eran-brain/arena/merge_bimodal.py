# -*- coding: utf-8 -*-
"""merge_bimodal.py — build the single deliverable JSON and print the verdict.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Reads results/BIMODAL-phaseA.json + results/BIMODAL-phaseB.json and writes
results/ARENA-BIMODAL-2026-08-21.json: every seed of every variant, the per-seed
diagnostics, the separator analysis that names the mechanism, and every fix
measured over the SAME seeds at the SAME budget.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
SUCCESS_TTC = 20.0
CHANCE, ORACLE_ACC, ORACLE_TTC = 1.0 / 3.0, 0.905, 10.0

KNOBS = ["lam", "ctx_gain", "trace_tau", "eta_q", "eta_v", "eps0",
         "eps_decay", "eps_floor", "strict_scale", "ne_gain"]
DIAGS = ["mean_ctx_over_obs", "mean_attraction_margin", "mean_sim_top1",
         "action_max_share", "proto_top1_share", "proto_unique_used",
         "n_proto_eval_end", "proto_displacement_mean", "persev_rate"]
RUNLEVEL = ["es_train_score", "life_final", "life_first", "generations",
            "ctx_horizon_trials"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - h) / d, 4), round((c + h) / d, 4))


def auc(pos, neg):
    if not pos or not neg:
        return None
    n = sum(1.0 if p > q else (0.5 if p == q else 0.0)
            for p in pos for q in neg)
    return round(n / (len(pos) * len(neg)), 3)


def best_split(pos, neg):
    vals = sorted(set(list(pos) + list(neg)))
    best = (None, len(pos) + len(neg))
    for t in vals:
        for e in (sum(1 for p in pos if p <= t) + sum(1 for q in neg if q > t),
                  sum(1 for p in pos if p > t) + sum(1 for q in neg if q <= t)):
            if e < best[1]:
                best = (t, e)
    return best


def bimodality(x):
    x = np.asarray(x, float)
    n = len(x)
    if n < 4:
        return None
    m, s = x.mean(), x.std(ddof=1)
    if s == 0:
        return None
    g = ((x - m) ** 3).mean() / s ** 3
    k = ((x - m) ** 4).mean() / s ** 4 - 3.0
    return round(float((g * g + 1) /
                       (k + 3.0 * (n - 1) ** 2 / ((n - 2) * (n - 3)))), 4)


def binom_two_sided(k, n, p=0.5):
    """Exact two-sided binomial p-value (used for McNemar on 24 paired seeds)."""
    if n == 0:
        return 1.0
    def pmf(i):
        return math.comb(n, i) * p ** i * (1 - p) ** (n - i)
    obs = pmf(k)
    return round(min(1.0, sum(pmf(i) for i in range(n + 1)
                              if pmf(i) <= obs + 1e-12)), 4)


def ok(r):
    return r["ttc_mean_online"] < SUCCESS_TTC


def variant_block(runs):
    good = [r for r in runs if ok(r)]
    bad = [r for r in runs if not ok(r)]
    accs = sorted(r["acc_online"] for r in runs)
    a = np.array(accs)
    gaps = np.diff(a) if len(a) > 1 else np.array([0.0])
    gi = int(np.argmax(gaps))
    lo, hi = wilson(len(good), len(runs))
    blk = {
        "n_seeds": len(runs),
        "n_success": len(good), "n_fail": len(bad),
        "success_criterion": f"ttc_mean_online < {SUCCESS_TTC}",
        "success_rate": round(len(good) / max(1, len(runs)), 4),
        "success_wilson95": [lo, hi],
        "acc_mean": round(float(a.mean()), 4),
        "acc_median": round(float(np.median(a)), 4),
        "acc_sorted": [round(float(x), 4) for x in a],
        "ttc_sorted": sorted(round(r["ttc_mean_online"], 2) for r in runs),
        "per_seed": sorted(
            [{"seed": r["seed"], "acc_online": r["acc_online"],
              "acc_frozen": r["acc_frozen"],
              "ttc": round(r["ttc_mean_online"], 2),
              "ttc_reached_frac": r["ttc_reached_frac_online"],
              "persev_rate": r["diag"]["persev_rate"],
              "trace_tau": r["knobs"]["trace_tau"],
              "lam": r["knobs"]["lam"], "ctx_gain": r["knobs"]["ctx_gain"],
              "n_proto": r["diag"]["n_proto_eval_end"],
              "es_train_score": r.get("es_train_score"),
              "life_final": r.get("life_final"),
              "success": ok(r)} for r in runs],
            key=lambda x: x["acc_online"]),
        "largest_gap_pp": round(float(gaps[gi]) * 100, 2),
        "gap_between": [round(float(a[gi]), 4), round(float(a[gi + 1]), 4)]
        if len(a) > 1 else None,
        "sarle_bimodality": bimodality(a),
        "acc_success_mean": (round(float(np.mean([r["acc_online"] for r in good])), 4)
                             if good else None),
        "acc_fail_mean": (round(float(np.mean([r["acc_online"] for r in bad])), 4)
                          if bad else None),
        "ttc_success_mean": (round(float(np.mean([r["ttc_mean_online"] for r in good])), 3)
                             if good else None),
        "ttc_fail_mean": (round(float(np.mean([r["ttc_mean_online"] for r in bad])), 3)
                          if bad else None),
    }
    sep = []
    if good and bad:
        rows = [(k, [r["knobs"][k] for r in bad], [r["knobs"][k] for r in good])
                for k in KNOBS]
        rows += [(k, [r[k] for r in bad], [r[k] for r in good])
                 for k in RUNLEVEL if all(r.get(k) is not None for r in runs)]
        rows += [("diag." + k, [r["diag"][k] for r in bad],
                  [r["diag"][k] for r in good])
                 for k in DIAGS if all(r["diag"].get(k) is not None
                                       for r in runs)]
        for name, pv, nv in rows:
            A = auc(pv, nv)
            thr, errs = best_split(pv, nv)
            sep.append({"variable": name,
                        "fail_mean": round(float(np.mean(pv)), 5),
                        "success_mean": round(float(np.mean(nv)), 5),
                        "auc_fail_over_success": A,
                        "best_threshold": round(float(thr), 5),
                        "misclassified": errs,
                        "separates_perfectly": errs == 0})
        sep.sort(key=lambda d: (d["misclassified"],
                                -abs((d["auc_fail_over_success"] or .5) - .5)))
    blk["separators"] = sep
    # mean error / perseveration curve by trials-since-switch, per group
    for grp, nm in ((good, "success"), (bad, "fail")):
        for key, short in (("err_curve_by_since_switch", "err"),
                           ("persev_curve_by_since_switch", "persev")):
            if grp:
                M = np.array([[np.nan if v is None else v
                               for v in r["diag"][key]] for r in grp], float)
                blk[f"{short}_curve_{nm}"] = [round(float(v), 4)
                                              for v in np.nanmean(M, axis=0)]
    return blk


def paired(runs_a, runs_b):
    """runs_b vs runs_a on the shared seeds."""
    A = {r["seed"]: r for r in runs_a}
    B = {r["seed"]: r for r in runs_b}
    seeds = sorted(set(A) & set(B))
    if not seeds:
        return None
    d = [B[s]["acc_online"] - A[s]["acc_online"] for s in seeds]
    n = len(seeds)
    se = float(np.std(d, ddof=1) / math.sqrt(n)) if n > 1 else 0.0
    b = sum(1 for s in seeds if ok(B[s]) and not ok(A[s]))
    c = sum(1 for s in seeds if ok(A[s]) and not ok(B[s]))
    return {"n_shared_seeds": n,
            "acc_delta_pp": round(float(np.mean(d)) * 100, 2),
            "acc_delta_se_pp": round(se * 100, 2),
            "acc_delta_t": (round(float(np.mean(d)) / se, 2) if se > 0 else None),
            "paired_wins_gt_1pp": sum(1 for x in d if x > 0.01),
            "paired_losses_gt_1pp": sum(1 for x in d if x < -0.01),
            "success_baseline": sum(1 for s in seeds if ok(A[s])),
            "success_variant": sum(1 for s in seeds if ok(B[s])),
            "mcnemar_b_gained": b, "mcnemar_c_lost": c,
            "mcnemar_exact_p": binom_two_sided(min(b, c), b + c)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    runs = []
    srcs = []
    for f in ("BIMODAL-phaseA.json", "BIMODAL-phaseB.json"):
        p = os.path.join(RES, f)
        if os.path.exists(p):
            j = json.load(open(p, encoding="utf-8"))
            runs.extend(j["runs"])
            srcs.append({"file": f, "wall_s": j["wall_s"], "host": j["host"]})
    byv = {}
    for r in runs:
        byv.setdefault(r["variant"], []).append(r)

    variants = {v: variant_block(rs) for v, rs in byv.items()}
    base = byv.get("base", [])
    comps = {v: paired(base, rs) for v, rs in byv.items()
             if v != "base" and base}

    payload = {
        "title": "ARENA BIMODAL — is ERAN-CTX rule switching a capability or a lottery?",
        "date": "2026-08-21",
        "sources": srcs,
        "chance": round(CHANCE, 4), "oracle_acc": ORACLE_ACC,
        "oracle_ttc": ORACLE_TTC,
        "reported_first": ("chance 33.3%; hand-coded win-stay/lose-shift oracle "
                           "90.5% at trials-to-criterion 10.0; the block times "
                           "out at 60 trials, so ttc 60 means 'never got there'."),
        "worth_of_one_trial": (
            "Held-out accuracy is measured over 24 episodes x 6 blocks. A fast "
            "arm reaches criterion in ~11 trials so a block is short: ~1,600 "
            "trials total, one trial = 0.063 pp, 1 SE at chance = 1.18 pp. A "
            "failing arm times out at 60 trials a block: ~8,000 trials, one "
            "trial = 0.013 pp, 1 SE at chance = 0.53 pp. Neither is the real "
            "uncertainty: the SEED SPREAD is, and that is why this file has "
            "24 seeds per arm and reports every one."),
        "protocol": {
            "budget_steps_per_seed": 12_000_000,
            "budget_note": ("4x the arena's matched rule budget, identical for "
                            "every variant here; half spent by ES over the "
                            "knobs, half by an online life."),
            "n_es_params": 10,
            "online_memory_cells_at_cap": "256 prototypes x (20 key dims + 3 actions) = 5,888",
            "eval": ("24 held-out episodes from seed 7,000,000. Training only "
                     "ever saw seeds 0..4,000,000. The ES-tuned knobs are FROZEN "
                     "at evaluation; acc_frozen additionally freezes online "
                     "learning, acc_online (the headline) lets the organism keep "
                     "learning inside the episode, which this task requires "
                     "because the rule changes mid-episode."),
            "no_tuning_on_eval": ("Every choice made in this file -- which seeds "
                                  "count as failures, which fix to try, which "
                                  "theta to transplant -- was made from TRAIN-side "
                                  "signals only (ES fitness / online life curve).")},
        "variants": variants,
        "paired_vs_base": comps,
        "runs": runs,
    }
    out = os.path.join(RES, "ARENA-BIMODAL-2026-08-21.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)

    order = ["base", "chem", "taucap", "taucap+chem", "restart", "transplant"]
    print("=" * 96)
    print(f"chance {CHANCE*100:.1f}%   ORACLE {ORACLE_ACC*100:.1f}% (ttc "
          f"{ORACLE_TTC})   block timeout 60 = never got there")
    print("=" * 96)
    print(f"{'variant':<13}{'succ/n':>9}{'rate':>8}{'Wilson95':>16}"
          f"{'acc mean':>10}{'succ acc':>10}{'fail acc':>10}{'ttc succ':>10}{'bimod':>8}")
    for v in order + [x for x in variants if x not in order]:
        if v not in variants:
            continue
        b = variants[v]
        print(f"{v:<13}{b['n_success']}/{b['n_seeds']:<7}"
              f"{b['success_rate']*100:>7.1f}%"
              f"{'[' + format(b['success_wilson95'][0]*100, '.1f') + ', ' + format(b['success_wilson95'][1]*100, '.1f') + ']':>16}"
              f"{b['acc_mean']*100:>9.1f}%"
              f"{(b['acc_success_mean'] or 0)*100:>9.1f}%"
              f"{(b['acc_fail_mean'] or 0)*100:>9.1f}%"
              f"{(b['ttc_success_mean'] or 0):>10.1f}"
              f"{(b['sarle_bimodality'] or 0):>8.3f}")
    print("\nPAIRED vs base, same 24 seeds, same budget:")
    for v in order:
        if v in comps and comps[v]:
            c = comps[v]
            print(f"  {v:<13} acc {c['acc_delta_pp']:+6.1f} pp (SE "
                  f"{c['acc_delta_se_pp']:.1f}, t={c['acc_delta_t']})   "
                  f"success {c['success_variant']}/{c['n_shared_seeds']} vs "
                  f"{c['success_baseline']}/{c['n_shared_seeds']}   "
                  f"McNemar gained {c['mcnemar_b_gained']} / lost "
                  f"{c['mcnemar_c_lost']}, exact p={c['mcnemar_exact_p']}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
