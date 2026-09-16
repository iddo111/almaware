"""PROOF MIKO-08 -- the adapter's defaults reproduced the refuted run (2026-09-06).

adapter_train.py's defaults were d_out=256, depth=2, lr=1e-3 -- and with d_out != d_in the
Adapter SILENTLY set residual=False and switched to the random-init head the 09-03 report
itself calls "worse than doing nothing". Meanwhile the configuration that actually produced
adapter-v1.pt (d_out=384, depth=1, lr=1e-5, patience implied 8) existed only in report prose:
no results file, no checkpoint field, no log, no shell history recorded it.

FAILS against the 09-03 tree (defaults 256/2/1e-3; Adapter(384, 256) degrades silently; the
run records nothing about itself).
PASSES against the fix.

    python proof_MIKO-08.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE))
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

checks: list[tuple[str, bool, str]] = []

src = (TARGET / "adapter_train.py").read_text(encoding="utf-8")
tree = ast.parse(src)

defaults: dict[str, object] = {}
for node in ast.walk(tree):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument" and node.args
            and isinstance(node.args[0], ast.Constant)):
        flag = node.args[0].value
        for kw in node.keywords:
            if kw.arg == "default":
                try:
                    defaults[flag] = ast.literal_eval(kw.value)
                except Exception:                                  # pragma: no cover
                    pass

WANT = {"--d-out": 384, "--depth": 1, "--lr": 1e-5, "--patience": 8}
for flag, want in WANT.items():
    got = defaults.get(flag)
    checks.append((f"default {flag} reproduces the shipped checkpoint's run",
                   got == want, f"default = {got!r}, expected {want!r}"))

# the silent degradation path must be gone
from adapter import Adapter  # noqa: E402
try:
    a = Adapter(d_in=384, d_out=256, depth=2)
    silent = getattr(a, "residual", None) is False
    raised = False
    note = ("Adapter(384, 256) built a random-init head with residual silently OFF"
            if silent else "Adapter(384, 256) built something unexpected")
except ValueError as e:
    raised = True
    note = f"refused: {str(e)[:100]}"
checks.append(("Adapter refuses residual with d_in != d_out instead of degrading", raised, note))

# the run must record itself
checks.append(("the checkpoint records the arguments it was produced with",
               '"args": vars(args)' in src,
               "vars(args) written into the checkpoint" if '"args": vars(args)' in src
               else "nothing records lr/d_out/depth/patience -- prose only"))
checks.append(("the final results record the arguments too",
               src.count('"args": vars(args)') >= 2,
               f"{src.count('args\": vars(args)')} sites write vars(args)"))
checks.append(("the adapter run leaves a stdout log next to its checkpoint",
               "adapter_train_stdout.log" in src,
               "tee to adapter_train_stdout.log" if "adapter_train_stdout.log" in src
               else "console output is lost, as it was on 09-03"))
checks.append(("the validation history is recorded, not just the winner",
               '"val_history"' in src,
               "val_history in the results file" if '"val_history"' in src else "absent"))

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-08: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
