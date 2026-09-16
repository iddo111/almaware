#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA-RECALL — one search box over every memory and every AI chat on this PC.
ALMA-RECALL — תיבת חיפוש אחת לכל הזיכרונות וכל השיחות של כל ה-AI במחשב.

Sources / מקורות:
  memory      Claude auto-memory .md files
  claude      Claude Code session transcripts (.jsonl)
  codex       OpenAI Codex CLI rollouts (.jsonl)
  grok        Grok CLI chat_history.jsonl
  gemini      Antigravity/Gemini workspace text artifacts (no chat transcripts stored locally)
  cursor      Cursor composer chats from state.vscdb (best-effort)
  perplexity  Perplexity desktop IndexedDB text fragments (best-effort, server-side truth)

No torch. No network. Local read-only indexing into SQLite FTS5.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HOME = os.path.expanduser("~")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "recall.db")
PORT = int(os.environ.get("RECALL_PORT", "8794"))

MEMORY_DIR = os.path.join(HOME, ".claude", "projects", "D--CLAUDE", "memory")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CODEX_DIRS = [
    os.path.join(HOME, ".codex", "sessions"),
    os.path.join(HOME, ".codex", "archived_sessions"),
]
GROK_SESSIONS = os.path.join(HOME, ".grok", "sessions")
GEMINI_BRAIN_DIRS = [
    os.path.join(HOME, ".gemini", "antigravity-ide", "brain"),
    os.path.join(HOME, ".gemini", "antigravity", "conversations"),
    os.path.join(HOME, ".gemini", "antigravity", "brain"),
]
CURSOR_VSCDB = [
    os.path.join(HOME, "AppData", "Roaming", "Cursor", "User", "globalStorage", "state.vscdb"),
]
CURSOR_WS_STORAGE = os.path.join(HOME, "AppData", "Roaming", "Cursor", "User", "workspaceStorage")
PERPLEXITY_LEVELDB = os.path.join(
    HOME, "AppData", "Roaming", "Perplexity", "IndexedDB",
    "https_www.perplexity.ai_0.indexeddb.leveldb",
)

RAMCHAT_DIR = os.path.join("D:" + os.sep, "CLAUDE", "RAMCHAT")
# Only the two DURABLE files. current_council.json / current_queue.json are stale
# (Aug-12) RAM snapshots whose transcript duplicates ramchat_session.json — indexing
# them would double every hit. CLAUDE.md: the *_session/_prompt_queue files are truth.
RAMCHAT_FILES = [
    os.path.join(RAMCHAT_DIR, "ramchat_session.json"),      # council transcript
    os.path.join(RAMCHAT_DIR, "ramchat_prompt_queue.json"),  # work queue
]

SOURCES = ["memory", "claude", "codex", "grok", "gemini", "cursor", "perplexity", "ramchat"]

# ----------------------------------------------------------------------------
# DB
# ----------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id       INTEGER PRIMARY KEY,
    source   TEXT NOT NULL,
    project  TEXT,
    sid      TEXT,
    path     TEXT NOT NULL UNIQUE,
    title    TEXT,
    started  TEXT,
    ended    TEXT,
    nmsg     INTEGER DEFAULT 0,
    chars    INTEGER DEFAULT 0,
    fmtime   REAL,
    fsize    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sessions_source  ON sessions(source);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started);

CREATE TABLE IF NOT EXISTS msgs (
    id      INTEGER PRIMARY KEY,
    sess    INTEGER NOT NULL,
    seq     INTEGER,
    role    TEXT,
    ts      TEXT,
    text    TEXT
);
CREATE INDEX IF NOT EXISTS idx_msgs_sess ON msgs(sess);

CREATE VIRTUAL TABLE IF NOT EXISTS msgs_fts USING fts5(
    text,
    content='msgs',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path=DB_PATH):
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init_db(con):
    con.executescript(SCHEMA)
    con.commit()


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def iso(ts):
    """Normalise a timestamp to ISO-8601 or return None."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:
            return None
    if isinstance(ts, str) and ts.strip():
        return ts.strip()
    return None


def flatten_content(content):
    """Claude/Grok content -> plain text. Keeps text + thinking, drops tool payloads."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, str):
                out.append(b)
                continue
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t in ("text", "input_text", "output_text", "summary_text"):
                out.append(b.get("text") or "")
            elif t == "thinking":
                th = b.get("thinking") or ""
                if th:
                    out.append("[thinking] " + th)
            elif t == "tool_use":
                out.append("[tool: %s]" % (b.get("name") or "?"))
    return "\n".join(x for x in out if x)


