#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALMA-GUARD v0.2 - one harness for every arm, so the A/B stays clean. FLEET ONLY.

    python3 -m alma_guard.v02_experiment cv    --arm arms/x.json --fold-seed 0 --out out/x.json
    python3 -m alma_guard.v02_experiment final --arm arms/x.json --seed 0      --out out/x.json

An ARM is a JSON object: {"name": ..., "kind": "alma" | "perceptron" | "logreg" |
"mlp", "task": "binary" | "multi", ...its own parameters}. Every arm sees the
identical rows, the identical group-aware folds and the identical hashed
features at its width. Only what learns differs.

`cv`    k-fold cross-validation on dataset.jsonl. Reports accuracy, P/R/F1,
        balanced accuracy, per-source accuracy and the SHORT-HEBREW false-alarm
        rate over the folds.
`final` trains on every row of dataset.jsonl, then scores each held-out source
        SEPARATELY - never pooled: fresh (v0.1, 16), guard-p2 (5), shield-tests
        (28), and fresh-v02 when it exists. The saved weights go to --save.

Training runs on eran2 under nice/taskset (see RESULTS.md §v0.2). Never the PC.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma_guard import data as D                                   # noqa: E402
from alma_guard import encoding as E                               # noqa: E402
from alma_guard.train import heads_for, label_of                   # noqa: E402
from alma_guard.train_vanilla_control import Linear                # noqa: E402
from alma_guard.weave import GuardWeave, Hyper                     # noqa: E402

HERE = Path(__file__).resolve().parent
HELDOUT_FILES = [("fresh.jsonl", None), ("fresh_v02.jsonl", "fresh-v02")]


# ------------------------------------------------------------------ vanilla MLP

class MLP:
    """The vanilla HIDDEN-LAYER control: the ALMA hidden weave's exact shape and
    parameter count (x->h, one->h, h->out, x->out skip, one->out), tanh hidden
    units, trained by ordinary backpropagation on a weighted logistic loss."""

    def __init__(self, heads, width, default, hidden, typical, seed=0,
                 init=0.02, h_init=1.0, skip=True):
        self.heads, self.width, self.default = list(heads), width, default
        self.H, self.skip = hidden, skip
        rng = random.Random(seed)
        a = h_init / math.sqrt(max(1, typical))
        self.W1 = [[rng.uniform(-a, a) for _ in range(width)] for _ in range(hidden)]
        self.b1 = [rng.uniform(-a, a) for _ in range(hidden)]
        K = len(self.heads)
        self.W2 = [[rng.uniform(-init, init) for _ in range(hidden)] for _ in range(K)]
        self.S = ([[rng.uniform(-init, init) for _ in range(width)] for _ in range(K)]
                  if skip else None)
        self.b2 = [rng.uniform(-init, init) for _ in range(K)]

    def params(self) -> int:
        K = len(self.heads)
        return self.H * self.width + self.H + K * self.H + K + (K * self.width if self.skip else 0)

    def _forward(self, f):
        fs = [i for i in f if 0 <= i < self.width]
        hid = []
        for j in range(self.H):
            wj = self.W1[j]
            hid.append(math.tanh(self.b1[j] + sum(wj[i] for i in fs)))
        outs = []
        for k in range(len(self.heads)):
            z = self.b2[k] + sum(w * x for w, x in zip(self.W2[k], hid))
            if self.skip:
                sk = self.S[k]
                z += sum(sk[i] for i in fs)
            outs.append(z)
        return fs, hid, outs

    def predict(self, f):
        _, _, outs = self._forward(f)
        best, bs = None, 0.0
        for k, s in enumerate(outs):
            if s >= 0.0 and (best is None or s > bs):
                best, bs = k, s
        return self.default if best is None else self.heads[best]

    def fit(self, feats, labels, epochs, lr, l2, seed=0, pos_weight=1.0):
        rng = random.Random(seed + 13)
        order = list(range(len(feats)))
        for ep in range(epochs):
            rng.shuffle(order)
            step = lr / (1.0 + ep * 0.1)
            for j in order:
                fs, hid, outs = self._forward(feats[j])
                y = labels[j]
                dh = [0.0] * self.H
                for k, name in enumerate(self.heads):
                    want = 1.0 if y == name else 0.0
                    p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, outs[k]))))
                    g = (want - p) * (pos_weight if want else 1.0)
                    w2 = self.W2[k]
                    for jj in range(self.H):
                        dh[jj] += g * w2[jj]
                        w2[jj] += step * (g * hid[jj] - l2 * w2[jj])
                    if self.skip:
                        sk = self.S[k]
                        for i in fs:
                            sk[i] += step * (g - l2 * sk[i])
                    self.b2[k] += step * g
                for jj in range(self.H):
                    gz = dh[jj] * (1.0 - hid[jj] * hid[jj])
                    if not gz:
                        continue
                    w1 = self.W1[jj]
                    for i in fs:
                        w1[i] += step * (gz - l2 * w1[i])
                    self.b1[jj] += step * gz


