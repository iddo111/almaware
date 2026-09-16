# -*- coding: utf-8 -*-
"""analyse_bimodal.py — name the mechanism, don't just report that it varies.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Reads one or more BIMODAL-*.json files and prints, for every variant:
  * the full per-seed distribution (never a mean on its own),
  * the success rate with a Wilson 95% interval,
  * whether the failures are a separate MODE or a tail (bimodality coefficient
    and the largest gap in the sorted accuracies),
  * for every knob and every eval diagnostic, how well it SEPARATES the failed
    seeds from the successful ones (AUC of a single-variable classifier, plus
    the best threshold). A separator with AUC 1.00 names the mechanism.
"""
import json
import math
import os
import sys

import numpy as np

SUCCESS_TTC = 20.0


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def auc(pos, neg):
    """P(a random FAILED seed scores higher than a random SUCCESSFUL one)."""
    if not pos or not neg:
        return None
    n = 0.0
    for p in pos:
        for q in neg:
            n += 1.0 if p > q else (0.5 if p == q else 0.0)
    return n / (len(pos) * len(neg))


def best_split(pos, neg):
    """Threshold that separates the two groups best; returns (thr, n_errors)."""
    vals = sorted(set(pos + neg))
    best = (None, len(pos) + len(neg))
    for i in range(len(vals)):
        t = vals[i]
        e = sum(1 for p in pos if p <= t) + sum(1 for q in neg if q > t)
        if e < best[1]:
            best = (t, e)
        e2 = sum(1 for p in pos if p > t) + sum(1 for q in neg if q <= t)
        if e2 < best[1]:
            best = (t, e2)
    return best


