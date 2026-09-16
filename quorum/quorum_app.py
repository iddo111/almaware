"""Windows entry point for the official QUORUM installer."""

from __future__ import annotations

import os
import threading
import webbrowser

# Born inert (project law): the installed app boots DISABLED and only shows the
# status page. The operator arms it with one deliberate click — the green
# הפעל·Enable button, which POSTs to the loopback-only /api/enable endpoint.
os.environ.setdefault("QUORUM_HOST", "127.0.0.1")
os.environ.setdefault("QUORUM_PORT", "8099")

import config  # noqa: E402  (environment must be fixed before configuration loads)
import server  # noqa: E402


def main() -> None:
    opener = threading.Timer(
        1.25,
        lambda: webbrowser.open(f"http://127.0.0.1:{config.PORT}"),
    )
    opener.daemon = True
    opener.start()
    server.main()


if __name__ == "__main__":
    main()
