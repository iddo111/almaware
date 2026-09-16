#!/usr/bin/env python3
# ALMA PRIVATE MASTER DASH — Iddo's eyes only.
# Token-gated (?key=... sets a cookie), bound to Tailscale + loopback. 100% stdlib, ours.
# Serves the consolidated product index with in-browser players + range streaming.
import http.server, socketserver, os, sys, json, html, re, secrets, urllib.parse

BASE = r"D:\CLAUDE\alma-consolidation"
PORT = 8896
sys.path.insert(0, BASE)
import control            # 2026-09-08: the CONTROL page (KESHEV pause/listen, fleet tiles, doors, safe starts)

# --demo-decoy <dir>: demonstrate the pause gate on a TEMP dir, never on the live mic, then exit.
if len(sys.argv) >= 3 and sys.argv[1] == "--demo-decoy":
    control.demo_decoy(sys.argv[2])
    sys.exit(0)
IDX = json.load(open(os.path.join(BASE, "index.json"), encoding="utf-8"))
PROD = IDX["products"]
for i, it in enumerate(PROD):
    it["id"] = i

TOKF = os.path.join(BASE, "hub_token.txt")
if os.path.exists(TOKF):
    TOKEN = open(TOKF).read().strip()
else:
    TOKEN = secrets.token_urlsafe(9)
    open(TOKF, "w").write(TOKEN)

PLAYABLE_V = (".mp4", ".webm", ".mov", ".m4v")
PLAYABLE_A = (".mp3", ".wav", ".flac")
CAT_ORDER = ["Movies", "Builds", "Books", "Audio", "Docs"]

def grp(path):
    parts = re.split(r"[\\/]", path)
    return parts[-2] if len(parts) >= 2 else "misc"

def build_page():
    bycat = {}
    for it in PROD:
        bycat.setdefault(it["cat"], []).append(it)
    total_gb = sum(i["size"] for i in PROD) / 1073741824
    out = [
        "<!doctype html><meta charset=utf-8>",
        "<meta name=viewport content='width=device-width,initial-scale=1'>",
        "<title>ALMA Private Master Dash</title><style>",
        "body{background:#faf9f7;color:#1a1a1a;font-family:system-ui,Segoe UI,Arial;margin:0;padding:24px;max-width:1200px}",
        "h1{font-size:24px;margin:0 0 2px} .sub{color:#777;margin:0 0 6px;font-size:13px}",
        ".lock{color:#b00;font-size:12px;margin:0 0 18px}",
        ".tabs{position:sticky;top:0;background:#faf9f7;padding:8px 0;border-bottom:1px solid #e6e3de;margin-bottom:16px}",
        ".tabs a{margin-right:14px;text-decoration:none;color:#8a5a2b;font-weight:600}",
        "h2{font-size:18px;margin:26px 0 4px;border-bottom:2px solid #eadfce;padding-bottom:4px}",
        ".g{color:#999;font-size:12px;margin:14px 0 6px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}",
        ".card{border:1px solid #e6e3de;border-radius:10px;padding:12px 14px;margin:0 0 12px;background:#fff;box-shadow:0 1px 2px #0000000a}",
        ".t{font-weight:600;font-size:15px} .f{color:#aaa;font-size:11px;margin:2px 0 8px}",
        "video{width:100%;max-width:640px;border-radius:6px;background:#000} audio{width:100%;max-width:640px}",
        "a.dl{display:inline-block;background:#8a5a2b;color:#fff;padding:6px 12px;border-radius:6px;text-decoration:none;font-size:13px}",
        "</style>",
        "<h1>&#128274; ALMA &mdash; Private Master Dash</h1>",
        "<p class=sub>%d creations &middot; %.2f GB &middot; consolidated from C/D/E/F</p>" % (len(PROD), total_gb),
        "<p class=lock>Private. Your eyes only. Token-gated, on your Tailscale.</p>",
        "<div class=tabs>" + " ".join(
            "<a href='#%s'>%s (%d)</a>" % (c, c, len(bycat.get(c, []))) for c in CAT_ORDER if bycat.get(c)) + "</div>",
    ]
    for c in CAT_ORDER:
        items = bycat.get(c)
        if not items:
            continue
        out.append("<h2 id='%s'>%s</h2>" % (c, c))
        groups = {}
        for it in items:
            groups.setdefault(grp(it["path"]), []).append(it)
        for gname in sorted(groups):
            out.append("<div class=g>%s</div>" % html.escape(gname))
            for it in sorted(groups[gname], key=lambda x: x["path"]):
                name = os.path.basename(it["path"])
                ext = os.path.splitext(name)[1].lower()
                mb = it["size"] / 1048576.0
                out.append("<div class=card><div class=t>%s</div><div class=f>%s &middot; %.1f MB</div>"
                           % (html.escape(name), html.escape(it["path"]), mb))
                if ext in PLAYABLE_V:
                    out.append("<video controls preload=metadata src='/media/%d'></video>" % it["id"])
                elif ext in PLAYABLE_A:
                    out.append("<audio controls preload=metadata src='/media/%d'></audio>" % it["id"])
                else:
                    out.append("<a class=dl href='/media/%d'>open / download</a>" % it["id"])
                out.append("</div>")
    return "".join(out)

