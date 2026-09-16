# -*- coding: utf-8 -*-
"""
INJECTION HARNESS -- a watchdog not proven against a real injected failure is
decoration.

Builds decoy organisms with a KNOWN disease and points the real, unmodified
sibling_watch.py at them.  Every decoy lives under ~/sibling-watch/inject/ and
nothing here ever touches ~/sibling or ~/sibling-ear.

Each decoy carries exactly ONE disease, so an alarm proves the detector that
should have fired -- and the silence of the other four proves it is not just
shouting at everything.
"""
import datetime as dt
import io
import json
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
LAB = os.path.join(HOME, "sibling-watch", "inject")
WATCH = os.path.join(LAB, "watch")


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def organ(name, root, unit="sibling-watch-decoy.service", period=60,
          code=None, floors=None):
    return {
        "name": name, "what": "DECOY for proving the watchdog", "root": root,
        "code": code or os.path.join(root, "decoy.py"), "unit": unit,
        "journal": "journal.jsonl", "round_kind": ["kind", "round"],
        "period_s": period, "objective": "exam",
        "floors": (floors if floors is not None else {"chance": 0.0833}),
        "born_field": "born",
        "series": {"exam": {"must_move": True}, "ruler": {"must_move": True},
                   "gate": {"must_move": True},
                   "born": {"must_move": False, "why": "birth constant"}},
    }


def build(name, rounds_spec):
    root = os.path.join(LAB, name)
    os.makedirs(root, exist_ok=True)
    io.open(os.path.join(root, "decoy.py"), "w", encoding="utf-8").write("# decoy\n")
    base = dt.datetime.now() - dt.timedelta(seconds=20 * len(rounds_spec))
    with io.open(os.path.join(root, "journal.jsonl"), "w", encoding="utf-8") as f:
        for i, r in enumerate(rounds_spec):
            rec = {"t": iso(base + dt.timedelta(seconds=20 * i)), "kind": "round"}
            rec.update(r)
            f.write(json.dumps(rec) + "\n")
    return root


def run(cfg, extra=()):
    path = os.path.join(LAB, "cfg.json")
    io.open(path, "w", encoding="utf-8").write(json.dumps(cfg))
    cmd = [sys.executable, os.path.join(HOME, "sibling_watch.py"), "--once",
           "--config", path, "--watch-root", WATCH] + list(extra)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def case_frozen():
    """The objective stops, and so does everything inside it.  The nezer's
    shape.  Sub-scores MOVE early so the DEAD detector must stay silent --
    that silence is half the proof."""
    rs = []
    for i in range(8):
        rs.append({"exam": 0.30 + 0.02 * i, "ruler": 0.4 + 0.01 * i,
                   "gate": 0.1 * i, "born": 0.2})
    for _ in range(8):
        rs.append({"exam": 0.44, "ruler": 0.47, "gate": 0.7, "born": 0.2})
    return build("frozen", rs)


def case_dead():
    """One sub-score has never moved once, while the objective climbs happily.
    This is the LayerNorm(1)/TN=4 scar, and it is invisible from the headline
    number -- exam is going UP the whole time."""
    rs = []
    for i in range(12):
        rs.append({"exam": 0.30 + 0.02 * i, "ruler": 0.4 + 0.03 * i,
                   "gate": 4.0, "born": 0.2})
    return build("dead", rs)


def case_diverge():
    """The objective falls under its own honest floor -- worse than not trying."""
    rs = []
    for i in range(8):
        rs.append({"exam": 0.50 - 0.01 * i, "ruler": 0.4 + 0.01 * i,
                   "gate": 0.1 * i, "born": 0.2})
    for i in range(5):
        rs.append({"exam": 0.06 - 0.001 * i, "ruler": 0.5 + 0.01 * i,
                   "gate": 0.9 + 0.01 * i, "born": 0.2})
    return build("diverge", rs)


def case_healthy():
    """The control.  Everything moving, nothing stuck, nothing below a floor.
    If this one alarms, every alarm above is worthless."""
    rs = []
    for i in range(12):
        rs.append({"exam": 0.30 + 0.02 * i, "ruler": 0.4 + 0.02 * i,
                   "gate": 0.1 * i, "born": 0.2})
    return build("healthy", rs)


if __name__ == "__main__":
    os.makedirs(WATCH, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    todo = {"frozen": case_frozen, "dead": case_dead, "diverge": case_diverge,
            "healthy": case_healthy}
    names = [what] if what in todo else list(todo)
    for n in names:
        root = todo[n]()
        # the decoy has no systemd unit and no live process; blank the unit so
        # STALL does not drown the detector under test.
        o = organ(n, root, unit="nonexistent-decoy.service", period=100000)
        rc, out = run([o])
        print("=" * 72)
        print("INJECTED: %s   (decoy at %s)" % (n.upper(), root))
        print("=" * 72)
        print(out)
        print("exit=%d" % rc)