def mk_title(msgs, fallback):
    for role, ts, text in msgs:
        if role == "user" and text:
            t = re.sub(r"<[^>]{1,40}>", " ", text)
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) > 8:
                return t[:120]
    return fallback


def read_text(path, limit=2_000_000):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


def iter_lines(path):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line
    except Exception:
        return


# ----------------------------------------------------------------------------
# Parsers — each returns (project, sid, title, msgs[(role, ts, text)])
# ----------------------------------------------------------------------------

def parse_claude(path):
    project = os.path.basename(os.path.dirname(path))
    sid = os.path.splitext(os.path.basename(path))[0]
    msgs = []
    cwd = None
    for line in iter_lines(path):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        cwd = o.get("cwd") or cwd
        t = o.get("type")
        if t not in ("user", "assistant"):
            continue
        m = o.get("message") or {}
        role = m.get("role") or t
        text = flatten_content(m.get("content"))
        if text and text.strip():
            msgs.append((role, iso(o.get("timestamp")), text))
    return (cwd or project), sid, mk_title(msgs, sid), msgs


def parse_codex(path):
    project = None
    sid = os.path.splitext(os.path.basename(path))[0]
    msgs = []
    for line in iter_lines(path):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        typ = o.get("type")
        p = o.get("payload")
        if not isinstance(p, dict):
            continue
        ts = iso(o.get("timestamp") or p.get("timestamp"))
        if typ == "session_meta":
            project = p.get("cwd") or project
            sid = p.get("session_id") or sid
        elif typ == "turn_context":
            project = project or p.get("cwd")
        elif typ == "event_msg":
            pt = p.get("type")
            if pt == "user_message":
                txt = p.get("message") or ""
                if txt.strip():
                    msgs.append(("user", ts, txt))
            elif pt == "agent_message":
                txt = p.get("message") or ""
                if txt.strip():
                    msgs.append(("assistant", ts, txt))
            elif pt == "agent_reasoning":
                txt = p.get("text") or ""
                if txt.strip():
                    msgs.append(("assistant", ts, "[reasoning] " + txt))
        elif typ == "response_item" and p.get("type") == "message":
            role = p.get("role")
            if role in ("user", "assistant"):
                txt = flatten_content(p.get("content"))
                if txt.strip() and not any(m[2] == txt for m in msgs[-4:]):
                    msgs.append((role, ts, txt))
    return project or "codex", sid, mk_title(msgs, sid), msgs


def parse_grok(path):
    d = os.path.dirname(path)
    sid = os.path.basename(d)
    project = urllib.parse.unquote(os.path.basename(os.path.dirname(d)))
    msgs = []
    for line in iter_lines(path):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        t = o.get("type")
        if t == "user":
            txt = flatten_content(o.get("content"))
            if txt.strip():
                msgs.append(("user", iso(o.get("timestamp")), txt))
        elif t == "assistant":
            txt = flatten_content(o.get("content"))
            if txt.strip():
                msgs.append(("assistant", iso(o.get("timestamp")), txt))
        elif t == "reasoning":
            txt = flatten_content(o.get("summary"))
            if txt.strip():
                msgs.append(("assistant", iso(o.get("timestamp")), "[reasoning] " + txt))
    return project, sid, mk_title(msgs, sid), msgs


FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_memory(path):
    raw = read_text(path)
    name = os.path.splitext(os.path.basename(path))[0]
    mtype = "memory"
    desc = ""
    m = FM_RE.match(raw)
    if m:
        fm = m.group(1)
        for key, pat in (("name", r"^name:\s*(.+)$"),
                         ("description", r"^description:\s*(.+)$"),
                         ("type", r"^\s*type:\s*(.+)$")):
            mm = re.search(pat, fm, re.M)
            if mm:
                val = mm.group(1).strip()
                if key == "name":
                    name = val
                elif key == "description":
                    desc = val
                else:
                    mtype = val
    title = name if not desc else "%s — %s" % (name, desc)
    return mtype, name, title[:200], [("memory", None, raw)]


