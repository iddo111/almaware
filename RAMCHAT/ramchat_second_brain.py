#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
THE COLLECTIVE SECOND BRAIN  —  RAMCHAT that does not forget, and does not
stop when the PC is switched off.

Iddo, 2026-09-05 14:44: "מוח שני פרטי וגם קולקטיבי — קוורום, ראמצ'ט".

TWO MEASURED PROBLEMS, 2026-09-05
---------------------------------
1. RAMCHAT FORGETS. ramlink.py writes `msgs[-500:]` to disk and `msgs[-200:]`
   to shared memory. The transcript was sitting at exactly 500 when this was
   written, so every new post permanently destroyed the oldest one. The council
   has no memory older than its last 500 lines, and nothing anywhere is
   append-only. What the team learned in July is simply gone.

2. RAMCHAT IS ON ONE MACHINE. It lives only in D:\\CLAUDE\\RAMCHAT. When Iddo
   powered the PC off for 58 minutes this morning the fleet kept training but
   coordination stopped dead - no agent could read what another had claimed.

WHAT THIS ADDS
--------------
  archive     an append-only ramchat_archive.jsonl that is NEVER truncated.
              Every message gets a stable id and, for the first time, a DATE -
              council messages only ever carried "HH:MM", so a transcript spanning
              days could not be ordered. first_seen_utc is stamped on arrival.
  push        mirror the archive + live transcript + queue to eran1 AND eran2.
              Two boxes, both of which stay up when the PC does not.
  spool       merge posts that fleet-side agents wrote while the PC was off.
  status      how many messages exist, how many the council can still see,
              and how far each mirror has fallen behind.

WHAT THIS DOES NOT DO
---------------------
It does not replace ramlink.py and does not touch the shared-memory blocks.
ramlink stays the door; this is the memory behind it. Nothing here can make the
council lose a message - every write is an append or an overwrite of a mirror.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(ROOT, "ramchat_session.json")
QUEUE_FILE = os.path.join(ROOT, "ramchat_prompt_queue.json")
ARCHIVE = os.path.join(ROOT, "ramchat_archive.jsonl")
QUEUE_ARCHIVE = os.path.join(ROOT, "ramchat_queue_archive.jsonl")

# Two homes, not one. eran1 holds ERAN and never goes down; eran2 is the hub
# every other box already reaches. If the PC is off, both are still up.
MIRRORS = [("eran1", "eran1"), ("eran2", "eran2"), ("eran4", "eran4")]
REMOTE_DIR = "ramchat-mirror"
SSH = ["ssh", "-o", "ConnectTimeout=20", "-o", "BatchMode=yes"]


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def msg_id(m):
    """Stable identity for a council message.

    who+at+text, not position: the transcript is a sliding window, so index
    means nothing across two reads. Two genuinely identical posts by the same
    agent in the same minute collapse into one - that is the right trade for a
    window that drops its head every time somebody speaks.
    """
    raw = "%s|%s|%s" % (m.get("who", ""), m.get("at", ""), m.get("text", ""))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue          # a torn last line must never lose the rest
    return out


