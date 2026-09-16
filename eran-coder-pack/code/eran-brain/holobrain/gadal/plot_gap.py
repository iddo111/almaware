"""GADAL — draw the train/val gap at every size, and where growth stopped.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The point of the picture is the SHAPE, not the decoration. It was drawn expecting a
U: test getting worse once capacity outruns the data. MEASURED, it is not a U. Train
climbs to a perfect fit and val flattens -- the textbook memorisation signature -- and
held-out accuracy keeps IMPROVING behind it, all the way to width 48. The picture is
kept exactly as it came out, because that is the result.

Renders bright, and writes JPEG + PDF -- never a raw .html -- per the deliverables law.
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))


def draw(path, out_stem, title):
    d = json.load(open(path, encoding="utf-8"))
    folds = d["folds"]
    hi = d["target"] == "decisions"
    ws = sorted(int(w) for w in folds[0]["fixed"])
    key = str if isinstance(next(iter(folds[0]["fixed"])), str) else int

    def col(w, k):
        return np.array([f["fixed"][key(w)][k] for f in folds])

    tr = np.array([col(w, "train").mean() for w in ws])
    va = np.array([col(w, "val").mean() for w in ws])
    te = np.array([col(w, "test").mean() for w in ws])
    gw = np.mean([f["gadal"]["width"] for f in folds])
    gte = np.mean([f["gadal"]["test"] for f in folds])
    floor = np.mean([f["majority"] for f in folds])
    ridge = np.mean([f["ridge49"] for f in folds])

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.8), facecolor="white")
    lbl = "accuracy" if hi else "-MAE"

    ax[0].plot(ws, tr, "o-", color="#1f77b4", label="train")
    ax[0].plot(ws, va, "s-", color="#ff7f0e", label="val")
    ax[0].plot(ws, te, "^-", color="#2ca02c", label="test (held-out)")
    ax[0].fill_between(ws, va, tr, color="#d62728", alpha=0.12, label="train-val gap")
    ax[0].axhline(floor, color="#888", ls=":", lw=1.4, label="do-nothing floor")
    ax[0].axhline(ridge, color="#9467bd", ls="--", lw=1.4, label="ridge49 (house model)")
    ax[0].axvline(gw, color="#000", ls="-.", lw=1.6)
    ax[0].plot([gw], [gte], "*", ms=18, color="#d62728", zorder=5,
               label=f"GADAL grew to {gw:.1f}")
    ax[0].set_xscale("log", base=2)
    ax[0].set_xticks(ws)
    ax[0].set_xticklabels(ws)
    ax[0].set_xlabel("hidden width (fixed-size control)")
    ax[0].set_ylabel(lbl)
    pk = int(np.argmax(te))
    fell = te[pk] - te[-1]
    ax[0].set_title("test FALLS once capacity outruns the signal (peak w=%d, then %+.3f)"
                    % (ws[pk], -fell) if fell > 0.02 else
                    "the gap grows — but test does not fall with it")
    ax[0].legend(fontsize=8, loc="best")
    ax[0].grid(alpha=0.25)

    mtr = np.array([col(w, "train_mse").mean() for w in ws])
    mva = np.array([col(w, "val_mse").mean() for w in ws])
    ax[1].plot(ws, mtr, "o-", color="#1f77b4", label="train MSE")
    ax[1].plot(ws, mva, "s-", color="#ff7f0e", label="val MSE")
    ax[1].axvline(gw, color="#000", ls="-.", lw=1.6, label=f"GADAL stopped at {gw:.1f}")
    ax[1].set_xscale("log", base=2)
    ax[1].set_yscale("log")
    ax[1].set_xticks(ws)
    ax[1].set_xticklabels(ws)
    ax[1].set_xlabel("hidden width")
    ax[1].set_ylabel("masked MSE (log)")
    ax[1].set_title("train MSE collapses %.0fx; val MSE %s"
                    % (mtr[0] / max(mtr.min(), 1e-12),
                       ("RISES %.0f%%" % (100 * (mva[-1] / mva[0] - 1)))
                       if mva[-1] > mva[0] * 1.1 else "never moves"))
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=0.25, which="both")

    fig.suptitle(title, fontsize=13)
    fig.tight_layout()
    for ext in ("jpg", "pdf"):
        fig.savefig(f"{out_stem}.{ext}", dpi=170, facecolor="white")
    plt.close(fig)
    print("wrote", out_stem + ".jpg /.pdf")


if __name__ == "__main__":
    runs = os.path.join(_HERE, "runs")
    for tag, title in (("decisions", "GADAL on MOREH decisions — 22 folds x 3 seeds, held out"),
                       ("decisions_shuffled",
                        "KNOWN-BAD CONTROL: the input->output map destroyed"),
                       ("amounts", "GADAL on MOREH amounts — the target with a real noise floor")):
        p = os.path.join(runs, tag + ".json")
        if os.path.exists(p):
            draw(p, os.path.join(runs, "gap_" + tag), title)
        else:
            print("skip (no run yet):", p)
