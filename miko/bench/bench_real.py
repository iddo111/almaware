# -*- coding: utf-8 -*-
"""MIKO's three metrics, measured on the REAL task for the first time.

PLAN.md section 3, in order:
  1 RELEVANCE   given a question and a page, reproduce the fleet's 0-1 relevance
                judgement from raw bytes. Baseline: a vanilla net of matched params.
  2 CALIBRATION does DISSENT PREDICT ERROR? If the high-dissent bucket is not
                measurably less accurate, the court thesis has failed and we say so.
  3 ROBUSTNESS  corrupt one seat (zero / invert / saturate) and measure the drop,
                under three aggregation rules: BLOC (MIKO's own), MEAN, MEDIAN.

Standing rules honoured: parameter counts matched within 1%, seeds >= 3, speed is never
a criterion, every number printed next to its control INCLUDING the ones that lose.

Splits are BY QUESTION, so the test set is questions the model never trained on.
"""
from __future__ import annotations

import argparse, json, math, random, sys, time
from collections import defaultdict

import torch
import torch.nn.functional as F

sys.path.insert(0, "/home/eran2/miko-bench/model")
from alma import encode_batch
from miko import Miko, Vanilla, matched_vanilla
from sefirot import ColumnTriad

DEV = "cuda" if torch.cuda.is_available() else "cpu"

# ── the corruption harness ───────────────────────────────────────────────────────
# A global switch, read inside a patched ColumnTriad.forward, so a TRAINED model can be
# re-run with one seat broken and with a different aggregation rule, without retraining.
CFG = {"victim": None, "how": None, "rule": "bloc"}

_orig_forward = ColumnTriad.forward


def corrupt(seat, how):
    if how == "zero":
        return torch.zeros_like(seat)
    if how == "invert":
        return -seat
    if how == "saturate":
        return torch.full_like(seat, 50.0)
    raise ValueError(how)


def aggregate(self, stack, rule):
    if rule == "bloc":
        return self.rule(stack)
    if rule == "mean":
        r = stack.mean(0)
    elif rule == "median":
        r = stack.median(dim=0).values
    else:
        raise ValueError(rule)
    dis = (stack - r.unsqueeze(0)).abs().max(dim=0).values
    return r, dis


def patched_forward(self, x, past=None):
    y_ch = self.chesed(x) + self.bias_chesed
    y_ge = self.gevurah(self.doubt(x)) + self.bias_gevurah
    y_ti = self.tiferet(x if past is None else 0.5 * (x + past))
    stack = torch.stack((y_ch, y_ge, y_ti), dim=0)
    if CFG["victim"] is not None:
        stack = stack.clone()
        stack[CFG["victim"]] = corrupt(stack[CFG["victim"]], CFG["how"])
    self.last_seats = stack
    ruling, dissent = aggregate(self, stack, CFG["rule"])
    return self.norm(self.act(ruling)), dissent


ColumnTriad.forward = patched_forward


