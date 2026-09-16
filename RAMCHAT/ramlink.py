#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAMLINK - the CLI door into the RAMCHAT council. / הדלת לחדר המועצה ב-RAM.

The shared RAM already exists. This is not a new system - it is a way for any
agent (Claude, Claude CLI, Codex, Grok, a shell script) to read and write the
same two named Windows shared-memory blocks the RAMCHAT GUI uses:

    RAMCHAT_COUNCIL_V1   16 MiB   magic RAMCHAT1   transcript + shared memory
    RAMCHAT_QUEUE_V1      8 MiB   magic RAMQUEU1   the work queue

Layout of both, exactly as ramchat.pyw writes it:
    [0:8]   8-byte magic
    [8:16]  little-endian unsigned 64-bit UTF-8 payload length
    [16:]   UTF-8 JSON

WHY THIS EXISTS: so two agents stop building the same thing twice. Claim a task
before you start it. If someone already holds it, `claim` refuses and tells you
who has it.

  ramlink post   <who> <text>          say something to the council
  ramlink read   [--tail N]            read the transcript
  ramlink add    <text> [--for WHO]    put work on the queue
  ramlink queue  [--mine WHO] [--open] list work
  ramlink claim  <task-id> <who>       take a task - ATOMIC, refuses if held
  ramlink done   <task-id> [result]    finish a task you hold
  ramlink hold                         keep the RAM blocks alive (see note)
  ramlink status                       is the council up?

