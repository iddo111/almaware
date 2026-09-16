#!/usr/bin/env python3
"""
ALMA FS MCP  --  filesystem tools for gpt-oss-120b / GLM / any MCP client.

Speaks BOTH MCP HTTP transports, so it connects to whatever your UI expects:

  * Streamable HTTP (current spec)   POST /mcp      + GET /mcp  (SSE stream)
  * HTTP+SSE (legacy transport)      GET  /sse      + POST /messages?session_id=

Stdlib only -- no pip install, nothing to break.

Point any MCP-capable chat UI at:  http://<host>:8930/mcp
If that UI wants the old transport, give it:  http://<host>:8930/sse

Tools: write_file, append_file, read_file, list_dir, delete_file
Writes are confined to ALLOWED_ROOTS.
"""

import json
import os
import queue
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HOST = os.environ.get("ALMA_FS_HOST", "0.0.0.0")
PORT = int(os.environ.get("ALMA_FS_PORT", "8930"))

# Everything the model is allowed to touch. Anything outside is refused.
ALLOWED_ROOTS = [
    os.path.abspath(p)
    for p in (
        os.environ.get("ALMA_FS_ROOTS")
        or r"D:\;C:\Users\<user>\Desktop;C:\Users\<user>\Downloads"
    ).split(";")
    if p.strip()
]

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "alma-fs", "version": "1.1.0"}

# session_id -> Queue of outbound JSON-RPC messages (legacy SSE transport)
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()