# ── stats helpers (no scipy dependency) ──────────────────────────────────────────
def pearson(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = (a.norm() * b.norm())
    return float((a * b).sum() / d) if float(d) > 1e-12 else float("nan")


def rankdata(x):
    order = torch.argsort(x)
    r = torch.zeros_like(x)
    r[order] = torch.arange(len(x), dtype=x.dtype, device=x.device)
    return r


def spearman(a, b):
    return pearson(rankdata(a), rankdata(b))


def ndcg_at_k(scores, labels, k=10):
    idx = torch.argsort(scores, descending=True)[:k]
    gains = labels[idx]
    dev = gains.device
    disc = 1.0 / torch.log2(torch.arange(len(gains), dtype=torch.float32, device=dev) + 2)
    dcg = float((gains * disc).sum())
    ideal = torch.sort(labels, descending=True).values[:k]
    idisc = 1.0 / torch.log2(torch.arange(len(ideal), dtype=torch.float32, device=dev) + 2)
    idcg = float((ideal * idisc).sum())
    return dcg / idcg if idcg > 1e-9 else float("nan")


# ── data ─────────────────────────────────────────────────────────────────────────
def load(path, max_len, split_seed=11):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    qids = sorted({r["question_id"] for r in rows})
    rng = random.Random(split_seed)
    rng.shuffle(qids)
    n = len(qids)
    n_tr, n_va = int(0.6 * n), int(0.2 * n)
    split = {"train": set(qids[:n_tr]),
             "val": set(qids[n_tr:n_tr + n_va]),
             "test": set(qids[n_tr + n_va:])}
    out = {}
    for name, s in split.items():
        sub = [r for r in rows if r["question_id"] in s]
        q = encode_batch([r["question"] for r in sub], max_len).to(DEV)
        p = encode_batch([r["page"] for r in sub], max_len).to(DEV)
        y = torch.tensor([float(r["score"]) for r in sub], device=DEV)
        g = torch.tensor([r["question_id"] for r in sub], device=DEV)
        out[name] = {"q": q, "p": p, "y": y, "qid": g, "n": len(sub),
                     "questions": sorted(s)}
    return out, rows


@torch.no_grad()
def predict(model, d, bs=64):
    model.eval()
    sc, di = [], []
    for i in range(0, d["n"], bs):
        o = model(d["q"][i:i + bs], d["p"][i:i + bs])
        sc.append(o["score"].float())
        dd = o["dissent"]
        di.append(dd.float() if dd.dim() else dd.float().expand(o["score"].shape[0]))
    return torch.cat(sc), torch.cat(di)


def train_one(model, tr, va, steps, bs, lr, log=None):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    best = (float("inf"), None)
    n = tr["n"]
    perm = torch.randperm(n, device=DEV)
    ptr = 0
    for st in range(steps):
        model.train()
        if ptr + bs > n:
            perm = torch.randperm(n, device=DEV); ptr = 0
        idx = perm[ptr:ptr + bs]; ptr += bs
        o = model(tr["q"][idx], tr["p"][idx])
        loss = F.mse_loss(o["score"], tr["y"][idx])
        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if (st + 1) % 50 == 0:
            s, _ = predict(model, va)
            vmae = float((s - va["y"]).abs().mean())
            if log is not None:
                log.append({"step": st + 1, "train_mse": float(loss.detach()), "val_mae": vmae})
            if vmae < best[0]:
                best = (vmae, {k: v.detach().clone() for k, v in model.state_dict().items()})
    if best[1] is not None:
        model.load_state_dict(best[1])
    return best[0]


def evaluate(model, te):
    s, dis = predict(model, te)
    err = (s - te["y"]).abs()
    res = {
        "mae": float(err.mean()),
        "rmse": float(((s - te["y"]) ** 2).mean().sqrt()),
        "pearson": pearson(s, te["y"]),
        "spearman": spearman(s, te["y"]),
    }
    nd = []
    for qid in te["questions"]:
        m = te["qid"] == qid
        if int(m.sum()) >= 5:
            nd.append(ndcg_at_k(s[m], te["y"][m], 10))
    res["ndcg@10"] = sum(nd) / len(nd) if nd else float("nan")
    # calibration: does dissent predict error?
    if float(dis.std()) > 1e-6:
        qs = torch.quantile(dis, torch.tensor([0.25, 0.5, 0.75], device=DEV))
        buckets = torch.bucketize(dis, qs)
        res["calibration"] = {
            "bucket_mae": [float(err[buckets == b].mean()) for b in range(4)],
            "bucket_n": [int((buckets == b).sum()) for b in range(4)],
            "hi_minus_lo_mae": float(err[buckets == 3].mean() - err[buckets == 0].mean()),
            "corr_dissent_abs_err": pearson(dis, err),
            "spearman_dissent_abs_err": spearman(dis, err),
            "dissent_std": float(dis.std()),
        }
    else:
        res["calibration"] = {"note": "dissent is constant - it cannot predict anything",
                              "dissent_std": float(dis.std())}
    return res, s, dis


def robustness(model, te, base_mae):
    out = {}
    for rule in ("bloc", "mean", "median"):
        for how in ("zero", "invert", "saturate"):
            maes = []
            for v in range(3):
                CFG.update(victim=v, how=how, rule=rule)
                s, _ = predict(model, te)
                maes.append(float((s - te["y"]).abs().mean()))
            CFG.update(victim=None, how=None, rule=rule)
            s, _ = predict(model, te)
            clean = float((s - te["y"]).abs().mean())
            out[f"{rule}/{how}"] = {
                "clean_mae": clean,
                "corrupt_mae_mean": sum(maes) / 3,
                "corrupt_mae_per_seat": maes,
                "degradation": sum(maes) / 3 - clean,
            }
    CFG.update(victim=None, how=None, rule="bloc")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="/home/eran2/miko-bench/data/pairs.jsonl")
    ap.add_argument("--out", default="/home/eran2/miko-bench/results.json")
    ap.add_argument("--d", type=int, default=96)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--max_len", type=int, default=1024)
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lr_miko", type=float, default=None)
    ap.add_argument("--lr_vanilla", type=float, default=None)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--split_seed", type=int, default=11)
    a = ap.parse_args()

    data, rows = load(a.pairs, a.max_len, a.split_seed)
    print(f"pairs {len(rows)}  train {data['train']['n']} / val {data['val']['n']} "
          f"/ test {data['test']['n']}  (split BY QUESTION)")
    print(f"train questions {len(data['train']['questions'])}  "
          f"val {len(data['val']['questions'])}  test {len(data['test']['questions'])}")

    ymean = float(data["train"]["y"].mean())
    trivial = float((data["test"]["y"] - ymean).abs().mean())
    print(f"\nTRIVIAL BASELINE (always predict the train mean {ymean:.3f}): "
          f"test MAE {trivial:.4f}\n")

    torch.manual_seed(0)
    probe = Miko(d=a.d, depth=a.depth, max_len=a.max_len)
    n_m = sum(p.numel() for p in probe.parameters())
    vprobe = matched_vanilla(probe, a.max_len)
    n_v = sum(p.numel() for p in vprobe.parameters())
    print(f"MIKO    {n_m:,} params (d={a.d} depth={a.depth})")
    print(f"vanilla {n_v:,} params (d={vprobe.d})  mismatch {abs(n_m-n_v)/n_m:.3%}\n")

    results = {
        "pairs_file": a.pairs, "n_pairs": len(rows),
        "config": vars(a), "device": DEV,
        "params": {"miko": n_m, "vanilla": n_v,
                   "mismatch": abs(n_m - n_v) / n_m},
        "trivial_baseline_test_mae": trivial,
        "split": {k: data[k]["questions"] for k in ("train", "val", "test")},
        "arms": {},
    }

    trained_miko = None
    for arm in ("miko", "vanilla"):
        per_seed = []
        for s in range(a.seeds):
            t0 = time.time()
            torch.manual_seed(s); random.seed(s)
            m = Miko(d=a.d, depth=a.depth, max_len=a.max_len)
            model = (m if arm == "miko" else matched_vanilla(m, a.max_len)).to(DEV)
            curve = []
            lr = (a.lr_miko if arm == "miko" else a.lr_vanilla) or a.lr
            vbest = train_one(model, data["train"], data["val"], a.steps, a.bs, lr, curve)
            res, _, _ = evaluate(model, data["test"])
            res["val_mae_best"] = vbest
            res["seconds"] = round(time.time() - t0, 1)
            res["lr"] = lr
            res["curve"] = curve[-6:]
            per_seed.append(res)
            print(f"  [{arm} seed {s}] test MAE {res['mae']:.4f}  "
                  f"spearman {res['spearman']:+.4f}  ndcg@10 {res['ndcg@10']:.4f}  "
                  f"({res['seconds']}s)")
            if arm == "miko" and s == 0:
                trained_miko = model
        agg = {}
        for k in ("mae", "rmse", "pearson", "spearman", "ndcg@10"):
            vals = [r[k] for r in per_seed if not math.isnan(r[k])]
            agg[k] = sum(vals) / len(vals) if vals else float("nan")
            agg[k + "_std"] = (sum((x - agg[k]) ** 2 for x in vals) / len(vals)) ** 0.5 if vals else float("nan")
        results["arms"][arm] = {"mean": agg, "seeds": per_seed}
        print(f"  == {arm}: MAE {agg['mae']:.4f} +- {agg['mae_std']:.4f}\n")

    mm = results["arms"]["miko"]["mean"]["mae"]
    vv = results["arms"]["vanilla"]["mean"]["mae"]
    results["relevance_winner"] = "miko" if mm < vv else "vanilla"
    results["relevance_margin_mae"] = vv - mm

    print("[3] ROBUSTNESS on the TRAINED MIKO (seed 0) - bloc vs mean vs median")
    base = results["arms"]["miko"]["seeds"][0]["mae"]
    results["robustness_trained"] = robustness(trained_miko, data["test"], base)
    for k, v in results["robustness_trained"].items():
        print(f"    {k:<18} clean {v['clean_mae']:.4f} -> corrupt {v['corrupt_mae_mean']:.4f}"
              f"   degradation {v['degradation']:+.4f}")

    json.dump(results, open(a.out, "w"), indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
