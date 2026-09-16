#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""almido_remote_session.py -- ALMIDO opens linkable shells on eran2.

An ALMIDO tool around the remote-sessions door
(http://<tailnet-ip>:8895): open returns a browser link the human
opens on any device; read/write drive it. Behind almido_gate like
every other hand: no ALLOW, no shell. Fail closed if the gate
cannot be imported.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, r"D:\CLAUDE\iddo-harness")
try:
    from almido_gate import gate as _gate
except Exception:
    _gate = None

DOOR = os.environ.get("REMOTE_SESS_DOOR", "http://<tailnet-ip>:8895")


def _call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(DOOR + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)[:200]}


def _allowed(what):
    if _gate is None:
        return False, "gate missing: fail closed"
    try:
        verdict = _gate("command", what)
    except Exception as e:
        return False, "gate error: %s" % e
    ok = verdict == "ALLOW" or getattr(verdict, "allow", False) is True
    return ok, "" if ok else "gate refused"


def remote_open(cmd=""):
    ok, why = _allowed("remote session open: %s" % (cmd or "shell"))
    if not ok:
        return {"error": why}
    r = _call("POST", "/api/sessions", {"cmd": cmd})
    if "id" in r:
        r["browser_link"] = \
            "https://<tailnet-host>:8895/s/" + r["id"]
    return r


def remote_read(sid, cursor=0):
    return _call("GET", "/api/sessions/%s?from=%d" % (sid, cursor))


def remote_write(sid, text):
    ok, why = _allowed("remote session write to %s" % sid)
    if not ok:
        return {"error": why}
    return _call("POST", "/api/sessions/%s/input" % sid, {"text": text})


def remote_kill(sid):
    return _call("DELETE", "/api/sessions/%s" % sid)


def remote_list():
    return _call("GET", "/api/sessions")
