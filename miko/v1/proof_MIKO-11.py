"""PROOF MIKO-11 -- the silent-empty path (code revision 2026-09-06).

The ERAN shape, latent here: an empty train set runs zero optimizer steps,
`ep_loss / max(1, n_steps)` prints a clean 0.0, evaluation still runs, and the UNTRAINED
epoch-1 model is saved as "best" (0.0 > -1.0). No exception, no log line. adapter_train.py
carried the same shape plus a `if i in q_id2row` filter that can drop every id if
e5_query_emb.pt is stale.

FAILS against the 09-03 tree (no refusal helper; `max(1, n_steps)` divides the emptiness away).
PASSES against the fix.

    python proof_MIKO-11.py [--dir <tree>]
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

try:
    import signals
except ImportError as e:
    signals = None
    checks.append(("an empty-input refusal helper exists", False,
                   f"import signals -> {e}"))

if signals is not None:
    assert_nonempty = getattr(signals, "assert_nonempty", None)
    checks.append(("an empty-input refusal helper exists", assert_nonempty is not None,
                   "signals.assert_nonempty(name, seq, where)" if assert_nonempty else "absent"))
    if assert_nonempty:
        try:
            assert_nonempty("train", [], "an empty split")
            fired = False
            note = "it accepted an empty train set"
        except SystemExit as e:
            fired = "EMPTY-TRAIN" in str(e)
            note = str(e)[:110]
        checks.append(("an empty train set is refused by name", fired, note))
        try:
            assert_nonempty("train", [("q", "id")], "a real split")
            passed = True
        except SystemExit:                                          # pragma: no cover
            passed = False
        checks.append(("a non-empty input is left alone", passed,
                       "no refusal on a real split"))

# the divide-the-emptiness-away idiom must be gone from the code (comments may cite it)
for f in ("train.py", "adapter_train.py"):
    src = (TARGET / f).read_text(encoding="utf-8")
    code_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    idiom = any("max(1, n_steps)" in ln for ln in code_lines)
    checks.append((f"{f} no longer divides by max(1, n_steps)", not idiom,
                   "gone from the code path" if not idiom
                   else "still there -- an epoch with no steps prints loss 0.0000"))
    checks.append((f"{f} names an empty epoch", "EMPTY-EPOCH" in src,
                   "present" if "EMPTY-EPOCH" in src else "an empty epoch is silent"))
    checks.append((f"{f} refuses an empty split before the loop",
                   "assert_nonempty" in src,
                   "present" if "assert_nonempty" in src else "absent"))

src_a = (TARGET / "adapter_train.py").read_text(encoding="utf-8")
checks.append(("adapter_train.py refuses a filter that dropped ids",
               "QUERY-CACHE-INCOMPLETE" in src_a,
               "present" if "QUERY-CACHE-INCOMPLETE" in src_a
               else "`if i in q_id2row` can drop everything with no word said"))

# the checkpoint-selection consequence: an untrained model must not be saved as 'best'
for f in ("train.py", "adapter_train.py"):
    src = (TARGET / f).read_text(encoding="utf-8")
    checks.append((f"{f} will not save a chance-level model as 'best'",
                   "> rand_baseline" in src,
                   "the save is baseline-guarded" if "> rand_baseline" in src
                   else "`0.0 > -1.0` saves the untrained epoch-1 model"))

ast.parse((TARGET / "train.py").read_text(encoding="utf-8"))       # still valid python

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-11: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
