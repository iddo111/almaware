# -*- coding: utf-8 -*-
"""proof_K6-13 -- a usefulness check whose only failing value is zero.

    python proof_K6-13.py <path-to-keshev_delivery_watchdog.py>

FAILS against keshev_delivery_watchdog.py.bak-rev-20260906, PASSES against the
fixed file. Pure stdlib; judge() is a pure function, so nothing is read, written
or restarted -- and this proof never touches the live microphone.

Measured at 12:22:47 today, from the watchdog's own state file: verdict OK,
delivery_rate 0.1316, alarms [], typed 1,249 / empty 8,240 / skip 8,317. It
called that healthy because NOTHING_DELIVERED fires only at typed == 0. One
step further and it is a liveness check -- the shape 23 of the 32 watchdogs
audited on 2026-09-05 already had.

The fix is NOT a hand-picked target rate. 13% may well be his normal (the
empties were measured to be room, breath and laughter). A number invented here
would false-alarm forever and be muted within a week. So:

  A  a stable low rate against its OWN history is OK, not an alarm
  B  the same rate collapsing to a third of that history is FAIL
  C  a rate three-quarters of the median is a WARNING, not a FAIL
  D  with no baseline, no alarm -- never alarm on evidence you do not have
  E  the alarm cannot fire on a tiny window (a quiet 20 minutes is not a fault)
  F  the history file is pruned, so the state it needs cannot grow forever
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import time
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
FAILS: list[str] = []


def check(name: str, ok: bool, detail="") -> None:
    print("  %-62s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


LIVE = {"paused": False, "paused_for_min": 0.0, "heartbeat_age_min": 0.2,
        "log_age_min": 0.3}
# the real 12:22 reading
TODAY = {"typed": 1249, "guarded": 117, "blocked": 0, "empty": 8240,
         "fail": 0, "skip": 8317}
STEADY = {"median_rate": 0.13, "n": 300, "span_h": 22.0}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="k6proof13-"))
    shutil.copy2(TARGET, tmp / "wd.py")
    spec = importlib.util.spec_from_file_location("k6_wd_under_test", tmp / "wd.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["k6_wd_under_test"] = m
    spec.loader.exec_module(m)
    print("proof_K6-13 against %s" % TARGET)

    # can judge() even be told what this mic normally delivers?
    try:
        m.judge(TODAY, LIVE, STEADY)
        derivable = True
        why = ""
    except TypeError as e:
        derivable = False
        why = "judge() takes no baseline: %s" % e
    check("the verdict can be derived from the run's own history", derivable, why)
    if not derivable:
        print("\nproof_K6-13: FAIL (%d) -> %s" % (len(FAILS), FAILS))
        return 1

    # ---- A: today's real reading, against today's real history -------------
    v, a = m.judge(TODAY, LIVE, STEADY)
    check("A 13% delivered on a 13% baseline is OK, not an alarm",
          v == "OK" and not a, "%s %s" % (v, a))

    # ---- B: the collapse the old file could not see ------------------------
    collapsed = {"typed": 30, "guarded": 20, "blocked": 0, "empty": 900,
                 "fail": 0, "skip": 40}
    w = []
    v, a = m.judge(collapsed, LIVE, STEADY, w)
    check("B 3% delivered on a 13% baseline is FAIL",
          v == "FAIL" and any("DELIVERY_COLLAPSED" in x for x in a),
          "%s %s" % (v, a))

    # and the old-shaped total failure must still fire, on its own alarm
    dead = {"typed": 0, "guarded": 30, "blocked": 2, "empty": 11, "fail": 0,
            "skip": 4}
    v, a = m.judge(dead, LIVE, STEADY)
    check("B zero delivered still fires NOTHING_DELIVERED",
          v == "FAIL" and any("NOTHING_DELIVERED" in x for x in a), a)

    # ---- C: halved is a warning, not a failure -----------------------------
    halved = {"typed": 85, "guarded": 20, "blocked": 0, "empty": 800,
              "fail": 0, "skip": 40}
    w = []
    v, a = m.judge(halved, LIVE, STEADY, w)
    check("C 9% on a 13% baseline warns without crying FAIL",
          v == "OK" and any("DELIVERY_DOWN" in x for x in w), "%s warn=%s" % (v, w))

    # ---- D: no baseline, no alarm ------------------------------------------
    v, a = m.judge(collapsed, LIVE, None)
    check("D a collapse with NO baseline raises nothing", v == "OK", a)

    # ---- E: a tiny window cannot trip it -----------------------------------
    tiny = {"typed": 0, "guarded": 1, "blocked": 0, "empty": 3, "fail": 0,
            "skip": 2}
    v, a = m.judge(tiny, LIVE, STEADY)
    check("E a 4-segment window raises nothing (a quiet 20 min is not a fault)",
          v == "OK", a)

    # ---- baseline() itself refuses thin evidence ---------------------------
    now = time.time()
    thin = [(now - i * 60, 5, 50) for i in range(10)]
    check("baseline() refuses fewer than %d samples"
          % m.BASELINE_MIN_SAMPLES, m.baseline(thin) is None, m.baseline(thin))
    burst = [(now - i, 5, 50) for i in range(200)]          # 200 s, not 2 h
    check("baseline() refuses a burst that spans no real time",
          m.baseline(burst) is None, m.baseline(burst))
    good = [(now - i * 300, 13, 100) for i in range(200)]   # ~16 h of cycles
    b = m.baseline(good)
    check("baseline() gives the median this mic really achieved",
          b is not None and abs(b["median_rate"] - 0.13) < 1e-9, b)

    # ---- F: the history it keeps is pruned ---------------------------------
    m.HISTORY = str(tmp / "hist.json")
    old_rows = [(now - 40 * 3600, 1, 100)] * 50          # older than the window
    kept = m.save_history(old_rows + good)
    reloaded = m.load_history()
    check("F the history drops rows older than the window",
          all(r[0] >= now - m.HISTORY_HOURS * 3600 for r in reloaded)
          and len(reloaded) == len(good),
          "kept=%d reloaded=%d of %d" % (len(kept), len(reloaded),
                                         len(old_rows) + len(good)))

    print("\nproof_K6-13: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