def parse_ramchat(path):
    """RAMCHAT council transcript / work queue — the team's shared memory.

    Council entries are {who, text, at} where `at` is HH:MM only (no date), so the
    per-message timestamp is left NULL and the file mtime carries the session time.
    The HH:MM is folded into the text so it stays visible and searchable.
    """
    base = os.path.basename(path).lower()
    try:
        data = json.loads(read_text(path))
    except Exception:
        return None
    if not isinstance(data, list):
        data = data.get("messages") or data.get("queue") or []
    msgs = []
    if "queue" in base:
        for it in data:
            if not isinstance(it, dict):
                continue
            who = it.get("source") or it.get("owner") or "queue"
            body = "\n".join(str(it.get(k, "")) for k in
                             ("id", "created_at", "status", "targets", "prompt",
                              "result", "response", "claimed_by", "note")
                             if it.get(k) not in (None, "", []))
            if body.strip():
                msgs.append((str(who), it.get("created_at"), body))
        title = "RAMCHAT work queue (%d tasks)" % len(msgs)
        kind = "queue"
    else:
        for it in data:
            if not isinstance(it, dict):
                continue
            who = str(it.get("who") or "?")
            txt = str(it.get("text") or "")
            if not txt.strip():
                continue
            msgs.append((who, None, "[%s %s] %s" % (it.get("at") or "", who, txt)))
        title = "RAMCHAT council transcript (%d messages)" % len(msgs)
        kind = "council"
    if not msgs:
        return None
    return kind, os.path.splitext(os.path.basename(path))[0], title, msgs


TEXTY = (".md", ".txt", ".json", ".jsonl", ".py", ".ts", ".js", ".html", ".yaml", ".yml", ".csv")


def parse_gemini_dir(d):
    """Antigravity keeps no chat transcripts locally — index the workspace's text artifacts."""
    sid = os.path.basename(d)
    msgs = []
    names = []
    total = 0
    for root, _dirs, files in os.walk(d):
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, d)
            names.append(rel)
            if not fn.lower().endswith(TEXTY):
                continue
            try:
                if os.path.getsize(fp) > 400_000:
                    continue
            except OSError:
                continue
            txt = read_text(fp, 400_000)
            if txt.strip():
                msgs.append(("artifact:" + rel, None, txt))
                total += len(txt)
            if total > 3_000_000:
                break
    if names:
        msgs.insert(0, ("manifest", None, "Files in workspace:\n" + "\n".join(names[:400])))
    return "antigravity", sid, "Antigravity workspace %s (%d files)" % (sid[:8], len(names)), msgs


def parse_cursor_db(path):
    """Cursor composer chats live in state.vscdb. Copy first — the app holds a lock."""
    out = []
    tmp = os.path.join(tempfile.gettempdir(), "alma_recall_cursor_%d.db" % os.getpid())
    try:
        shutil.copy2(path, tmp)
        for ext in ("-wal", "-shm"):
            if os.path.exists(path + ext):
                try:
                    shutil.copy2(path + ext, tmp + ext)
                except Exception:
                    pass
        con = sqlite3.connect(tmp)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for tbl in tables:
            cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % tbl).fetchall()]
            if not ({"key", "value"} <= set(cols)):
                continue
            for key, value in con.execute("SELECT key, value FROM %s" % tbl):
                if not isinstance(key, str):
                    continue
                if not re.search(r"composer|chat|bubble|aiService", key, re.I):
                    continue
                if isinstance(value, bytes):
                    value = value.decode("utf-8", "replace")
                if not isinstance(value, str) or len(value) < 40:
                    continue
                try:
                    obj = json.loads(value)
                except Exception:
                    continue
                msgs = _cursor_msgs(obj)
                if msgs:
                    out.append((key, msgs))
        con.close()
    except Exception:
        pass
    finally:
        for p in (tmp, tmp + "-wal", tmp + "-shm"):
            try:
                os.remove(p)
            except OSError:
                pass
    return out


def _cursor_msgs(obj):
    msgs = []

    def walk(o):
        if isinstance(o, dict):
            txt = o.get("text") or o.get("richText") or o.get("content")
            if isinstance(txt, str) and txt.strip() and len(txt.strip()) > 2:
                t = o.get("type")
                role = "user" if t in (1, "1", "user") else (
                    "assistant" if t in (2, "2", "assistant") else "msg")
                msgs.append((role, iso(o.get("createdAt") or o.get("timestamp")), txt))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return msgs[:2000]


def parse_perplexity():
    """Perplexity threads live on their servers. Local LevelDB holds partial text only."""
    if not os.path.isdir(PERPLEXITY_LEVELDB):
        return []
    buf = bytearray()
    for fn in sorted(os.listdir(PERPLEXITY_LEVELDB)):
        if not fn.endswith((".ldb", ".log")):
            continue
        fp = os.path.join(PERPLEXITY_LEVELDB, fn)
        try:
            with open(fp, "rb") as f:
                buf += f.read()
        except Exception:
            continue
    if not buf:
        return []
    runs = re.findall(rb"[\x20-\x7e\xc0-\xff\r\n\t]{100,}", bytes(buf))
    seen = set()
    frags = []
    for r in runs:
        s = r.decode("utf-8", "replace").strip()
        letters = sum(ch.isalpha() for ch in s)
        if letters < len(s) * 0.4:
            continue
        key = s[:120]
        if key in seen:
            continue
        seen.add(key)
        frags.append(s)
    return frags[:20000]


