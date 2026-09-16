#!/usr/bin/env python3
"""patch_life.py — give the ARM's eran_life.py a --closed-loop flag.

A selftest that passes while the real loop crashes is worthless, and that exact
failure happened elsewhere on this machine tonight. pc/run_arms.py exercises
Brain/Chemistry/School/sleep directly with the ear precomputed; it does NOT
exercise the life loop — the drives, the parent inbox, the dev gate, the
babble, the metrics writer, the checkpoint. This flag makes the REAL
eran_life.py run with the closed loop in it, so "it works" means the whole
organism ran, not that one function returned.

Refuses outside ~/eran-brain-pc.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.basename(ROOT) != "eran-brain-pc":
    sys.exit(f"REFUSED: only inside ~/eran-brain-pc, not {ROOT}")

LIFE = os.path.join(ROOT, "eran_life.py")
src = open(LIFE, encoding="utf-8").read()
if "--closed-loop" in src:
    print("already patched")
    sys.exit(0)

anchor_arg = '''    ap.add_argument("--state", default=None,'''
add_arg = '''    ap.add_argument("--closed-loop", action="store_true",
                    help="route layer-0 hearing through Brain.hear_pc — the "
                         "top-down prediction arrow (body/predict.py). The "
                         "PARALLEL ARM only; the living organism has no such "
                         "flag and never sees this file.")
'''
assert anchor_arg in src
src = src.replace(anchor_arg, add_arg + anchor_arg, 1)

anchor_run = '''    lock = acquire_lock()                          # held for the process's life'''
add_run = '''    if args.closed_loop:
        # One swap, at layer 0, in the arm only. MAX_LAYERS is 1 so this is
        # every hearing the organism does; if depth were ever unlocked the
        # layers above would need their own predictors and this line would
        # have to say so rather than silently apply.
        from predict import Predictor
        _pred = Predictor()

        def _hear_closed(self, vec, chem, beat, learn=True):
            return self.hear_pc(vec, chem, beat, _pred, learn=learn)

        Brain.hear = _hear_closed
        print(f"[life] CLOSED LOOP armed: layer-0 hearing -> Brain.hear_pc, "
              f"PC_FEEDBACK_GAIN={genome.PC_FEEDBACK_GAIN}, "
              f"top-k={genome.PC_TOPK}")

'''
assert anchor_run in src
src = src.replace(anchor_run, add_run + anchor_run, 1)

open(LIFE, "w", encoding="utf-8").write(src)
print(f"patched {LIFE}")
