#!/usr/bin/env bash
# Answers "is my ant farm alive and is it learning?" without needing to know
# that the unit is a --user unit. `systemctl is-active voice-ant-farm` (no
# --user) reports "could not be found", which reads as "dead" but is not.
set -u
cd "$HOME/voice-ant-farm" || exit 1

echo "unit:    $(systemctl --user is-active voice-ant-farm.service) / $(systemctl --user is-enabled voice-ant-farm.service) / linger=$(loginctl show-user "$(whoami)" -p Linger --value)"
systemctl --user show voice-ant-farm.service -p Environment --value | sed 's/^/env:     /'
echo "last:    $(journalctl --user -u voice-ant-farm.service -o cat -n 40 --no-pager 2>/dev/null | grep -E '^\[' | tail -1)"
# VAF-10: the loop's own alarm marker, so a week of failed cycles is visible here.
if [ -f state/UNHEALTHY ]; then
  echo "UNHEALTHY: $(cat state/UNHEALTHY)"
else
  echo "health:  no UNHEALTHY marker"
fi

python3 - <<'PY'
import json, glob, os, time
from datetime import datetime, timezone
print("state:")
try:
    r = json.load(open("state/round.json"))
    print("   round %s  lane %s" % (r["round"], r["lane"]))
except Exception as exc:
    print("   round.json unreadable: %s" % exc)
for p in sorted(glob.glob("state/ant-*/current.json")):
    ant = os.path.basename(os.path.dirname(p))
    d = json.load(open(p))
    age = (time.time() - os.path.getmtime(p)) / 3600.0
    synthetic = d.get("exemplars_from_synthetic_audio")
    mark = "" if not synthetic else "  <-- %d/%s SYNTHETIC EXEMPLARS" % (synthetic, d.get("units"))
    print("   %-6s heldout_error_after=%r  seed=%-7s promoted %.1fh ago%s"
          % (ant, d["heldout_error_after"], d["seed"], age, mark))

try:
    cycles = [json.loads(x) for x in open("logs/cycles.jsonl") if x.strip()]
except FileNotFoundError:
    cycles = []
events = [c for c in cycles if "event" in c]
cycles = [c for c in cycles if "ants" in c]
print("cycles:  %d logged, %d loop events" % (len(cycles), len(events)))
for event in events[-3:]:
    print("   event %s" % json.dumps(event, sort_keys=True)[:160])

# VAF-02: the flat threshold is DERIVED from this loop's own measured cadence -
# "unchanged for a whole day of cycles" - instead of the hand-picked flat>=8.
def stamp(cycle):
    try:
        return datetime.strptime(cycle["round_id"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None

stamps = [s for s in (stamp(c) for c in cycles) if s]
per_day = None
if len(stamps) >= 2:
    span_days = (stamps[-1] - stamps[0]).total_seconds() / 86400.0
    if span_days > 0:
        per_day = max(2, int(round(len(stamps) / span_days)))
print("cadence: %s cycles/day measured" % (per_day if per_day else "unknown"))
if cycles:
    series = {}
    for c in cycles:
        for a in c.get("ants", []):
            series.setdefault(a["ant"], []).append(a["heldout_error_after_fire"])
    for ant, vals in sorted(series.items()):
        flat = 0
        for v in reversed(vals):
            if v == vals[-1]:
                flat += 1
            else:
                break
        threshold = per_day or 8
        mark = "  <-- FLAT (>= %d = a full day)" % threshold if flat >= threshold else ""
        print("   %-6s unchanged for %d of last %d cycles%s" % (ant, flat, len(vals), mark))

# VAF-02: the search-exhaustion verdict the cycle itself writes, so a reader
# sees the same number the loop acts on.
try:
    status = json.load(open("state/search-status.json"))
except (FileNotFoundError, ValueError):
    status = None
if status:
    print("search:  all_exhausted=%s  (written %s)"
          % (status.get("all_exhausted"), status.get("written_at")))
    for item in status.get("ants", []):
        print("   %-6s exhausted=%-5s restarts_since_promotion=%-6s best=%s incumbent=%s window=%s/day"
              % (item["ant"], item["search_exhausted"], item["restarts_since_promotion"],
                 item["best_in_window"], item["incumbent_error"],
                 item["restarts_per_day_measured"]))
else:
    print("search:  no state/search-status.json yet (written by the next cycle)")

try:
    acceptance = json.load(open("state/acceptance-current.json"))
    age = (time.time() - os.path.getmtime("state/acceptance-current.json")) / 3600.0
    print("gate:    overall=%s  %.1fh old  layers=%s"
          % (acceptance.get("overall"), age,
             json.dumps({k: v["status"] for k, v in acceptance.get("layers", {}).items()})))
except (FileNotFoundError, ValueError, KeyError):
    print("gate:    no acceptance report")
PY
