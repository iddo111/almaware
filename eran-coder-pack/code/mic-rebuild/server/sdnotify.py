"""stdlib sd_notify — K10 (PHASE2-DESIGN.md sections 2 + 6).

One datagram to $NOTIFY_SOCKET, zero dependencies. The server pets the
systemd watchdog (WATCHDOG=1) ONLY after a successful canary decode —
scar 5 (health = real output, never process-alive) wired into the
supervisor itself. Off systemd (no NOTIFY_SOCKET, or a platform without
AF_UNIX) every call is a quiet no-op returning False.
"""
from __future__ import annotations

import os
import socket

READY = "READY=1"
WATCHDOG = "WATCHDOG=1"
STOPPING = "STOPPING=1"


def notify(state: str, env=None) -> bool:
    """Send one sd_notify datagram. False = not under systemd / send failed."""
    env = os.environ if env is None else env
    path = env.get("NOTIFY_SOCKET")
    if not path or not hasattr(socket, "AF_UNIX"):
        return False
    # An abstract-namespace socket starts with '@' in the env var.
    addr = "\0" + path[1:] if path.startswith("@") else path
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.send(state.encode("utf-8"))
        return True
    except OSError:
        return False


class Notifier:
    """The server's handle on systemd; injectable/stubable in tests."""

    def __init__(self, env=None):
        self._env = env

    def ready(self) -> bool:
        return notify(READY, env=self._env)

    def watchdog(self) -> bool:
        return notify(WATCHDOG, env=self._env)

    def stopping(self) -> bool:
        return notify(STOPPING, env=self._env)
