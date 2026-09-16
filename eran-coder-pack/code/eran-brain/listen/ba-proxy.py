"""A clickable door to ERAN's throat.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The listening window lives on eran2 at <tailnet-ip>:8845. A Tailscale address does not
render as a clickable link in Iddo's app; **127.0.0.1 does** (CLICKABLE-ACCESS LAW).
So this forwards, unchanged, from the PC's loopback to eran2.

Nothing is cached, nothing is stored, nothing is played. It is a door.

    python ba-proxy.py          ->  http://127.0.0.1:8846/
"""
import http.server
import socketserver
import urllib.error
import urllib.request

UPSTREAM = "http://<tailnet-ip>:8845"
PORT = 8846
HOP = {"connection", "keep-alive", "transfer-encoding", "upgrade",
       "proxy-authenticate", "proxy-authorization", "te", "trailers"}


class Door(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        try:
            with urllib.request.urlopen(UPSTREAM + self.path, timeout=30) as r:
                body = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() not in HOP and k.lower() != "content-length":
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            self.send_error(e.code, e.reason)
        except Exception as e:                                    # noqa: BLE001
            msg = ("<h2>eran2 לא עונה</h2><p>%s</p>"
                   "<p>The listening window on eran2:8845 is unreachable from here. "
                   "Check Tailscale, then <code>systemctl --user status "
                   "eran-throat-listen</code> on eran2.</p>" % e).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print("door open: http://127.0.0.1:%d/  ->  %s" % (PORT, UPSTREAM), flush=True)
    S(("127.0.0.1", PORT), Door).serve_forever()
