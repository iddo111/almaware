# -*- coding: utf-8 -*-
"""send.py -- PC-side stdlib socket client for DJ_ALMIDO, the Ableton Live
Remote Script (DJ_ALMIDO/, listening on 127.0.0.1:8865 once installed and
selected as a Control Surface -- see INSTALL.md). Speaks the same
newline-delimited JSON protocol DJ_ALMIDO/server.py implements.

Mirrors bridge/midi_out.py's shape (open once, send many, close on exit;
fails LOUDLY and honestly when the peer is not reachable, never pretends a
send worked) but over TCP/JSON instead of a MIDI port, because that is what
DJ_ALMIDO actually listens on -- see DJ_ALMIDO/__init__.py's docstring for
why a socket, not MIDI, was the right choice on the Ableton side.
"""
import json
import socket
import sys

HOST = "127.0.0.1"
PORT = 8865  # claimed in RAMCHAT 2026-09-08 (claude-cli-FABLE-dj); see DJ_ALMIDO/manager.py
TIMEOUT_S = 3.0


class NotConnected(RuntimeError):
    pass


class Sender:
    """Thin stateful wrapper: connect once, send many commands, close on
    exit. dry_run=True never opens a socket -- prints what it would have
    sent, for testing the pipeline before Ableton/DJ_ALMIDO is running."""

    def __init__(self, host: str = HOST, port: int = PORT, dry_run: bool = False,
                 timeout: float = TIMEOUT_S):
        self.host = host
        self.port = port
        self.dry_run = dry_run
        self.timeout = timeout
        self._sock = None
        self._buf = b""
        if not dry_run:
            self._connect()

    def _connect(self):
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as e:
            raise NotConnected(
                f"Could not connect to DJ_ALMIDO at {self.host}:{self.port} ({e}). "
                f"Is Ableton Live open with DJ_ALMIDO selected as a Control Surface "
                f"(Preferences -> Link/MIDI)? See ableton/INSTALL.md."
            ) from e

    def send_command(self, cmd: str, **fields) -> dict:
        """Send one command {"cmd": cmd, **fields}, wait for and return the
        one JSON reply line (a dict with at least "ok": bool). Raises
        NotConnected on any transport failure -- never fabricates a reply."""
        msg = {"cmd": cmd}
        msg.update(fields)
        if self.dry_run or self._sock is None:
            print(f"[send.py DRY-RUN] would send {msg}", file=sys.stderr)
            return {"ok": True, "cmd": cmd, "result": None, "dry_run": True}
        line = (json.dumps(msg) + "\n").encode("utf-8")
        try:
            self._sock.sendall(line)
            reply_line = self._read_line()
        except OSError as e:
            raise NotConnected(f"send/recv to DJ_ALMIDO failed: {e}") from e
        return json.loads(reply_line.decode("utf-8"))

    def _read_line(self) -> bytes:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if chunk == b"":
                raise NotConnected("DJ_ALMIDO closed the connection")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def main():
    """CLI smoke helper: python send.py [--dry-run] [--host H] [--port P] CMD [--param N]
    e.g.  python send.py --dry-run PLAY
          python send.py --dry-run SET_TEMPO --param 64
          python send.py PING"""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd")
    ap.add_argument("--param", type=int, default=None)
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fields = {}
    if args.param is not None:
        fields["param"] = args.param

    with Sender(args.host, args.port, dry_run=args.dry_run) as sender:
        reply = sender.send_command(args.cmd, **fields)
        print(json.dumps(reply, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
