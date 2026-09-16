"""printer-autoresume.py -- Iddo's order 2026-08-22 05:35: "take command, continue
the print, do not stop it", then he went to sleep.

The print (cone_body_PLA, 41 h total) paused at 18.5% because the toolhead runout
sensor reads filament_detected=false. That is a physical fault: no command can fix
it, someone has to feed filament. So this does not try.

What it does: watch. The moment filament is physically present again -- which can
only happen because a human put it there -- it resumes the print, so the machine
does not sit idle for hours waiting to be noticed.

Guards, because an unattended machine deserves them:
  * filament must read present CONTINUOUSLY for HOLD_S before anything is sent.
    A flickering sensor resuming into an empty hot end would print air for hours.
  * it resumes ONCE, then keeps watching only to report.
  * it never cancels, never changes temperature, never moves an axis.
  * everything, including every state change, is appended to the log.
"""
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

PRINTER = "<lan-ip>"
POLL_S = 20
HOLD_S = 60          # filament must be present this long before resuming
MAX_HOURS = 10
LOG = Path(r"D:\CLAUDE\tools\printer-autoresume.log")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def say(msg):
    line = f"{now()}  {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def get(path):
    url = f"http://{PRINTER}:7125{path}"
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r)


def post(path):
    url = f"http://{PRINTER}:7125{path}"
    req = urllib.request.Request(url, method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def state():
    objs = urllib.parse.quote("filament_switch_sensor filament_sensor", safe="")
    d = get(f"/printer/objects/query?print_stats&virtual_sdcard&{objs}&extruder&heater_bed")["result"]["status"]
    sensor = d.get("filament_switch_sensor filament_sensor", {})
    return {
        "state": d["print_stats"].get("state"),
        "progress": (d["virtual_sdcard"].get("progress") or 0) * 100,
        "pos": d["virtual_sdcard"].get("file_position"),
        "filament": bool(sensor.get("filament_detected")),
        "nozzle": d["extruder"]["temperature"],
        "nozzle_t": d["extruder"]["target"],
        "bed": d["heater_bed"]["temperature"],
    }


say("=" * 78)
say("autoresume armed. printer=%s poll=%ds hold=%ds max=%dh" % (PRINTER, POLL_S, HOLD_S, MAX_HOURS))
try:
    s = state()
    say("start state: %s  %.2f%%  filament=%s  nozzle %.0f/%.0f  bed %.0f"
        % (s["state"], s["progress"], s["filament"], s["nozzle"], s["nozzle_t"], s["bed"]))
except Exception as e:
    say("could not reach printer at start: %r" % (e,))

deadline = time.time() + MAX_HOURS * 3600
present_since = None
resumed = False
last_report = 0.0
last_state = None
fails = 0

while time.time() < deadline:
    try:
        s = state()
        fails = 0
    except Exception as e:
        fails += 1
        if fails in (1, 5, 20):
            say("printer unreachable (%d in a row): %r" % (fails, e))
        time.sleep(POLL_S)
        continue

    key = (s["state"], s["filament"], round(s["progress"], 1))
    if key != last_state:
        say("state=%s filament=%s progress=%.2f%% pos=%s nozzle=%.0f/%.0f bed=%.0f"
            % (s["state"], s["filament"], s["progress"], s["pos"], s["nozzle"], s["nozzle_t"], s["bed"]))
        last_state = key

    if s["state"] == "printing":
        if present_since is not None or not resumed:
            say("PRINTING. nothing to do.")
        present_since = None
        if time.time() - last_report > 1800:
            say("still printing, %.2f%%" % s["progress"])
            last_report = time.time()
        time.sleep(POLL_S)
        continue

    if s["state"] in ("complete", "cancelled", "error"):
        say("print ended with state=%s. stopping watch." % s["state"])
        break

    if s["state"] == "paused" and not resumed:
        if s["filament"]:
            if present_since is None:
                present_since = time.time()
                say("filament DETECTED. holding %ds to be sure it is a real load, not a flicker." % HOLD_S)
            elif time.time() - present_since >= HOLD_S:
                say("filament stable for %ds -> sending RESUME" % HOLD_S)
                try:
                    post("/printer/print/resume")
                except Exception as e:
                    say("resume request error: %r" % (e,))
                time.sleep(8)
                try:
                    s2 = state()
                    say("after resume: state=%s progress=%.2f%% pos=%s" % (s2["state"], s2["progress"], s2["pos"]))
                    if s2["state"] == "printing":
                        say("RESUMED SUCCESSFULLY.")
                        resumed = True
                    else:
                        say("resume did not take. will retry on the next stable window.")
                        present_since = None
                except Exception as e:
                    say("could not confirm resume: %r" % (e,))
        else:
            if present_since is not None:
                say("filament gone again before the hold elapsed. reset.")
            present_since = None

    time.sleep(POLL_S)

say("watch finished (deadline or print ended).")