# ------------------------------------------------------------------ arms

def typical_present(rows, width) -> int:
    fs = [E.features(r["text"], width) for r in rows]
    return max(1, round(sum(len(f) for f in fs) / max(1, len(fs))))


def make_model(arm: dict, heads, default, seed: int, typical: int):
    kind = arm["kind"]
    if kind == "alma":
        keys = Hyper.__dataclass_fields__.keys()
        hp = {k: v for k, v in arm.items() if k in keys}
        hp["seed"] = seed
        if hp.get("hidden") and not hp.get("typical"):
            hp["typical"] = typical
        return GuardWeave(heads, Hyper(**hp), default=default)
    if kind in ("perceptron", "logreg"):
        return Linear(heads, arm["width"], default, seed=seed)
    if kind == "mlp":
        return MLP(heads, arm["width"], default, arm["hidden"],
                   arm.get("typical") or typical, seed=seed,
                   h_init=arm.get("h_init", 1.0), skip=arm.get("skip", True))
    raise ValueError(f"unknown kind {kind!r}")


def fit(model, arm, feats, labels, seed):
    kind = arm["kind"]
    if kind == "alma":
        rng = random.Random(seed + 1)
        order = list(range(len(feats)))
        for _ in range(arm.get("epochs", 15)):
            rng.shuffle(order)
            for i in order:
                model.present(feats[i], labels[i], learn=True)
    elif kind == "perceptron":
        model.fit_perceptron(feats, labels, arm["epochs"], arm["lr"], seed,
                             arm.get("pos_weight", 1.0))
    elif kind == "logreg":
        model.fit_logreg(feats, labels, arm["epochs"], arm["lr"], arm.get("l2", 1e-4),
                         seed, arm.get("pos_weight", 1.0))
    else:
        model.fit(feats, labels, arm["epochs"], arm["lr"], arm.get("l2", 1e-4),
                  seed, arm.get("pos_weight", 1.0))


def predict(model, arm, f):
    return model.predict(f)[0] if arm["kind"] == "alma" else model.predict(f)


def n_params(model, arm) -> int:
    if arm["kind"] == "alma":
        return sum(1 for t in model.weave.threads if not t.dst.startswith("say")
                   for _ in t.strands)
    if arm["kind"] == "mlp":
        return model.params()
    return len(model.heads) * (model.width + 1)


def summary(rows, idx, truth, pred, task):
    # For the 4-class task `metrics` would score a class name against "attack" and
    # report zeros, so the attack-vs-benign reading is computed on binarised labels.
    m = D.metrics([D.binarise(t) for t in truth], [D.binarise(p) for p in pred])
    m["acc"] = sum(1 for t, p in zip(truth, pred) if t == p) / len(truth) if truth else 0.0
    out_extra = {}
    if task == "multi":
        out_extra["per_class_recall"] = {
            c: (sum(1 for t, p in zip(truth, pred) if t == c and p == c)
                / max(1, sum(1 for t in truth if t == c)))
            for c in D.CLASSES}
        out_extra["binary_acc"] = m["tp"] + m["tn"] and (m["tp"] + m["tn"]) / len(truth)
    return {"metrics": m, "majority": D.majority_baseline(truth), **out_extra,
            "per_source": D.per_source(rows, idx, truth, pred),
            "short_hebrew": D.short_hebrew(rows, idx, truth, pred)}


# ------------------------------------------------------------------ modes

