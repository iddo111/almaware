"""proof_SNN-3 — a training run must leave weights behind.

  FAILS on train.py.bak-rev-20260906  (no torch.save anywhere in the tree)
  PASSES on the fixed train.py        (runs/<id>.pt loads and answers again)
"""
import argparse
import glob
import os
import shutil
import sys
import tempfile

import numpy as np

from _proofcommon import HERE, Quiet, load, tiny_cfg, fake_percepts, verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    a = ap.parse_args()
    T = load(a.src, "train_under_test")

    tmp = tempfile.mkdtemp(prefix="proof_snn3_")
    try:
        # Big enough to actually learn something: a checkpoint that only
        # reproduces 0% would prove nothing.
        xtr, ytr = fake_percepts(440, seed=1)
        xte, yte = fake_percepts(110, seed=2)
        cfg = tiny_cfg(hidden=64, epochs=20, run_id="proof-snn3",
                       results=os.path.join(tmp, "proof-snn3.json"))
        res = T.run(cfg, Quiet(), log=lambda *a: None,
                    data=(xtr, ytr, xte, yte), install_signals=False)
        pts = sorted(glob.glob(os.path.join(tmp, "*.pt")))
        print(f"run finished: final {res['final_test_acc']:.2%} | "
              f"checkpoints written: {[os.path.basename(p) for p in pts]}")
        if not pts:
            return verdict(False, "the run saved NO weights — the 85.61% net "
                                  "of 2026-08-21 no longer exists anywhere")

        # The real question: can the saved net be asked the exam again?
        pred, classes, _ = T.predict(os.path.join(tmp, "proof-snn3.pt"), xte,
                                     device="cpu")
        acc = float((pred == yte).mean())
        net, meta = T.load_checkpoint(os.path.join(tmp, "proof-snn3.pt"), "cpu")
        print(f"reloaded {meta['which']} checkpoint: {len(classes)} classes, "
              f"cfg.hidden={meta['cfg']['hidden']}, re-asked exam -> {acc:.2%} "
              f"(run reported {res['final_test_acc']:.2%})")
        ok = (abs(acc - res["final_test_acc"]) < 1e-6
              and acc > res["chance"] and len(set(pred.tolist())) > 1
              and res.get("checkpoint") and meta["cfg"]["hidden"] == cfg["hidden"]
              and list(classes) == list(meta["classes"]))
        return verdict(ok, "a saved net must reproduce its own reported score")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
