# -*- coding: utf-8 -*-
"""Pick each arm's learning rate on the VALIDATION questions, never on test.

Both arms get the same sweep, the same budget and the same seed, so neither is
handicapped by a hyperparameter chosen for the other.
"""
import json, random, sys, time
import torch

sys.path.insert(0, "/home/eran2/miko-bench")
sys.path.insert(0, "/home/eran2/miko-bench/model")
import bench_real as B
from miko import Miko, matched_vanilla

MAXLEN, D, DEPTH, STEPS, BS = 1024, 96, 4, 500, 32
data, rows = B.load("/home/eran2/miko-bench/data/pairs.jsonl", MAXLEN, 11)
print(f"train {data['train']['n']} val {data['val']['n']} test {data['test']['n']}", flush=True)

out = {}
for arm in ("miko", "vanilla"):
    for lr in (3e-4, 1e-3, 3e-3):
        t0 = time.time()
        torch.manual_seed(0); random.seed(0)
        m = Miko(d=D, depth=DEPTH, max_len=MAXLEN)
        model = (m if arm == "miko" else matched_vanilla(m, MAXLEN)).to(B.DEV)
        curve = []
        v = B.train_one(model, data["train"], data["val"], STEPS, BS, lr, curve)
        out[f"{arm}@{lr}"] = {"val_mae_best": v, "curve": curve, "sec": round(time.time() - t0)}
        print(f"{arm:<8} lr={lr:<7} val_MAE_best={v:.4f}  "
              f"last3={[round(c['val_mae'],4) for c in curve[-3:]]}  ({time.time()-t0:.0f}s)",
              flush=True)

json.dump(out, open("/home/eran2/miko-bench/lr_sweep.json", "w"), indent=2)
best = {}
for arm in ("miko", "vanilla"):
    cands = {lr: out[f"{arm}@{lr}"]["val_mae_best"] for lr in (3e-4, 1e-3, 3e-3)}
    best[arm] = min(cands, key=cands.get)
    print(f"BEST {arm}: lr={best[arm]}  (val MAE {cands[best[arm]]:.4f})")
json.dump(best, open("/home/eran2/miko-bench/lr_best.json", "w"))
