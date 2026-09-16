#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""עזרא הסופר / EZRA HASOFER -- a small resident scribe.

Iddo, 2026-09-12: a transcriber that ALWAYS logs our conversations with a real
(RTC) timestamp -- small, smart, resident, and built to SAVE tokens, not spend
them: it writes one compact line per turn (no thinking blocks, no tool-call
payloads, no attachments) so peek.py/grep can search months of talk for a few
hundred tokens instead of re-reading raw session JSONL (which runs 5-25MB per
session and is 90% tool noise).

WHAT IT READS
    Every *.jsonl under C:\\Users\\iddo1\\.claude\\projects\\D--CLAUDE\\ (this
    workspace's Claude Code sessions). Each line there already carries a real
    ISO-8601 timestamp from the harness -- Ezra does not invent time, only
    reads it (per [CLOCK] discipline: never state a time you did not measure).

WHAT IT WRITES
    D:\\CLAUDE\\ezra-hasofer\\log.jsonl -- one line per user/assistant text
    turn: {"ts": "...", "session": "...", "role": "user"|"assistant", "text": "..."}
    Thinking blocks, tool_use/tool_result blocks, hook noise, attachments and
    file-history snapshots are all skipped on purpose -- that is the token
    saving. Only visible conversation text is kept.

INCREMENTAL
    D:\\CLAUDE\\ezra-hasofer\\state.json tracks a byte offset per source file,
    so a resident re-run only reads what is new. Safe to run every few minutes
    forever; cost is O(new bytes), not O(all history).

RESIDENT
    Windows Scheduled Task "Ezra-HaSofer" runs this every 5 minutes (same
    pattern as brain2's watchdog -- ONLOGON triggers are blocked in this
    sandbox, MINUTE triggers are not). A lock file prevents overlap if a run
    is still going when the next tick fires.
"""
import json
import os
import sys
import glob
import time

PROJ_DIR = r"C:\Users\<user>\.claude\projects\D--CLAUDE"
OUT_DIR = r"D:\CLAUDE\ezra-hasofer"
LOG_PATH = os.path.join(OUT_DIR, "log.jsonl")
STATE_PATH = os.path.join(OUT_DIR, "state.json")
LOCK_PATH = os.path.join(OUT_DIR, "ezra.lock")


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            return json.load(open(STATE_PATH, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    json.dump(state, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def extract_text(content):
    """content is either a plain string (user turns) or a list of blocks
    (assistant turns, sometimes user turns with attachments). Keep only
    visible text -- never thinking, never tool_use/tool_result payloads."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p).strip()
    return ""


def process_file(path, offset, out_f):
    size = os.path.getsize(path)
    if size <= offset:
        return offset, 0
    written = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        for line in f:
            offset += len(line.encode("utf-8", "replace"))
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = d.get("message") or {}
            role = msg.get("role") or t
            text = extract_text(msg.get("content"))
            if not text:
                continue
            ts = d.get("timestamp") or ""
            session = d.get("sessionId") or os.path.basename(path).replace(".jsonl", "")
            out_f.write(json.dumps(
                {"ts": ts, "session": session, "role": role, "text": text},
                ensure_ascii=False) + "\n")
            written += 1
    return offset, written


def run_once():
    if os.path.exists(LOCK_PATH):
        # a previous run may still be going, or crashed mid-run -- refuse to
        # stack up concurrent writers on the same log file.
        age = time.time() - os.path.getmtime(LOCK_PATH)
        if age < 600:
            print("ezra: lock held (%.0fs old), skipping this tick" % age)
            return
        print("ezra: stale lock (%.0fs old), clearing" % age)
    open(LOCK_PATH, "w").write(str(os.getpid()))
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        state = load_state()
        total_written = 0
        with open(LOG_PATH, "a", encoding="utf-8") as out_f:
            for path in sorted(glob.glob(os.path.join(PROJ_DIR, "*.jsonl"))):
                offset = state.get(path, 0)
                new_offset, written = process_file(path, offset, out_f)
                if new_offset != offset:
                    state[path] = new_offset
                total_written += written
        save_state(state)
        if total_written:
            msg = "ezra: +%d turns logged" % total_written
            print(msg)
            with open(os.path.join(OUT_DIR, "activity.log"), "a", encoding="utf-8") as af:
                af.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    finally:
        try:
            os.remove(LOCK_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    run_once()
