# -*- coding: utf-8 -*-
r"""MIKO round 2 - the FIVE-WAY rule comparison, on a four-figure question pool.

Iddo, 2026-09-05 13:59: "תרחיב להרבה יותר מ-500 שאלות - ותעשה את מיקו לפי בית דין החלטי".

Two changes from round 1, and both are measured here:

CHANGE 1 - QUESTIONS. Round 1 had 65. The diagnosis was memorisation of 39 training
           questions: train MSE fell while val MAE stayed flat, and the vanilla control
           fit train HARDER while generalising WORSE. So the pool is now four figures.
           TRAIN/VAL are corpus-grounded questions (breadth). The SEALED TEST is the
           questions derived from Iddo's own written material - a different distribution.
           A model that only answers auto-generated questions has learned the generator.
           A second in-distribution test (gtest) separates "more questions helped at all"
           from "it transfers to his questions".

CHANGE 2 - THE COURT DECIDES. `ColumnTriad.rule` is a softmax over company: an average
           in which the out-voted seat keeps a share. `rule_decisive` discards the
           outlier from the verdict entirely. Five arms are trained on the same data,
           the same seeds and the same budget:

               decisive   the agreeing bloc rules IN FULL, outlier discarded
               bloc       round 1's soft company-weighted ruling
               median     the middle seat
               mean       plain average of three
               vanilla    no court at all, parameters matched

Dissent is max - min for EVERY arm (PLAN.md section 2), so the calibration column is
comparable across rules. Round 1's bloc used max|seat - ruling| instead; that is why its
calibration numbers are not directly comparable to these.

METHOD, non-negotiable:
  * split BY QUESTION. Test questions are never seen in training.
  * lr and the decisive theta are chosen on VALIDATION only (sweep2.py).
  * seeds >= 3.
  * every number is printed next to the trivial floors: constant-zero / train-median,
    random ranking and BM25.
  * the sealed set is scored ONCE, at the end, by --final.
"""
from __future__ import annotations

import argparse, json, math, random, statistics, sys, time
from collections import defaultdict

import torch
import torch.nn.functional as F

sys.path.insert(0, "/home/eran2/miko-bench/model")
from alma import encode_batch
from miko import Miko, Vanilla, matched_vanilla
from sefirot import ColumnTriad

DEV = "cuda" if torch.cuda.is_available() else "cpu"

# ── the switchboard: which rule rules, and which seat (if any) is broken ──────────
CFG = {"rule": "bloc", "theta": 0.0, "victim": None, "how": None}

_orig_forward = ColumnTriad.forward


def corrupt(seat, how):
    if how == "zero":
        return torch.zeros_like(seat)
    if how == "invert":
        return -seat
    if how == "saturate":
        return torch.full_like(seat, 50.0)
    raise ValueError(how)


def apply_rule(self, stack):
    """One place where all four rules live, so the comparison is auditable."""
    rule = CFG["rule"]
    if rule == "decisive":
        return self.rule_decisive(stack, CFG["theta"])
    # dissent is max - min for every rule (PLAN.md section 2), so it is comparable
    dissent = stack.max(dim=0).values - stack.min(dim=0).values
    if rule == "bloc":
        ruling, _ = self.rule(stack)
    elif rule == "median":
        ruling = stack.median(dim=0).values
    elif rule == "mean":
        ruling = stack.mean(0)
    else:
        raise ValueError(rule)
    return ruling, dissent


def patched_forward(self, x, past=None):
    y_ch = self.chesed(x) + self.bias_chesed
    y_ge = self.gevurah(self.doubt(x)) + self.bias_gevurah
    y_ti = self.tiferet(x if past is None else 0.5 * (x + past))
    stack = torch.stack((y_ch, y_ge, y_ti), dim=0)
    if CFG["victim"] is not None:
        stack = stack.clone()
        stack[CFG["victim"]] = corrupt(stack[CFG["victim"]], CFG["how"])
    self.last_seats = stack
    ruling, dissent = apply_rule(self, stack)
    return self.norm(self.act(ruling)), dissent


ColumnTriad.forward = patched_forward


