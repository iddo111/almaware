#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA-RECALL MCP server — the memory door for local coder models.
שרת MCP של ALMA-RECALL — דלת הזיכרון למודלים המקומיים.

Exposes the ALMA-RECALL index (recall.db — every Claude/Codex/Grok/Gemini/
Cursor/Perplexity chat on this PC + Claude's memory files) as MCP tools, so a
local model (qwen-code CLI etc.) can search Iddo's whole history itself instead
of answering from a blank slate.

Tools:
  recall_search(query, limit?, source?, since?)  search everything
  recall_session(id, max_chars?)                 pull one full conversation
  recall_stats()                                 what is indexed, how fresh
  project_list()                                 project dirs under D:\\CLAUDE
  memory_read(name?)                             Claude memory files (the laws)

Transports (both pure stdlib, no deps, per ALMAWARE purity):
  python recall_mcp.py stdio                     for the PC's own qwen CLI
  python recall_mcp.py http [--port 8795] [--host 0.0.0.0]
                                                 streamable-HTTP for the DGX
                                                 fleet over the tailnet

Read-only. Never writes to recall.db. Does not touch recall.py.
"""
import io
import json
import os
import re
import sqlite3
import sys
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "recall.db")
PROJECTS_ROOT = os.path.dirname(APP_DIR)  # D:\CLAUDE
HOME = os.path.expanduser("~")
MEMORY_DIR = os.path.join(HOME, ".claude", "projects", "D--CLAUDE", "memory")

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "alma-recall", "version": "1.0.0"}

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log(msg):
    sys.stderr.write("[recall-mcp] %s\n" % msg)
    sys.stderr.flush()


# ----------------------------------------------------------------------------
# DB (read-only)
# ----------------------------------------------------------------------------

def connect_ro():
    uri = "file:%s?mode=ro" % urllib.parse.quote(DB_PATH.replace("\\", "/"))
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def fts_query(q):
    """Human query -> FTS5 MATCH expression. Same shape as recall.py."""
    q = (q or "").strip()
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


def clip(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 2] + " …"


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------

def t_recall_search(args):
    query = (args.get("query") or "").strip()
    if not query:
        return "recall_search needs a non-empty `query`."
    limit = max(1, min(int(args.get("limit") or 8), 40))
    sources = [s.strip() for s in (args.get("source") or "").split(",") if s.strip()]
    since = (args.get("since") or "").strip()
    expr = fts_query(query)
    if not expr:
        return "Query reduced to nothing after sanitising."
    where, params = "", [expr]
    if sources:
        where += " AND s.source IN (%s)" % ",".join("?" * len(sources))
        params += sources
    if since:
        where += " AND COALESCE(m.ts, s.started, '') >= ?"
        params.append(since)
    params.append(limit)
    sql = """
    SELECT m.sess, m.seq, m.role, m.ts, s.source, s.project, s.title, s.started,
           snippet(msgs_fts, 0, '', '', ' … ', 30) AS snip
    FROM msgs_fts
    JOIN msgs m ON m.id = msgs_fts.rowid
    JOIN sessions s ON s.id = m.sess
    WHERE msgs_fts MATCH ?%s
    ORDER BY bm25(msgs_fts) LIMIT ?
    """ % where
    con = connect_ro()
    try:
        rows = con.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        return "Search error: %s" % e
    finally:
        con.close()
    if not rows:
        return ("No matches for %r%s. Try fewer/shorter terms, or drop the "
                "source/since filters." % (query, " (filters applied)" if (sources or since) else ""))
    out = ["%d results for %r (best first). Use recall_session(id) for a full "
           "conversation." % (len(rows), query)]
    for r in rows:
        date = (r["ts"] or r["started"] or "")[:16].replace("T", " ")
        out.append(
            "\n[session %d · %s · %s]\n  project: %s\n  title:   %s\n  (%s) %s"
            % (r["sess"], r["source"], date or "undated",
               clip(r["project"], 80), clip(r["title"], 100),
               r["role"] or "?", clip(re.sub(r"\s+", " ", r["snip"] or ""), 350)))
    return "\n".join(out)


def t_recall_session(args):
    sid = args.get("id")
    if sid is None:
        return "recall_session needs `id` (from recall_search results)."
    sid = int(sid)
    max_chars = max(1000, min(int(args.get("max_chars") or 12000), 60000))
    con = connect_ro()
    try:
        s = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not s:
            return "No session with id %d." % sid
        msgs = con.execute(
            "SELECT seq, role, ts, text FROM msgs WHERE sess=? ORDER BY seq",
            (sid,)).fetchall()
    finally:
        con.close()
    head = ("Session %d · source=%s · project=%s\ntitle: %s\nspan: %s .. %s · %d messages\n"
            % (sid, s["source"], s["project"], s["title"],
               (s["started"] or "")[:19], (s["ended"] or "")[:19], s["nmsg"]))
    parts, used = [head], len(head)
    for m in msgs:
        t = clip(re.sub(r"\n{3,}", "\n\n", m["text"] or ""), 2500)
        block = "\n--- [%d] %s %s ---\n%s" % (
            m["seq"], m["role"], (m["ts"] or "")[:19], t)
        if used + len(block) > max_chars:
            parts.append("\n… truncated at %d chars (%d of %d messages shown). "
                         "Call again with higher max_chars if needed."
                         % (max_chars, len(parts) - 1, len(msgs)))
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


def t_recall_stats(_args):
    con = connect_ro()
    try:
        rows = con.execute(
            "SELECT source, COUNT(*) n, SUM(nmsg) m, SUM(chars) c,"
            " MIN(started) a, MAX(ended) b FROM sessions GROUP BY source ORDER BY source"
        ).fetchall()
        last = con.execute("SELECT v FROM meta WHERE k='last_index'").fetchone()
    finally:
        con.close()
    tot_s = sum(r["n"] for r in rows)
    tot_m = sum(r["m"] or 0 for r in rows)
    tot_c = sum(r["c"] or 0 for r in rows)
    out = ["ALMA-RECALL index — %d sessions, %d messages, %.1f M chars."
           % (tot_s, tot_m, tot_c / 1e6),
           "Last indexed: %s" % (last["v"] if last else "unknown"), ""]
    for r in rows:
        out.append("  %-11s %6d sessions %9d msgs  %7.1f M chars  %s .. %s"
                   % (r["source"], r["n"], r["m"] or 0, (r["c"] or 0) / 1e6,
                      (r["a"] or "")[:10], (r["b"] or "")[:10]))
    return "\n".join(out)


def t_project_list(_args):
    entries = []
    try:
        for name in os.listdir(PROJECTS_ROOT):
            p = os.path.join(PROJECTS_ROOT, name)
            if not os.path.isdir(p) or name.startswith("."):
                continue
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            entries.append((mt, name))
    except OSError as e:
        return "Cannot list %s: %s" % (PROJECTS_ROOT, e)
    entries.sort(reverse=True)
    out = ["%d project directories under %s (newest activity first):"
           % (len(entries), PROJECTS_ROOT), ""]
    from datetime import datetime
    for mt, name in entries:
        out.append("  %s  %s" % (datetime.fromtimestamp(mt).strftime("%Y-%m-%d"), name))
    return "\n".join(out)


def t_memory_read(args):
    name = (args.get("name") or "").strip()
    if name and not re.fullmatch(r"[\w.\-]+", name):
        return "Bad memory name. Use the bare file name, e.g. project_dgx_topology."
    if not os.path.isdir(MEMORY_DIR):
        return "Memory directory not found at %s" % MEMORY_DIR
    if not name:
        name = "MEMORY.md"
    if not name.endswith(".md"):
        name += ".md"
    path = os.path.join(MEMORY_DIR, name)
    if not os.path.isfile(path):
        files = sorted(f for f in os.listdir(MEMORY_DIR) if f.endswith(".md"))
        return ("No memory file %r. %d files exist. Closest matches:\n  %s"
                % (name, len(files),
                   "\n  ".join(f for f in files if name[:6].lower().rstrip(".md") in f.lower())[:3000]
                   or "\n  ".join(files[:60])))
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        body = f.read(120_000)
    if name == "MEMORY.md":
        body += ("\n\n---\nEvery [name](name.md) link above is readable via "
                 "memory_read(name). That is where project details and standing laws live.")
    return body


TOOLS = [
    {
        "name": "recall_search",
        "description": (
            "Search Iddo's ENTIRE local AI history: every Claude/Codex/Grok/Gemini/"
            "Cursor conversation on this PC plus Claude's memory files (4,600+ "
            "sessions, 174k+ messages). Use this FIRST whenever a question touches "
            "past work, decisions, projects, hardware, or people — do not guess from "
            "a blank slate. Supports quoted \"exact phrases\"; terms are ANDed."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms. Hebrew and English both work."},
                "limit": {"type": "integer", "description": "Max results, default 8, max 40."},
                "source": {"type": "string", "description": "Optional comma list to filter: memory,claude,codex,grok,gemini,cursor,perplexity."},
                "since": {"type": "string", "description": "Optional ISO date, e.g. 2026-07-01 — only newer messages."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recall_session",
        "description": ("Fetch one full conversation by the session id shown in "
                        "recall_search results. Use when a snippet looks important "
                        "and you need the surrounding discussion or decision."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Session id from recall_search."},
                "max_chars": {"type": "integer", "description": "Cap on returned chars, default 12000, max 60000."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "recall_stats",
        "description": "What the ALMA-RECALL index contains per source and when it was last refreshed.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "project_list",
        "description": ("List every project directory under D:\\CLAUDE with its "
                        "last-modified date — the map of what exists at all."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_read",
        "description": (
            "Read Claude's persistent memory files — the single most valuable "
            "source: standing laws, project state, decisions. Call with no name to "
            "get MEMORY.md (the index), then call again with a file name from the "
            "index, e.g. memory_read(name='project_dgx_topology')."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Memory file name without path, .md optional. Omit for the index."},
            },
        },
    },
]

TOOL_FNS = {
    "recall_search": t_recall_search,
    "recall_session": t_recall_session,
    "recall_stats": t_recall_stats,
    "project_list": t_project_list,
    "memory_read": t_memory_read,
}


# ----------------------------------------------------------------------------
# JSON-RPC / MCP core
# ----------------------------------------------------------------------------

def rpc_result(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def rpc_error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle(msg):
    """One JSON-RPC message in -> response dict out, or None for notifications."""
    if not isinstance(msg, dict):
        return rpc_error(None, -32600, "invalid request")
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        client_proto = params.get("protocolVersion") or PROTOCOL_VERSION
        return rpc_result(rid, {
            "protocolVersion": client_proto,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
            "instructions": (
                "This server is the memory of this machine's human (Iddo) and his "
                "AI team. Before answering anything about past work, projects, "
                "decisions, or hardware: recall_search it, or memory_read() the "
                "index. Answer from what you find, with dates and sources."),
        })
    if method in ("notifications/initialized", "notifications/cancelled",
                  "notifications/roots/list_changed"):
        return None
    if rid is None:
        return None  # unknown notification — ignore
    if method == "ping":
        return rpc_result(rid, {})
    if method == "tools/list":
        return rpc_result(rid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = TOOL_FNS.get(name)
        if not fn:
            return rpc_error(rid, -32602, "unknown tool: %r" % name)
        try:
            text = fn(params.get("arguments") or {})
            return rpc_result(rid, {"content": [{"type": "text", "text": text}],
                                    "isError": False})
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return rpc_result(rid, {"content": [{"type": "text",
                                                 "text": "tool failed: %s" % e}],
                                    "isError": True})
    if method in ("resources/list", "prompts/list"):
        key = method.split("/")[0]
        return rpc_result(rid, {key: []})
    return rpc_error(rid, -32601, "method not found: %r" % method)


# ----------------------------------------------------------------------------
# Transport: stdio (newline-delimited JSON)
# ----------------------------------------------------------------------------

def serve_stdio():
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    log("stdio transport up · db=%s" % DB_PATH)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            stdout.write(json.dumps(rpc_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        resp = handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()


# ----------------------------------------------------------------------------
# Transport: streamable HTTP (stateless), for the DGX fleet over the tailnet
# ----------------------------------------------------------------------------

class McpHttpHandler(BaseHTTPRequestHandler):
    server_version = "AlmaRecallMCP/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        pass

    def _reply(self, code, obj=None):
        data = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        if data:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/health"):
            return self._reply(200, {"ok": True, "server": SERVER_INFO,
                                     "transport": "streamable-http", "endpoint": "/mcp"})
        return self._reply(405, {"error": "SSE stream not offered; POST /mcp"})

    def do_DELETE(self):
        return self._reply(200)

    def do_POST(self):
        if self.path.rstrip("/") != "/mcp":
            return self._reply(404, {"error": "POST /mcp"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception:
            return self._reply(400, rpc_error(None, -32700, "parse error"))
        if isinstance(body, list):
            resps = [r for r in (handle(m) for m in body) if r is not None]
            return self._reply(202) if not resps else self._reply(200, resps)
        resp = handle(body)
        if resp is None:
            return self._reply(202)
        return self._reply(200, resp)


def serve_http(host, port):
    srv = ThreadingHTTPServer((host, port), McpHttpHandler)
    log("streamable-HTTP up on http://%s:%d/mcp · db=%s" % (host, port, DB_PATH))
    srv.serve_forever()


# ----------------------------------------------------------------------------

def main():
    argv = sys.argv[1:]
    mode = argv[0] if argv else "stdio"
    if mode == "stdio":
        serve_stdio()
        return 0
    if mode == "http":
        host, port = "0.0.0.0", 8795
        if "--host" in argv:
            host = argv[argv.index("--host") + 1]
        if "--port" in argv:
            port = int(argv[argv.index("--port") + 1])
        serve_http(host, port)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
