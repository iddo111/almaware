#!/bin/bash
# nanny.sh — checks the REAL outputs (health:ok != working), every 10 minutes.
#
# REVISION 2026-09-06 (ERAN-02, Iddo's code-revision order 11:47).
# ---------------------------------------------------------------------------
# This script used to answer EVERY metrics problem with
#     systemctl --user restart eranb-life.service
# — the one remedy that is poison for a starving or slow-booting organism, and
# a remedy applied to a state it could not name (stale = crashed? booting?
# hung? starving? being examined?). Its 900 s threshold was hand-picked and
# unrelated to the beat rate (one beat is ~4.6 ms, so 900 s is ~194,000 missed
# beats), and in 16 days it never once refused anything meaningful: 173 SICK
# lines, all serve-silent, 0 life restarts. A gate that never refused is not
# demonstrated. Two laws come out of this week:
#
#   1. A WATCHER MAY ONLY ACT ON A STATE IT CAN NAME.
#   2. A FAMINE CHECK MUST NEVER RESTART A LIVING THING.
#
# So, from here:
#   * eranb-life is NEVER restarted here. systemd (Restart=always) already
#     restarts a process that is actually dead; a process that is alive but
#     quiet must be LOOKED AT, not killed. Problems are named into
#     state/ALARM-* and state/nanny.log.
#   * staleness is derived from the metrics file's OWN inter-line interval
#     (200x the median gap, floor 120 s) instead of a constant, and is
#     suspended while the unit is younger than its recorded boot time — the
#     old threshold would have killed every boot once the 55 GB metrics scan
#     passed 15 minutes (ERAN-01).
#   * FAMINE is checked directly: metrics lines that carry no "surprise" key
#     mean he is being served an empty menu. That is the 2026-09-06 near-death
#     and this check would have caught it. It is an ALARM, never a restart.
#   * the observation window on :8820 is stateless and IS still restarted.
set -u
HOME_DIR="${HOME}"
BASE="${HOME_DIR}/eran-brain"
STATE="${BASE}/state"
METRICS="${STATE}/metrics.jsonl"
BRAIN="${STATE}/brain.json.gz"
LOG="${STATE}/nanny.log"
STAMP="$(date -Is)"
PROBLEMS=""
ACTIONS=""

# --- 1. the life loop: is it FED, and is it SPEAKING? -----------------------
# ActiveEnterTimestampMonotonic is microseconds since boot; /proc/uptime is
# seconds since boot. A unit younger than its own boot budget is not judged.
UNIT_MONO="$(systemctl --user show eranb-life.service \
             -p ActiveEnterTimestampMonotonic --value 2>/dev/null || echo 0)"
UPTIME_S="$(cut -d' ' -f1 /proc/uptime 2>/dev/null || echo 0)"

VERDICT="$(METRICS="${METRICS}" STATE="${STATE}" \
           UNIT_MONO="${UNIT_MONO}" UPTIME_S="${UPTIME_S}" \
           nice -n 19 python3 - <<'PY' 2>/dev/null
import datetime
import json
import os
import statistics
import time

path = os.environ["METRICS"]
state = os.environ["STATE"]
BLOCK = 512 * 1024
TAIL = 400
FED_MIN = 0.90          # below this fraction of fed beats -> FAMINE
STALE_FACTOR = 200.0    # 200x the file's OWN median gap
STALE_FLOOR = 120.0     # ...but never twitchier than two minutes
BOOT_FLOOR = 300.0      # a boot is never judged stale inside this


def say(kind, detail):
    print("%s %s" % (kind, detail))
    raise SystemExit(0)


if not os.path.exists(path):
    say("missing", "no metrics file at all")

# bounded tail read: constant cost however long he lives (ERAN-01's lesson)
with open(path, "rb") as fb:
    size = fb.seek(0, os.SEEK_END)
    start = max(0, size - BLOCK)
    fb.seek(start)
    raw = fb.read()
if start:
    nl = raw.find(b"\n")
    raw = raw[nl + 1:] if nl >= 0 else b""
rows = []
for line in raw.decode("utf-8", "replace").splitlines()[-TAIL:]:
    line = line.strip()
    if not line:
        continue
    try:
        rows.append(json.loads(line))
    except ValueError:
        pass
if not rows:
    say("stale", "no parseable metrics line in the last %d bytes" % BLOCK)

age = time.time() - os.path.getmtime(path)

