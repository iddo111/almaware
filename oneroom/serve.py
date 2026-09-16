# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Serve the one room.

    http://127.0.0.1:8880/          walk in

A live 127.0.0.1 page is the ONLY thing that renders clickable in Iddo's app — an
absolute Windows path does not, and a raw .html on the Desktop is swept away by the
tidy task within the hour. So this is the door.

`/gate.json` is served straight out of `out/`, so the measurements panel in the page
always shows what the ruler last actually measured. If the gate has not run, the
page says so rather than showing a number from somewhere else.

Port 8880, claimed in RAMCHAT before binding. BELOW_NORMAL: nothing on this PC may
compete with Iddo's live microphone. Pure stdlib.
"""
from __future__ import annotations

import http.server
import os
import shutil
import sys

# Under pythonw.exe there is NO console, so sys.stdout is None and
# `sys.stdout.reconfigure(...)` raises AttributeError before anything binds — which
# is exactly how this server silently failed to start detached the first time. Log
# to a file instead, and never assume a console exists.
HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or not hasattr(sys.stdout, "reconfigure"):
    sys.stdout = sys.stderr = open(os.path.join(HERE, "serve.log"), "a",
                                   encoding="utf-8", buffering=1)
else:
    sys.stdout.reconfigure(encoding="utf-8")
WEB = os.path.join(HERE, "web")
OUT = os.path.join(HERE, "out")
HUB = r"D:\CLAUDE\_deliverables\hub"
PORT = 8880


class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "application/javascript",
                      ".json": "application/json",
                      ".bin": "application/octet-stream",
                      ".html": "text/html; charset=utf-8"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def translate_path(self, path):
        if path.split("?")[0] == "/gate.json":
            return os.path.join(OUT, "gate.json")
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass                      # quiet: this runs beside a live microphone


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def publish_to_hub() -> None:
    """The JPEG still belongs where the tidy task cannot reach it (:8868)."""
    try:
        os.makedirs(HUB, exist_ok=True)
        for src, dst in (("room-lit.jpg", "oneroom-workshop-lit.jpg"),
                         ("room-dark.jpg", "oneroom-workshop-dark.jpg")):
            p = os.path.join(WEB, src)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(HUB, dst))
                print(f"  hub: {dst}")
    except Exception as e:
        print(f"  hub copy failed: {e}")


def main() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        print("priority BELOW_NORMAL")
    except Exception as e:
        print(f"priority: could not lower ({e})")
    publish_to_hub()
    print(f"  one room  http://127.0.0.1:{PORT}/")
    Server(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