def bimodality(x):
    """Sarle's bimodality coefficient. > 0.555 (uniform) suggests bimodal."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 4:
        return None
    m = x.mean()
    s = x.std(ddof=1)
    if s == 0:
        return None
    g = ((x - m) ** 3).mean() / s ** 3
    k = ((x - m) ** 4).mean() / s ** 4 - 3.0
    return float((g * g + 1) / (k + 3.0 * (n - 1) ** 2 / ((n - 2) * (n - 3))))


KNOBS = ["lam", "ctx_gain", "trace_tau", "eta_q", "eta_v", "eps0",
         "eps_decay", "eps_floor", "strict_scale", "ne_gain"]
DIAGS = ["mean_ctx_over_obs", "mean_attraction_margin", "mean_sim_top1",
         "action_max_share", "proto_top1_share", "proto_unique_used",
         "n_proto_eval_end", "n_proto_eval_start", "proto_displacement_mean",
         "persev_rate"]
RUNLEVEL = ["es_train_score", "life_final", "life_first", "generations",
            "ctx_horizon_trials"]


def report(runs, label):
    good = [r for r in runs if r["ttc_mean_online"] < SUCCESS_TTC]
    bad = [r for r in runs if r["ttc_mean_online"] >= SUCCESS_TTC]
    accs = [r["acc_online"] for r in runs]
    lo, hi = wilson(len(good), len(runs))
    print("=" * 78)
    print(f"VARIANT {label}   n={len(runs)} seeds")
    print("=" * 78)
    print(f"  chance 33.3%   oracle 90.5% (ttc 10.0)")
    print(f"  SUCCESS (ttc<{SUCCESS_TTC}) {len(good)}/{len(runs)} = "
          f"{100*len(good)/len(runs):.1f}%  "
          f"Wilson95 [{100*lo:.1f}, {100*hi:.1f}]")
    srt = sorted(runs, key=lambda r: r["acc_online"])
    print("  per-seed acc%  : " +
          " ".join(f"{r['acc_online']*100:.1f}" for r in srt))
    print("  per-seed ttc   : " +
          " ".join(f"{r['ttc_mean_online']:.1f}" for r in srt))
    print("  per-seed seed  : " + " ".join(f"{r['seed']}" for r in srt))
    a = np.array(sorted(accs))
    gaps = np.diff(a)
    gi = int(np.argmax(gaps))
    print(f"  mean {np.mean(a)*100:.1f}%  median {np.median(a)*100:.1f}%  "
          f"min {a[0]*100:.1f}%  max {a[-1]*100:.1f}%")
    bc = bimodality(a)
    print(f"  largest gap in the sorted accuracies: "
          f"{gaps[gi]*100:.1f} pp between {a[gi]*100:.1f}% and {a[gi+1]*100:.1f}%"
          f"   |  Sarle bimodality coefficient {bc:.3f} "
          f"({'BIMODAL' if bc and bc > 0.555 else 'not bimodal'} vs 0.555 uniform)")
    if good and bad:
        print(f"  success acc {np.mean([r['acc_online'] for r in good])*100:.1f}% "
              f"ttc {np.mean([r['ttc_mean_online'] for r in good]):.1f}   |   "
              f"fail acc {np.mean([r['acc_online'] for r in bad])*100:.1f}% "
              f"ttc {np.mean([r['ttc_mean_online'] for r in bad]):.1f}")

    if not (good and bad):
        print("  (no contrast to compute: one of the groups is empty)")
        return
    print("-" * 78)
    print(f"  {'variable':<28}{'fail mean':>11}{'succ mean':>11}"
          f"{'AUC':>7}{'thr':>10}{'errs':>6}")
    rows = []
    for k in KNOBS:
        rows.append((k, [r["knobs"][k] for r in bad],
                     [r["knobs"][k] for r in good]))
    for k in RUNLEVEL:
        if all(r.get(k) is not None for r in runs):
            rows.append((k, [r[k] for r in bad], [r[k] for r in good]))
    for k in DIAGS:
        if all(r["diag"].get(k) is not None for r in runs):
            rows.append(("diag." + k, [r["diag"][k] for r in bad],
                         [r["diag"][k] for r in good]))
    scored = []
    for name, pv, nv in rows:
        A = auc(pv, nv)
        thr, errs = best_split(pv, nv)
        scored.append((abs((A or 0.5) - 0.5), name, np.mean(pv), np.mean(nv),
                       A, thr, errs))
    for _, name, pm, nm, A, thr, errs in sorted(scored, reverse=True):
        star = " <<< SEPARATES PERFECTLY" if errs == 0 else ""
        print(f"  {name:<28}{pm:>11.4g}{nm:>11.4g}{A:>7.2f}{thr:>10.4g}"
              f"{errs:>6}{star}")


def main():
    paths = sys.argv[1:]
    if not paths:
        here = os.path.dirname(os.path.abspath(__file__))
        d = os.path.join(here, "results")
        paths = [os.path.join(d, f) for f in sorted(os.listdir(d))
                 if f.startswith("BIMODAL-")]
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    allruns = {}
    for p in paths:
        j = json.load(open(p, encoding="utf-8"))
        for r in j["runs"]:
            allruns.setdefault(r["variant"], []).append(r)
    for v, runs in allruns.items():
        report(runs, v)
        print()
    if len(allruns) > 1:
        print("=" * 78)
        print("HEAD TO HEAD (same seeds, same budget)")
        print("=" * 78)
        base = allruns.get("base")
        if base:
            bs = {r["seed"]: r for r in base}
            for v, runs in allruns.items():
                if v == "base":
                    continue
                common = [r for r in runs if r["seed"] in bs]
                if not common:
                    continue
                d = [r["acc_online"] - bs[r["seed"]]["acc_online"]
                     for r in common]
                wins = sum(1 for x in d if x > 0.01)
                loss = sum(1 for x in d if x < -0.01)
                sg = sum(1 for r in common if r["ttc_mean_online"] < SUCCESS_TTC)
                sb = sum(1 for r in common
                         if bs[r["seed"]]["ttc_mean_online"] < SUCCESS_TTC)
                se = np.std(d, ddof=1) / math.sqrt(len(d)) if len(d) > 1 else 0
                print(f"  {v:<12} vs base on {len(common)} shared seeds: "
                      f"acc delta {np.mean(d)*100:+.1f} pp (SE {se*100:.1f}), "
                      f"paired wins {wins} / losses {loss}, "
                      f"success {sg}/{len(common)} vs base {sb}/{len(common)}")


if __name__ == "__main__":
    main()
