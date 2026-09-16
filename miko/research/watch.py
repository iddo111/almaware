#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
watch.py -- register a research topic once; a later run repeats the
research (via dig.py's run_research) and reports only what is NEW since
last time. State lives in a small sqlite file: watch_state.db (topics +
every URL already seen per topic).

Usage:
    python watch.py add "topic question" [--pages N] [--minutes M]
    python watch.py list
    python watch.py run <topic-id>
    python watch.py run --all
"""
import sys
import os
import time
import sqlite3
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _rescommon import lower_priority, utf8_stdio, RESEARCH_DIR, sum_via_toolkit  # noqa: E402
from dig import run_research  # noqa: E402

DB_PATH = os.path.join(RESEARCH_DIR, "watch_state.db")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS topics(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        pages INTEGER NOT NULL DEFAULT 10,
        minutes REAL NOT NULL DEFAULT 8,
        created_at TEXT NOT NULL,
        last_run_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS seen_urls(
        topic_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        title TEXT,
        first_seen_at TEXT NOT NULL,
        PRIMARY KEY(topic_id, url)
    )""")
    conn.commit()
    return conn


def cmd_add(args):
    conn = db()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO topics(question,pages,minutes,created_at) VALUES (?,?,?,?)",
        (args.topic, args.pages, args.minutes, now))
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    print("registered topic #%d: %s (pages=%d minutes=%.1f)" % (tid, args.topic, args.pages, args.minutes))
    print("no baseline yet -- run it once with: python watch.py run %d" % tid)


def cmd_list(args):
    conn = db()
    rows = conn.execute(
        "SELECT id,question,pages,minutes,created_at,last_run_at FROM topics ORDER BY id").fetchall()
    if not rows:
        print('no topics registered yet -- use: python watch.py add "<topic>"')
    for r in rows:
        seen_n = conn.execute("SELECT COUNT(*) FROM seen_urls WHERE topic_id=?", (r[0],)).fetchone()[0]
        print("#%-3d %-55s last_run=%-20s known_urls=%d" %
              (r[0], r[1][:55], r[5] or "never", seen_n))
    conn.close()


def _run_one(conn, tid):
    row = conn.execute("SELECT question,pages,minutes FROM topics WHERE id=?", (tid,)).fetchone()
    if not row:
        print("watch.py: no topic #%s (see: python watch.py list)" % tid)
        return
    question, pages, minutes = row
    known = set(r[0] for r in conn.execute(
        "SELECT url FROM seen_urls WHERE topic_id=?", (tid,)))
    is_baseline = (len(known) == 0)

    print("watch.py: running topic #%d -- %s" % (tid, question))
    report = run_research(question, max_pages=pages, max_minutes=minutes)

    new_pages = [p for p in report["pages"] if p["url"] not in known]
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for p in report["pages"]:
        conn.execute(
            "INSERT OR IGNORE INTO seen_urls(topic_id,url,title,first_seen_at) VALUES (?,?,?,?)",
            (tid, p["url"], p.get("title", ""), now))
    conn.execute("UPDATE topics SET last_run_at=? WHERE id=?", (now, tid))
    conn.commit()

    print()
    print("run %s -- %d page(s) read this pass, %.1fs elapsed"
          % (report["run_id"], report["pages_read"], report["elapsed_sec"]))
    if is_baseline:
        print("BASELINE established for topic #%d: %d page(s) recorded. "
              "Run again later to see what's NEW." % (tid, len(report["pages"])))
    elif not new_pages:
        print("NOTHING NEW since the last run of topic #%d." % tid)
    else:
        print("NEW since last run (%d page(s)):" % len(new_pages))
        if len(new_pages) > 6:
            tmp = os.path.join(report["run_dir"], "_delta.txt")
            with open(tmp, "w", encoding="utf-8") as fh:
                for p in new_pages:
                    fh.write("%s -- %s\n" % (p["title"], p["url"]))
            # reuse tokensave/sum.py exactly as shipped to compress a big delta
            print(sum_via_toolkit(tmp))
        else:
            for p in new_pages:
                print("  - %s -- %s" % (p["title"], p["url"]))
    print()
    print("full synthesis for this run:")
    print(report["synthesis"])
    print()
    print("journal: %s" % os.path.join(report["run_dir"], "journal.jsonl"))


def cmd_run(args):
    conn = db()
    if args.all:
        ids = [r[0] for r in conn.execute("SELECT id FROM topics").fetchall()]
        if not ids:
            print("no topics registered -- use: python watch.py add \"<topic>\"")
        for tid in ids:
            _run_one(conn, tid)
            print("=" * 60)
    elif args.topic:
        try:
            tid = int(args.topic)
        except ValueError:
            print("watch.py: topic id must be a number (see: python watch.py list)")
            conn.close()
            return
        _run_one(conn, tid)
    else:
        print("watch.py: give a topic id or --all (see: python watch.py list)")
    conn.close()


def main():
    ap = argparse.ArgumentParser(prog="watch.py", description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="register a topic")
    a.add_argument("topic")
    a.add_argument("--pages", type=int, default=10)
    a.add_argument("--minutes", type=float, default=8.0)

    sub.add_parser("list", help="list registered topics")

    r = sub.add_parser("run", help="re-run a topic and report what's new")
    r.add_argument("topic", nargs="?")
    r.add_argument("--all", action="store_true")

    args = ap.parse_args()
    lower_priority()
    utf8_stdio()

    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "run":
        cmd_run(args)


if __name__ == "__main__":
    main()