NOTE ON WINDOWS SHARED MEMORY: a named mapping only lives while at least one
process holds it open. If the RAMCHAT GUI is closed and no `ramlink hold` is
running, the block disappears. That is why every write also lands in the JSON
files on disk - those are the durable truth, RAM is the fast mirror.
"""
from __future__ import annotations

import argparse
import json
import mmap
import os
import struct
import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))

COUNCIL_NAME = "RAMCHAT_COUNCIL_V1"
COUNCIL_SIZE = 16 * 1024 * 1024
COUNCIL_MAGIC = b"RAMCHAT1"

QUEUE_NAME = "RAMCHAT_QUEUE_V1"
QUEUE_SIZE = 8 * 1024 * 1024
QUEUE_MAGIC = b"RAMQUEU1"

SCHEMA = 1

SESSION_FILE = os.path.join(ROOT, "ramchat_session.json")
SHARED_FILE = os.path.join(ROOT, "ramchat_shared_memory.json")
QUEUE_FILE = os.path.join(ROOT, "ramchat_prompt_queue.json")
LOCK_FILE = os.path.join(ROOT, "ramlink.lock")

MAX_TRANSCRIPT = 200
MAX_QUEUE = 500

# Two producers write this queue with two vocabularies: ramlink uses
# open/in_progress/done, the RAMCHAT GUI uses processing/completed/failed.
# `queue --open` must understand BOTH or it advertises finished work as open.
TERMINAL_STATUS = ("done", "cancelled", "completed", "failed", "rejected")
BUSY_STATUS = ("in_progress", "processing", "claimed")


# ---------------------------------------------------------------------------
# Cross-process lock. Exclusive-create is atomic on Windows and POSIX alike.
# ---------------------------------------------------------------------------

class Lock(object):
    def __init__(self, path=LOCK_FILE, timeout=10.0):
        self.path = path
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self.fd, ("%d" % os.getpid()).encode())
                return self
            except FileExistsError:
                # stale lock from a killed process? 30 s is far longer than any
                # legitimate read-modify-write here.
                try:
                    if time.time() - os.path.getmtime(self.path) > 30:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise TimeoutError("ramlink lock held too long: " + self.path)
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            if self.fd is not None:
                os.close(self.fd)
            os.remove(self.path)
        except OSError:
            pass
        return False


# ---------------------------------------------------------------------------
# Shared memory
# ---------------------------------------------------------------------------

def _open(name, size):
    try:
        return mmap.mmap(-1, size, tagname=name, access=mmap.ACCESS_WRITE)
    except OSError:
        return None
    except (ValueError, AttributeError, TypeError):
        return None       # tagname is Windows-only; on POSIX fall back to disk


def read_block(name, size, magic):
    """Return the JSON in a named block, or None if absent/empty/foreign."""
    m = _open(name, size)
    if m is None:
        return None
    try:
        m.seek(0)
        head = m.read(16)
        if len(head) < 16 or head[:8] != magic:
            return None
        n = struct.unpack("<Q", head[8:16])[0]
        if n == 0 or n > size - 16:
            return None
        raw = m.read(n)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    finally:
        m.close()


def write_block(name, size, magic, payload_obj):
    raw = json.dumps(payload_obj, ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw) > size - 16:
        return False, "payload %d bytes exceeds block" % len(raw)
    m = _open(name, size)
    if m is None:
        return False, "cannot open mapping %s" % name
    try:
        m.seek(0)
        m.write(magic + struct.pack("<Q", len(raw)) + raw)
        m.flush()
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        m.close()


# ---------------------------------------------------------------------------
# Disk (durable truth)
# ---------------------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    # 2026-09-06 11:25: a bare os.replace() LOSES POSTS on Windows. If any other
    # process (another session's `read`, the GUI, an MCP bridge) has the target
    # open at that instant, the rename raises PermissionError (WinError 5) and the
    # message is gone -- observed live with ~10 agents posting concurrently. A
    # retry costs nothing when the lock is transient (it always is here) and
    # turns a silent coordination hole into at worst a one-second delay.
    last = None
    for _attempt in range(40):            # up to ~2 s total
        try:
            os.replace(tmp, path)
            break
        except PermissionError as e:      # WinError 5 / 32: target held open
            last = e
            time.sleep(0.05)
    else:
        raise last


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# State: read RAM first, fall back to disk
# ---------------------------------------------------------------------------

# RAM is a CACHE, disk is the truth. If the block is stale or a holder wrote an
# older snapshot over it, a naive "RAM first" read makes tasks vanish - claim
# then reports "no such task" for work that plainly exists. Always take whichever
# source has more entries.

def get_transcript():
    disk_msgs = load_json(SESSION_FILE, [])
    disk_shared = load_json(SHARED_FILE, {})
    blk = read_block(COUNCIL_NAME, COUNCIL_SIZE, COUNCIL_MAGIC)
    ram_msgs = blk.get("transcript") if blk and isinstance(blk.get("transcript"), list) else None
    if ram_msgs is not None and len(ram_msgs) >= len(disk_msgs):
        return ram_msgs, (blk.get("shared_memory") or disk_shared), "ram"
    return disk_msgs, disk_shared, "disk"


def get_queue():
    disk_items = load_json(QUEUE_FILE, [])
    blk = read_block(QUEUE_NAME, QUEUE_SIZE, QUEUE_MAGIC)
    ram_items = blk.get("items") if blk and isinstance(blk.get("items"), list) else None
    if ram_items is not None and len(ram_items) >= len(disk_items):
        return ram_items, "ram"
    return disk_items, "disk"


def put_transcript(msgs, shared):
    save_json(SESSION_FILE, msgs[-MAX_QUEUE:])
    ok, err = write_block(COUNCIL_NAME, COUNCIL_SIZE, COUNCIL_MAGIC, {
        "schema": SCHEMA,
        "mapping": COUNCIL_NAME,
        "updated_at": now_iso(),
        "transcript": msgs[-MAX_TRANSCRIPT:],
        "shared_memory": shared,
    })
    return ok, err


def put_queue(items):
    save_json(QUEUE_FILE, items[-MAX_QUEUE:])
    ok, err = write_block(QUEUE_NAME, QUEUE_SIZE, QUEUE_MAGIC, {
        "schema": SCHEMA,
        "mapping": QUEUE_NAME,
        "updated_at": now_iso(),
        "items": items[-MAX_QUEUE:],
    })
    return ok, err


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_post(a):
    with Lock():
        msgs, shared, src = get_transcript()
        msgs.append({"who": a.who, "text": a.text.strip(),
                     "at": datetime.now().strftime("%H:%M")})
        ok, err = put_transcript(msgs, shared)
    print("posted as %s (%d messages, source=%s, ram=%s)"
          % (a.who, len(msgs), src, "ok" if ok else err))
    return 0


def cmd_read(a):
    msgs, shared, src = get_transcript()
    if a.json:
        print(json.dumps({"transcript": msgs[-a.tail:], "shared_memory": shared},
                         ensure_ascii=False, indent=2))
        return 0
    print("council transcript  (source=%s, %d total)" % (src, len(msgs)))
    print("-" * 68)
    full = getattr(a, "full", False)
    for m in msgs[-a.tail:]:
        text = (m.get("text") or "").replace("\n", " ")
        if not full and len(text) > 200:
            text = text[:200] + " ...(+%d chars, --full)" % (len(text) - 200)
        print("[%s] %-10s %s" % (m.get("at", "--:--"), m.get("who", "?"), text))
    mission = (shared or {}).get("mission")
    if mission:
        print("-" * 68)
        mission = str(mission)
        if not full and len(mission) > 200:
            mission = mission[:200] + " ...(+%d chars, --full)" % (len(mission) - 200)
        print("mission: %s" % mission)
    return 0


def cmd_add(a):
    with Lock():
        items, src = get_queue()
        task = {
            "id": datetime.now().strftime("task-%Y%m%d-%H%M%S-%f"),
            "created_at": now_iso(),
            "source": a.by,
            "targets": [a.for_] if a.for_ else [],
            "status": "open",
            "prompt": a.text.strip(),
            "claimed_by": None,
        }
        items.append(task)
        ok, err = put_queue(items)
    print("added %s  (%d in queue, ram=%s)" % (task["id"], len(items),
                                               "ok" if ok else err))
    print(task["id"])
    return 0


def cmd_queue(a):
    items, src = get_queue()
    rows = items
    if a.mine:
        rows = [t for t in rows if t.get("claimed_by") == a.mine
                or a.mine in (t.get("targets") or [])]
    if a.open:
        rows = [t for t in rows if not t.get("claimed_by")
                and t.get("status") not in TERMINAL_STATUS
                and t.get("status") not in BUSY_STATUS]
    print("queue  (source=%s, showing %d of %d)" % (src, len(rows), len(items)))
    print("-" * 78)
    for t in rows[-40:]:
        held = t.get("claimed_by") or "-"
        print("%-30s %-9s held=%-10s %s"
              % (t.get("id", "?")[:30], str(t.get("status"))[:9], held[:10],
                 (t.get("prompt") or "").replace("\n", " ")[:34]))
    return 0


def cmd_claim(a):
    """Atomic. Under the lock: read, check, write. Two racers -> one winner."""
    with Lock():
        items, src = get_queue()
        task = next((t for t in items if t.get("id") == a.task_id), None)
        if task is None:
            print("no such task: %s" % a.task_id)
            return 2
        holder = task.get("claimed_by")
        if holder and holder != a.who:
            print("REFUSED - already held by %s since %s"
                  % (holder, task.get("claimed_at", "?")))
            return 1
        task["claimed_by"] = a.who
        task["claimed_at"] = now_iso()
        task["status"] = "in_progress"
        ok, err = put_queue(items)
    print("CLAIMED %s by %s (ram=%s)" % (a.task_id, a.who, "ok" if ok else err))
    return 0


def cmd_done(a):
    with Lock():
        items, src = get_queue()
        task = next((t for t in items if t.get("id") == a.task_id), None)
        if task is None:
            print("no such task: %s" % a.task_id)
            return 2
        if task.get("claimed_by") and a.who and task["claimed_by"] != a.who:
            print("REFUSED - held by %s, not %s" % (task["claimed_by"], a.who))
            return 1
        task["status"] = "done"
        task["finished_at"] = now_iso()
        if a.result:
            task["result"] = a.result
        ok, err = put_queue(items)
    print("DONE %s (ram=%s)" % (a.task_id, "ok" if ok else err))
    return 0


def cmd_status(a):
    c = read_block(COUNCIL_NAME, COUNCIL_SIZE, COUNCIL_MAGIC)
    q = read_block(QUEUE_NAME, QUEUE_SIZE, QUEUE_MAGIC)
    print("RAMLINK status")
    print("-" * 60)
    print("  %-22s %s" % (COUNCIL_NAME,
                          "LIVE, %d msgs, updated %s" % (len(c.get("transcript") or []),
                                                         c.get("updated_at"))
                          if c else "empty / not held by any process"))
    print("  %-22s %s" % (QUEUE_NAME,
                          "LIVE, %d items, updated %s" % (len(q.get("items") or []),
                                                          q.get("updated_at"))
                          if q else "empty / not held by any process"))
    print("  disk session   %d messages" % len(load_json(SESSION_FILE, [])))
    print("  disk queue     %d items" % len(load_json(QUEUE_FILE, [])))
    if not c or not q:
        print()
        print("  A named block only lives while a process holds it open.")
        print("  Run 'ramlink hold' (or the RAMCHAT GUI) to keep RAM warm.")
    return 0


def cmd_hold(a):
    """Keep both blocks mapped so they survive between one-shot commands."""
    msgs, shared, _ = get_transcript()
    items, _ = get_queue()
    c = _open(COUNCIL_NAME, COUNCIL_SIZE)
    q = _open(QUEUE_NAME, QUEUE_SIZE)
    if c is None or q is None:
        print("could not map shared memory")
        return 1
    put_transcript(msgs, shared)
    put_queue(items)
    print("holding %s + %s  -  Ctrl+C to release" % (COUNCIL_NAME, QUEUE_NAME))
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nreleased")
    finally:
        try:
            c.close()
            q.close()
        except Exception:
            pass
    return 0


def main():
    p = argparse.ArgumentParser(prog="ramlink", description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("post", help="say something to the council")
    s.add_argument("who")
    s.add_argument("text")
    s.set_defaults(fn=cmd_post)

    s = sub.add_parser("read", help="read the transcript")
    s.add_argument("--tail", type=int, default=20)
    s.add_argument("--json", action="store_true")
    s.add_argument("--full", action="store_true",
                   help="print whole messages (default cuts at 200 chars with a marker)")
    s.set_defaults(fn=cmd_read)

    s = sub.add_parser("add", help="put work on the queue")
    s.add_argument("text")
    s.add_argument("--for", dest="for_", default=None)
    s.add_argument("--by", default="claude")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("queue", help="list work")
    s.add_argument("--mine", default=None)
    s.add_argument("--open", action="store_true")
    s.set_defaults(fn=cmd_queue)

    s = sub.add_parser("claim", help="take a task, atomically")
    s.add_argument("task_id")
    s.add_argument("who")
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("done", help="finish a task you hold")
    s.add_argument("task_id")
    s.add_argument("result", nargs="?", default=None)
    s.add_argument("--who", default=None)
    s.set_defaults(fn=cmd_done)

    sub.add_parser("status", help="is the council up?").set_defaults(fn=cmd_status)
    sub.add_parser("hold", help="keep the RAM blocks alive").set_defaults(fn=cmd_hold)

    a = p.parse_args()
    # Windows Python prints CRLF. Piping an id through a shell loop leaves a
    # trailing carriage return on it, and claim then reports "no such task"
    # for work that plainly exists. Strip it here so every caller is safe.
    if getattr(a, "task_id", None):
        a.task_id = a.task_id.strip()
    for f_ in ("who", "mine", "by", "for_"):
        v = getattr(a, f_, None)
        if isinstance(v, str):
            setattr(a, f_, v.strip())
        if isinstance(v, str):
            setattr(a, f_, v.strip())
    if not getattr(a, "fn", None):
        p.print_help()
        return 1
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
