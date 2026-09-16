#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ALMA EMDR - standalone launcher.

Serves the EMDR tool from http://127.0.0.1:<port>/ and opens it in a browser
window with no address bar (Edge/Chrome --app mode).

WHY A LOCAL SERVER AND NOT JUST THE .html FILE:
  the WebSerial API (which drives the buzzer box over USB) only works in a
  "secure context". file:// is NOT one. http://127.0.0.1 IS one. So the EXE
  serves the page to itself, and the buzzer box works.

Build the EXE:
  pyinstaller --onefile --noconsole --name ALMA-EMDR \
      --add-data "ALMA-EMDR.html;." alma_emdr_launcher.py
"""
import os
import sys
import time
import socket
import threading
import webbrowser
import subprocess
import http.server
import socketserver

APP_NAME = "ALMA-EMDR"
HTML_NAME = "ALMA-EMDR.html"
PREFERRED_PORTS = [8931, 8932, 8933, 8934, 8935, 0]


def resource_dir():
    """PyInstaller unpacks --add-data into sys._MEIPASS; else use script dir."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def load_html():
    path = os.path.join(resource_dir(), HTML_NAME)
    with open(path, "rb") as fh:
        return fh.read()


HTML_BYTES = load_html()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/" + HTML_NAME):
            self._send(HTML_BYTES)
        elif path == "/health":
            self._send(b"ok", "text/plain; charset=utf-8")
        elif path == "/favicon.ico":
            self._send(b"", "image/x-icon", 204)
        else:
            self._send("<h1>404</h1>".encode("utf-8"), code=404)

    def log_message(self, *a):
        pass  # silence


def free_port():
    for p in PREFERRED_PORTS:
        try:
            s = socket.socket()
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError("no free port")


def find_browser():
    """Return (exe, arg_template) for a Chromium browser that supports --app."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def main():
    port = free_port()
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    url = "http://127.0.0.1:%d/" % port
    browser = find_browser()
    proc = None
    if browser:
        profile = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AlmaEmdrProfile")
        try:
            proc = subprocess.Popen([
                browser,
                "--app=" + url,
                "--user-data-dir=" + profile,
                "--window-size=1280,800",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate,AutofillServerCommunication",
            ])
        except Exception:
            proc = None
    if proc is None:
        webbrowser.open(url)

    if proc is not None:
        proc.wait()            # exe lives as long as the window
    else:
        # opened in the default browser - keep serving until the user closes us
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    httpd.shutdown()


if __name__ == "__main__":
    main()
