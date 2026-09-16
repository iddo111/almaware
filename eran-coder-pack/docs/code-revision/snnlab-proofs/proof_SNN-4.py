"""proof_SNN-4 — hidden_rate is the DEAD-NETWORK check, so it must be true.

Two failures, one variable:
  (a) a run stopped at the start of an epoch wrote hidden_rate 0.0 — "dead" —
      for a network that had just been firing (results/syllables-20260821-201105
      .json: stopped, 55.30%, hidden_rate 0.0).
  (b) a genuinely silent run wrote a normal results row and a normal history
      entry, gated by nothing (results/syllables-20260821-201220.json: 134
      epochs, hidden_rate 0.0, 4.545% = exactly chance).

  FAILS on train.py.bak-rev-20260906   PASSES on the fixed train.py
"""
import argparse
import os
import shutil
import sys
import tempfile

from _proofcommon import HERE, Quiet, load, tiny_cfg, fake_percepts, verdict


class StopAfter(dict):
    """_STOP that flips to True on the Nth read — a SIGTERM at a chosen batch."""
    def __init__(self, n):
        super().__init__(now=False)
        self.n, self.reads = n, 0

    def __getitem__(self, k):
        if k == "now":
            self.reads += 1
            return self.reads > self.n
        return super().__getitem__(k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    a = ap.parse_args()
    T = load(a.src, "train_under_test")

    tmp = tempfile.mkdtemp(prefix="proof_snn4_")
    try:
        xtr, ytr = fake_percepts(128, seed=1)      # 2 batches of 64
        xte, yte = fake_percepts(44, seed=2)

        # (a) alive, then stopped at the FIRST batch of epoch 1.
        T._STOP = StopAfter(2)                     # epoch 0 has 2 batches
        res = T.run(tiny_cfg(epochs=4, run_id="proof-snn4a",
                             results=os.path.join(tmp, "a.json")),
                    Quiet(), log=lambda *a: None,
                    data=(xtr, ytr, xte, yte), install_signals=False)
        print(f"(a) stopped run: epochs_done={res['epochs_done']} "
              f"test={res['final_test_acc']:.2%} hidden_rate={res['hidden_rate']}")
        alive_ok = (res["stopped"] and res["epochs_done"] >= 1
                    and res["hidden_rate"] not in (None, 0.0)
                    and not res.get("dead", False))

        # (b) genuinely silent: no input current, and a threshold no bias can
        # reach on its own. Nothing in the hidden layer fires, at all.
        T._STOP = dict(now=False)
        dead = T.run(tiny_cfg(epochs=2, input_gain=0.0, threshold=50.0,
                              run_id="proof-snn4b",
                              results=os.path.join(tmp, "b.json")),
                     Quiet(), log=lambda *a: None,
                     data=(xtr, ytr, xte, yte), install_signals=False)
        print(f"(b) silent run:  hidden_rate={dead['hidden_rate']} "
              f"dead={dead.get('dead')} beats_chance={dead.get('beats_chance')} "
              f"vs_organism={dead.get('vs_prototype_organism')}")
        dead_ok = (dead.get("dead") is True
                   and dead.get("beats_chance") is None
                   and dead.get("vs_prototype_organism") is None)

        return verdict(alive_ok and dead_ok,
                       "a stopped run must not be reported as dead, and a dead "
                       "run must not be reported as a score")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
