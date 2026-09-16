#!/usr/bin/env python3
"""Paired old-vs-new comparison, split into a CONTAMINATED half and a CLEAN half.

CODER-05, 2026-09-06.

The original docstring said the two runs are compared "over identical data" and
that "the only differences are the weights and the batch size". The first half is
true and the second half is not, and the difference matters more than the number.

Both runs start at dom_cursor=0 / rep_cursor=0, and MixedLoader decides
domain-vs-replay purely from the GLOBAL sequence index, so after k optimiser
steps a run has consumed sequences [0, k*block_size) whatever block_size is.
New step k covers the same SET as old step 16k (128 vs 8 per step). That part
holds.

What the old comparison did not say: the NEW run does not start from the base
model. It starts from init_weights_step1017.pt, extracted from the OLD run's
checkpoint at step 1017 -- and that checkpoint's train_state.json records
seq_index 8136, i.e. those weights had ALREADY TRAINED on global sequences
0..8135. Every new-run step below the boundary is therefore being scored on text
it has already seen once. The reported -0.2568 nats (-16 sigma) is real learning
plus first-pass memorisation, in unknown proportion, and it cannot be separated
after the fact.

So this version prints both halves and refuses to report only the flattering one:

  CONTAMINATED  new steps whose sequences overlap [0, old_seq_index)
  CLEAN         new steps entirely past it -- the only honest loss comparison
                available from train.out

Neither half answers "is the model better on code it has never seen". That takes
eval_ckpt.py on the held-out set; this file only compares training losses.
"""
import json
import math
import os
import re
import statistics as st
import sys

STEP_RE = re.compile(r"step (\d+)/(\d+) loss ([0-9.]+) gnorm ([0-9.]+)")


def first_clean_step(old_seq_index, block_size):
    """First NEW step whose sequences are entirely unseen by the warm-start weights.

    New step d covers global sequences [(d-1)*block, d*block). It is clean when
    (d-1)*block >= old_seq_index, i.e. d >= ceil(old_seq_index/block) + 1.

    >>> first_clean_step(8136, 128)
    65
    >>> first_clean_step(8192, 128)
    65
    >>> first_clean_step(0, 128)
    1
    """
    if not old_seq_index or old_seq_index <= 0 or block_size <= 0:
        return 1
    return -(-int(old_seq_index) // int(block_size)) + 1


def read_init_seq_index(path):
    """seq_index recorded in the checkpoint the new run was warm-started from."""
    try:
        with open(path, encoding="utf-8") as f:
            return int(json.load(f).get("seq_index") or 0)
    except Exception:
        return 0


def stat(v):
    return (st.mean(v), st.stdev(v) / math.sqrt(len(v)) if len(v) > 1 else float("nan"))


def compare(old_losses, new_losses, label):
    if len(old_losses) < 2 or len(new_losses) < 2:
        print(f"  {label:<13} not enough steps yet "
              f"(old n={len(old_losses)}, new n={len(new_losses)})")
        return
    mo, so = stat(old_losses)
    mn, sn = stat(new_losses)
    d = mn - mo
    sd = math.sqrt(so ** 2 + sn ** 2)
    print(f"  {label:<13} old {mo:.4f} +/- {so:.4f} (n={len(old_losses):<5})   "
          f"new {mn:.4f} +/- {sn:.4f} (n={len(new_losses):<5})   "
          f"diff {d:+.4f} +/- {sd:.4f} ({d / sd:+.2f} sigma)")


def main(argv):
    train_out = argv[1] if len(argv) > 1 else "train.out"
    init_state = (argv[2] if len(argv) > 2 else
                  os.path.expanduser("~/coder-train/ckpt/step_00001017/train_state.json"))
    block = int(argv[3]) if len(argv) > 3 else 128

    old, new = [], []
    with open(train_out, errors="replace") as f:
        for line in f:
            m = STEP_RE.search(line)
            if not m:
                continue
            s, t = int(m.group(1)), int(m.group(2))
            rec = (s, float(m.group(3)), float(m.group(4)))
            (old if t == 8000 else new).append(rec)

    if not new:
        sys.exit("no steps from the new run yet")

    seq_index = read_init_seq_index(init_state)
    boundary = first_clean_step(seq_index, block)
    n = len(new)
    ratio = block // 8          # old block_size was 8

    print(f"WARM START: the new run's weights come from a checkpoint at "
          f"seq_index {seq_index:,}")
    print(f"            -> new steps 1..{boundary - 1} re-see sequences those weights "
          f"already trained on")
    print(f"            -> new steps {boundary}.. are the first genuinely unseen data")
    print(f"new run has {n} step(s); old run has {len(old)} step(s)")
    print()

    # --- contaminated half: the number the old script printed on its own -----
    hi = min(n, boundary - 1)
    if hi >= 1:
        o = [x[1] for x in old if x[0] <= ratio * hi]
        nn = [x[1] for x in new if x[0] <= hi]
        compare(o, nn, "CONTAMINATED")
        print("                (new steps 1..%d -- the warm-start weights had already "
              "trained on this text;\n"
              "                 a lower loss here is partly memorisation and must NOT "
              "be reported as learning)" % hi)
    else:
        print("  CONTAMINATED  none")
    print()

    # --- clean half ----------------------------------------------------------
    if n >= boundary:
        o = [x[1] for x in old if ratio * (boundary - 1) < x[0] <= ratio * n]
        nn = [x[1] for x in new if x[0] >= boundary]
        compare(o, nn, "CLEAN")
        print("                (new steps %d..%d -- data neither set of weights had "
              "seen before this run)" % (boundary, n))
    else:
        print(f"  CLEAN         not reached yet: the new run is at step {n}, "
              f"the first clean step is {boundary}")
        print(f"                => there is currently NO uncontaminated loss "
              f"comparison. Do not quote one.")
    print()

    go = [x[2] for x in old]
    gn = [x[2] for x in new]
    if go and gn:
        print(f"  gnorm  old {st.mean(go):.3f}  new {st.mean(gn):.3f}   (clip = 1.0)")
    if len(old) > 1:
        print(f"  per-step loss sd  old {st.stdev([x[1] for x in old]):.4f}", end="")
    if n > 2:
        print(f"   new (excl. step 1) {st.stdev([x[1] for x in new[1:]]):.4f}")
    else:
        print()
    print()
    print("NOTE: both halves are TRAINING loss. Whether the model is better on code "
          "it has\n      never seen is a different question, and only eval_ckpt.py on "
          "heldout.jsonl\n      answers it. That number does not exist yet.")


if __name__ == "__main__":
    main(sys.argv)
