"""PROOF MIKO-07 -- the advertised scar guard was not on the path (2026-09-06).

model.py's docstring says the guard "runs against MikoBiEncoder before any number from it is
trusted". It did not: no file imported scar_guard, and `run()` with no argument built a FRESH
random MikoBiEncoder(d=64, depth=2) and guarded THAT -- never the trained 50M net, never the
Adapter (whose "parallel version" does not exist in v1/). A gate that never refused is not a
demonstrated gate.

FAILS against the 09-03 tree: run() passes with no model, returns PASS:False without raising
on a scarred model, and nothing imports it.
PASSES against the fix.

    python proof_MIKO-07.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE))
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

import torch.nn as nn   # noqa: E402

import scar_guard       # noqa: E402
from model import MikoBiEncoder  # noqa: E402
from adapter import Adapter      # noqa: E402

checks: list[tuple[str, bool, str]] = []

# 1. it must not invent a model to guard
try:
    scar_guard.run()
    invented = True
    note = "run() with no model returned a verdict about a net nobody ships"
except TypeError as e:
    invented = False
    note = f"refused: {str(e).splitlines()[0][:90]}"
checks.append(("run() cannot be called without the model being trusted", not invented, note))

# 2. it must REFUSE a scarred model -- the 2026-08-29 catastrophe, injected
scarred = MikoBiEncoder(d=16, depth=1, vocab_size=1024)
scarred.scar_head = nn.LayerNorm(1)          # identically zero for every input, forever
try:
    scar_guard.run(scarred)
    refused = False
    note = "it returned normally on a model containing nn.LayerNorm(1)"
except AssertionError as e:
    refused = True
    note = f"raised: {str(e)[:90]}"
except TypeError as e:                        # pragma: no cover
    refused = False
    note = f"TypeError: {e}"
checks.append(("a LayerNorm(1) scar makes the guard RAISE", refused, note))

# 3. it must pass a healthy model (a gate that refuses everything is useless too)
try:
    r = scar_guard.run(MikoBiEncoder(d=16, depth=1, vocab_size=1024))
    healthy = bool(r["PASS"])
    note = f"std across pairs = {r['dynamic']['std_across_pairs']:.4f}"
except Exception as e:                        # pragma: no cover
    healthy = False
    note = f"raised on a healthy model: {e}"
checks.append(("a healthy model passes", healthy, note))

# 4. the Adapter must have a guard at all
run_adapter = getattr(scar_guard, "run_adapter", None)
checks.append(("a guard exists for the Adapter", run_adapter is not None,
               "scar_guard.run_adapter(adapter, d_in)" if run_adapter
               else "absent -- the report's 'parallel version for the adapter' does not exist"))
if run_adapter is not None:
    a = Adapter(d_in=32, d_out=32, depth=1)
    try:
        run_adapter(a, d_in=32)
        a_ok = True
        a_note = "healthy adapter passes"
    except Exception as e:
        a_ok = False
        a_note = f"raised on a healthy adapter: {e}"
    checks.append(("the adapter guard passes a healthy adapter", a_ok, a_note))

    scarred_a = Adapter(d_in=32, d_out=32, depth=1)
    scarred_a.scar_head = nn.LayerNorm(1)
    try:
        run_adapter(scarred_a, d_in=32)
        a_ref = False
        a_note2 = "it accepted an adapter containing nn.LayerNorm(1)"
    except AssertionError as e:
        a_ref = True
        a_note2 = f"raised: {str(e)[:90]}"
    checks.append(("the adapter guard REFUSES a scarred adapter", a_ref, a_note2))

# 5. it must actually be on the path
for f in ("train.py", "adapter_train.py", "compare_all.py", "search.py", "exam_detail.py",
          "eval_exam.py"):
    src = (TARGET / f).read_text(encoding="utf-8")
    on = "scar_guard" in src
    checks.append((f"{f} calls the guard", on,
                   "imported and called" if on else "does not mention scar_guard"))

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-07: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