# ── stats (no scipy) ─────────────────────────────────────────────────────────────
def pearson(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = a.norm() * b.norm()
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


# ── data: split BY QUESTION, and by ORIGIN ───────────────────────────────────────
def load(path, max_len, split_seed=11, val_cap=1024, verbose=True):
    """train/val/gtest come from the CORPUS-grounded questions.
    sealed = every IDDO-derived question, held out entirely."""
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    origin = {}
    for r in rows:
        origin[r["question_id"]] = r.get("origin", "corpus")
    corp = sorted(q for q, o in origin.items() if o == "corpus")
    iddo = sorted(q for q, o in origin.items() if o == "iddo")
    rng = random.Random(split_seed)
    rng.shuffle(corp)
    n = len(corp)
    n_tr, n_va = int(0.70 * n), int(0.15 * n)
    split = {"train": set(corp[:n_tr]),
             "val": set(corp[n_tr:n_tr + n_va]),
             "gtest": set(corp[n_tr + n_va:]),
             "sealed": set(iddo)}
    out = {}
    for name, s in split.items():
        sub = [r for r in rows if r["question_id"] in s]
        q = encode_batch([r["question"] for r in sub], max_len).to(DEV)
        p = encode_batch([r["page"] for r in sub], max_len).to(DEV)
        y = torch.tensor([float(r["score"]) for r in sub], device=DEV)
        g = torch.tensor([r["question_id"] for r in sub], device=DEV)
        out[name] = {"q": q, "p": p, "y": y, "qid": g, "n": len(sub),
                     "questions": sorted(s)}
        if verbose:
            print(f"  {name:<7} {len(sub):6d} rows over {len(s):5d} questions", flush=True)
    # a fixed subsample of val, used for the periodic in-training check only
    vn = out["val"]["n"]
    idx = torch.randperm(vn, generator=torch.Generator().manual_seed(0))[:min(val_cap, vn)]
    idx = idx.to(DEV)
    out["val_small"] = {k: (v[idx] if torch.is_tensor(v) else v)
                        for k, v in out["val"].items() if k != "questions"}
    out["val_small"]["n"] = int(idx.numel())
    out["val_small"]["questions"] = out["val"]["questions"]
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


def train_one(model, tr, va, steps, bs, lr, log=None, eval_every=100, seed=0):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    best = (float("inf"), None)
    n = tr["n"]
    g = torch.Generator(device=DEV).manual_seed(seed)
    perm = torch.randperm(n, device=DEV, generator=g)
    ptr = 0
    for st in range(steps):
        model.train()
        if ptr + bs > n:
            perm = torch.randperm(n, device=DEV, generator=g); ptr = 0
        idx = perm[ptr:ptr + bs]; ptr += bs
        o = model(tr["q"][idx], tr["p"][idx])
        loss = F.mse_loss(o["score"], tr["y"][idx])
        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if (st + 1) % eval_every == 0:
            s, _ = predict(model, va)
            vmae = float((s - va["y"]).abs().mean())
            if log is not None:
                log.append({"step": st + 1, "train_mse": float(loss.detach()),
                            "val_mae": vmae})
            if vmae < best[0]:
                best = (vmae, {k: v.detach().clone() for k, v in model.state_dict().items()})
    if best[1] is not None:
        model.load_state_dict(best[1])
    return best[0]


def evaluate(model, te, min_per_q=10):
    s, dis = predict(model, te)
    err = (s - te["y"]).abs()
    res = {"n": te["n"],
           "mae": float(err.mean()),
           "rmse": float(((s - te["y"]) ** 2).mean().sqrt()),
           "pearson": pearson(s, te["y"]),
           "spearman": spearman(s, te["y"])}
    nd = []
    qid = te["qid"]
    for q in torch.unique(qid).tolist():
        m = qid == q
        if int(m.sum()) >= min_per_q and float(te["y"][m].max()) > 1e-9:
            v = ndcg_at_k(s[m], te["y"][m], 10)
            if not math.isnan(v):
                nd.append(v)
    res["ndcg@10"] = sum(nd) / len(nd) if nd else float("nan")
    res["ndcg_n_questions"] = len(nd)
    if float(dis.std()) > 1e-6:
        qs = torch.quantile(dis.float(), torch.tensor([0.25, 0.5, 0.75], device=DEV))
        b = torch.bucketize(dis, qs)
        res["calibration"] = {
            "bucket_mae": [float(err[b == i].mean()) for i in range(4)],
            "bucket_n": [int((b == i).sum()) for i in range(4)],
            "hi_minus_lo_mae": float(err[b == 3].mean() - err[b == 0].mean()),
            "corr_dissent_abs_err": pearson(dis, err),
            "spearman_dissent_abs_err": spearman(dis, err),
            "dissent_std": float(dis.std())}
    else:
        res["calibration"] = {"note": "dissent constant - it cannot predict anything",
                              "dissent_std": float(dis.std())}
    return res, s, dis


def robustness(model, te):
    """One seat broken, the SAME trained weights, every rule. Post-hoc, no retraining."""
    out = {}
    keep_rule, keep_theta = CFG["rule"], CFG["theta"]
    for rule in ("decisive", "bloc", "median", "mean"):
        CFG.update(rule=rule, victim=None, how=None)
        s, _ = predict(model, te)
        clean = float((s - te["y"]).abs().mean())
        for how in ("zero", "invert", "saturate"):
            maes = []
            for v in range(3):
                CFG.update(victim=v, how=how)
                s, _ = predict(model, te)
                maes.append(float((s - te["y"]).abs().mean()))
            CFG.update(victim=None, how=None)
            out[f"{rule}/{how}"] = {"clean_mae": clean,
                                    "corrupt_mae_mean": sum(maes) / 3,
                                    "corrupt_mae_per_seat": maes,
                                    "degradation": sum(maes) / 3 - clean}
    CFG.update(rule=keep_rule, theta=keep_theta, victim=None, how=None)
    return out


# ── the floors ───────────────────────────────────────────────────────────────────
def floors(data, name):
    te = data[name]["y"]
    tr = data["train"]["y"]
    med = float(tr.median()); mean = float(tr.mean())
    mae = lambda c: float((te - c).abs().mean())
    return {"predict_zero": mae(0.0), "predict_train_median": mae(med),
            "predict_train_mean": mae(mean),
            "train_median": med, "train_mean": mean,
            "best_constant_mae": min(mae(0.0), mae(med), mae(mean))}


def rank_floors(data, name, ranks_path, pairs_rows, min_per_q=10):
    """random ordering and BM25 ordering on the SAME pages, same questions."""
    ranks = {int(k): v for k, v in json.load(open(ranks_path)).items()}
    pos = {qi: {d: i for i, d in enumerate(v)} for qi, v in ranks.items()}
    keep = set(data[name]["questions"])
    by_q = defaultdict(list)
    for r in pairs_rows:
        if r["question_id"] in keep:
            by_q[r["question_id"]].append((int(r["pair_id"].split("_d")[1]), r["score"]))

    def ndcg(vals, k=10):
        dcg = sum(x / math.log2(i + 2) for i, x in enumerate(vals[:k]))
        ideal = sorted(vals, reverse=True)[:k]
        idcg = sum(x / math.log2(i + 2) for i, x in enumerate(ideal))
        return dcg / idcg if idcg > 1e-9 else None

    rnd_all, bm_all = [], []
    rng = random.Random(7)
    WORST = 10 ** 9
    for qi, items in by_q.items():
        labels = [s for _, s in items]
        if len(labels) < min_per_q or max(labels) <= 1e-9:
            continue
        vals = []
        for _ in range(200):
            sh = labels[:]; rng.shuffle(sh)
            v = ndcg(sh)
            if v is not None:
                vals.append(v)
        if vals:
            rnd_all.append(statistics.mean(vals))
        ordered = sorted(items, key=lambda t: pos.get(qi, {}).get(t[0], WORST))
        v = ndcg([s for _, s in ordered])
        if v is not None:
            bm_all.append(v)
    return {"n_questions": len(bm_all),
            "random_ndcg@10": statistics.mean(rnd_all) if rnd_all else float("nan"),
            "bm25_ndcg@10": statistics.mean(bm_all) if bm_all else float("nan")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="/home/eran2/miko-bench/data/pairs2.jsonl")
    ap.add_argument("--ranks", default="/home/eran2/miko-bench/data/ranks2.json")
    ap.add_argument("--out", default="/home/eran2/miko-bench/results2.json")
    ap.add_argument("--d", type=int, default=96)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--max_len", type=int, default=1024)
    ap.add_argument("--steps", type=int, default=2500)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--eval_every", type=int, default=100)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--split_seed", type=int, default=11)
    ap.add_argument("--arms", default="decisive,bloc,median,mean,vanilla")
    ap.add_argument("--lr", default="")        # arm=lr,arm=lr,...
    ap.add_argument("--theta", type=float, default=0.0)
    ap.add_argument("--final", action="store_true",
                    help="ALSO score the SEALED Iddo questions. Use ONCE.")
    a = ap.parse_args()

    lrs = {}
    for kv in a.lr.split(","):
        if "=" in kv:
            k, v = kv.split("=")
            lrs[k.strip()] = float(v)

    print("loading ...", flush=True)
    data, rows = load(a.pairs, a.max_len, a.split_seed)
    print(f"pairs {len(rows)}   split BY QUESTION, and by ORIGIN", flush=True)

    torch.manual_seed(0)
    probe = Miko(d=a.d, depth=a.depth, max_len=a.max_len)
    n_m = sum(p.numel() for p in probe.parameters())
    vprobe = matched_vanilla(probe, a.max_len)
    n_v = sum(p.numel() for p in vprobe.parameters())
    print(f"\nMIKO    {n_m:,} params (d={a.d} depth={a.depth})")
    print(f"vanilla {n_v:,} params (d={vprobe.d})  mismatch {abs(n_m-n_v)/n_m:.3%}\n")

    test_sets = ["gtest"] + (["sealed"] if a.final else [])
    results = {"pairs_file": a.pairs, "n_pairs": len(rows), "config": vars(a),
               "params": {"miko": n_m, "vanilla": n_v,
                          "mismatch": abs(n_m - n_v) / n_m},
               "split_sizes": {k: {"rows": data[k]["n"],
                                   "questions": len(data[k]["questions"])}
                               for k in ("train", "val", "gtest", "sealed")},
               "floors": {t: floors(data, t) for t in test_sets},
               "rank_floors": {t: rank_floors(data, t, a.ranks, rows) for t in test_sets},
               "arms": {}}
    for t in test_sets:
        f = results["floors"][t]
        rf = results["rank_floors"][t]
        print(f"FLOORS on {t}: predict-0 MAE {f['predict_zero']:.4f}  "
              f"train-median({f['train_median']:.3f}) {f['predict_train_median']:.4f}  "
              f"train-mean({f['train_mean']:.3f}) {f['predict_train_mean']:.4f}")
        print(f"          random NDCG@10 {rf['random_ndcg@10']:.4f}   "
              f"BM25 NDCG@10 {rf['bm25_ndcg@10']:.4f}   "
              f"({rf['n_questions']} questions)\n")

    trained = {}
    for arm in a.arms.split(","):
        arm = arm.strip()
        if not arm:
            continue
        per_seed = []
        for s in range(a.seeds):
            t0 = time.time()
            torch.manual_seed(s); random.seed(s)
            m = Miko(d=a.d, depth=a.depth, max_len=a.max_len)
            model = (matched_vanilla(m, a.max_len) if arm == "vanilla" else m).to(DEV)
            CFG.update(rule=("bloc" if arm == "vanilla" else arm), theta=a.theta,
                       victim=None, how=None)
            lr = lrs.get(arm, 3e-4)
            curve = []
            vbest = train_one(model, data["train"], data["val_small"], a.steps, a.bs,
                              lr, curve, a.eval_every, seed=s)
            r = {"val_mae_best": vbest, "lr": lr, "seconds": round(time.time() - t0, 1),
                 "curve": curve[-6:]}
            for t in test_sets:
                res, _, _ = evaluate(model, data[t])
                r[t] = res
            per_seed.append(r)
            gt = r["gtest"]
            print(f"  [{arm} seed {s}] gtest MAE {gt['mae']:.4f}  "
                  f"ndcg@10 {gt['ndcg@10']:.4f}  spearman {gt['spearman']:+.4f}"
                  + (f"   | SEALED MAE {r['sealed']['mae']:.4f} "
                     f"ndcg@10 {r['sealed']['ndcg@10']:.4f}" if a.final else "")
                  + f"  ({r['seconds']}s)", flush=True)
            if s == 0 and arm != "vanilla":
                trained[arm] = model
        agg = {}
        for t in test_sets:
            for k in ("mae", "rmse", "pearson", "spearman", "ndcg@10"):
                vals = [x[t][k] for x in per_seed if not math.isnan(x[t][k])]
                agg[f"{t}.{k}"] = sum(vals) / len(vals) if vals else float("nan")
                agg[f"{t}.{k}_std"] = (statistics.pstdev(vals) if len(vals) > 1 else 0.0)
            cal = [x[t]["calibration"].get("hi_minus_lo_mae") for x in per_seed
                   if "hi_minus_lo_mae" in x[t]["calibration"]]
            agg[f"{t}.dissent_hi_minus_lo"] = cal
        results["arms"][arm] = {"mean": agg, "seeds": per_seed}
        print(f"  == {arm}: gtest MAE {agg['gtest.mae']:.4f} +- {agg['gtest.mae_std']:.4f}"
              + (f"   SEALED MAE {agg['sealed.mae']:.4f} +- {agg['sealed.mae_std']:.4f}"
                 if a.final else "") + "\n", flush=True)

    if trained:
        arm0 = "decisive" if "decisive" in trained else sorted(trained)[0]
        print(f"ROBUSTNESS on the trained {arm0} (seed 0), one seat broken, every rule")
        results["robustness_trained_on"] = arm0
        results["robustness"] = robustness(trained[arm0], data[test_sets[-1]])
        for k, v in results["robustness"].items():
            print(f"    {k:<20} clean {v['clean_mae']:.4f} -> "
                  f"corrupt {v['corrupt_mae_mean']:.4f}   deg {v['degradation']:+.4f}")

    json.dump(results, open(a.out, "w"), indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
