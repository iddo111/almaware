# -*- coding: utf-8 -*-
"""Shared proof harness for the sense_organ (SENSES lobe) code revision, 2026-09-06.

Never touches the live organ: every test runs the CODE UNDER TEST in this process, over a
socketpair, with no port bound and no service signalled.
"""
import importlib.machinery
import importlib.util
import json
import os
import socket
import struct
import sys
import threading

_N = [0]


def load(path, env=None):
    """Import a sense_organ.py (fixed file or .bak) as a fresh throwaway module."""
    old = {}
    for k, v in (env or {}).items():
        old[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        _N[0] += 1
        name = "sense_under_test_%d" % _N[0]
        # SourceFileLoader by hand: the .bak-rev-20260906 copy has no .py suffix, and
        # spec_from_file_location alone returns None for it.
        loader = importlib.machinery.SourceFileLoader(name, path)
        spec = importlib.util.spec_from_loader(name, loader)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def pair(mod):
    """(client, server_thread) with mod.handle() serving the server end."""
    a, b = socket.socketpair()
    err = []

    def run():
        try:
            mod.handle(b)
        except BaseException as exc:            # noqa: BLE001 -- that IS the measurement
            err.append(exc)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return a, t, err


def send(sock, req, audio=b""):
    req = dict(req)
    req.setdefault("audio_bytes", len(audio))   # a caller may LIE on purpose
    body = json.dumps(req).encode("utf-8")
    sock.sendall(struct.pack("!I", len(body)) + body + audio)


def recv(sock, timeout=20.0):
    """-> (parsed_json, raw_json_bytes, audio_bytes)"""
    sock.settimeout(timeout)

    def exact(n):
        buf = b""
        while len(buf) < n:
            c = sock.recv(n - len(buf))
            if not c:
                raise ConnectionError("closed with %d/%d" % (len(buf), n))
            buf += c
        return buf
    (ln,) = struct.unpack("!I", exact(4))
    raw = exact(ln)
    res = json.loads(raw)                       # lenient, so we can SEE a bare NaN
    audio = exact(int(res.get("audio_bytes", 0)))
    return res, raw, audio


def strict(raw):
    """json.loads that refuses NaN/Infinity, the way a non-python client would."""
    def boom(c):
        raise ValueError("bare %s on the wire" % c)
    return json.loads(raw, parse_constant=boom)


def report(checks):
    """checks: list of (label, ok, detail). Prints and exits 0 only if all ok."""
    ok = True
    for label, good, detail in checks:
        print("  [%s] %s -- %s" % ("PASS" if good else "FAIL", label, detail))
        ok = ok and bool(good)
    print("PROOF %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)
