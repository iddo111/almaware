"""proof_SNN-5 — no number picked ON the exam may be reported as a score.

  best_test_acc is the max over epochs of accuracy on the HELDOUT: early
  stopping on the test set. It was published beside final_test_acc as if the
  two were the same kind of thing (201010: final 81.82% / best 85.61%), and
  sweep.py chose the winning config by the mean of three best-of-60 numbers.

  FAILS on the .bak files   PASSES on the fixed train.py + sweep.py
"""
import argparse
import os
import shutil
import sys
import tempfile

import numpy as np

from _proofcommon import HERE, Quiet, load, tiny_cfg, fake_percepts, verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    ap.add_argument("--sweep", default=os.path.join(HERE, "sweep.py"))
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="proof_snn5_")
    ok_train = ok_sweep = False
    try:
        T = load(a.src, "train_under_test")
        xtr, ytr = fake_percepts(128, seed=1)
        xte, yte = fake_percepts(44, seed=2)
        res = T.run(tiny_cfg(epochs=3, run_id="proof-snn5",
                             results=os.path.join(tmp, "r.json")),
                    Quiet(), log=lambda *a: None,
                    data=(xtr, ytr, xte, yte), install_signals=False)
        print(f"train: final={res['final_test_acc']:.4f} "
              f"best={res['best_test_acc']:.4f} "
              f"reported={res.get('reported_test_acc')} "
              f"oracle_flag={res.get('best_test_acc_is_oracle')}")
        ok_train = (res.get("best_test_acc_is_oracle") is True
                    and res.get("reported_test_acc") == res["final_test_acc"]
                    and "oracle" in str(res.get("best_test_acc_note", "")).lower())

        S = load(a.sweep, "sweep_under_test")
        calls = {"n": 0}

        def fake_run(cfg, events, log=None, data=None, install_signals=True):
            calls["n"] += 1
            return {"best_test_acc": 0.90, "final_test_acc": 0.50,
                    "organism_comparable": True}
        real = S.T.run
        S.T.run = fake_run
        try:
            out = S.one(dict(tiny_cfg()), (xtr, ytr, xte, yte), seeds=(0, 1, 2))
        finally:
            S.T.run = real
        mean = out[0]
        print(f"sweep.one() over 3 fake runs (final 50.00%, best 90.00%) "
              f"selected on: {mean:.2%}")
        ok_sweep = abs(mean - 0.50) < 1e-9 and calls["n"] == 3

        return verdict(ok_train and ok_sweep,
                       "the reported score must be the final epoch; the best "
                       "epoch is an oracle and must be labelled as one")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
