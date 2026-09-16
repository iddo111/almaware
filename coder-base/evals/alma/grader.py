#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Objective, executable grader for the ALMA neural-net eval ladder.

Runs a SUBMITTED weave (.json or .voice) through the REAL alma.Loom — the
same runtime shipped in D:\\CLAUDE\\alma-language\\alma\\loom.py. There is no
proxy here: a task passes only if the loom, run beat-by-beat, produces the
exact expected numbers.

Usage:
    PYTHONIOENCODING=utf-8 python grader.py <task_id> <path/to/submission.json|.voice>
    PYTHONIOENCODING=utf-8 python grader.py all reference_solutions/   # self-test

task_id in {L0, L1, L2, L3, L4, L5}. See tasks/<task_id>_*.md for the prose
spec each submission must satisfy; this file is the ground truth for what
"pass" means.

CONTRACT every submission must honor (stated again in each task file):
  - Input values arrive as SEEDS into knots with the exact names given for
    that task (e.g. 'x', or 'x1'/'x2'/'x3'). The grader OVERWRITES only the
    seed(s) targeting those input knots for each test case; every other seed
    already in the file (e.g. a helper "always emit 0" reference) is left
    exactly as authored and reused for every test case.
  - The result must be observable at exactly one fringe knot named 'y', and
    that knot must record EXACTLY ONE value per run within the horizon.
  - A submission may use any internal topology/knot names it likes, and may
    freely use the four shipped spells (xor, max, min, sign) UNLESS a task
    explicitly disallows one (L3 and L5 disallow spell=xor, because the whole
    point of those two tasks is composing a hidden layer, not calling the
    answer that already ships in alma/spells.py).
"""
from __future__ import annotations

import itertools
import os
import sys

ALMA_ROOT = r"D:\CLAUDE\alma-language"
sys.path.insert(0, ALMA_ROOT)

from alma import Loom, Seed, Weave, WeaveError          # noqa: E402
from alma.text import from_json, parse_voice            # noqa: E402


def load_weave(path: str) -> Weave:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.lower().endswith(".voice"):
        return parse_voice(text)
    return from_json(text)


def run_case(base: Weave, inputs: dict, beats: int) -> list:
    """Rebuild the weave's seed list: drop any seed targeting an input knot
    named in `inputs`, keep every other seed untouched, add the new input
    seeds at beat 1, then run and return the recorded fringe('y') values."""
    w = base
    keep = [s for s in w.seeds if s.dst not in inputs]
    w.seeds = keep + [Seed(dst, float(v), 1) for dst, v in inputs.items()]
    w.validate()
    result = Loom().run(w, beats)
    return result.fringe("y"), result


def bool_grid(names):
    for combo in itertools.product((0.0, 1.0), repeat=len(names)):
        yield dict(zip(names, combo))


# ---------------------------------------------------------------- tasks

def expect_L0(x):
    return 3.0 * x + 7.0


def expect_L1(x1, x2, x3):
    return 0.5 * x1 - 0.25 * x2 + 2.0 * x3 - 1.0


def expect_L2(x1, x2):
    return 1.0 if (x1 and x2) else -1.0


def expect_L3(x1, x2):
    return 1.0 if (x1 != x2) else -1.0


def expect_L4(x):
    return max(x, 0.0)


def expect_L5(x1, x2):
    return 1.0 if (x1 != x2) else -1.0


TASKS = {
    "L0": dict(inputs=("x",), cases=[{"x": v} for v in (-2.0, 0.0, 5.0, 10.0, 3.25)],
               expect=lambda c: expect_L0(c["x"]), tol=1e-6, disallow_spells=()),
    "L1": dict(inputs=("x1", "x2", "x3"),
               cases=[{"x1": a, "x2": b, "x3": c} for a, b, c in
                      [(4.0, -2.0, 1.0), (0.0, 0.0, 0.0), (-3.0, 5.0, -1.5),
                       (1.0, 1.0, 1.0), (7.0, -7.0, 2.5)]],
               expect=lambda c: expect_L1(c["x1"], c["x2"], c["x3"]), tol=1e-6,
               disallow_spells=()),
    "L2": dict(inputs=("x1", "x2"), cases=list(bool_grid(("x1", "x2"))),
               expect=lambda c: expect_L2(c["x1"], c["x2"]), tol=0,
               disallow_spells=()),
    "L3": dict(inputs=("x1", "x2"), cases=list(bool_grid(("x1", "x2"))),
               expect=lambda c: expect_L3(c["x1"], c["x2"]), tol=0,
               disallow_spells=("xor",)),
    "L4": dict(inputs=("x",), cases=[{"x": v} for v in (-3.0, -0.5, 0.0, 2.0, 7.25)],
               expect=lambda c: expect_L4(c["x"]), tol=1e-9, disallow_spells=()),
    "L5": dict(inputs=("x1", "x2"), cases=list(bool_grid(("x1", "x2"))),
               expect=lambda c: expect_L5(c["x1"], c["x2"]), tol=0,
               disallow_spells=("xor",)),
}


def grade(task_id: str, path: str, beats: int = 24, verbose: bool = True) -> bool:
    spec = TASKS[task_id]
    try:
        base = load_weave(path)
    except WeaveError as e:
        print(f"[{task_id}] FAIL — could not parse '{path}': {e}")
        return False

    for spell_name in spec["disallow_spells"]:
        used = {k.spell for k in base.knots.values() if k.verb == "spell"}
        if spell_name in used:
            print(f"[{task_id}] FAIL — uses spell='{spell_name}' directly, "
                  f"which this task disallows (that spell already ships the "
                  f"answer in alma/spells.py; the task is to compose it from "
                  f"scratch out of the six combining verbs plus sign/max).")
            return False

    if "y" not in base.knots or base.knots["y"].verb != "fringe":
        print(f"[{task_id}] FAIL — no knot named 'y' with verb=fringe.")
        return False

    all_ok = True
    for case in spec["cases"]:
        try:
            got, result = run_case(base, case, beats)
        except WeaveError as e:
            print(f"[{task_id}] FAIL on input {case}: WeaveError: {e}")
            all_ok = False
            continue
        expect = spec["expect"](case)
        tol = spec["tol"]
        ok = (len(got) == 1) and (abs(got[0] - expect) <= tol if tol else got[0] == expect)
        if verbose:
            status = "ok" if ok else "FAIL"
            print(f"[{task_id}] {case} -> got={got}  expect={expect}  [{status}]"
                  f"{'' if result.finished else '  (WARNING: horizon cut the run short)'}")
        all_ok = all_ok and ok
    print(f"[{task_id}] {'PASS' if all_ok else 'FAIL'}  ({path})")
    return all_ok


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    task_id, path = argv[1], argv[2]
    if task_id == "all":
        # self-test mode: path is a directory of L0.json .. L5.json / L2.voice
        ok = True
        for t in TASKS:
            for ext in (".json", ".voice"):
                cand = os.path.join(path, t + ext)
                if os.path.exists(cand):
                    ok = grade(t, cand) and ok
        return 0 if ok else 1
    ok = grade(task_id, path)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
