# Serve D:\Darwish\generated as a clickable, in-app-playable audio page (loopback only).
# Windows paths don't click in Iddo's app; a localhost http link does. Bright design.
import http.server, socketserver, os, html, glob, re

DIR = r"D:\Darwish\generated"
PORT = 8831

def label(fn):
    m = re.search(r"step(\d+)", fn)
    d = re.match(r"(\d{4})(\d{2})(\d{2})", fn)
    step = f"step {int(m.group(1)):,}" if m else ""
    date = f"{d.group(3)}.{d.group(2)}" if d else ""
    return (date + "  " + step).strip() or fn

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIR, **k)

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            files = sorted((os.path.basename(f) for f in glob.glob(os.path.join(DIR, "*.mp3"))), reverse=True)
            cards = []
            for f in files:
                cards.append(
                    '<div class="s"><div class="t">%s</div><div class="f">%s</div>'
                    '<audio controls preload="metadata" src="/%s"></audio></div>'
                    % (html.escape(label(f)), html.escape(f), html.escape(f))
                )
            body = (
                "<!doctype html><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                "<title>Darwish AI - samples</title><style>"
                "body{background:#fff;color:#1a1a1a;font-family:system-ui,Segoe UI,Arial;margin:0;padding:28px;}"
                "h1{font-size:22px;margin:0 0 4px} .sub{color:#666;margin:0 0 22px;font-size:14px}"
                ".s{border:1px solid #e5e5e5;border-radius:12px;padding:16px 18px;margin:0 0 14px;box-shadow:0 1px 3px #0000000d}"
                ".t{font-weight:600;font-size:16px} .f{color:#999;font-size:12px;margin:2px 0 10px}"
                "audio{width:100%}</style>"
                "<h1>&#127925; Darwish AI &mdash; generated samples</h1>"
                "<p class=sub>Your music-brain learning, one 60s sample a day. Newest first. Click play.</p>"
                + "".join(cards)
            )
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), H) as httpd:
    print("serving %s on http://127.0.0.1:%d/" % (DIR, PORT))
    httpd.serve_forever()
