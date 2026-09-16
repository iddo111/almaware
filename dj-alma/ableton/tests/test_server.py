# -*- coding: utf-8 -*-
"""test_server.py -- exercises DJ_ALMIDO/server.py's real socket framing
(non-blocking accept, partial-line buffering, multiple-commands-in-one-recv)
over an actual loopback TCP connection. This does NOT touch Live or the
`ableton`/`Live` modules -- server.py is pure stdlib, and DJ_ALMIDO/__init__.py
only imports those lazily inside create_instance(), so `from DJ_ALMIDO.server
import TCPJSONServer` is safe from a plain host Python with no Ableton
running (see __init__.py's own docstring on why that import is lazy).

Binds to port 0 (OS-assigned free port) so this never collides with the
claimed :8865 or the booth's :8863.
"""
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ABLETON_DIR = os.path.dirname(HERE)  # D:\CLAUDE\dj-alma\ableton
if ABLETON_DIR not in sys.path:
    sys.path.insert(0, ABLETON_DIR)

from DJ_ALMIDO.server import TCPJSONServer


def _drain_reply(server, client, timeout_s=2.0):
    """Poll server.process() and read from client until a full newline-
    terminated reply has arrived, or the timeout expires."""
    deadline = time.time() + timeout_s
    buf = b""
    client.settimeout(0.05)
    while time.time() < deadline:
        server.process()
        try:
            chunk = client.recv(65536)
            if chunk:
                buf += chunk
        except socket.timeout:
            pass
        except BlockingIOError:
            pass
        if b"\n" in buf:
            break
    return buf


def test_single_command_roundtrip():
    received = []

    def on_message(msg):
        received.append(msg)
        return {"ok": True, "cmd": msg.get("cmd"), "result": {"echo": True}}

    server = TCPJSONServer("127.0.0.1", 0, on_message)
    port = server._listen_sock.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        client.sendall(b'{"cmd": "PING"}\n')
        buf = _drain_reply(server, client)
        line, _, _ = buf.partition(b"\n")
        reply = json.loads(line.decode("utf-8"))
        assert reply["ok"] is True
        assert reply["cmd"] == "PING"
        assert received == [{"cmd": "PING"}]
    finally:
        client.close()
        server.shutdown()


def test_command_split_across_two_sends():
    """A command whose JSON line is split mid-write (e.g. a large WRITE_NOTES
    payload with many notes) must still be reassembled correctly before
    dispatch sees it."""
    received = []

    def on_message(msg):
        received.append(msg)
        return {"ok": True, "cmd": msg.get("cmd")}

    server = TCPJSONServer("127.0.0.1", 0, on_message)
    port = server._listen_sock.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        payload = json.dumps({"cmd": "SET_TEMPO", "param": 64}).encode("utf-8")
        half = len(payload) // 2
        client.sendall(payload[:half])
        server.process()  # nothing to dispatch yet -- no newline received
        assert received == []
        client.sendall(payload[half:] + b"\n")
        _drain_reply(server, client)
        assert received == [{"cmd": "SET_TEMPO", "param": 64}]
    finally:
        client.close()
        server.shutdown()


def test_two_commands_in_one_send():
    received = []

    def on_message(msg):
        received.append(msg)
        return {"ok": True, "cmd": msg.get("cmd")}

    server = TCPJSONServer("127.0.0.1", 0, on_message)
    port = server._listen_sock.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        two = (json.dumps({"cmd": "PLAY"}) + "\n" + json.dumps({"cmd": "STOP"}) + "\n").encode("utf-8")
        client.sendall(two)
        deadline = time.time() + 2
        while time.time() < deadline and len(received) < 2:
            server.process()
            time.sleep(0.01)
        assert received == [{"cmd": "PLAY"}, {"cmd": "STOP"}]
    finally:
        client.close()
        server.shutdown()


def test_bad_json_gets_error_reply_not_a_crash():
    server = TCPJSONServer("127.0.0.1", 0, lambda msg: {"ok": True})
    port = server._listen_sock.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        client.sendall(b"{not json at all\n")
        buf = _drain_reply(server, client)
        line, _, _ = buf.partition(b"\n")
        reply = json.loads(line.decode("utf-8"))
        assert reply["ok"] is False
    finally:
        client.close()
        server.shutdown()


def test_dispatch_exception_is_caught_and_reported():
    def on_message(msg):
        raise RuntimeError("boom")

    server = TCPJSONServer("127.0.0.1", 0, on_message)
    port = server._listen_sock.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        client.sendall(b'{"cmd": "PLAY"}\n')
        buf = _drain_reply(server, client)
        line, _, _ = buf.partition(b"\n")
        reply = json.loads(line.decode("utf-8"))
        assert reply["ok"] is False
        assert "boom" in reply["error"]
    finally:
        client.close()
        server.shutdown()


if __name__ == "__main__":
    import inspect
    fails = 0
    tests = [obj for name, obj in sorted(globals().items())
             if name.startswith("test_") and inspect.isfunction(obj)]
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            fails += 1
            print(f"ERROR {t.__name__}: {e!r}")
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