PAGE = None

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authed(self):
        c = self.headers.get("Cookie", "")
        return ("hubkey=" + TOKEN) in c

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        if q.get("key", [None])[0] == TOKEN:
            self.send_response(302)
            self.send_header("Set-Cookie", "hubkey=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000" % TOKEN)
            self.send_header("Location", parsed.path if parsed.path.startswith("/") else "/")
            self.end_headers()
            return
        if not self._authed():
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Private.</h2><p>Append your access key to the URL: <code>?key=YOUR_KEY</code></p>")
            return
        if parsed.path in ("/control", "/control/"):
            return self._send(200, "text/html; charset=utf-8", control.control_page(TOKEN).encode("utf-8"))
        if parsed.path == "/control/api/state":
            force = q.get("force", ["0"])[0] == "1"
            return self._send(200, "application/json; charset=utf-8",
                              json.dumps(control.full_state(force), ensure_ascii=False).encode("utf-8"))
        if parsed.path == "/control/api/audit":
            try:
                tail = open(control.AUDIT, encoding="utf-8").read()[-20000:]
            except OSError:
                tail = ""
            return self._send(200, "text/plain; charset=utf-8", tail.encode("utf-8"))
        if parsed.path in ("/", "/index.html"):
            data = build_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        m = re.match(r"^/media/(\d+)$", parsed.path)
        if m:
            i = int(m.group(1))
            if 0 <= i < len(PROD):
                return self._serve_file(PROD[i]["path"])
        self.send_error(404)

    def _send(self, code, ctype, data):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # Cookie gate AND the token in the body (the page embeds it): a cross-site form gets 403.
        parsed = urllib.parse.urlparse(self.path)
        if not self._authed():
            return self._send(403, "application/json", b'{"ok":false,"result":"forbidden"}')
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            body = {}
        if body.get("key") != TOKEN:
            return self._send(403, "application/json", b'{"ok":false,"result":"bad-key"}')
        ip = self.client_address[0]
        if parsed.path == "/control/api/action":
            code, out = control.run_action(str(body.get("action", "")), body, ip=ip)
            return self._send(code, "application/json; charset=utf-8",
                              json.dumps(out, ensure_ascii=False).encode("utf-8"))
        # 2026-09-11 (WAVE B3): the two endpoints that carry Iddo's own words and
        # his work queue. Same cookie + key gate as an action, PLUS the
        # per-process CSRF token the page embeds -- the :8941 pattern.
        if parsed.path in ("/control/api/ask", "/control/api/queue"):
            if self.headers.get("X-CSRF-Token", "") != control.CSRF:
                return self._send(403, "application/json", b'{"ok":false,"result":"bad-csrf"}')
            fn = control.run_ask if parsed.path.endswith("/ask") else control.run_queue
            code, out = fn(body, ip=ip)
            return self._send(code, "application/json; charset=utf-8",
                              json.dumps(out, ensure_ascii=False).encode("utf-8"))
        return self._send(404, "application/json", b'{"ok":false,"result":"no-such-endpoint"}')

    def _serve_file(self, path):
        if not os.path.isfile(path):
            self.send_error(404)
            return
        size = os.path.getsize(path)
        ctype = self.guess_type(path)
        rng = self.headers.get("Range")
        if not rng:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(path, "rb") as f:
                self.copyfile(f, self.wfile)
            return
        mm = re.match(r"bytes=(\d*)-(\d*)", rng)
        start = int(mm.group(1)) if mm and mm.group(1) else 0
        end = int(mm.group(2)) if mm and mm.group(2) else size - 1
        end = min(end, size - 1)
        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            rem = length
            while rem > 0:
                chunk = f.read(min(65536, rem))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                rem -= len(chunk)

socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer.daemon_threads = True
control.set_below_normal()      # the PC is the mic's machine; this hub never outranks it
control.start_prober()          # 2026-09-11 (B3): probing moves OFF the request path
# 2026-09-11: the page's script had been ONE SyntaxError since 09-09 -- every tile
# frozen, every button dead, and the server could not tell (still 200, still valid
# HTML). Now every start parses it with node and writes the verdict to the audit log.
_js_ok, _js_detail = control.check_page_js()
control.audit("page.js.check", "ok" if _js_ok is True else ("skipped" if _js_ok == "skipped" else "SYNTAX-ERROR"),
              {"detail": _js_detail}, who="private_hub startup")
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), H) as httpd:
    print("ALMA Private Dash on http://0.0.0.0:%d/  (token in hub_token.txt)" % PORT)
    httpd.serve_forever()
