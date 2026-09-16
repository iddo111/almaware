#!/usr/bin/env bash
# Answers "is my ant farm alive and is it learning?" without needing to know
# that the unit is a --user unit. `systemctl is-active voice-ant-farm` (no
# --user) reports "could not be found", which reads as "dead" but is not.
set -u
cd "$HOME/voice-ant-farm" || exit 1

echo "unit:    $(systemctl --user is-active voice-ant-farm.service) / $(systemctl --user is-enabled voice-ant-farm.service) / linger=$(loginctl show-user "$(whoami)" -p Linger --value)"
systemctl --user show voice-ant-farm.service -p Environment --value | sed 's/^/env:     /'
echo "last:    $(journalctl --user -u voice-ant-farm.service -o cat -n 40 --no-pager 2>/dev/null | grep -E '^\[' | tail -1)"

python3 - <<'PY'
import json, glob, os, time
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
    print("   %-6s heldout_error_after=%r  seed=%-7s promoted %.1fh ago"
          % (ant, d["heldout_error_after"], d["seed"], age))

try:
    cycles = [json.loads(x) for x in open("logs/cycles.jsonl") if x.strip()]
except FileNotFoundError:
    cycles = []
print("cycles:  %d logged" % len(cycles))
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
        mark = "  <-- FLAT" if flat >= 8 else ""
        print("   %-6s unchanged for %d of last %d cycles%s" % (ant, flat, len(vals), mark))
PY
