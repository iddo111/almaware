# -*- coding: utf-8 -*-
"""proof_DW-07.py — the journal must record events, not every heartbeat forever.

THE DEFECT (measured on the real file):
    state/metrics.jsonl = 237,755,561 bytes / 1,678,809 lines, of which
    1,666,716 (99.3%) were idle beats that said nothing new — ~34 MB a day, no
    rotation, no pruning, growing for the life of the process.

WHAT THIS PROVES, through the REAL Life._metrics_line:
    1,000 idle beats plus 5 events, on a fake clock. Old: 1,005 lines. Fixed: the
    5 events plus a heartbeat a minute, the same schema, and a day boundary moves
    the closed day to metrics-<date>.jsonl instead of growing forever.

    python3 proof_DW-07.py --mode old   -> FAIL
    python3 proof_DW-07.py              -> PASS
"""
import datetime
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rev20260906 as rev  # noqa: E402

MODE = rev.mode_from_argv()
TREE, SWAPPED = rev.enter(MODE)

sys.modules.setdefault("psy_synth", types.ModuleType("psy_synth"))
import genome              # noqa: E402
import darwish_life as dl  # noqa: E402

BEATS = 1000
DT = 0.36                  # measured beat period: 2.75 beats/s

c = rev.Checks(__doc__.strip().splitlines()[0], MODE)
print("  tree=%s  swapped=%s" % (TREE, SWAPPED or "(none: this IS the tree)"))

SANDBOX = tempfile.mkdtemp(prefix="dw-rev-metrics-")
dl.STATE_DIR = SANDBOX
dl.METRICS_FILE = os.path.join(SANDBOX, "metrics.jsonl")


class _Clock(types.ModuleType):
    now = 1_757_000_000.0

    @classmethod
    def time(cls):
        return cls.now

    @staticmethod
    def sleep(_s):
        return None


clock = _Clock("time")
dl.time = clock

life = dl.Life.__new__(dl.Life)
life.ablate = []
life.beat = 0
life.tokens_eaten = 0
life.brain = types.SimpleNamespace(mass=1_954_803)
life.drives = types.SimpleNamespace(E=0.42)
life.chem = types.SimpleNamespace(da=0.08, sht=0.5, ach=1.0)
life._last_metrics_ts = 0.0
life._metrics_day = datetime.date.fromtimestamp(clock.now).isoformat()


def lines():
    if not os.path.exists(dl.METRICS_FILE):
        return []
    with open(dl.METRICS_FILE, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


for i in range(BEATS):                       # 1,000 idle beats, 360 simulated s
    life.beat += 1
    clock.now += DT
    life._metrics_line({})                   # one_beat passes an empty extra
idle = lines()

for i in range(5):                           # 5 real events
    life.beat += 1
    clock.now += DT
    life._metrics_line({"ate": "shard-%02d.json" % i, "tokens": 58265,
                        "nutrition": 0.946})
allx = lines()
events = [x for x in allx if "ate" in x]
heartbeats = [x for x in allx if x.get("heartbeat")]

print("  %d idle beats -> %d lines; +5 events -> %d lines total (%d heartbeats)"
      % (BEATS, len(idle), len(allx), len(heartbeats)))

c.check("idle beats are not journalled one by one", len(idle) <= 20,
        "%d lines for %d idle beats" % (len(idle), BEATS))
c.check("every event is journalled", len(events) == 5, "%d event lines" % len(events))
c.check("silence is still visible (a heartbeat exists)", len(idle) >= 1,
        "%d heartbeat lines in %.0f simulated seconds" % (len(idle), BEATS * DT))
c.check("the schema is unchanged",
        bool(allx) and all(k in allx[-1] for k in
                           ("ts", "beat", "mass", "E", "da", "sht", "ach",
                            "tokens_eaten")),
        str(sorted(allx[-1]))[:140] if allx else "no lines")

# --- daily rotation ---------------------------------------------------------
c.check("Life._roll_metrics_day exists", hasattr(dl.Life, "_roll_metrics_day"))
if hasattr(dl.Life, "_roll_metrics_day"):
    yesterday = (datetime.date.fromtimestamp(clock.now)
                 - datetime.timedelta(days=1)).isoformat()
    life._metrics_day = yesterday
    before_n = len(lines())
    life.beat += 1
    clock.now += DT
    life._metrics_line({"ate": "after-midnight.json"})
    archived = os.path.join(SANDBOX, "metrics-%s.jsonl" % yesterday)
    c.check("the closed day is moved aside, not deleted",
            os.path.exists(archived)
            and len(open(archived, encoding="utf-8").readlines()) == before_n,
            os.path.basename(archived))
    c.check("the live file starts fresh after rotation", len(lines()) == 1,
            "%d lines" % len(lines()))

c.done()
