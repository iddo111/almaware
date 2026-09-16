# -*- coding: utf-8 -*-
"""PROOF TZ-6 — the materials checks are inside the suite that gets counted

Run it against the code on disk:      python proof_TZ-6.py
Run it against the pre-fix backup:    python proof_TZ-6.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import subprocess


def _collect(target):
    r = subprocess.run([sys.executable, "-m", "pytest", target, "-q",
                        "--collect-only"], cwd=ROOT, capture_output=True, text=True)
    n = 0
    for line in (r.stdout + r.stderr).splitlines():
        line = line.strip()
        if line.endswith("tests collected") or " tests collected" in line:
            for tok in line.split():
                if tok.isdigit():
                    n = int(tok)
                    break
        if line.startswith("no tests ran") or "no tests collected" in line:
            n = 0
    return n


def main():
    stray = [f for f in os.listdir(ROOT)
             if f.startswith("test_") and f.endswith(".py")]
    assert not stray, (
        f"{stray} sit in the tzelem ROOT, and count_tests.py runs `pytest tests -q`. "
        f"tests.json reports the suite as green while these are outside it entirely.")
    n = _collect("tests")
    assert n >= 40, (
        f"`pytest tests` collects only {n} tests. The materials organ's checks are "
        f"still not in the number night_sheet.py prints as the night's coverage.")
    print(f"PASS  {ROOT}")
    print(f"      no test_*.py stranded in the tzelem root")
    print(f"      `pytest tests -q --collect-only` = {n} tests (was 21)")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