# how long has the unit been up? (never judge a boot)
try:
    unit_age = float(os.environ["UPTIME_S"]) - float(os.environ["UNIT_MONO"]) / 1e6
except (KeyError, ValueError, TypeError):
    unit_age = 1e9
boot_budget = BOOT_FLOOR
try:
    with open(os.path.join(state, "boot.json"), "r", encoding="utf-8") as f:
        boot_budget = max(BOOT_FLOOR, 3.0 * float(json.load(f).get("boot_seconds", 0)))
except (OSError, ValueError, TypeError, KeyError):
    pass

# (a) FAMINE — a beat that ate nothing writes no "surprise" key. This is the
#     2026-09-06 signature (an empty menu that raises nothing) and the one
#     thing the old nanny never looked at.
fed = sum(1 for r in rows if "surprise" in r)
frac = fed / float(len(rows))
if frac < FED_MIN:
    say("famine", "only %d of the last %d metrics lines carry 'surprise' "
                  "(%.1f%%) - he is being served an empty menu. DO NOT RESTART."
                  % (fed, len(rows), 100.0 * frac))

# (b) staleness, derived from his own cadence
ts = []
for r in rows:
    try:
        ts.append(datetime.datetime.fromisoformat(r["ts"]).timestamp())
    except (KeyError, ValueError, TypeError):
        pass
gaps = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
median = statistics.median(gaps) if gaps else 1.0
budget = max(STALE_FLOOR, STALE_FACTOR * max(median, 0.001))
if age > budget:
    if unit_age <= boot_budget:
        say("ok", "metrics %.0fs old but the unit is only %.0fs up "
                  "(boot budget %.0fs) - a boot is not a stall" %
                  (age, unit_age, boot_budget))
    say("stale", "metrics %.0fs old; budget %.0fs = %gx median gap %.3fs. "
                 "NAMED, NOT RESTARTED - look at it." %
        (age, budget, STALE_FACTOR, median))

say("ok", "%d lines, %.1f%% fed, metrics %.0fs old (budget %.0fs, median gap "
          "%.3fs), unit up %.0fs" %
    (len(rows), 100.0 * frac, age, budget, median, unit_age))
PY
)"

rm -f "${STATE}/ALARM-famine" "${STATE}/ALARM-stalled" 2>/dev/null
case "${VERDICT%% *}" in
    famine)
        PROBLEMS="${PROBLEMS} FAMINE"
        echo "${STAMP} ${VERDICT}" > "${STATE}/ALARM-famine"
        ACTIONS="${ACTIONS} wrote-ALARM-famine"
        ;;
    stale|missing)
        PROBLEMS="${PROBLEMS} metrics-${VERDICT%% *}"
        echo "${STAMP} ${VERDICT}" > "${STATE}/ALARM-stalled"
        ACTIONS="${ACTIONS} wrote-ALARM-stalled"
        ;;
    ok)
        ;;
    *)
        # An empty or unrecognised verdict means the CHECK failed, not that
        # everything is fine. A checker that fails open is the shape we are
        # hunting; it does not get to be silent either.
        PROBLEMS="${PROBLEMS} nanny-check-failed"
        echo "${STAMP} check produced no verdict: '${VERDICT}'" \
            > "${STATE}/ALARM-stalled"
        ACTIONS="${ACTIONS} wrote-ALARM-stalled"
        ;;
esac

# --- 2. brain file integrity (named, never restarted) -----------------------
if [ -f "${BRAIN}" ]; then
    if ! nice -n 19 python3 -c "import gzip,json; json.load(gzip.open('${BRAIN}','rt'))" 2>/dev/null; then
        PROBLEMS="${PROBLEMS} brain-corrupt"
    fi
fi

# --- 3. the observation window (stateless: this one MAY be restarted) -------
if ! curl -sf -m 5 "http://127.0.0.1:8820/" >/dev/null 2>&1; then
    PROBLEMS="${PROBLEMS} serve-silent"
    systemctl --user restart eranb-serve.service
    ACTIONS="${ACTIONS} restarted-eranb-serve"
fi

# eranb-life is NEVER restarted from here. See the header.
if [ -n "${PROBLEMS}" ]; then
    echo "${STAMP} SICK:${PROBLEMS} ->${ACTIONS:- named-only} | ${VERDICT}" >> "${LOG}"
else
    echo "${STAMP} ok (real outputs checked, not liveness) | ${VERDICT}" >> "${LOG}"
fi
exit 0