def _resolve(path: str) -> str:
    """Absolute path, or raise if it escapes the allowed roots."""
    if not path or not path.strip():
        raise ValueError("path is required")
    p = os.path.abspath(os.path.expanduser(path.strip()))
    for root in ALLOWED_ROOTS:
        if p == root or p.startswith(root.rstrip("\\/") + os.sep):
            return p
    raise ValueError(
        f"path outside allowed roots: {p}\nallowed: {'; '.join(ALLOWED_ROOTS)}"
    )


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "write_file",
        "description": (
            "Write text to a file on the user's machine, creating parent "
            "directories as needed. Overwrites an existing file. Use this "
            "whenever the user asks you to create or save a file -- you CAN "
            "write to their disk, do not hand back a code snippet instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": r"Absolute path, e.g. D:\notes\hello.txt",
                },
                "content": {"type": "string", "description": "Full file contents"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "append_file",
        "description": "Append text to the end of a file, creating it if absent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the user's machine and return its contents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_bytes": {"type": "integer", "description": "Default 200000"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": "List the files and folders in a directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a single file. Does not touch directories.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]


def tool_write_file(args):
    p = _resolve(args.get("path", ""))
    content = args.get("content", "")
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return f"Wrote {len(content.encode('utf-8'))} bytes to {p}"


def tool_append_file(args):
    p = _resolve(args.get("path", ""))
    content = args.get("content", "")
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return f"Appended {len(content.encode('utf-8'))} bytes to {p}"


def tool_read_file(args):
    p = _resolve(args.get("path", ""))
    limit = int(args.get("max_bytes") or 200000)
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read(limit)


def tool_list_dir(args):
    p = _resolve(args.get("path", ""))
    rows = []
    for name in sorted(os.listdir(p)):
        full = os.path.join(p, name)
        if os.path.isdir(full):
            rows.append(f"[dir]  {name}")
        else:
            rows.append(f"       {name}  ({os.path.getsize(full)} bytes)")
    return "\n".join(rows) or "(empty)"


def tool_delete_file(args):
    p = _resolve(args.get("path", ""))
    if os.path.isdir(p):
        raise ValueError("refusing to delete a directory")
    os.remove(p)
    return f"Deleted {p}"


HANDLERS = {
    "write_file": tool_write_file,
    "append_file": tool_append_file,
    "read_file": tool_read_file,
    "list_dir": tool_list_dir,
    "delete_file": tool_delete_file,
}


# --------------------------------------------------------------------------
# JSON-RPC / MCP
# --------------------------------------------------------------------------

def handle_rpc(msg):
    """Return a response dict, or None for notifications."""
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    if method == "initialize":
        # Echo the client's protocol version when we understand it; some
        # clients hang up on a version they did not ask for.
        want = params.get("protocolVersion") or PROTOCOL_VERSION
        return ok(
            {
                "protocolVersion": want,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "You have real access to this machine's filesystem. When the "
                    "user asks for a file to be written, call write_file -- never "
                    "reply that you cannot touch their computer."
                ),
            }
        )

    if method in ("notifications/initialized", "initialized"):
        return None
    if method and method.startswith("notifications/"):
        return None

    if method == "ping":
        return ok({})

    if method == "tools/list":
        return ok({"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if fn is None:
            return err(-32602, f"unknown tool: {name}")
        try:
            text = fn(args)
            return ok({"content": [{"type": "text", "text": str(text)}], "isError": False})
        except Exception as exc:  # surfaced to the model so it can retry
            return ok(
                {"content": [{"type": "text", "text": f"ERROR: {exc}"}], "isError": True}
            )

    if method in ("resources/list", "prompts/list"):
        return ok({method.split("/")[0]: []})
    if method == "resources/templates/list":
        return ok({"resourceTemplates": []})

    return err(-32601, f"method not found: {method}")


STATUS_PAGE = """<!doctype html>
<meta charset="utf-8"><title>ALMA FS MCP</title>
<style>
 body{{font:15px/1.6 system-ui,sans-serif;max-width:640px;margin:8vh auto;padding:0 20px;
      background:#0f1115;color:#e7e9ee}}
 code{{background:#1b1f27;padding:2px 7px;border-radius:5px;color:#8fd3ff}}
 .ok{{color:#5ad18a;font-weight:600}} h1{{font-size:20px}}
 li{{margin:.3em 0}} .m{{color:#9aa3b2}}
</style>
<h1>ALMA FS MCP <span class="ok">&#9679; running</span></h1>
<p class="m">This URL is an MCP endpoint, not a web page. Your browser sends GET;
MCP clients POST here. Nothing is wrong.</p>
<p>Add <b>one</b> of these in your chat UI's MCP settings:</p>
<ul>
  <li>Streamable HTTP &mdash; <code>{base}/mcp</code></li>
  <li>Legacy SSE &mdash; <code>{base}/sse</code></li>
</ul>
<p>Tools: {tools}</p>
<p class="m">Writable roots: {roots}</p>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s  %s\n" % (self.address_string(), fmt % a))

    # ---------------- helpers ----------------

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Mcp-Session-Id", "alma-fs")
        self._cors()
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _open_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Mcp-Session-Id", "alma-fs")
        self._cors()
        self.end_headers()

    def _sse_write(self, raw: str):
        self.wfile.write(raw.encode("utf-8"))
        self.wfile.flush()

    def _wants_html(self):
        return "text/html" in (self.headers.get("Accept") or "")

    def _base_url(self):
        host = self.headers.get("Host") or f"127.0.0.1:{PORT}"
        return f"http://{host}"

    # ---------------- verbs ----------------

    def do_OPTIONS(self):
        self._send(204)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path in ("/health", "/mcp/health"):
            return self._send(
                200,
                json.dumps(
                    {"status": "ok", "server": SERVER_INFO, "roots": ALLOWED_ROOTS,
                     "endpoints": ["/mcp", "/sse"]}
                ).encode(),
            )

        # Legacy HTTP+SSE transport: stream opens here, client POSTs to /messages.
        if path == "/sse":
            sid = uuid.uuid4().hex
            q = queue.Queue()
            with SESSIONS_LOCK:
                SESSIONS[sid] = q
            try:
                self._open_sse()
                self._sse_write(f"event: endpoint\ndata: /messages?session_id={sid}\n\n")
                while True:
                    try:
                        item = q.get(timeout=15)
                    except queue.Empty:
                        self._sse_write(": keepalive\n\n")
                        continue
                    if item is None:
                        break
                    self._sse_write(f"event: message\ndata: {json.dumps(item)}\n\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with SESSIONS_LOCK:
                    SESSIONS.pop(sid, None)
            return

        # Streamable HTTP: GET opens the server->client stream. We never push
        # unsolicited messages, so this is a keepalive-only stream. Clients that
        # open it stay connected instead of erroring out.
        if path in ("/mcp", "/"):
            if self._wants_html():
                body = STATUS_PAGE.format(
                    base=self._base_url(),
                    tools=", ".join(t["name"] for t in TOOLS),
                    roots="; ".join(ALLOWED_ROOTS),
                ).encode("utf-8")
                return self._send(200, body, "text/html; charset=utf-8")
            try:
                self._open_sse()
                while True:
                    time.sleep(15)
                    self._sse_write(": keepalive\n\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return

        self._send(404, b'{"error":"not found"}')

    def do_DELETE(self):
        self._send(204)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            msg = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            return self._send(
                400,
                json.dumps(
                    {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": f"parse error: {exc}"}}
                ).encode(),
            )

        # Legacy transport: reply travels back over the client's SSE stream.
        if path == "/messages":
            sid = (parse_qs(parsed.query).get("session_id") or [None])[0]
            with SESSIONS_LOCK:
                q = SESSIONS.get(sid)
            if q is None:
                return self._send(404, b'{"error":"unknown or expired session_id"}')
            for m in msg if isinstance(msg, list) else [msg]:
                r = handle_rpc(m)
                if r is not None:
                    q.put(r)
            return self._send(202, b'{"status":"accepted"}')

        # Streamable HTTP: reply inline.
        if isinstance(msg, list):
            out = [r for r in (handle_rpc(m) for m in msg) if r is not None]
            return self._send(202) if not out else self._send(200, json.dumps(out).encode())

        resp = handle_rpc(msg)
        if resp is None:
            return self._send(202)
        return self._send(200, json.dumps(resp).encode())


def main():
    for root in ALLOWED_ROOTS:
        print(f"  allowed root: {root}")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    print(f"ALMA FS MCP  streamable: http://{HOST}:{PORT}/mcp", flush=True)
    print(f"ALMA FS MCP  legacy sse: http://{HOST}:{PORT}/sse", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
