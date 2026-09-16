# -*- coding: utf-8 -*-
"""The constant baselines, computed properly.

MAE is minimised by the MEDIAN, not the mean, and 64% of these labels sit at ~0.
So the honest floor a learned model must clear is 'always predict the train median',
not 'always predict the train mean'. bench_real.py reported the mean version; this
file reports both, and the median one is the one that counts.
"""
import json, random, statistics

rows = [json.loads(l) for l in open("/home/eran2/miko-bench/data/pairs.jsonl")]
qids_all = sorted({r["question_id"] for r in rows})

for ss in (11, 23):
    qids = list(qids_all)
    random.Random(ss).shuffle(qids)
    n = len(qids)
    ntr, nva = int(0.6 * n), int(0.2 * n)
    tr_q, te_q = set(qids[:ntr]), set(qids[ntr + nva:])
    trl = [r["score"] for r in rows if r["question_id"] in tr_q]
    te = [r["score"] for r in rows if r["question_id"] in te_q]
    mean, med = statistics.mean(trl), statistics.median(trl)
    mae = lambda c: sum(abs(x - c) for x in te) / len(te)
    print(f"split_seed {ss}: n_train={len(trl)} n_test={len(te)} "
          f"test_mean={statistics.mean(te):.4f} test_median={statistics.median(te):.4f}")
    print(f"   predict train MEAN   ({mean:.4f}) -> test MAE {mae(mean):.4f}")
    print(f"   predict train MEDIAN ({med:.4f}) -> test MAE {mae(med):.4f}"
          f"   <-- the MAE-optimal constant")
    print(f"   predict 0.0                     -> test MAE {mae(0.0):.4f}")
    best = min([("mean", mae(mean)), ("median", mae(med)), ("zero", mae(0.0))], key=lambda t: t[1])
    print(f"   strongest constant baseline: {best[0]} at MAE {best[1]:.4f}\n")
