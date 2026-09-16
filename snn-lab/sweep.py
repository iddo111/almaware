"""sweep.py — find the knobs on a DEV split, then open the exam once.

The 132-item heldout is ERAN's exam. Every published number on this corpus
(chance 4.55%, random-frames 46.21%, raw+loudest60 68.94%, the prototype
organism 62.88%, the frozen cochlea's own nearest-centroid 79.55%) is measured
on it. If this lab tuned its hyper-parameters against that same 132 items and
then reported the best one, the number would be inflated and the comparison
dishonest — you would be reporting the luckiest of N draws.

So: carve a stratified dev split out of the 396 training wavs, sweep on THAT,
pick the winner on dev, retrain on the full 396, and only then open the heldout
— once, for one config. That number is comparable to the published ones.

    python sweep.py                 # dev sweep + one final exam
    python sweep.py --dry           # dev sweep only, exam untouched
"""
import argparse
import json
import os
import time

import numpy as np

import cochlea
import train as T

HERE = os.path.dirname(os.path.abspath(__file__))


class Quiet:
    def __call__(self, *a, **k):
        pass

    def close(self):
        pass


def stratified_dev(x, y, frac=0.25, seed=0):
    """Same number of items held back from every one of the 22 classes."""
    rng = np.random.RandomState(seed)
    dev = []
    for c in np.unique(y):
        idx = np.where(y == c)[0]
        rng.shuffle(idx)
        dev.extend(idx[:max(1, int(round(frac * len(idx))))])
    dev = np.array(sorted(dev))
    keep = np.setdiff1d(np.arange(len(y)), dev)
    return x[keep], y[keep], x[dev], y[dev]


GRID = [
    dict(hidden=256, steps=32, beta=0.90, recurrent=False),
    dict(hidden=512, steps=32, beta=0.90, recurrent=False),
    dict(hidden=1024, steps=32, beta=0.90, recurrent=False),
    dict(hidden=512, steps=32, beta=0.70, recurrent=False),
    dict(hidden=512, steps=32, beta=0.95, recurrent=False),
    dict(hidden=512, steps=64, beta=0.90, recurrent=False),
    dict(hidden=512, steps=32, beta=0.90, recurrent=True),
    dict(hidden=1024, steps=32, beta=0.90, recurrent=True),
    dict(hidden=1024, steps=64, beta=0.95, recurrent=True),
    dict(hidden=512, steps=32, beta=0.90, recurrent=False, encoding="static"),
    dict(hidden=1024, steps=32, beta=0.90, recurrent=False, encoding="static"),
]
BASE = dict(dataset="syllables", encoding="cochlea-time", surrogate="atan",
            lr=2e-3, batch=64, threshold=1.0, input_gain=13.86, epochs=60,
            seed=0, threads=4, device="auto", log_every=10 ** 9,
            eval_train_n=400, run_id="sweep", events=None, results=None)


def one(cfg, data, seeds=(0, 1, 2)):
    """Mean best-accuracy over seeds — one seed on 99 dev items is noise."""
    accs = []
    for s in seeds:
        c = dict(cfg, seed=s)
        r = T.run(c, Quiet(), log=lambda *a: None, data=data,
                  install_signals=False)
        accs.append(r["best_test_acc"])
    return float(np.mean(accs)), float(np.std(accs)), accs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true",
                    help="dev sweep only — do not open the heldout")
    ap.add_argument("--epochs", type=int, default=60)
    a = ap.parse_args()

    xtr, ytr, xhe, yhe = T.load_syllables()
    xa, ya, xd, yd = stratified_dev(xtr, ytr, frac=0.25, seed=0)
    print(f"train {len(ya)}  dev {len(yd)}  heldout {len(yhe)} (SEALED)")
    print(f"chance {cochlea.CHANCE:.4%}\n")
    print(f"{'config':58s} {'dev mean':>9s} {'sd':>6s}")

    rows = []
    for g in GRID:
        cfg = dict(BASE, epochs=a.epochs, **g)
        t0 = time.time()
        m, sd, accs = one(cfg, (xa, ya, xd, yd))
        name = (f"h{cfg['hidden']} T{cfg['steps']} b{cfg['beta']} "
                f"{cfg['encoding']}{' +rec' if cfg['recurrent'] else ''}")
        print(f"{name:58s} {m:9.2%} {sd:6.2%}   ({time.time()-t0:.0f}s)")
        rows.append({"cfg": {k: cfg[k] for k in
                             ("hidden", "steps", "beta", "encoding",
                              "recurrent", "epochs", "lr", "input_gain",
                              "threshold", "surrogate", "batch")},
                     "dev_mean": m, "dev_sd": sd, "dev_seeds": accs})

    rows.sort(key=lambda r: -r["dev_mean"])
    win = rows[0]
    print(f"\nDEV WINNER: {win['cfg']}  ->  {win['dev_mean']:.2%}")

    out = {"chance": cochlea.CHANCE, "n_train": len(ya), "n_dev": len(yd),
           "dev_frac": 0.25, "sweep": rows,
           "winner_cfg": win["cfg"], "dev_mean": win["dev_mean"]}

    if not a.dry:
        print("\nopening the exam ONCE, for the dev winner, retrained on all "
              f"{len(ytr)} training wavs (3 seeds):")
        cfg = dict(BASE, **win["cfg"])
        accs, finals = [], []
        for s in (0, 1, 2):
            r = T.run(dict(cfg, seed=s), Quiet(), log=lambda *a: None,
                      data=(xtr, ytr, xhe, yhe), install_signals=False)
            accs.append(r["best_test_acc"])
            finals.append(r["final_test_acc"])
            print(f"  seed {s}: final {r['final_test_acc']:.2%}  "
                  f"best {r['best_test_acc']:.2%}")
        org = cochlea.ORGANISM["prototype_organism_heldout"]
        out["heldout_final_seeds"] = finals
        out["heldout_best_seeds"] = accs
        out["heldout_final_mean"] = float(np.mean(finals))
        out["heldout_best_mean"] = float(np.mean(accs))
        out["prototype_organism"] = org
        out["beats_prototype_organism"] = bool(np.mean(finals) > org)
        print(f"\nHELDOUT (132 items), mean of 3 seeds: "
              f"final {np.mean(finals):.2%}  best-epoch {np.mean(accs):.2%}")
        print(f"chance                          {cochlea.CHANCE:.2%}")
        for k, v in sorted(cochlea.BASELINES.items(), key=lambda kv: kv[1]):
            print(f"{k:32s}{v:.2%}")
        print(f"{'prototype organism':32s}{org:.2%}")
        print(f"VERDICT: the SNN "
              f"{'BEATS' if np.mean(finals) > org else 'does NOT beat'} "
              f"the prototype organism "
              f"({np.mean(finals):.2%} vs {org:.2%}, "
              f"{100*(np.mean(finals)-org):+.2f} pp)")

    p = os.path.join(HERE, "results", "SWEEP.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
