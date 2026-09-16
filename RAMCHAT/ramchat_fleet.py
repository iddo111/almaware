#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAMCHAT, FLEET SIDE  —  the council door on eran1/eran2, for when the PC is off.

Iddo powered the PC off for 58 minutes on the morning of 2026-09-05. The fleet
kept training the whole time; coordination stopped dead, because RAMCHAT lives
only on D:. This is the other half of the door.

    python3 ~/ramchat-mirror/ramchat_fleet.py read  --tail 20
    python3 ~/ramchat-mirror/ramchat_fleet.py post  <who> "what you are doing"
    python3 ~/ramchat-mirror/ramchat_fleet.py queue --open
    python3 ~/ramchat-mirror/ramchat_fleet.py status

HOW IT DIFFERS FROM ramlink.py, AND WHY
---------------------------------------
ramlink writes two named Windows shared-memory blocks. Those do not exist on
Linux and cannot be reached across the network, so a fleet-side agent has no
way to write the council directly. Instead:

  READ  is served from the mirror the PC pushed (ramchat_archive.jsonl - the
        full history, not the 500-message window).
  POST  is APPEND-ONLY into spool/<host>.jsonl. The PC merges the spool into
        the real council on its next `ramchat_second_brain.py spool`.

So a post from the fleet is never lost, but it is not instantly visible to
agents on the PC - it lands when the PC comes back. Say what you are doing
anyway: the point of the council is that the next agent finds out.

CLAIMING IS DELIBERATELY NOT OFFERED HERE. `claim` is atomic only because one
process arbitrates it; a spooled claim could not refuse a competing claim made
on the PC in the same minute, and a claim that cannot refuse is worse than no
claim at all. Post your intention instead, and claim properly when the PC is up.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(ROOT, "ramchat_archive.jsonl")
SESSION = os.path.join(ROOT, "ramchat_session.json")
QUEUE = os.path.join(ROOT, "ramchat_prompt_queue.json")
MIRROR = os.path.join(ROOT, "MIRROR.json")
SPOOL_DIR = os.path.join(ROOT, "spool")

TERMINAL = ("done", "cancelled", "completed", "failed", "rejected")


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def load_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def cmd_read(a):
    msgs = read_jsonl(ARCHIVE) or load_json(SESSION, [])
    spooled = []
    if os.path.isdir(SPOOL_DIR):
        # only *.jsonl at the top level is unmerged; spool/merged/ is history
        for fn in sorted(os.listdir(SPOOL_DIR)):
            if fn.endswith(".jsonl"):
                spooled += read_jsonl(os.path.join(SPOOL_DIR, fn))
    print("council transcript  (fleet mirror, %d archived + %d not yet merged)"
          % (len(msgs), len(spooled)))
    freshness()
    print("-" * 68)
    for m in (msgs + spooled)[-a.tail:]:
        mark = "*" if m in spooled else " "
        print("%s[%s] %-10s %s" % (mark, m.get("at", "--:--"), m.get("who", "?"),
                                   (m.get("text") or "").replace("\n", " ")[:200]))
    if spooled:
        print("-" * 68)
        print("* = written on the fleet, waiting for the PC to merge it")
    return 0


def cmd_post(a):
    os.makedirs(SPOOL_DIR, exist_ok=True)
    host = socket.gethostname()
    row = {"who": a.who, "text": a.text.strip(),
           "at": datetime.now().strftime("%H:%M"),
           "spooled_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "spooled_on": host}
    path = os.path.join(SPOOL_DIR, "%s.jsonl" % host)
    with io.open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n = len(read_jsonl(path))
    print("spooled as %s on %s (%d waiting to merge)" % (a.who, host, n))
    print("this reaches the PC council when someone runs "
          "`python ramchat_second_brain.py spool` there.")
    return 0


def cmd_queue(a):
    items = load_json(QUEUE, [])
    shown = 0
    for t in items:
        st = str(t.get("status", "open")).lower()
        if a.open and st in TERMINAL:
            continue
        print("%-30s %-9s held=%-12s %s"
              % (t.get("id", "?"), st, t.get("claimed_by") or "-",
                 str(t.get("prompt", ""))[:60]))
        shown += 1
    print("-" * 68)
    print("%d shown. THIS IS A MIRROR - it can be stale, and you cannot claim "
          "from here (see the note at the top of this file)." % shown)
    freshness()
    return 0


def freshness():
    d = load_json(MIRROR, {})
    if not d:
        print("  (no MIRROR.json - this mirror has never been pushed)")
        return
    print("  mirror pushed %s with %s messages" %
          (d.get("pushed_utc"), d.get("messages")))


def cmd_status(a):
    print("RAMCHAT FLEET MIRROR on %s" % socket.gethostname())
    print("  dir      : %s" % ROOT)
    print("  archive  : %d messages" % len(read_jsonl(ARCHIVE)))
    print("  queue    : %d tasks" % len(load_json(QUEUE, [])))
    sp = 0
    if os.path.isdir(SPOOL_DIR):
        for fn in os.listdir(SPOOL_DIR):
            if fn.endswith(".jsonl"):        # spool/merged/ is already home
                sp += len(read_jsonl(os.path.join(SPOOL_DIR, fn)))
    print("  spooled  : %d posts waiting for the PC" % sp)
    freshness()
    return 0


def main():
    ap = argparse.ArgumentParser(description="RAMCHAT council, fleet side")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("read"); r.add_argument("--tail", type=int, default=20)
    p = sub.add_parser("post"); p.add_argument("who"); p.add_argument("text")
    q = sub.add_parser("queue"); q.add_argument("--open", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()
    return {"read": cmd_read, "post": cmd_post, "queue": cmd_queue,
            "status": cmd_status}.get(a.cmd, lambda _: (ap.print_help() or 0))(a)


if __name__ == "__main__":
    sys.exit(main())
