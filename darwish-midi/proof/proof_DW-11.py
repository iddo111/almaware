# -*- coding: utf-8 -*-
"""proof_DW-11.py — a tap must never be paid twice, lost, or renamed away.

THE DEFECT (code reading; never triggered, because no tap was ever written):
    pay_taps() read the whole taps-<date>.jsonl and then
    os.rename(path, path + '.paid'). tap_server.py appends to that exact path all
    day from another process, so:
      (a) a tap appended between the read and the rename was renamed away and
          never paid — the father's thumb, silently swallowed;
      (b) a second payout on the same day renamed a fresh file ONTO the existing
          .paid, and POSIX rename destroyed the earlier record.

WHAT THIS PROVES, with the REAL body/parent.py:
    two taps written across two payouts, plus one tap appended at the exact
    commit point. Old: a record is destroyed and the commit-point tap is never
    paid. Fixed: every tap is paid exactly once and every record survives.

    python3 proof_DW-11.py --mode old   -> FAIL
    python3 proof_DW-11.py              -> PASS
"""
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rev20260906 as rev  # noqa: E402

MODE = rev.mode_from_argv()
TREE, SWAPPED = rev.enter(MODE)

import parent              # noqa: E402

c = rev.Checks(__doc__.strip().splitlines()[0], MODE)
print("  tree=%s  swapped=%s" % (TREE, SWAPPED or "(none: this IS the tree)"))

SANDBOX = tempfile.mkdtemp(prefix="dw-rev-taps-")
INBOX = os.path.join(SANDBOX, "inbox")
OUTBOX = os.path.join(SANDBOX, "outbox")
os.makedirs(INBOX)
os.makedirs(OUTBOX)
TAPS = os.path.join(INBOX, "taps-2026-09-06.jsonl")     # tap_server's daily path

PAID = []


class _Brain:
    def pay_trace(self, trace, v, eta, chem):
        PAID.append(v)
        return 1, 0


class _Chem:
    ach = 1.0

    def mode(self, a):
        self.ach = a

    def valence(self, v):
        return None


def song(song_id):
    with open(os.path.join(OUTBOX, song_id + ".trace.json"), "w") as f:
        json.dump({"trace": {"1|7": {"7": 1.0}}}, f)


def append_tap(song_id, value):
    """Exactly what tap_server.write_tap() does: append to the daily file."""
    with open(TAPS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"song_id": song_id, "tap": value,
                            "ts": "2026-09-06T12:00:00Z"}) + "\n")


def records_on_disk():
    """Every tap record still readable anywhere in the inbox, under any name."""
    out = []
    for name in sorted(os.listdir(INBOX)):
        if ".jsonl" not in name or name.endswith(".cursor"):
            continue
        with open(os.path.join(INBOX, name), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line)["song_id"])
                    except (ValueError, KeyError):
                        pass
    return out


for sid in ("chai-a", "chai-b", "chai-c"):
    song(sid)

brain, chem = _Brain(), _Chem()
quiet = lambda *_a, **_k: None                                   # noqa: E731

# --- payout 1: one tap ------------------------------------------------------
append_tap("chai-a", 1.0)
parent.pay_taps(brain, chem, INBOX, OUTBOX, log=quiet)

# --- the father taps again later the same day -------------------------------
append_tap("chai-b", 2.0)
parent.pay_taps(brain, chem, INBOX, OUTBOX, log=quiet)

on_disk = records_on_disk()
print("  after two payouts: paid=%s   records still on disk=%s"
      % (PAID, sorted(on_disk)))
c.check("both taps were paid", PAID.count(1.0) == 1 and PAID.count(2.0) == 1,
        "paid=%s" % PAID)
c.check("no tap record was destroyed",
        sorted(on_disk) == ["chai-a", "chai-b"], "on disk=%s" % sorted(on_disk))

# --- a tap that lands at the exact commit point -----------------------------
real_rename, real_replace = os.rename, os.replace
fired = {"n": 0}


def _at_commit(fn):
    def wrapper(src, dst):
        if fired["n"] == 0 and str(src).endswith(".jsonl"):
            fired["n"] = 1
            append_tap("chai-c", 1.0)      # the father taps DURING the payout
        elif fired["n"] == 0 and str(dst).endswith(".cursor"):
            fired["n"] = 1
            append_tap("chai-c", 1.0)
        return fn(src, dst)
    return wrapper


os.rename = _at_commit(real_rename)
os.replace = _at_commit(real_replace)
try:
    append_tap("chai-a", 1.0)              # something to pay, so a commit happens
    parent.pay_taps(brain, chem, INBOX, OUTBOX, log=quiet)
finally:
    os.rename, os.replace = real_rename, real_replace

before = len(PAID)
parent.pay_taps(brain, chem, INBOX, OUTBOX, log=quiet)          # the next beat
print("  commit-point tap fired=%d; paid on the next beat: %d"
      % (fired["n"], len(PAID) - before))
c.check("a tap written at the commit point is not swallowed",
        fired["n"] == 1 and len(PAID) - before >= 1,
        "%d payments on the following beat" % (len(PAID) - before))
c.check("that tap survives on disk too", "chai-c" in records_on_disk())

# --- and nothing is ever paid twice -----------------------------------------
before = len(PAID)
parent.pay_taps(brain, chem, INBOX, OUTBOX, log=quiet)
parent.pay_taps(brain, chem, INBOX, OUTBOX, log=quiet)
c.check("an already-paid tap is never paid again", len(PAID) == before,
        "%d extra payments on two idle beats" % (len(PAID) - before))

c.done()
