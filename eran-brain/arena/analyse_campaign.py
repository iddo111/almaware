# -*- coding: utf-8 -*-
"""analyse_campaign.py — score the single-knob campaign against the recorded
baselines, paired by seed.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

Every variant is paired with base (9/24) and taucap (15/24) from
results/ARENA-BIMODAL-2026-08-21.json -- same seeds, same 12,000,000-step
budget, same harness -- so McNemar on the discordant seeds is the right test
and the accuracy comparison is paired, not two independent means.
"""
import glob
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
SUCCESS_TTC = 20.0


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * max(0.0, c - h), 1), round(100 * min(1.0, c + h), 1))


def mcnemar_exact(b, c):
    """Two-sided exact binomial on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def ok(r):
    t = r.get("ttc_mean_online")
    return (t is not None) and (t < SUCCESS_TTC)


def load_baselines():
    p = os.path.join(RESULTS, "ARENA-BIMODAL-2026-08-21.json")
    runs = json.load(open(p, encoding="utf-8"))["runs"]
    out = {}
    for v in ("base", "taucap"):
        out[v] = {r["seed"]: r for r in runs if r["variant"] == v}
    return out


def load_campaign():
    out = {}
    for path in sorted(glob.glob(os.path.join(RESULTS, "BIMODAL-single-*.json"))):
        d = json.load(open(path, encoding="utf-8"))
        for r in d["runs"]:
            out.setdefault(r["variant"], {})[r["seed"]] = r
    return out


def compare(name, arm, ref, ref_name):
    seeds = sorted(set(arm) & set(ref))
    b = sum(1 for s in seeds if ok(arm[s]) and not ok(ref[s]))     # variant wins
    c = sum(1 for s in seeds if not ok(arm[s]) and ok(ref[s]))     # variant loses
    p = mcnemar_exact(b, c)
    da = np.mean([arm[s]["acc_online"] - ref[s]["acc_online"] for s in seeds])
    sd = np.std([arm[s]["acc_online"] - ref[s]["acc_online"] for s in seeds], ddof=1)
    return {"vs": ref_name, "n_paired": len(seeds), "won": b, "lost": c,
            "mcnemar_p": round(p, 4),
            "paired_acc_delta_pp": round(100 * float(da), 2),
            "paired_acc_se_pp": round(100 * float(sd) / math.sqrt(len(seeds)), 2)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    base = load_baselines()
    camp = load_campaign()
    if not camp:
        print("no BIMODAL-single-*.json yet")
        return

    rows = []
    print(f"{'variant':<14}{'succ':>8}{'  95% Wilson':>16}{'acc':>8}"
          f"{'  vs base (won/lost, p)':>26}{'  vs taucap':>24}")
    print("-" * 100)
    for v in ("base", "taucap"):
        arm = base[v]
        k = sum(1 for s in arm if ok(arm[s]))
        lo, hi = wilson(k, len(arm))
        acc = np.mean([arm[s]["acc_online"] for s in arm])
        print(f"{v+' (recorded)':<14}{k:>3}/{len(arm):<4}{f'[{lo},{hi}]':>16}"
              f"{100*acc:>7.1f}%")
    print("-" * 100)
    for v in sorted(camp):
        arm = camp[v]
        k = sum(1 for s in arm if ok(arm[s]))
        lo, hi = wilson(k, len(arm))
        acc = np.mean([arm[s]["acc_online"] for s in arm])
        cb = compare(v, arm, base["base"], "base")
        ct = compare(v, arm, base["taucap"], "taucap")
        vs_base = "+{}/-{} p={}".format(cb["won"], cb["lost"], cb["mcnemar_p"])
        vs_tau = "+{}/-{} p={}".format(ct["won"], ct["lost"], ct["mcnemar_p"])
        print(f"{v:<14}{k:>3}/{len(arm):<4}{f'[{lo},{hi}]':>16}"
              f"{100*acc:>7.1f}%{vs_base:>26}{vs_tau:>24}")
        rows.append({"variant": v, "n": len(arm), "n_success": k,
                     "wilson95": [lo, hi],
                     "acc_online_mean": round(float(acc), 4),
                     "vs_base": cb, "vs_taucap": ct,
                     "knob_medians": {kk: round(float(np.median(
                         [arm[s]["knobs"][kk] for s in arm])), 4)
                         for kk in arm[list(arm)[0]]["knobs"]}})

    payload = {"title": "Single-knob decode-range campaign",
               "date": "2026-08-22",
               "budget_steps_per_seed": 12_000_000,
               "success_rule": "mean trials-to-criterion < 20 (unchanged)",
               "recorded_baselines": {
                   v: {"n_success": sum(1 for s in base[v] if ok(base[v][s])),
                       "n": len(base[v])} for v in base},
               "variants": rows}
    out = os.path.join(RESULTS, "SINGLE-KNOB-CAMPAIGN-2026-08-22.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
