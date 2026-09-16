# -*- coding: utf-8 -*-
"""
THE RELAY -- carries the sibling's alarms from eran3 to where Iddo actually
looks.

The watchdog lives on eran3 and cannot reach RAMCHAT (RAMCHAT is shared memory
on the PC).  So this runs on the PC, every few minutes, and does three things:

  1 pulls NEW lines from eran3:~/sibling-watch/alarms.jsonl and posts each one
    to RAMCHAT, so every agent on this machine sees it;
  2 writes SIBLING-STATUS.txt next to this file -- plain text, first line is
    the verdict, for the morning report to read without ssh;
  3 WATCHES THE WATCHDOG.  If eran3 cannot be reached, or status.json has not
    been refreshed in STALE_MIN minutes, that is itself an alarm and it is
    posted.  An instrument nobody checks is an instrument that has already
    failed quietly.

It never touches the sibling and never touches the watchdog.  Reads only.

    python watch_relay.py           one pass
    python watch_relay.py --dry     one pass, print instead of posting
"""
import argparse
import io
import json
import os
import subprocess
import sys
import datetime as dt
# 2026-09-08: windowless (pythonw) parent + console child = Windows Terminal pops a window and
# steals Iddo's focus (measured: 41 ssh.exe windows before noon). Every console child gets no window.
_NOWIN = 0x08000000 if os.name == "nt" else 0


HERE = os.path.dirname(os.path.abspath(__file__))
RAMCHAT = r"D:\CLAUDE\RAMCHAT"
HOST = "eran3"
REMOTE = "~/sibling-watch"
CURSOR = os.path.join(HERE, ".relay-cursor.json")
STATUS_OUT = os.path.join(HERE, "SIBLING-STATUS.txt")
WHO = "sibling-watchdog"
STALE_MIN = 15


def ssh(cmd, timeout=60):
    p = subprocess.run(["ssh", HOST, cmd], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout,
                       creationflags=_NOWIN)
    return p.returncode, p.stdout.decode("utf-8", "replace"), \
        p.stderr.decode("utf-8", "replace")


def ramchat(msg, dry=False):
    if dry:
        print("[would post] %s" % msg[:400])
        return 0
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "ramlink.py", "post", WHO, msg],
                       cwd=RAMCHAT, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=60,
                       creationflags=_NOWIN)
    sys.stdout.write(p.stdout.decode("utf-8", "replace"))
    return p.returncode


def load(path, default):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.now()

    rc, out, err = ssh("cat %s/status.json 2>/dev/null; echo '---SPLIT---'; "
                       "wc -c < %s/alarms.jsonl 2>/dev/null || echo 0"
                       % (REMOTE, REMOTE))
    if rc != 0:
        ramchat("SIBLING WATCHDOG UNREACHABLE: ssh %s failed (rc=%d) at %s. %s "
                "-- nobody is watching the sibling right now."
                % (HOST, rc, now.strftime("%H:%M"), err.strip()[:200]), a.dry)
        io.open(STATUS_OUT, "w", encoding="utf-8").write(
            "[GREY] UNREACHABLE %s  ssh %s failed\n" % (now.strftime("%F %T"), HOST))
        return 3

    raw, _, size_s = out.partition("---SPLIT---")
    try:
        size = int(size_s.strip() or 0)
    except Exception:
        size = 0
    st = None
    try:
        st = json.loads(raw.strip())
    except Exception:
        pass

    # --- 2: the plain file the morning report reads -------------------------
    if st:
        age_min = (now - dt.datetime.strptime(st["ts"], "%Y-%m-%dT%H:%M:%S")
                   ).total_seconds() / 60.0
        head = "%s SIBLING %s  %d alarm / %d warn  checked %.0fm ago" % (
            st["verdict"], st["host"], st["n_alarm"], st["n_warn"], age_min)
        body = [head, ""]
        for name, o in st.get("organs", {}).items():
            body.append("  %-6s %-9s rounds=%-5s last=%-6s %s=%s  seal=%s"
                        % (name, o.get("unit_active"), o.get("rounds"),
                           o.get("last_round_age") or "-", o.get("objective"),
                           o.get("objective_now"), o.get("seal")))
        body.append("")
        for f in st.get("findings", []):
            body.append("  %-5s %-8s %s" % (f["level"], f["code"], f["msg"]))
        body.append("")
        body.append("  one command:  ssh eran3 sibling-watch")
        io.open(STATUS_OUT, "w", encoding="utf-8").write("\n".join(body) + "\n")
    else:
        age_min = 1e9
        io.open(STATUS_OUT, "w", encoding="utf-8").write(
            "[GREY] NO STATUS on %s -- the watchdog has not written one.\n" % HOST)

    # --- 3: watch the watchdog ---------------------------------------------
    cur = load(CURSOR, {})
    if age_min > STALE_MIN:
        last_cry = cur.get("stale_cry", 0)
        if (now.timestamp() - last_cry) > 3600:
            ramchat("SIBLING WATCHDOG IS STALE: %s/status.json last written %.0f "
                    "minutes ago (expected every 3m). The sibling may be running "
                    "unwatched -- check `systemctl --user status "
                    "sibling-watch.timer` on %s." % (REMOTE, age_min, HOST), a.dry)
            cur["stale_cry"] = now.timestamp()

    # --- 1: carry the alarms -----------------------------------------------
    off = int(cur.get("offset", 0))
    if size < off:          # the log rotated or was truncated: start over
        off = 0
    new_lines = []
    if size > off:
        rc, out, err = ssh("tail -c +%d %s/alarms.jsonl" % (off + 1, REMOTE))
        if rc == 0:
            new_lines = [l for l in out.splitlines() if l.strip()]
            off = size

    posted = 0
    for line in new_lines:
        try:
            r = json.loads(line)
        except Exception:
            continue
        who = r["organ"] if not r.get("series") else "%s.%s" % (r["organ"], r["series"])
        tag = "STILL" if r.get("repeat") else "NEW"
        ramchat("SIBLING WATCHDOG ALARM (%s) [%s] %s %s on %s -- %s  "
                "(first seen %s; one command: `ssh eran3 sibling-watch`)"
                % (tag, r["code"], who, r["t"], HOST, r["msg"], r.get("first_seen")),
                a.dry)
        posted += 1

    cur["offset"] = off
    cur["last_run"] = now.strftime("%F %T")
    io.open(CURSOR, "w", encoding="utf-8").write(json.dumps(cur, indent=1))
    print("relay: verdict=%s posted=%d offset=%d status=%s"
          % ((st or {}).get("verdict", "?"), posted, off, STATUS_OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