# ----------------------------------------------------------------------------
# Indexer
# ----------------------------------------------------------------------------

class Indexer(object):
    def __init__(self, con, log=print):
        self.con = con
        self.log = log
        self.stats = {}

    def _known(self):
        return {r["path"]: (r["fmtime"], r["fsize"], r["id"])
                for r in self.con.execute("SELECT path, fmtime, fsize, id FROM sessions")}

    def _store(self, path, source, project, sid, title, msgs, fmtime, fsize, old_id=None):
        if old_id is not None:
            self.con.execute("DELETE FROM msgs_fts WHERE rowid IN "
                             "(SELECT id FROM msgs WHERE sess=?)", (old_id,))
            self.con.execute("DELETE FROM msgs WHERE sess=?", (old_id,))
            self.con.execute("DELETE FROM sessions WHERE id=?", (old_id,))
        times = [t for _r, t, _x in msgs if t]
        chars = sum(len(t) for _r, _t, t in msgs)
        cur = self.con.execute(
            "INSERT INTO sessions(source,project,sid,path,title,started,ended,nmsg,chars,fmtime,fsize)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (source, project, sid, path, title,
             min(times) if times else iso(fmtime),
             max(times) if times else iso(fmtime),
             len(msgs), chars, fmtime, fsize))
        sess = cur.lastrowid
        for i, (role, ts, text) in enumerate(msgs):
            c = self.con.execute(
                "INSERT INTO msgs(sess,seq,role,ts,text) VALUES(?,?,?,?,?)",
                (sess, i, role, ts, text))
            self.con.execute("INSERT INTO msgs_fts(rowid, text) VALUES(?,?)",
                             (c.lastrowid, text))
        return sess

    def _sweep(self, source, files, parser, kind="file"):
        known = self._known()
        added = updated = skipped = 0
        for n, path in enumerate(files):
            try:
                st = os.stat(path) if kind == "file" else None
                fmtime = st.st_mtime if st else _dir_mtime(path)
                fsize = st.st_size if st else 0
            except OSError:
                continue
            prev = known.get(path)
            if prev and abs(prev[0] - fmtime) < 0.5 and prev[1] == fsize:
                skipped += 1
                continue
            try:
                project, sid, title, msgs = parser(path)
            except Exception:
                continue
            if not msgs:
                continue
            self._store(path, source, project, sid, title, msgs, fmtime, fsize,
                        prev[2] if prev else None)
            if prev:
                updated += 1
            else:
                added += 1
            if (n + 1) % 200 == 0:
                self.con.commit()
                self.log("  %s: %d/%d" % (source, n + 1, len(files)))
        self.con.commit()
        self.stats[source] = {"scanned": len(files), "added": added,
                              "updated": updated, "unchanged": skipped}
        self.log("  %-10s scanned=%d added=%d updated=%d unchanged=%d"
                 % (source, len(files), added, updated, skipped))

    # -- per source -----------------------------------------------------------

    def run(self, only=None):
        t0 = time.time()
        want = set(only or SOURCES)
        if "memory" in want:
            self.log("[memory]")
            files = _glob(MEMORY_DIR, ".md")
            self._sweep("memory", files, parse_memory)
        if "claude" in want:
            self.log("[claude]")
            files = [p for p in _walk(CLAUDE_PROJECTS, ".jsonl")
                     if os.sep + "memory" + os.sep not in p]
            self._sweep("claude", files, parse_claude)
        if "codex" in want:
            self.log("[codex]")
            files = []
            for d in CODEX_DIRS:
                files += _walk(d, ".jsonl")
            self._sweep("codex", files, parse_codex)
        if "grok" in want:
            self.log("[grok]")
            files = [p for p in _walk(GROK_SESSIONS, ".jsonl")
                     if os.path.basename(p) == "chat_history.jsonl"]
            self._sweep("grok", files, parse_grok)
        if "gemini" in want:
            self.log("[gemini]")
            dirs = []
            for base in GEMINI_BRAIN_DIRS:
                if os.path.isdir(base):
                    dirs += [os.path.join(base, d) for d in os.listdir(base)
                             if os.path.isdir(os.path.join(base, d))]
            self._sweep("gemini", dirs, parse_gemini_dir, kind="dir")
        if "ramchat" in want:
            self.log("[ramchat]")
            files = [p for p in RAMCHAT_FILES if os.path.isfile(p)]
            self._sweep("ramchat", files, parse_ramchat)
        if "cursor" in want:
            self.log("[cursor]")
            self._index_cursor()
        if "perplexity" in want:
            self.log("[perplexity]")
            self._index_perplexity()
        self.con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_index',?)",
                         (datetime.now().isoformat(timespec="seconds"),))
        self.con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_stats',?)",
                         (json.dumps(self.stats, ensure_ascii=False),))
        self.con.commit()
        self.log("done in %.1fs" % (time.time() - t0))
        return self.stats

    def _index_cursor(self):
        dbs = [p for p in CURSOR_VSCDB if os.path.isfile(p)]
        if os.path.isdir(CURSOR_WS_STORAGE):
            for d in os.listdir(CURSOR_WS_STORAGE):
                p = os.path.join(CURSOR_WS_STORAGE, d, "state.vscdb")
                if os.path.isfile(p):
                    dbs.append(p)
        known = self._known()
        added = 0
        for db in dbs:
            try:
                st = os.stat(db)
            except OSError:
                continue
            for key, msgs in parse_cursor_db(db):
                vpath = "%s#%s" % (db, key)
                prev = known.get(vpath)
                if prev and abs(prev[0] - st.st_mtime) < 0.5:
                    continue
                self._store(vpath, "cursor", os.path.basename(os.path.dirname(db)),
                            key, mk_title(msgs, key)[:120], msgs,
                            st.st_mtime, st.st_size, prev[2] if prev else None)
                added += 1
        self.con.commit()
        self.stats["cursor"] = {"scanned": len(dbs), "added": added,
                                "updated": 0, "unchanged": 0}
        self.log("  cursor     dbs=%d chats=%d" % (len(dbs), added))

    def _index_perplexity(self):
        frags = parse_perplexity()
        vpath = PERPLEXITY_LEVELDB + "#fragments"
        prev = self._known().get(vpath)
        if not frags:
            self.stats["perplexity"] = {"scanned": 0, "added": 0, "updated": 0,
                                        "unchanged": 0, "note": "no local text found"}
            self.log("  perplexity none (threads are server-side)")
            return
        msgs = [("fragment", None, f) for f in frags]
        self._store(vpath, "perplexity", "perplexity-desktop", "leveldb",
                    "Perplexity local text fragments (best-effort, %d)" % len(frags),
                    msgs, time.time(), 0, prev[2] if prev else None)
        self.con.commit()
        self.stats["perplexity"] = {"scanned": 1, "added": 1, "updated": 0,
                                    "unchanged": 0, "fragments": len(frags)}
        self.log("  perplexity fragments=%d" % len(frags))


