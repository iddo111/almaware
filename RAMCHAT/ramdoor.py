#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAMDOOR — RAMCHAT's door for devices that are not this PC.

Iddo, 2026-09-16: he wants Claude CLI on the phone wired into the council.
RAMCHAT lives in Windows shared memory plus two JSON files on this PC, so a
phone could not reach it at all. This is the missing door -- and ONLY a door:
it holds no state of its own, calls ramlink's own functions, and adds no
second copy of anything. One source of truth stays one source of truth.

Not a harness (ONE HARNESS LAW explicitly lists RAMCHAT as not-a-harness):
no brain, no memory, no UI. It is a socket in front of ramlink.py.

Open on the tailnet with no token, per Iddo's standing decision of 2026-09-15
("אין לי מה לגנוב") -- the tailnet IS the boundary. Bind 127.0.0.1 only and
let `tailscale serve` publish it; never bind 0.0.0.0.

    GET  /status                  is the council up
    GET  /read?tail=20            the transcript, newest last
    GET  /queue?open=1            the work queue
    POST /post   {who, text}      say something
    POST /add    {text, for}      put work on the queue
    POST /claim  {id, who}        take a task -- ATOMIC, refusal means stop
    POST /done   {id, result}     finish a task you hold

Run:  python ramdoor.py          (port 8841, claimed in RAMCHAT 2026-09-16)
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)                    # ramlink resolves its JSON files relative to cwd

import ramlink  # noqa: E402

PORT = 8841
MAX_BODY = 256 * 1024


class Door(BaseHTTPRequestHandler):
    server_version = "ramdoor/1.0"

    # ---- plumbing --------------------------------------------------------
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, code, msg, detail=""):
        # Say what broke. A door that answers {"ok":true} while the council is
        # down is the exact failure this project keeps writing laws about.
        self._send(code, {"ok": False, "error": msg, "detail": detail[:400]})

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > MAX_BODY:
            raise ValueError("body too large (%d bytes)" % n)
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def log_message(self, fmt, *a):
        sys.stderr.write("[ramdoor] %s\n" % (fmt % a))

    def do_OPTIONS(self):
        self._send(204, {})

    # ---- reads -----------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/status":
                msgs, shared, src = ramlink.get_transcript()
                items, qsrc = ramlink.get_queue()
                return self._send(200, {
                    "ok": True, "door": "ramchat", "port": PORT,
                    "messages": len(msgs),
                    "source": src, "queue_source": qsrc,
                    "queue_open": sum(1 for i in items
                                      if (i.get("status") or "open") == "open"),
                    "queue_total": len(items),
                })

            if u.path == "/read":
                tail = int((q.get("tail") or ["20"])[0])
                tail = max(1, min(tail, 500))
                msgs, shared, src = ramlink.get_transcript()
                return self._send(200, {"ok": True, "source": src,
                                        "total": len(msgs),
                                        "messages": msgs[-tail:]})

            if u.path == "/queue":
                items, qsrc = ramlink.get_queue()
                if (q.get("open") or ["0"])[0] not in ("0", "false", ""):
                    items = [i for i in items
                             if (i.get("status") or "open") == "open"]
                return self._send(200, {"ok": True, "source": qsrc,
                                        "count": len(items), "tasks": items})

            if u.path == "/handout":
                # A handout that lives only on the PC is useless to the phone
                # it was written for. Serve it from the same door it describes.
                h = os.path.join(HERE, "HANDOUT-phone-claude-20260916.md")
                if not os.path.exists(h):
                    return self._fail(404, "handout not on disk", h)
                data = open(h, encoding="utf-8").read().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                return self.wfile.write(data)

            if u.path == "/":
                return self._send(200, {
                    "ok": True, "door": "ramchat",
                    "endpoints": ["GET /status", "GET /read?tail=20",
                                  "GET /queue?open=1", "GET /handout",
                                  "POST /post {who,text}",
                                  "POST /add {text,for}", "POST /claim {id,who}",
                                  "POST /done {id,result}"],
                })
            return self._fail(404, "no such endpoint", u.path)
        except Exception as e:  # noqa: BLE001
            return self._fail(500, "%s: %s" % (type(e).__name__, e),
                              traceback.format_exc())

    # ---- writes ----------------------------------------------------------
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            b = self._body()
        except Exception as e:  # noqa: BLE001
            return self._fail(400, "bad JSON body", str(e))

        try:
            if u.path == "/post":
                who = (b.get("who") or "").strip()
                text = (b.get("text") or "").strip()
                if not who or not text:
                    return self._fail(400, "need both 'who' and 'text'")
                msgs, shared, _src = ramlink.get_transcript()
                msgs.append({"ts": ramlink.now_iso(), "who": who, "text": text})
                ramlink.put_transcript(msgs, shared)
                return self._send(200, {"ok": True, "posted_as": who,
                                        "messages": len(msgs)})

            if u.path == "/add":
                text = (b.get("text") or "").strip()
                if not text:
                    return self._fail(400, "need 'text'")
                items, _ = ramlink.get_queue()
                tid = "task-%s-%06d" % (
                    ramlink.now_iso().replace("-", "").replace(":", "")
                    .replace("T", "-").split("+")[0].split(".")[0],
                    len(items))
                items.append({"id": tid, "text": text,
                              "for": b.get("for") or "anyone",
                              "status": "open", "held": None,
                              "created": ramlink.now_iso()})
                ramlink.put_queue(items)
                return self._send(200, {"ok": True, "id": tid})

            if u.path == "/claim":
                tid, who = (b.get("id") or "").strip(), (b.get("who") or "").strip()
                if not tid or not who:
                    return self._fail(400, "need both 'id' and 'who'")
                # The claim must stay ATOMIC -- that is the one rule of RAMCHAT.
                # ramlink's Lock is what makes it atomic; use it, never bypass it.
                with ramlink.Lock():
                    items, _ = ramlink.get_queue()
                    t = next((i for i in items if i.get("id") == tid), None)
                    if t is None:
                        return self._fail(404, "no such task", tid)
                    holder = t.get("held")
                    if holder and holder != who:
                        return self._send(409, {"ok": False, "refused": True,
                                                "held_by": holder,
                                                "error": "already claimed -- pick another task"})
                    t["held"] = who
                    t["status"] = "working"
                    t["claimed_at"] = ramlink.now_iso()
                    ramlink.put_queue(items)
                return self._send(200, {"ok": True, "id": tid, "held_by": who})

            if u.path == "/done":
                tid = (b.get("id") or "").strip()
                if not tid:
                    return self._fail(400, "need 'id'")
                with ramlink.Lock():
                    items, _ = ramlink.get_queue()
                    t = next((i for i in items if i.get("id") == tid), None)
                    if t is None:
                        return self._fail(404, "no such task", tid)
                    t["status"] = "done"
                    t["result"] = (b.get("result") or "")[:2000]
                    t["done_at"] = ramlink.now_iso()
                    ramlink.put_queue(items)
                return self._send(200, {"ok": True, "id": tid})

            return self._fail(404, "no such endpoint", u.path)
        except Exception as e:  # noqa: BLE001
            return self._fail(500, "%s: %s" % (type(e).__name__, e),
                              traceback.format_exc())


if __name__ == "__main__":
    # 127.0.0.1 ONLY. tailscale serve publishes it to the tailnet; binding
    # 0.0.0.0 would put the council on the house LAN, which nobody asked for.
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Door)
    print("[ramdoor] RAMCHAT door on http://127.0.0.1:%d/  (tailnet via tailscale serve)"
          % PORT, flush=True)
    srv.serve_forever()
