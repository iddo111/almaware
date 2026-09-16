"""Dummy KESHEV entrypoint for the criterion-7 test (K4).

Mirrors the REAL app.py startup contract (PHASE2-DESIGN.md section 7, scar 1):
the mutex acquire is the FIRST meaningful statement, before any heavy import.

  winner: acquires the mutex, holds it for --hold seconds (standing in for
          process life), prints WINNER, exits 0.
  loser:  writes ONE refusal log line to <logdir>/refusal-<pid>.log and
          exits 11 — the whole process lives well under 1 second.

Usage: dummy_entrypoint.py <logdir> [--hold SECONDS] [--name MUTEXNAME]
"""
import os
import sys
import time

_T0 = time.perf_counter()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import mutexguard  # noqa: E402

if __name__ == "__main__":
    logdir = sys.argv[1]
    name = mutexguard.MUTEX_NAME
    hold = 6.0
    args = sys.argv[2:]
    while args:
        a = args.pop(0)
        if a == "--hold":
            hold = float(args.pop(0))
        elif a == "--name":
            name = args.pop(0)

    def _refusal_log(line: str) -> None:
        # in-process lifetime from interpreter top (_T0) to the refusal —
        # the honest <1s measurement for criterion 7
        elapsed = time.perf_counter() - _T0
        path = os.path.join(logdir, f"refusal-{os.getpid()}.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"{line} elapsed_s={elapsed:.3f}\n")

    # FIRST statement of the app proper: exits 11 with one log line if duplicate.
    _handle = mutexguard.acquire_or_exit(name=name, log=_refusal_log)

    elapsed = time.perf_counter() - _T0
    print(f"WINNER pid={os.getpid()} acquire_s={elapsed:.3f}", flush=True)
    time.sleep(hold)
    sys.exit(0)