def _dir_mtime(d):
    newest = 0.0
    for root, _dirs, files in os.walk(d):
        for fn in files:
            try:
                m = os.path.getmtime(os.path.join(root, fn))
            except OSError:
                continue
            if m > newest:
                newest = m
    return newest or os.path.getmtime(d)


def _glob(d, ext):
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(ext)]


def _walk(d, ext):
    out = []
    if not os.path.isdir(d):
        return out
    for root, _dirs, files in os.walk(d):
        for fn in files:
            if fn.endswith(ext):
                out.append(os.path.join(root, fn))
    return out


# ----------------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------------

def fts_query(q):
    """Turn a human query into an FTS5 MATCH expression. Quote every term."""
    q = q.strip()
    if not q:
        return None
    phrases = re.findall(r'"([^"]+)"', q)
    rest = re.sub(r'"[^"]+"', " ", q)
    terms = [t for t in re.split(r"\s+", rest) if t]
    parts = ['"%s"' % p.replace('"', "") for p in phrases]
    for t in terms:
        t = re.sub(r'["*()^:]', " ", t).strip()
        if not t:
            continue
        parts.append('"%s"*' % t)
    return " AND ".join(parts) if parts else None


def search(con, q, sources=None, limit=60):
    expr = fts_query(q)
    if not expr:
        return []
    src = list(sources or [])
    where = ""
    args = [expr]
    if src:
        where = " AND s.source IN (%s)" % ",".join("?" * len(src))
        args += src
    args.append(limit)
    sql = """
    SELECT m.id AS mid, m.sess, m.seq, m.role, m.ts, s.source, s.project, s.title,
           s.path, s.started, s.nmsg,
           snippet(msgs_fts, 0, '<mark>', '</mark>', ' … ', 24) AS snip,
           bm25(msgs_fts) AS score
    FROM msgs_fts
    JOIN msgs m ON m.id = msgs_fts.rowid
    JOIN sessions s ON s.id = m.sess
    WHERE msgs_fts MATCH ?%s
    ORDER BY score LIMIT ?
    """ % where
    try:
        rows = con.execute(sql, args).fetchall()
    except sqlite3.OperationalError as e:
        return [{"error": str(e)}]
    return [dict(r) for r in rows]


