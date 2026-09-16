# -*- coding: utf-8 -*-
"""
A DECOY ORGANISM -- a real systemd --user service with a real pid and a real
journal, built only so the watchdog can be proven against a real process death
and a real seal breach.

It exists because the alternative is killing the sibling to test the alarm, and
the sibling is not a test fixture.  Nothing here reads or writes anything of
~/sibling or ~/sibling-ear.

--breach opens a READ file descriptor inside ERAN's tree and holds it.  Read
only, nothing written, nothing changed: that is already a seal breach by the
sibling's law ("may read its own copies, never ERAN's live state"), and it is
the safest possible way to prove the detector sees one.
"""
import argparse
import datetime as dt
import io
import json
import os
import time

ROOT = os.path.join(os.path.expanduser("~"), "sibling-watch", "inject", "live")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, default=20.0)
    ap.add_argument("--freeze", action="store_true",
                    help="stop moving the objective, but keep journalling")
    ap.add_argument("--breach", default=None,
                    help="hold a read fd open on this path (a forbidden tree)")
    a = ap.parse_args()

    os.makedirs(ROOT, exist_ok=True)
    io.open(os.path.join(ROOT, "decoy.py"), "w", encoding="utf-8").write("# decoy\n")

    held = None
    if a.breach:
        held = open(a.breach, "rb")  # read only. Nothing is written, ever.

    i = 0
    while True:
        exam = 0.44 if a.freeze else min(0.90, 0.30 + 0.01 * i)
        rec = {"t": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "kind": "round",
               "exam": round(exam, 4), "ruler": round(0.40 + 0.005 * i, 4),
               "gate": round(0.1 * (i % 7), 4), "born": 0.2, "pid": os.getpid()}
        with io.open(os.path.join(ROOT, "journal.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        i += 1
        time.sleep(a.period)
    if held:
        held.close()


if __name__ == "__main__":
    main()
