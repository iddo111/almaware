# -*- coding: utf-8 -*-
"""PROOF SO-10 -- no socket timeout and no cap on the declared lengths: a client that
announced a 4 GiB header and then stalled pinned a daemon thread in recv_exact forever, and
a body that was not valid UTF-8 raised UnicodeDecodeError straight out of handle()'s except
tuple (it is a ValueError, not a JSONDecodeError) and killed the thread with a traceback.

    python3 proof_SO-10.py ~/eran-organs/sense_organ.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-10.py ~/eran-organs/sense_organ.py                    -> PASS

socketpair only. No port is bound, no service is touched.
"""
import os
import socket
import struct
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_harness as H                                          # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-organs/sense_organ.py")
print("PROOF SO-10 against %s" % PATH)
mod = H.load(PATH, env={"ERAN_ORGAN_HOST": "127.0.0.1"})
checks = []

# 1. an absurd declared header length must be refused, not waited on
cli, srv = socket.socketpair()
th = threading.Thread(target=lambda: _swallow(mod, srv), daemon=True)


def _swallow(m, s):
    try:
        m.handle(s)
    except BaseException:                                           # noqa: BLE001
        pass


th.start()
cli.sendall(struct.pack("!I", 4000000000))          # 4 GB of JSON, and then nothing
cli.settimeout(5.0)
try:
    res, raw, _ = H.recv(cli, timeout=5.0)
    got, ok = "replied %r" % (res.get("error"),), isinstance(res.get("error"), str)
except Exception as exc:                                            # noqa: BLE001
    got, ok = "no reply in 5 s (%s: %s)" % (type(exc).__name__, exc), False
checks.append(("a 4 GB header declaration is refused by name, not waited on", ok, got))
cli.close()
th.join(timeout=3.0)
checks.append(("the thread that served it is gone (not pinned in recv_exact)",
               not th.is_alive(), "alive=%s" % th.is_alive()))

# 2. a body that is not UTF-8 must not escape handle()
cli2, srv2 = socket.socketpair()
cli2.sendall(struct.pack("!I", 4) + b"\xff\xfe\xff\xfe")
try:
    mod.handle(srv2)
    got2, ok2 = "handle() returned normally", True
except UnicodeDecodeError as exc:
    got2, ok2 = "UnicodeDecodeError escaped handle(): %s" % exc, False
except Exception as exc:                                            # noqa: BLE001
    got2, ok2 = "%s escaped handle(): %s" % (type(exc).__name__, exc), False
checks.append(("a non-UTF-8 frame costs one connection, not a thread traceback", ok2, got2))
checks.append(("the connection was given a timeout",
               srv2.gettimeout() is not None,
               "gettimeout()=%r" % (srv2.gettimeout(),)))
cli2.close()

# 3. an absurd audio_bytes must be refused too
cli3, srv3 = socket.socketpair()
th3 = threading.Thread(target=lambda: _swallow(mod, srv3), daemon=True)
th3.start()
H.send(cli3, {"op": "hear", "audio_bytes": 3000000000})
try:
    res, _, _ = H.recv(cli3, timeout=5.0)
    got3 = "replied %r" % (res.get("error"),)
    ok3 = isinstance(res.get("error"), str) and "audio_bytes" in res["error"]
except Exception as exc:                                            # noqa: BLE001
    got3, ok3 = "no reply in 5 s (%s: %s)" % (type(exc).__name__, exc), False
checks.append(("a 3 GB audio declaration is refused by name", ok3, got3))
cli3.close()

# 4. control: a normal request still works after all the fences
cli4, srv4 = socket.socketpair()
th4 = threading.Thread(target=lambda: _swallow(mod, srv4), daemon=True)
th4.start()
H.send(cli4, {"op": "ping"})
res4, _, _ = H.recv(cli4, timeout=10.0)
checks.append(("control: ping still answers", res4.get("pong") is True, "res=%s" % res4))
cli4.close()

H.report(checks)