def stats(con):
    out = {"sources": [], "total_sessions": 0, "total_msgs": 0, "total_chars": 0}
    for r in con.execute(
            "SELECT source, COUNT(*) n, SUM(nmsg) m, SUM(chars) c,"
            " MIN(started) a, MAX(ended) b FROM sessions GROUP BY source ORDER BY source"):
        out["sources"].append({"source": r["source"], "sessions": r["n"],
                               "msgs": r["m"] or 0, "chars": r["c"] or 0,
                               "first": r["a"], "last": r["b"]})
        out["total_sessions"] += r["n"]
        out["total_msgs"] += r["m"] or 0
        out["total_chars"] += r["c"] or 0
    for k in ("last_index", "last_stats"):
        row = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        out[k] = row["v"] if row else None
    out["db_size"] = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    return out


def get_session(con, sess_id):
    s = con.execute("SELECT * FROM sessions WHERE id=?", (sess_id,)).fetchone()
    if not s:
        return None
    msgs = con.execute(
        "SELECT seq, role, ts, text FROM msgs WHERE sess=? ORDER BY seq", (sess_id,)).fetchall()
    return {"session": dict(s), "msgs": [dict(m) for m in msgs]}


# ----------------------------------------------------------------------------
# Web UI
# ----------------------------------------------------------------------------

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALMA-RECALL — memory + every AI chat</title>
<style>
:root{--bg:#fbfbf7;--card:#fff;--ink:#16181d;--dim:#6b7280;--line:#e6e6df;
 --acc:#0f766e;--acc2:#0d9488;--mark:#fde68a;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.55 "Segoe UI",system-ui,-apple-system,Arial,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
 padding:14px 20px 10px;z-index:5}
h1{margin:0 0 2px;font-size:19px;letter-spacing:.2px}
h1 small{color:var(--dim);font-weight:400;font-size:13px;margin-inline-start:8px}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 60px}
.searchrow{display:flex;gap:8px;margin-top:10px;max-width:1080px}
input[type=search]{flex:1;padding:11px 14px;font-size:16px;border:1.5px solid var(--line);
 border-radius:10px;background:var(--card);color:var(--ink)}
input[type=search]:focus{outline:none;border-color:var(--acc)}
button{padding:11px 16px;border:0;border-radius:10px;background:var(--acc);color:#fff;
 font-size:15px;cursor:pointer}
