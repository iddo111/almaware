# -*- coding: utf-8 -*-
"""Shared proof harness for eran-throat-listen.py, 2026-09-06 code revision.

Loads the page code under test and serves ONE request on 127.0.0.1 with an ephemeral
port the kernel picks. It never binds 8845 and never touches the running server (pid 3252).
"""
import http.client
import importlib.machinery
import importlib.util
import sys
import threading

_N = [0]


def load(path):
    _N[0] += 1
    name = "listen_under_test_%d" % _N[0]
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def get(mod, path="/"):
    """-> (status, body_bytes). Throwaway server on 127.0.0.1:0, shut down after."""
    srv = mod.S(("127.0.0.1", 0), mod.H)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        conn.request("GET", path)
        r = conn.getresponse()
        body = r.read()
        conn.close()
        return r.status, body
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)


def report(checks):
    ok = True
    for label, good, detail in checks:
        print("  [%s] %s -- %s" % ("PASS" if good else "FAIL", label, detail))
        ok = ok and bool(good)
    print("PROOF %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)
