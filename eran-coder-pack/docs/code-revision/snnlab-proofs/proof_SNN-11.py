"""proof_SNN-11 — a run's tail thread must speak only for its own run.

_tail closed over `self.proc`, which launch() rebinds. Every previous run's
thread therefore saw the NEW process as alive, never reached its exit
condition, and lived for the life of the server — one leaked thread per run —
while still holding `self`, so it could stamp 'training exited with code N
before finishing' onto a run that had only just started.

No subprocess is spawned: the processes here are stand-ins with poll().

  FAILS on server.py.bak-rev-20260906   PASSES on the fixed server.py
"""
import argparse
import inspect
import os
import sys
import threading
import time

from _proofcommon import HERE, load, verdict


class FakeProc:
    def __init__(self, rc=None):
        self.rc = rc

    def poll(self):
        return self.rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "server.py"))
    a = ap.parse_args()
    mod = load(a.src, "server_under_test")

    lab = mod.Lab()
    dead_proc = FakeProc(rc=1)          # run A: already exited
    lab.run_id, lab.proc = "run-A", dead_proc
    missing = os.path.join(HERE, "runs", "__proof_snn11_no_such_run.jsonl")

    args_taken = len(inspect.signature(lab._tail).parameters)
    args = (missing, dead_proc, "run-A") if args_taken == 3 else (missing,)
    t = threading.Thread(target=lab._tail, args=args, daemon=True)
    t.start()
    print(f"_tail takes {args_taken} argument(s) besides self "
          f"({'its own proc + run id' if args_taken == 3 else 'only the path'})")

    time.sleep(0.4)
    # A NEW run starts while A's thread is still settling.
    live_proc = FakeProc(rc=None)
    lab.reset()
    lab.run_id, lab.proc = "run-B", live_proc

    t.join(timeout=6.0)
    leaked = t.is_alive()
    print(f"run-A's thread after run-B started: "
          f"{'STILL ALIVE (leaked)' if leaked else 'exited'}")
    print(f"error stamped onto run-B by run-A's thread: {lab.error!r}")

    ok = (not leaked) and lab.error is None and args_taken == 3
    lab.run_id = None                    # let any stray thread go
    return verdict(ok, "one thread per run, and it dies with its own process")


if __name__ == "__main__":
    sys.exit(main())
