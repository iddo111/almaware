#!/usr/bin/env python3
"""HELIOS - static document server for the tailnet. Port 8840 (claimed in RAMCHAT 2026-09-16).
Not a harness: serves files, holds no brain and no memory."""
import http.server, socketserver, os, sys

PORT = 8840
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def log_message(self, fmt, *args):
        sys.stderr.write("[helios] %s\n" % (fmt % args))

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as httpd:
        print(f"[helios] serving {ROOT} on http://127.0.0.1:{PORT}/", flush=True)
        httpd.serve_forever()
