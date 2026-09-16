"""PROOF MIKO-03 -- checkpoint selection ran on a dead signal (code revision 2026-09-06).

val recall@1 was identically 0.0000 for all 15 epochs of the 09-03 from-scratch run, so
`val > best_val` fired only at epoch 1 (0.0 > -1.0): the shipped miko-v1.pt IS the epoch-1
model and the loop idled ten more epochs to patience. The adapter run declined monotonically
from epoch 1, so its "best" was the first epoch too. In both runs "best" == first: selection
never selected. No check named the state.

FAILS against the 09-03 code (no signals module at all; the loop cannot name a dead metric,
and it saves a checkpoint whose val is at chance as "best").
PASSES against the fix.

    python proof_MIKO-03.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE))
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

checks: list[tuple[str, bool, str]] = []

try:
    import signals
    have = True
except ImportError as e:
    signals = None
    have = False
    checks.append(("a named-state gate for the validation signal exists", False,
                   f"import signals -> {e}. The 09-03 loops had no way to name "
                   "'validation flat at chance' at all."))

if have:
    base = signals.random_baseline(835)          # the real corpus size
    # 1. the exact 09-03 from-scratch history: 0.0 fifteen times
    dead = signals.val_signal_state([0.0] * 3, base)
    checks.append(("flat-at-chance is named VAL-DEAD", bool(dead) and "VAL-DEAD" in dead,
                   (dead or "returned None -- the run would keep going").split("\n")[0][:110]))

    # 2. the exact 09-03 adapter history, epochs 1-5
    hist = [0.6666666666666666, 0.6212121212121212, 0.5454545454545454, 0.5, 0.45454545454545453]
    dec = signals.val_signal_state(hist, base)
    checks.append(("never-beats-epoch-1 is named VAL-DECLINING",
                   bool(dec) and "VAL-DECLINING" in dec,
                   (dec or "returned None -- 8 more epochs would run to patience")
                   .split("\n")[0][:110]))

    # 3. a healthy plateau must NOT be killed
    alive = signals.val_signal_state([0.70, 0.70, 0.70, 0.72], base)
    checks.append(("a healthy plateau well above chance is left alone", alive is None,
                   "None (keeps training)" if alive is None else f"false positive: {alive[:80]}"))

    # 4. a normal noisy improving run must NOT be killed
    alive2 = signals.val_signal_state([0.30, 0.28, 0.31, 0.29, 0.35], base)
    checks.append(("a dipping-then-recovering run is left alone", alive2 is None,
                   "None (keeps training)" if alive2 is None else f"false positive: {alive2[:80]}"))

for f in ("train.py", "adapter_train.py"):
    src = (TARGET / f).read_text(encoding="utf-8")
    checks.append((f"{f} consults the gate every epoch",
                   "signals.val_signal_state" in src,
                   "val_signal_state called in the loop" if "signals.val_signal_state" in src
                   else "no gate in the loop"))
    checks.append((f"{f} refuses to call chance-level 'best'",
                   "> rand_baseline" in src,
                   "the save is guarded by the random baseline" if "> rand_baseline" in src
                   else "`val > best_val` alone -- 0.0 > -1.0 saves an untrained model"))
    checks.append((f"{f} refuses to report when nothing beat the baseline",
                   "NO-CHECKPOINT" in src,
                   "present" if "NO-CHECKPOINT" in src else "it would reload whatever is on disk"))

# the historical evidence, for the record
mp = TARGET / "metrics.jsonl"
if mp.exists():
    rows = [json.loads(l) for l in mp.open(encoding="utf-8")]
    vals = [r["val_recall@1"] for r in rows]
    print(f"[info] 09-03 from-scratch run: {len(rows)} epochs, val recall@1 = "
          f"{sorted(set(vals))}, train_loss {rows[0]['train_loss']:.4f} -> "
          f"{rows[-1]['train_loss']:.4f}")
    if have:
        b = signals.random_baseline(835)
        first = next((i + 1 for i in range(len(vals))
                      if signals.val_signal_state(vals[:i + 1], b)), None)
        print(f"[info] the fixed gate would have stopped that run at epoch {first} "
              f"instead of {len(rows)}")

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-03: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