def run_cv(arm, fold_seed, k):
    task = arm.get("task", "binary")
    heads, default = heads_for(task)
    rows = D.load()
    width = arm["width"]
    feats = [E.features(r["text"], width) for r in rows]
    labels = [label_of(r, task) for r in rows]
    fs = D.folds(rows, k, seed=fold_seed)
    truth, pred, idx, per_fold, params = [], [], [], [], None
    for f in range(k):
        te = fs[f]
        tr = [i for j, g in enumerate(fs) if j != f for i in g]
        t0 = time.time()
        typ = round(sum(len(feats[i]) for i in tr) / len(tr))
        model = make_model(arm, heads, default, fold_seed, typ)
        params = n_params(model, arm)
        fit(model, arm, [feats[i] for i in tr], [labels[i] for i in tr], fold_seed)
        t = [labels[i] for i in te]
        p = [predict(model, arm, feats[i]) for i in te]
        truth += t
        pred += p
        idx += te
        mm = D.metrics(t, p)
        per_fold.append({"acc": mm["acc"], "f1": mm["f1"], "secs": time.time() - t0})
        print(f"  [{arm['name']}] fold {f+1}/{k} acc {mm['acc']:.3f} F1 {mm['f1']:.3f} "
              f"({time.time()-t0:.0f}s)", flush=True)
    out = {"mode": "cv", "arm": arm, "fold_seed": fold_seed, "folds": k,
           "params": params, "per_fold": per_fold, "rows": len(rows),
           **summary(rows, idx, truth, pred, task)}
    return out


def run_final(arm, seed, save=""):
    task = arm.get("task", "binary")
    heads, default = heads_for(task)
    rows = D.load()
    width = arm["width"]
    feats = [E.features(r["text"], width) for r in rows]
    labels = [label_of(r, task) for r in rows]
    typ = round(sum(len(f) for f in feats) / len(feats))
    t0 = time.time()
    model = make_model(arm, heads, default, seed, typ)
    fit(model, arm, feats, labels, seed)
    secs = time.time() - t0
    out = {"mode": "final", "arm": arm, "seed": seed, "rows": len(rows),
           "params": n_params(model, arm), "train_secs": secs, "heldout": {}}
    tr_pred = [predict(model, arm, f) for f in feats]
    out["train_fit"] = D.metrics(labels, tr_pred)
    for fname, force_source in HELDOUT_FILES:
        p = HERE / fname
        if not p.exists():
            continue
        held = D.load(p)
        by: dict[str, list[int]] = {}
        for i, r in enumerate(held):
            by.setdefault(force_source or r.get("source", "?"), []).append(i)
        for src, ids in sorted(by.items()):
            hr = [held[i] for i in ids]
            t = [label_of(r, task) for r in hr]
            pr = [predict(model, arm, E.features(r["text"], width)) for r in hr]
            s = summary(hr, list(range(len(hr))), t, pr, task)
            s["misses"] = [{"text": r["text"][:120], "want": a, "got": b}
                           for r, a, b in zip(hr, t, pr) if a != b]
            out["heldout"][src] = s
            m = s["metrics"]
            sh = s["short_hebrew"]
            print(f"  [{arm['name']}] seed {seed} {src:13s} n={m['n']:3d} acc {m['acc']:.3f} "
                  f"R {m['recall']:.3f} F1 {m['f1']:.3f}  shortHE FA "
                  f"{sh['false_alarms']}/{sh['benign_n']}", flush=True)
    if save and arm["kind"] == "alma":
        Path(save).write_text(json.dumps({"task": task, "hyper": model.hyper.__dict__,
                                          "heads": model.heads, "default": model.default,
                                          "weights": model.weights()}), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("cv", "final"))
    ap.add_argument("--arm", required=True, help="path to an arm JSON")
    ap.add_argument("--fold-seed", type=int, default=0)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--save", default="")
    args = ap.parse_args()
    arm = json.loads(Path(args.arm).read_text(encoding="utf-8"))
    t0 = time.time()
    if args.mode == "cv":
        out = run_cv(arm, args.fold_seed, args.folds)
    else:
        out = run_final(arm, args.seed, args.save)
    out["wall_secs"] = time.time() - t0
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.mode == "cv":
        m = out["metrics"]
        sh = out["short_hebrew"]
        print(f"[{arm['name']}] CV fold-seed {args.fold_seed}: acc {m['acc']:.4f} P {m['precision']:.4f} "
              f"R {m['recall']:.4f} F1 {m['f1']:.4f} bal {m['balanced']:.4f}  shortHE FA "
              f"{sh['false_alarms']}/{sh['benign_n']}  params {out['params']}  {out['wall_secs']:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
