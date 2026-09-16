"""Run every KAV revision proof twice: against the backup, then against the fix.

A proof only counts if it FAILS on `old` and PASSES on `new`.
    python proofs/run_all.py            -> runs them all, writes the outputs
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = r"D:\CLAUDE\_deliverables\code-revision\kav-proofs"
os.makedirs(OUT, exist_ok=True)


def main() -> int:
    only = sys.argv[1:]
    proofs = sorted(glob.glob(os.path.join(HERE, "proof_KAV-*.py")))
    if only:
        proofs = [p for p in proofs if any(o in p for o in only)]
    rows, bad = [], 0
    for path in proofs:
        name = os.path.basename(path)[:-3]
        res = {}
        for variant in ("old", "new"):
            t = time.time()
            p = subprocess.run([sys.executable, path, variant],
                               capture_output=True, text=True, cwd=HERE, timeout=1800)
            res[variant] = (p.returncode, (p.stdout or "") + (p.stderr or ""),
                            round(time.time() - t, 1))
            io.open(os.path.join(OUT, f"{name}.{variant}.txt"), "w",
                    encoding="utf-8", newline="\n").write(res[variant][1])
        ok = res["old"][0] != 0 and res["new"][0] == 0
        bad += 0 if ok else 1
        rows.append((name, res["old"][0], res["new"][0], ok,
                     res["old"][2], res["new"][2]))
        print(f"{'OK ' if ok else 'BAD'} {name:16s} old exit {res['old'][0]} "
              f"({res['old'][2]:5.1f}s)  new exit {res['new'][0]} ({res['new'][2]:5.1f}s)")
        if not ok:
            print("      --- old ---")
            print("      " + res["old"][1].strip().replace("\n", "\n      ")[-1500:])
            print("      --- new ---")
            print("      " + res["new"][1].strip().replace("\n", "\n      ")[-1500:])
    print(f"\n{len(rows) - bad}/{len(rows)} proofs FAIL on the backup and PASS on the fix")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
