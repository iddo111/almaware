# -*- coding: utf-8 -*-
"""Choose theta and the learning rates on VALIDATION ONLY. The test sets are not opened.

stage theta : the DECISIVE rule's agreement threshold, measured rather than guessed.
              theta is in units of the batch's own mean bloc-gap.
                theta = 0     -> always 2-1: the outlier is always discarded
                theta -> inf  -> always 3-0: which is exactly the plain mean of three
              So the sweep contains its own control at both ends.

stage lr    : every arm gets the same three learning rates and the same budget, so no
              arm is handicapped by a hyperparameter that was chosen for another.

Nothing here ever looks at gtest or sealed.
"""
import argparse, json, random, sys, time
import torch

HOME = "/home/eran2/miko-bench"
sys.path.insert(0, HOME)
sys.path.insert(0, HOME + "/model")
import bench2 as B
from miko import Miko, matched_vanilla

ap = argparse.ArgumentParser()
ap.add_argument("--stage", choices=["theta", "lr"], required=True)
ap.add_argument("--pairs", default=HOME + "/data/pairs2.jsonl")
ap.add_argument("--steps", type=int, default=600)
ap.add_argument("--bs", type=int, default=32)
ap.add_argument("--d", type=int, default=96)
ap.add_argument("--depth", type=int, default=4)
ap.add_argument("--max_len", type=int, default=1024)
ap.add_argument("--eval_every", type=int, default=100)
ap.add_argument("--split_seed", type=int, default=11)
ap.add_argument("--lr", type=float, default=3e-4)
ap.add_argument("--theta", type=float, default=0.0)
ap.add_argument("--out", required=True)
a = ap.parse_args()

data, rows = B.load(a.pairs, a.max_len, a.split_seed)
print(f"train {data['train']['n']} / val {data['val']['n']} "
      f"(val_small {data['val_small']['n']})  -- test sets NOT loaded into any decision",
      flush=True)

out = {}
if a.stage == "theta":
    grid = [("decisive", t, a.lr) for t in (0.0, 0.25, 0.5, 1.0, 2.0, 1e9)]
else:
    grid = [(arm, a.theta, lr)
            for arm in ("decisive", "bloc", "median", "mean", "vanilla")
            for lr in (3e-4, 1e-3, 3e-3)]

for arm, theta, lr in grid:
    t0 = time.time()
    torch.manual_seed(0); random.seed(0)
    m = Miko(d=a.d, depth=a.depth, max_len=a.max_len)
    model = (matched_vanilla(m, a.max_len) if arm == "vanilla" else m).to(B.DEV)
    B.CFG.update(rule=("bloc" if arm == "vanilla" else arm), theta=theta,
                 victim=None, how=None)
    curve = []
    v = B.train_one(model, data["train"], data["val_small"], a.steps, a.bs, lr,
                    curve, a.eval_every, seed=0)
    tag = f"{arm}@theta={theta:g}@lr={lr:g}"
    out[tag] = {"val_mae_best": v, "curve": curve, "sec": round(time.time() - t0)}
    print(f"{tag:<34} val_MAE_best={v:.4f}  "
          f"last3={[round(c['val_mae'], 4) for c in curve[-3:]]}  "
          f"({time.time()-t0:.0f}s)", flush=True)

json.dump(out, open(a.out, "w"), indent=2)
best = min(out, key=lambda k: out[k]["val_mae_best"])
print(f"\nBEST on validation: {best}  (val MAE {out[best]['val_mae_best']:.4f})")
if a.stage == "lr":
    for arm in ("decisive", "bloc", "median", "mean", "vanilla"):
        c = {k: v["val_mae_best"] for k, v in out.items() if k.startswith(arm + "@")}
        if c:
            b = min(c, key=c.get)
            print(f"  BEST {arm:<9} {b}  val MAE {c[b]:.4f}")
print(f"wrote {a.out}")
