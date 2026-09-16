# -*- coding: utf-8 -*-
"""The round 2 table: five rules, every floor, losses printed as loudly as wins."""
import json, sys, glob

paths = sys.argv[1:] or sorted(glob.glob("/home/eran2/miko-bench/results2*.json"))
ARMS = ("decisive", "bloc", "median", "mean", "vanilla")

for p in paths:
    R = json.load(open(p))
    C = R["config"]
    print("=" * 96)
    print(f"{p}")
    print(f"pairs={R['n_pairs']}  split_seed={C['split_seed']}  steps={C['steps']}  "
          f"bs={C['bs']}  seeds={C['seeds']}  theta={C['theta']}")
    print(f"params: MIKO {R['params']['miko']:,}  vanilla {R['params']['vanilla']:,}  "
          f"mismatch {R['params']['mismatch']:.3%}")
    ss = R["split_sizes"]
    print("split (BY QUESTION, and by ORIGIN):")
    for k in ("train", "val", "gtest", "sealed"):
        print(f"    {k:<7} {ss[k]['rows']:7d} rows over {ss[k]['questions']:5d} questions")

    tests = [t for t in ("gtest", "sealed") if t in R["floors"]]
    for t in tests:
        f, rf = R["floors"][t], R["rank_floors"][t]
        title = ("gtest = held-out CORPUS-grounded questions (in distribution)"
                 if t == "gtest" else
                 "SEALED = questions derived from IDDO'S OWN material (out of distribution)")
        print("\n" + "-" * 96)
        print(f"### {title}")
        print(f"FLOORS   constant-zero MAE {f['predict_zero']:.4f}   "
              f"train-median({f['train_median']:.3f}) {f['predict_train_median']:.4f}   "
              f"train-mean({f['train_mean']:.3f}) {f['predict_train_mean']:.4f}")
        print(f"         random NDCG@10 {rf['random_ndcg@10']:.4f}   "
              f"BM25 NDCG@10 {rf['bm25_ndcg@10']:.4f}   over {rf['n_questions']} questions")
        print(f"\n{'arm':<10}{'MAE':>9}{'+-':>8}{'vs floor':>10}{'ndcg@10':>9}"
              f"{'+-':>8}{'spearman':>10}{'pearson':>9}{'lr':>8}")
        best = f["best_constant_mae"]
        for arm in ARMS:
            if arm not in R["arms"]:
                continue
            m = R["arms"][arm]["mean"]
            lr = R["arms"][arm]["seeds"][0].get("lr", "-")
            d = m[f"{t}.mae"] - best
            print(f"{arm:<10}{m[f'{t}.mae']:>9.4f}{m[f'{t}.mae_std']:>8.4f}"
                  f"{d:>+10.4f}{m[f'{t}.ndcg@10']:>9.4f}{m[f'{t}.ndcg@10_std']:>8.4f}"
                  f"{m[f'{t}.spearman']:>+10.4f}{m[f'{t}.pearson']:>+9.4f}{str(lr):>8}")
        for arm in ARMS:
            if arm in R["arms"]:
                print(f"    per-seed MAE {arm:<9} "
                      f"{[round(s[t]['mae'], 4) for s in R['arms'][arm]['seeds']]}")
        ranked = sorted([a for a in ARMS if a in R["arms"]],
                        key=lambda a: R["arms"][a]["mean"][f"{t}.mae"])
        print(f"    -> order on MAE (best first): {' < '.join(ranked)}")
        for a in ranked:
            v = R["arms"][a]["mean"][f"{t}.mae"]
            print(f"    -> {a:<9} {v:.4f} vs best constant {best:.4f}  "
                  f"{'BEATS the floor' if v < best else 'LOSES to the floor'}")
        rk = sorted([a for a in ARMS if a in R["arms"]],
                    key=lambda a: -R["arms"][a]["mean"][f"{t}.ndcg@10"])
        print(f"    -> order on NDCG@10 (best first): {' > '.join(rk)}")
        for a in rk:
            v = R["arms"][a]["mean"][f"{t}.ndcg@10"]
            print(f"    -> {a:<9} NDCG@10 {v:.4f}  vs random {rf['random_ndcg@10']:.4f}  "
                  f"vs BM25 {rf['bm25_ndcg@10']:.4f}  "
                  f"{'above chance' if v > rf['random_ndcg@10'] else 'AT OR BELOW CHANCE'}")

        print("\nCALIBRATION - does dissent (max-min) predict error? Q4-Q1 MAE, per seed")
        for arm in ARMS:
            if arm not in R["arms"]:
                continue
            cs = [s[t]["calibration"] for s in R["arms"][arm]["seeds"]]
            if "note" in cs[0]:
                print(f"    {arm:<10} {cs[0]['note']}")
                continue
            k = len(cs)
            hl = sum(c["hi_minus_lo_mae"] for c in cs) / k
            cr = sum(c["corr_dissent_abs_err"] for c in cs) / k
            per = [round(c["hi_minus_lo_mae"], 4) for c in cs]
            sign = "CONSISTENT" if all(x > 0 for x in per) or all(x < 0 for x in per) \
                else "SIGN FLIPS ACROSS SEEDS"
            print(f"    {arm:<10} Q4-Q1 {hl:+.4f}  corr {cr:+.4f}  per-seed {per}  <- {sign}")

    if "robustness" in R:
        print("\n" + "-" * 96)
        print(f"ROBUSTNESS - one seat broken on the trained {R['robustness_trained_on']} "
              f"(seed 0), every rule, on {tests[-1]}")
        print(f"    {'rule/corruption':<22}{'clean':>9}{'corrupt':>10}{'degradation':>13}")
        rb = R["robustness"]
        for rule in ARMS[:4]:
            for how in ("zero", "invert", "saturate"):
                k = f"{rule}/{how}"
                if k in rb:
                    v = rb[k]
                    print(f"    {k:<22}{v['clean_mae']:>9.4f}"
                          f"{v['corrupt_mae_mean']:>10.4f}{v['degradation']:>+13.4f}")
        print("    mean degradation over the three corruptions (lower = more robust):")
        deg = {}
        for rule in ARMS[:4]:
            ks = [f"{rule}/{h}" for h in ("zero", "invert", "saturate") if f"{rule}/{h}" in rb]
            if ks:
                deg[rule] = sum(rb[k]["degradation"] for k in ks) / len(ks)
        for rule, d in sorted(deg.items(), key=lambda kv: kv[1]):
            print(f"      {rule:<10} {d:+.4f}")
        if deg:
            print(f"    -> most robust: {min(deg, key=deg.get)}")
    print()