button:hover{background:var(--acc2)}
button.ghost{background:#fff;color:var(--ink);border:1.5px solid var(--line)}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;align-items:center}
.chip{padding:4px 11px;border:1.5px solid var(--line);border-radius:999px;background:#fff;
 cursor:pointer;font-size:13px;color:var(--dim);user-select:none}
.chip.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.chip .n{opacity:.7;font-size:11px;margin-inline-start:5px}
.hit{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;
 margin-top:10px;cursor:pointer}
.hit:hover{border-color:var(--acc)}
.hit .meta{font-size:12px;color:var(--dim);display:flex;gap:9px;flex-wrap:wrap;margin-bottom:5px}
.tag{background:#eef2f1;color:#0f766e;border-radius:5px;padding:1px 7px;font-weight:600;
 font-size:11px;text-transform:uppercase;letter-spacing:.4px}
.tag.memory{background:#fef3c7;color:#92400e}.tag.claude{background:#e0f2fe;color:#075985}
.tag.codex{background:#ecfdf5;color:#065f46}.tag.grok{background:#f3e8ff;color:#6b21a8}
.tag.gemini{background:#ffe4e6;color:#9f1239}.tag.cursor{background:#e5e7eb;color:#374151}
.tag.perplexity{background:#dbeafe;color:#1e40af}
.hit .title{font-weight:600;margin-bottom:4px}
.snip{white-space:pre-wrap;word-break:break-word;font-size:14px;color:#333}
mark{background:var(--mark);padding:0 1px;border-radius:2px}
.note{color:var(--dim);font-size:13px;margin-top:14px}
#stats table{border-collapse:collapse;width:100%;background:var(--card);
 border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-top:10px}
#stats th,#stats td{padding:8px 12px;text-align:start;border-bottom:1px solid var(--line);font-size:13px}
#stats th{background:#f4f4ee;font-weight:600}
dialog{border:0;border-radius:14px;padding:0;max-width:900px;width:92vw;max-height:86vh;
 box-shadow:0 20px 60px rgba(0,0,0,.25)}
dialog::backdrop{background:rgba(0,0,0,.35)}
.dhead{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);
 padding:12px 16px;display:flex;justify-content:space-between;gap:10px;align-items:start}
.dbody{padding:8px 16px 20px;overflow:auto;max-height:72vh}
.msg{border-top:1px solid var(--line);padding:10px 0}
.msg .r{font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.5px}
.msg .t{white-space:pre-wrap;word-break:break-word;font-size:14px;margin-top:3px}
.msg.user .r{color:#0f766e}.msg.assistant .r{color:#7c3aed}
.path{font-family:Consolas,monospace;font-size:11px;color:var(--dim);word-break:break-all}
.spin{color:var(--dim);padding:14px 0}
</style></head><body>
<header>
<h1>ALMA-RECALL <small>זיכרון + כל השיחות · memory + every AI chat, one box</small></h1>
<div class="searchrow">
  <input type="search" id="q" placeholder="Search everything… / חפש בכל…  (try: memristor, ערן, &quot;exact phrase&quot;)" autofocus>
  <button id="go">Search</button>
  <button class="ghost" id="reindex" title="Rescan all sources">↻ Reindex</button>
</div>
<div class="filters" id="filters"></div>
</header>
<div class="wrap">
  <div id="results"></div>
  <div id="stats"></div>
</div>
<dialog id="dlg"><div class="dhead"><div><div id="dtitle" style="font-weight:700"></div>
<div class="path" id="dpath"></div></div><button class="ghost" onclick="dlg.close()">Close</button></div>
<div class="dbody" id="dbody"></div></dialog>
<script>
const $=s=>document.querySelector(s);
let active=new Set(), counts={};
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function loadStats(){
  const st=await (await fetch('/api/stats')).json();
  counts={}; st.sources.forEach(s=>counts[s.source]=s.sessions);
  const order=['memory','claude','codex','grok','gemini','cursor','perplexity'];
  $('#filters').innerHTML='<span style="font-size:13px;color:#6b7280">Sources:</span>'+
    order.map(s=>`<span class="chip${active.has(s)?' on':''}" data-s="${s}">${s}<span class="n">${counts[s]||0}</span></span>`).join('');
  document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    const s=c.dataset.s; active.has(s)?active.delete(s):active.add(s);
    c.classList.toggle('on'); if($('#q').value.trim())run();});
  const rows=st.sources.map(s=>`<tr><td><span class="tag ${s.source}">${s.source}</span></td>
    <td>${s.sessions.toLocaleString()}</td><td>${(s.msgs||0).toLocaleString()}</td>
    <td>${((s.chars||0)/1e6).toFixed(1)} M</td><td>${(s.first||'').slice(0,10)}</td>
    <td>${(s.last||'').slice(0,10)}</td></tr>`).join('');
  $('#stats').innerHTML=`<div class="note">Indexed ${st.total_sessions.toLocaleString()} sessions ·
    ${st.total_msgs.toLocaleString()} messages · ${(st.total_chars/1e6).toFixed(1)} M chars ·
    db ${(st.db_size/1e6).toFixed(1)} MB · last index ${st.last_index||'—'}</div>
    <table><tr><th>source</th><th>sessions</th><th>messages</th><th>chars</th><th>first</th><th>last</th></tr>${rows}</table>`;
}
async function run(){
  const q=$('#q').value.trim(); if(!q)return;
  $('#results').innerHTML='<div class="spin">searching…</div>'; $('#stats').innerHTML='';
  const u='/api/search?q='+encodeURIComponent(q)+
    (active.size?'&source='+[...active].join(','):'');
  const r=await (await fetch(u)).json();
  if(r.error){$('#results').innerHTML='<div class="note">Query error: '+esc(r.error)+'</div>';return;}
  if(!r.hits.length){$('#results').innerHTML='<div class="note">No matches. / אין תוצאות.</div>';loadStats();return;}
  $('#results').innerHTML='<div class="note">'+r.hits.length+' hits for <b>'+esc(q)+'</b></div>'+
   r.hits.map(h=>`<div class="hit" onclick="openSess(${h.sess},${h.seq})">
    <div class="meta"><span class="tag ${h.source}">${h.source}</span>
    <span>${esc(h.role||'')}</span><span>${esc((h.ts||h.started||'').slice(0,16).replace('T',' '))}</span>
    <span>${esc((h.project||'').slice(-52))}</span><span>${h.nmsg} msgs</span></div>
    <div class="title">${esc(h.title||'')}</div>
    <div class="snip">${h.snip}</div></div>`).join('');
}
async function openSess(id,seq){
  const d=await (await fetch('/api/session?id='+id)).json();
  $('#dtitle').textContent=d.session.source.toUpperCase()+' · '+(d.session.title||'');
  $('#dpath').textContent=d.session.path;
  $('#dbody').innerHTML=d.msgs.map(m=>`<div class="msg ${m.role}" id="m${m.seq}">
    <div class="r">${esc(m.role)} ${esc((m.ts||'').slice(0,19).replace('T',' '))}</div>
    <div class="t">${esc(m.text)}</div></div>`).join('');
  dlg.showModal();
  const el=document.getElementById('m'+seq); if(el)el.scrollIntoView({block:'center'});
}
$('#go').onclick=run;
$('#q').addEventListener('keydown',e=>{if(e.key==='Enter')run();});
$('#reindex').onclick=async()=>{
  $('#reindex').textContent='indexing…'; $('#reindex').disabled=true;
  const r=await (await fetch('/api/reindex',{method:'POST'})).json();
  $('#reindex').textContent='↻ Reindex'; $('#reindex').disabled=false;
  alert('Reindex done:\n'+JSON.stringify(r.stats,null,1)); loadStats();
};
loadStats();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "AlmaRecall/1.0"
    indexing = threading.Lock()

    def log_message(self, fmt, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._send(200, PAGE, "text/html; charset=utf-8")
            con = connect()
            if u.path == "/api/stats":
                return self._send(200, stats(con))
            if u.path == "/api/search":
                q = (qs.get("q") or [""])[0]
                srcs = [s for s in (qs.get("source") or [""])[0].split(",") if s]
                lim = min(int((qs.get("limit") or ["60"])[0]), 300)
                hits = search(con, q, srcs, lim)
                if hits and isinstance(hits[0], dict) and "error" in hits[0]:
                    return self._send(200, {"error": hits[0]["error"]})
                return self._send(200, {"hits": hits})
            if u.path == "/api/session":
                d = get_session(con, int((qs.get("id") or ["0"])[0]))
                return self._send(200 if d else 404, d or {"error": "not found"})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path != "/api/reindex":
            return self._send(404, {"error": "not found"})
        if not Handler.indexing.acquire(blocking=False):
            return self._send(409, {"error": "index already running"})
        try:
            con = connect()
            init_db(con)
            st = Indexer(con).run()
            con.close()
            return self._send(200, {"ok": True, "stats": st})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": str(e)})
        finally:
            Handler.indexing.release()


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def cmd_index(args):
    con = connect()
    init_db(con)
    only = args[0].split(",") if args else None
    Indexer(con).run(only)
    s = stats(con)
    print("\nTOTAL: %d sessions, %d messages, %.1f M chars, db %.1f MB"
          % (s["total_sessions"], s["total_msgs"], s["total_chars"] / 1e6,
             s["db_size"] / 1e6))
    con.close()


def cmd_search(args):
    if not args:
        print("usage: recall.py search <query>")
        return
    con = connect()
    init_db(con)
    for h in search(con, " ".join(args), limit=25):
        if "error" in h:
            print("error:", h["error"])
            break
        snip = re.sub(r"</?mark>", "", h["snip"]).replace("\n", " ")
        print("[%s] %s  %s\n    %s\n" % (h["source"], (h["ts"] or "")[:16],
                                         (h["title"] or "")[:70], snip[:200]))
    con.close()


def cmd_stats(_args):
    con = connect()
    init_db(con)
    s = stats(con)
    print("last index:", s["last_index"])
    for r in s["sources"]:
        print("  %-11s %6d sessions  %8d msgs  %8.1f M chars  %s .. %s"
              % (r["source"], r["sessions"], r["msgs"], r["chars"] / 1e6,
                 (r["first"] or "")[:10], (r["last"] or "")[:10]))
    print("TOTAL %d sessions / %d msgs / %.1f M chars / db %.1f MB"
          % (s["total_sessions"], s["total_msgs"], s["total_chars"] / 1e6,
             s["db_size"] / 1e6))
    con.close()


def cmd_serve(_args):
    con = connect()
    init_db(con)
    con.close()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("ALMA-RECALL serving on http://127.0.0.1:%d/" % PORT)
    print("Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main():
    cmds = {"index": cmd_index, "search": cmd_search, "stats": cmd_stats, "serve": cmd_serve}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        print("usage: recall.py {index|search|stats|serve} [args]")
        return 1
    cmds[sys.argv[1]](sys.argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
