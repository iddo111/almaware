"""Count the tests by RUNNING them, so the sheet cannot print a stale number.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

`night_sheet.py` prints "every number on this page is read from a measurement
file". The test counts were the exception: they were typed by hand, and by the
time the page was built they were already wrong. A page that says it never
hand-types a number, and hand-types one, is worse than a page that says nothing.
So the counts come from a real pytest run, with the exit status kept beside them —
a suite that FAILED must not be able to report its size as if it passed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

SUITES = {
    "alma": r"D:\CLAUDE\alma-language",
    "tzelem": r"D:\CLAUDE\eran-brain\holobrain\tzelem",
    "winston": r"D:\CLAUDE\eran-brain\holobrain\winston",
    "moreh": r"D:\CLAUDE\eran-brain\holobrain\moreh",
    "safa-achat": r"D:\CLAUDE\eran-brain\holobrain\safa-achat",
    "kav": r"D:\CLAUDE\eran-brain\holobrain\kav",
}
LINE = re.compile(r"(\d+) (passed|failed|skipped|xfailed|error)")


def run_one(name: str, cwd: str) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"],
                       cwd=cwd, capture_output=True, text=True,
                       env=env, timeout=1800)
    tail = (p.stdout or "") + (p.stderr or "")
    counts = {k: int(v) for v, k in LINE.findall(tail)}
    return {"passed": counts.get("passed", 0),
            "failed": counts.get("failed", 0) + counts.get("error", 0),
            "skipped": counts.get("skipped", 0),
            "xfailed": counts.get("xfailed", 0),
            "exit": p.returncode, "green": p.returncode == 0}


def main() -> dict:
    out = {}
    for name, cwd in SUITES.items():
        out[name] = run_one(name, cwd)
        r = out[name]
        print(f"{name:12s} {r['passed']:3d} passed  {r['failed']} failed  "
              f"{'GREEN' if r['green'] else 'RED'}", flush=True)
    out["all_green"] = all(v["green"] for k, v in out.items() if k != "all_green")
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "out-night", "tests.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(("ALL GREEN" if out["all_green"] else "NOT GREEN") + f" -> {dst}")
    return out


if __name__ == "__main__":
    sys.exit(0 if main()["all_green"] else 1)
