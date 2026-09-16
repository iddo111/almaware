#!/usr/bin/env python3
"""proof_ERAN-13.py -- the sleep summary must not drown journald.

Defect: sleep.cycle() printed a "[sleep] pruned ..." line to stdout/journald on
every single sleep -- every ~9 s, about 9,300 lines a day. journald's 389 MB
retention had already evicted the 2026-08-21 boot lines, so the wake / rebirth
/ error lines that say WHAT this process is actually running are gone and
unrecoverable. The same summary is written IN FULL to journal-<date>.md every
night, so nothing is lost by printing the routine one night in 100 -- and a
layer birth must always be printed.

sleep._should_log_sleep is lifted out of the file by source segment; numpy and
genome are never imported and no sleep cycle is run.

    python3 proof_ERAN-13.py           # body/sleep.py as it is now
    python3 proof_ERAN-13.py --bak     # body/sleep.py.bak-rev-20260906
"""
import ast
import io
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
N = 1000


def _grab(path, names):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    segs = []
    for want in names:
        node = None
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and n.name == want:
                node = n
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == want:
                        node = n
        if node is None:
            return None, src
        segs.append(textwrap.dedent(ast.get_source_segment(src, node) or ""))
    g = {}
    exec(compile("\n".join(segs), "sleep-fragment", "exec"), g)
    return g, src


def main():
    bak = "--bak" in sys.argv
    path = os.path.join(HERE, "sleep.py") + (".bak-rev-20260906" if bak else "")
    print("proof ERAN-13 -- one routine sleep line in SLEEP_LOG_EVERY, births always")
    print("  sleep     : %s" % path)
    if not os.path.exists(path):
        print("FAIL: missing %s" % path)
        return 1

    g, src = _grab(path, ["SLEEP_LOG_EVERY", "_SLEEPS_SEEN", "_should_log_sleep"])
    if g is None:
        print("  _should_log_sleep / SLEEP_LOG_EVERY: NOT FOUND -- every sleep "
              "still prints to journald (~9,300 lines/day)")
        print("RESULT: FAIL")
        return 1

    every = g["SLEEP_LOG_EVERY"]
    fn = g["_should_log_sleep"]
    routine = sum(1 for _ in range(N) if fn(None))
    births = sum(1 for _ in range(50) if fn({"layer": 1}))
    used = "_should_log_sleep(birth)" in src
    per_day = 9300.0 * routine / float(N)
    ok = (routine == N // every and births == 50 and used and every >= 20)
    print("  %d routine sleeps -> %d printed (SLEEP_LOG_EVERY=%d, expect %d)"
          % (N, routine, every, N // every))
    print("  50 layer births   -> %d printed (must be 50: a birth is never quiet)"
          % births)
    print("  cycle() uses the gate: %s" % used)
    print("  journald load: ~9,300 lines/day -> ~%.0f lines/day" % per_day)
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