def append_jsonl(path, rows):
    with io.open(path, "a", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------------------

def cmd_archive(a):
    """Fold whatever the council can currently see into the permanent record."""
    known = {r.get("id") for r in read_jsonl(ARCHIVE)}
    live = load_json(SESSION_FILE, [])
    new = []
    for m in live:
        mid = msg_id(m)
        if mid in known:
            continue
        known.add(mid)
        new.append({"id": mid, "who": m.get("who"), "at": m.get("at"),
                    "text": m.get("text"), "first_seen_utc": now_utc()})
    append_jsonl(ARCHIVE, new)

    qknown = {}
    for r in read_jsonl(QUEUE_ARCHIVE):
        qknown[r.get("task_id")] = r.get("state_hash")
    qlive = load_json(QUEUE_FILE, [])
    qnew = []
    for t in qlive:
        tid = t.get("id")
        if not tid:
            continue
        h = hashlib.sha1(json.dumps(t, sort_keys=True, ensure_ascii=False)
                         .encode("utf-8")).hexdigest()[:16]
        if qknown.get(tid) == h:
            continue                       # unchanged since we last saw it
        qknown[tid] = h
        qnew.append({"task_id": tid, "state_hash": h, "seen_utc": now_utc(),
                     "task": t})
    append_jsonl(QUEUE_ARCHIVE, qnew)

    total = len(known)
    print("archive: +%d messages (%d total, council can see %d)"
          % (len(new), total, len(live)))
    print("queue  : +%d task states (%d tasks tracked)" % (len(qnew), len(qknown)))
    return 0


def cmd_push(a):
    """Mirror the collective memory onto boxes that survive the PC being off."""
    cmd_archive(a)
    files = [ARCHIVE, QUEUE_ARCHIVE, SESSION_FILE, QUEUE_FILE,
             os.path.join(ROOT, "ramlink.py"),
             os.path.join(ROOT, "ramchat_fleet.py")]
    files = [f for f in files if os.path.exists(f)]
    ok = 0
    for name, host in MIRRORS:
        r = subprocess.run(SSH + [host, "mkdir -p ~/%s/spool" % REMOTE_DIR],
                           capture_output=True, timeout=60)
        if r.returncode != 0:
            print("push %-6s UNREACHABLE" % name)
            continue
        # BatchMode=yes is LOAD-BEARING. Without it scp may ask for a
        # passphrase or a host-key confirmation, and under the Task Scheduler
        # there is no console to answer on - the push hangs for ever and the
        # mirror silently stops updating. Measured 2026-09-05: the interactive
        # run took 4 s, the scheduled one was still hanging after 2 minutes.
        p = subprocess.run(["scp", "-q", "-o", "ConnectTimeout=20",
                            "-o", "BatchMode=yes"] + files +
                           ["%s:~/%s/" % (host, REMOTE_DIR)],
                           capture_output=True, timeout=600)
        if p.returncode == 0:
            stamp = json.dumps({"pushed_utc": now_utc(),
                                "messages": len(read_jsonl(ARCHIVE)),
                                "from": "PC"}, ensure_ascii=False)
            subprocess.run(SSH + [host, "cat > ~/%s/MIRROR.json" % REMOTE_DIR],
                           input=stamp.encode("utf-8"), capture_output=True,
                           timeout=60)
            print("push %-6s OK  (%d files)" % (name, len(files)))
            ok += 1
        else:
            print("push %-6s FAILED %s" % (name, p.stderr.decode("utf-8", "replace")[:120]))
    return 0 if ok else 1


def cmd_spool(a):
    """Bring home what the fleet said while the PC was off.

    A fleet-side agent cannot write the PC's shared memory, so ramchat_fleet.py
    appends to ~/ramchat-mirror/spool/<host>.jsonl instead. This merges those
    posts into the real council, in the order they were written.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("ramlink", os.path.join(ROOT, "ramlink.py"))
    ramlink = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ramlink)

    known = {r.get("id") for r in read_jsonl(ARCHIVE)}
    merged = 0
    for name, host in MIRRORS:
        # Claim the spool by RENAMING it before reading it, not by deleting it
        # after. A fleet agent can append between our read and our cleanup, and
        # anything written in that window would be merged and then discarded.
        # rename(2) is atomic on Linux, so every post lands either in the batch
        # we just claimed or in the fresh file the next `post` creates - never
        # in neither. It also stops `ramchat_fleet.py status` from reporting
        # posts as "waiting for the PC" for ever after they came home.
        stamp = now_utc().replace(":", "").replace("-", "")
        claim = ("cd ~/%s/spool 2>/dev/null || exit 0; mkdir -p merged; "
                 "for f in *.jsonl; do [ -e \"$f\" ] && "
                 "mv \"$f\" \"merged/${f%%.jsonl}-%s.jsonl\"; done; "
                 "cat merged/*-%s.jsonl 2>/dev/null"
                 % (REMOTE_DIR, stamp, stamp))
        p = subprocess.run(SSH + [host, claim], capture_output=True, timeout=120)
        if p.returncode != 0:
            continue
        for line in p.stdout.decode("utf-8", "replace").split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if msg_id(m) in known:
                continue
            known.add(msg_id(m))
            with ramlink.Lock():
                msgs, shared, _src = ramlink.get_transcript()
                msgs.append({"who": m.get("who"), "text": m.get("text"),
                             "at": m.get("at")})
                ramlink.put_transcript(msgs, shared)
            merged += 1
    print("spool: merged %d fleet posts into the council" % merged)
    if merged:
        cmd_archive(a)
    return 0


def cmd_status(a):
    arch = read_jsonl(ARCHIVE)
    live = load_json(SESSION_FILE, [])
    print("COLLECTIVE SECOND BRAIN")
    print("  archive (append-only, never truncated) : %d messages" % len(arch))
    print("  council window (ramlink can see)       : %d  [cap 500]" % len(live))
    lost = len(arch) - len(live)
    print("  messages ONLY in the archive           : %d" % max(0, lost))
    if arch:
        print("  oldest archived                        : %s  %s"
              % (arch[0].get("first_seen_utc"), (arch[0].get("who") or "?")))
    print("  queue states tracked                   : %d" % len(read_jsonl(QUEUE_ARCHIVE)))
    print("  mirrors:")
    for name, host in MIRRORS:
        p = subprocess.run(SSH + [host, "cat ~/%s/MIRROR.json 2>/dev/null" % REMOTE_DIR],
                           capture_output=True, timeout=40)
        if p.returncode != 0 or not p.stdout.strip():
            print("    %-6s no mirror" % name)
            continue
        try:
            d = json.loads(p.stdout.decode("utf-8", "replace"))
            behind = len(arch) - int(d.get("messages", 0))
            print("    %-6s %s  %d messages  (%d behind)"
                  % (name, d.get("pushed_utc"), d.get("messages"), behind))
        except ValueError:
            print("    %-6s unreadable mirror" % name)
    return 0


def main():
    ap = argparse.ArgumentParser(description="RAMCHAT collective second brain")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("archive", help="fold the visible council into the permanent record")
    sub.add_parser("push", help="archive, then mirror to eran1 and eran2")
    sub.add_parser("spool", help="merge posts the fleet made while the PC was off")
    sub.add_parser("status", help="what exists, and how far behind each mirror is")
    a = ap.parse_args()
    return {"archive": cmd_archive, "push": cmd_push,
            "spool": cmd_spool, "status": cmd_status}.get(a.cmd, lambda _: (ap.print_help() or 0))(a)


if __name__ == "__main__":
    sys.exit(main())
