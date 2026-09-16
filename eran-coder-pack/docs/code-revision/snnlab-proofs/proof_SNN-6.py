"""proof_SNN-6 — an empty or lopsided feed must RAISE, not succeed quietly.

This is the shape that nearly starved ERAN: a filter that can exclude
everything, and a loop that treats zero batches as a finished epoch.
`for s in range(0, 0, B)` never runs, evaluate() divides by max(1, n), and a
full results JSON is written with epochs_done == epochs and a chance-level
score. Nothing asserted that one sample had been read.

  FAILS on train.py.bak-rev-20260906   PASSES on the fixed train.py
"""
import argparse
import os
import shutil
import sys
import tempfile

import numpy as np

from _proofcommon import HERE, Quiet, load, tiny_cfg, fake_percepts, verdict


def raised(fn):
    try:
        fn()
    except Exception as e:                                       # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:90]}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    a = ap.parse_args()
    T = load(a.src, "train_under_test")

    tmp = tempfile.mkdtemp(prefix="proof_snn6_")
    try:
        xte, yte = fake_percepts(44, seed=2)
        empty_x = np.zeros((0, 8, 24), dtype=np.float32)
        empty_y = np.zeros((0,), dtype=np.int64)

        out = {}

        def run_empty():
            out["res"] = T.run(tiny_cfg(epochs=3, run_id="proof-snn6a",
                                        results=os.path.join(tmp, "a.json")),
                               Quiet(), log=lambda *a: None,
                               data=(empty_x, empty_y, xte, yte),
                               install_signals=False)
        err_empty = raised(run_empty)
        if err_empty is None:
            r = out["res"]
            print(f"EMPTY TRAINING SET produced a clean run: "
                  f"epochs_done={r['epochs_done']} n_train={r['n_train']} "
                  f"final={r['final_test_acc']:.2%} "
                  f"beats_chance={r.get('beats_chance')}")
        else:
            print(f"empty training set -> {err_empty}")

        # One class missing entirely — a split that silently drops a syllable.
        xtr, ytr = fake_percepts(128, seed=1)
        keep = ytr != 5
        lop_x, lop_y = xtr[keep], ytr[keep]

        def run_lopsided():
            T.run(tiny_cfg(epochs=1, run_id="proof-snn6b",
                           results=os.path.join(tmp, "b.json")),
                  Quiet(), log=lambda *a: None,
                  data=(lop_x, lop_y, xte, yte), install_signals=False)
        err_lop = raised(run_lopsided)
        print(f"class 'ha' missing from train -> "
              f"{err_lop or 'NO ERROR (trained on 21 of 22 classes silently)'}")

        ok = err_empty is not None and err_lop is not None
        return verdict(ok, "a run that never read a sample is not a run")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
