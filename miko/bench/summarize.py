# -*- coding: utf-8 -*-
"""Print MIKO's three metrics the way the PLAN demands: next to the control, losses included."""
import json, sys, glob

paths = sys.argv[1:] or sorted(glob.glob("/home/eran2/miko-bench/results_split*.json"))
for p in paths:
    R = json.load(open(p))
    print("=" * 78)
    print(f"{p}   pairs={R['n_pairs']}  split_seed={R['config']['split_seed']}  "
          f"steps={R['config']['steps']}  seeds={R['config']['seeds']}")
    print(f"params: MIKO {R['params']['miko']:,}  vanilla {R['params']['vanilla']:,}  "
          f"mismatch {R['params']['mismatch']:.3%}")
    print(f"TRIVIAL BASELINE (predict train mean): test MAE {R['trivial_baseline_test_mae']:.4f}")
    print()
    print("[1] RELEVANCE  (lower MAE better; spearman/ndcg higher better)")
    hdr = f"    {'arm':<9}{'MAE':>9}{'+-':>8}{'RMSE':>9}{'pearson':>9}{'spearman':>10}{'ndcg@10':>9}{'lr':>8}"
    print(hdr)
    for arm in ("miko", "vanilla"):
        m = R["arms"][arm]["mean"]
        lr = R["arms"][arm]["seeds"][0].get("lr", "-")
        print(f"    {arm:<9}{m['mae']:>9.4f}{m['mae_std']:>8.4f}{m['rmse']:>9.4f}"
              f"{m['pearson']:>9.4f}{m['spearman']:>10.4f}{m['ndcg@10']:>9.4f}{str(lr):>8}")
    print(f"    per-seed MAE  miko    {[round(s['mae'],4) for s in R['arms']['miko']['seeds']]}")
    print(f"    per-seed MAE  vanilla {[round(s['mae'],4) for s in R['arms']['vanilla']['seeds']]}")
    print(f"    -> WINNER on relevance: {R['relevance_winner'].upper()}  "
          f"(margin {R['relevance_margin_mae']:+.4f} MAE)")
    tb = R["trivial_baseline_test_mae"]
    for arm in ("miko", "vanilla"):
        m = R["arms"][arm]["mean"]["mae"]
        print(f"    -> {arm} vs trivial baseline: {m:.4f} vs {tb:.4f}  "
              f"({'BEATS it' if m < tb else 'LOSES to it'})")

    print("\n[2] CALIBRATION  - does dissent predict error?")
    for arm in ("miko", "vanilla"):
        cs = [s["calibration"] for s in R["arms"][arm]["seeds"]]
        if "note" in cs[0]:
            print(f"    {arm:<9} {cs[0]['note']} (std {cs[0]['dissent_std']:.2e})")
            continue
        k = len(cs)
        hl = sum(c["hi_minus_lo_mae"] for c in cs) / k
        cr = sum(c["corr_dissent_abs_err"] for c in cs) / k
        sp = sum(c["spearman_dissent_abs_err"] for c in cs) / k
        buckets = [sum(c["bucket_mae"][i] for c in cs) / k for i in range(4)]
        print(f"    {arm:<9} MAE by dissent quartile (Q1 lowest -> Q4 highest):")
        print(f"              {[round(b,4) for b in buckets]}")
        print(f"              Q4-Q1 = {hl:+.4f}   corr(dissent,|err|) = {cr:+.4f}   "
              f"spearman = {sp:+.4f}")
        print(f"              per-seed Q4-Q1: {[round(c['hi_minus_lo_mae'],4) for c in cs]}")

    print("\n[3] ROBUSTNESS  - one corrupted seat, on the TRAINED MIKO (test MAE)")
    rb = R["robustness_trained"]
    print(f"    {'rule/corruption':<20}{'clean':>9}{'corrupt':>10}{'degradation':>13}")
    for rule in ("bloc", "mean", "median"):
        for how in ("zero", "invert", "saturate"):
            v = rb[f"{rule}/{how}"]
            print(f"    {rule+'/'+how:<20}{v['clean_mae']:>9.4f}{v['corrupt_mae_mean']:>10.4f}"
                  f"{v['degradation']:>+13.4f}")
    print("    mean degradation over the three corruptions:")
    for rule in ("bloc", "mean", "median"):
        d = sum(rb[f"{rule}/{how}"]["degradation"] for how in ("zero", "invert", "saturate")) / 3
        a = sum(abs(rb[f"{rule}/{how}"]["degradation"]) for how in ("zero", "invert", "saturate")) / 3
        print(f"      {rule:<8} signed {d:+.4f}   absolute shift {a:.4f}")
    print()
