# -*- coding: utf-8 -*-
"""server.py -- a non-blocking TCP/JSON socket server that lives inside
Live's own process.

WHY NON-BLOCKING, NOT A THREAD: Live's embedded Python does not support
starting a normal blocking-accept() thread safely from inside a Control
Surface (this is documented first-hand in AbletonOSC's manager.py: "Live's
embedded Python implementation does not appear to support threading, and
beachballs when a thread is started"). AbletonOSC's own fix -- a non-blocking
UDP socket, polled once per ~100ms "tick" from ControlSurface.schedule_message
-- is the confirmed-working pattern for this exact Live version (see
DJ_ALMIDO/__init__.py's docstring for how that was verified against real,
current source, not guessed). This module is the same pattern over TCP
instead of UDP: a non-blocking listening socket, non-blocking client sockets,
and a `process()` method meant to be called from manager.py's tick().

WIRE FORMAT: newline-delimited JSON, one command object per line in, one
JSON reply object per line out. e.g.
    -> {"cmd": "PLAY"}
    <- {"ok": true, "cmd": "PLAY", "result": null}
    -> {"cmd": "SET_TEMPO", "param": 64}
    <- {"ok": true, "cmd": "SET_TEMPO", "result": {"bpm": 140.0}}
    -> {"cmd": "WRITE_NOTES", "track_index": 4, "clip_slot_index": 0,
        "notes": [{"pitch": 60, "start_time": 0.0, "duration": 0.5}],
        "clip_length_beats": 32.0}
    <- {"ok": false, "cmd": "WRITE_NOTES", "error": "track_index 4 out of range (0..3)"}

process() never raises out to the caller -- a malformed line, a dispatch
exception, or a dead socket is logged and skipped, never crashes the tick
loop (a crashed tick loop means Live silently stops responding to ALL
DJ_ALMIDO commands, mid-set, with no visible error -- worse than one bad
command being dropped).
"""
import errno
import json
import socket


NONBLOCKING_ERRNOS = (errno.EWOULDBLOCK, errno.EAGAIN)


class TCPJSONServer:
    def __init__(self, host, port, on_message, logger=None):
        """on_message: callable(dict) -> dict. Called once per complete
        newline-delimited JSON object received; must return a JSON-serializable
        dict to send back (this module handles the ok/error envelope only when
        on_message itself raises -- on_message is expected to return its own
        {"ok": ..., ...} shaped dict; see dispatch.py)."""
        self.host = host
        self.port = port
        self.on_message = on_message
        self.logger = logger
        self._clients = {}  # socket -> bytes (partial buffer)
        self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_sock.setblocking(False)
        self._listen_sock.bind((host, port))
        self._listen_sock.listen(5)
        self._log(f"DJ_ALMIDO: listening on {host}:{port}")

    def _log(self, msg):
        if self.logger:
            try:
                self.logger(msg)
            except Exception:
                pass

    # -- accept ---------------------------------------------------------
    def _accept_new(self):
        while True:
            try:
                conn, addr = self._listen_sock.accept()
            except OSError as e:
                if e.errno in NONBLOCKING_ERRNOS or isinstance(e, BlockingIOError):
                    break
                # Any other accept() error: stop trying this tick, do not crash.
                self._log(f"DJ_ALMIDO: accept() error: {e!r}")
                break
            conn.setblocking(False)
            self._clients[conn] = b""
            self._log(f"DJ_ALMIDO: client connected from {addr}")

    # -- close ------------------------------------------------------------
    def _close_client(self, sock):
        self._clients.pop(sock, None)
        try:
            sock.close()
        except OSError:
            pass

    # -- send ---------------------------------------------------------------
    def _send(self, sock, obj):
        try:
            line = (json.dumps(obj, default=str) + "\n").encode("utf-8")
            sock.sendall(line)
        except OSError as e:
            self._log(f"DJ_ALMIDO: send failed, dropping client: {e!r}")
            self._close_client(sock)

    # -- one poll, called every tick -----------------------------------------
    def process(self):
        self._accept_new()
        for sock in list(self._clients.keys()):
            buf = self._clients.get(sock, b"")
            try:
                while True:
                    chunk = sock.recv(65536)
                    if chunk == b"":
                        # Peer closed the connection cleanly.
                        self._close_client(sock)
                        buf = None
                        break
                    buf += chunk
            except OSError as e:
                if not (e.errno in NONBLOCKING_ERRNOS or isinstance(e, BlockingIOError)):
                    self._log(f"DJ_ALMIDO: recv error, dropping client: {e!r}")
                    self._close_client(sock)
                    buf = None

            if buf is None:
                continue  # client was closed above

            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                self._clients[sock] = buf
                line = line.strip()
                if not line:
                    continue
                self._handle_line(sock, line)
            self._clients[sock] = buf

    def _handle_line(self, sock, raw_line: bytes):
        try:
            msg = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            self._log(f"DJ_ALMIDO: bad JSON, dropped: {raw_line!r} ({e!r})")
            self._send(sock, {"ok": False, "error": f"bad JSON: {e}"})
            return
        try:
            reply = self.on_message(msg)
        except Exception as e:  # a bad command must never kill the tick loop
            self._log(f"DJ_ALMIDO: dispatch raised for {msg!r}: {e!r}")
            reply = {"ok": False, "cmd": msg.get("cmd") if isinstance(msg, dict) else None,
                     "error": repr(e)}
        self._send(sock, reply)

    def shutdown(self):
        for sock in list(self._clients.keys()):
            self._close_client(sock)
        try:
            self._listen_sock.close()
        except OSError:
            pass
        self._log("DJ_ALMIDO: server shut down")
