"""MIKO v1 -- named states for the training signals.  (code revision 2026-09-06)

Both MIKO training loops selected checkpoints and stopped early on a metric that was
numerically DEAD, and neither noticed:

  * train.py         val recall@1 was identically 0.0000 for all 15 epochs, so
                     `val > best_val` fired only at epoch 1 (0.0 > -1.0). The shipped
                     miko-v1.pt IS the epoch-1 model and the loop then idled ten more
                     epochs to patience. (MIKO-03)
  * adapter_train.py val recall@1 fell monotonically from epoch 1 (0.667 -> 0.348), so
                     "best" was again the first epoch, 11 optimizer steps in. (MIKO-03)

In both runs "best" == first: selection never selected anything, and nothing anywhere
said so. These helpers exist so the state has a NAME and the run stops on it -- and so
the gate can be tested without running a training loop (a gate that never refused is not
a demonstrated gate).
"""
from __future__ import annotations


def random_baseline(n_docs: int) -> float:
    """recall@1 a uniformly random ranker scores over n_docs candidates."""
    return 1.0 / max(1, n_docs)


def val_signal_state(val_hist: list[float], rand_baseline: float,
                     flat_k: int = 3, decline_k: int = 5) -> str | None:
    """Return a NAMED dead-signal state, or None while the signal is alive.

    VAL-DEAD      the metric has not moved for `flat_k` epochs AND sits at or below what
                  a coin flip scores. Flat at chance is not "training slowly".
    VAL-DECLINING the metric has never once improved on epoch 1 across `decline_k`
                  epochs, i.e. the best checkpoint is the first and selection has, again,
                  selected nothing.
    """
    if not val_hist:
        return None
    if (len(val_hist) >= flat_k
            and len(set(val_hist[-flat_k:])) == 1
            and val_hist[-1] <= rand_baseline):
        return (f"VAL-DEAD: val recall@1 unchanged for {flat_k} epochs at {val_hist[-1]:.4f}, "
                f"at or below the random-ranking baseline ({rand_baseline:.4f}). The "
                "validation signal is dead, not merely flat -- refusing to keep training or "
                "to call any epoch 'best'. See MIKO-03.")
    if (len(val_hist) >= decline_k
            and val_hist[0] == max(val_hist)
            and all(a >= b for a, b in zip(val_hist, val_hist[1:]))
            and val_hist[-1] < val_hist[0]):
        return (f"VAL-DECLINING: val recall@1 has never beaten epoch 1 in {len(val_hist)} "
                f"epochs ({val_hist[0]:.4f} -> {val_hist[-1]:.4f}). 'best' is the first "
                "epoch, i.e. selection has selected nothing. See MIKO-03.")
    return None


def assert_nonempty(name: str, seq, where: str) -> None:
    """Refuse an empty input instead of succeeding without reading anything.

    MIKO-11, and the shape that nearly silenced ERAN on 2026-09-06: a split that
    classified every file as test made serve_menu() return an empty menu forever -- no
    exception, no log line, beats kept being written. Here the same shape would run zero
    optimizer steps, print a clean `loss=0.0000` through `ep_loss / max(1, n_steps)`, and
    still save an UNTRAINED epoch-1 checkpoint as "best".
    """
    n = len(seq) if hasattr(seq, "__len__") else 0
    if n == 0:
        raise SystemExit(f"EMPTY-{name.upper()}: 0 items from {where} -- refusing to run on "
                         "nothing. See MIKO-11.")
