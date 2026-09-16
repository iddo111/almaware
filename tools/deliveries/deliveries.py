"""המשלוחים — one clickable page for everything Claude hands Iddo.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"למה אתה לא נותן לי לינקים לחיצים כאשר ביקשתי זאת יותר ממאה פעם."*

He is right, and there are **three separate memory files** about it — the newest
(2026-08-27) says in its own description: *"He had to ask more than once, which means it
was not being applied."* Then on 2026-08-30 he had to ask again. A fourth promise is worth
nothing. This is mechanism instead.

**The whole problem in one line:** a browser cannot open `D:\\...` from a page — that is a
security rule, not a bug — so a path is never a link. But a *local server* can. So every
row here is a real `http://127.0.0.1` link, and clicking it makes THIS process run
`Start-Process` on the file. **The link opens the thing.**

Safety: bound to loopback only; it will only open files that live under one of the
allow-listed roots, resolved with realpath so `..` cannot walk out.

    python deliveries.py       ->  http://127.0.0.1:8848/
"""
from __future__ import annotations

import html
import http.server
import json
import os
import socketserver
import subprocess
import time
import urllib.parse

PORT = 8848
DESKTOP = os.path.expanduser(r"~/Desktop")
ROOTS = [os.path.realpath(DESKTOP), os.path.realpath(r"D:/CLAUDE")]
SHOW_EXT = (".jpg", ".jpeg", ".png", ".pdf", ".mp4", ".wav", ".mp3", ".m4a",
            ".txt", ".md", ".csv", ".svg", ".lnk", ".url", ".html")
SKIP = ("desktop.ini", "thumbs.db")

# Live local windows worth one click. Checked each load; dead ones are shown greyed.
SERVICES = [
    ("ERAN — ה־BA שלו, חי", "http://127.0.0.1:8846/", "מה שערן אומר עכשיו, מהחיפוש החי"),
    ("היד — לאסוף משיכות", "http://127.0.0.1:8847/", "מצייר על המסך, נשמר עם זמן ולחץ"),
    ("המשלוחים — הדף הזה", "http://127.0.0.1:8848/", ""),
]


def within_roots(p: str) -> bool:
    rp = os.path.realpath(p)
    return any(rp == r or rp.startswith(r + os.sep) for r in ROOTS)


def desktop_items(days: int = 14):
    now = time.time()
    out = []
    try:
        names = os.listdir(DESKTOP)
    except OSError:
        return out
    for n in names:
        if n.lower() in SKIP or not n.lower().endswith(SHOW_EXT):
            continue
        p = os.path.join(DESKTOP, n)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if now - st.st_mtime > days * 86400:
            continue
        out.append({"name": n, "path": p, "mtime": st.st_mtime,
                    "size": st.st_size, "ext": os.path.splitext(n)[1].lower()})
    out.sort(key=lambda d: -d["mtime"])
    return out


def alive(url: str) -> bool:
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(url, timeout=1.2)
        return True
    except urllib.error.HTTPError:
        return True                       # answered, just not 200
    except Exception:                     # noqa: BLE001
        return False


CSS = """
*{box-sizing:border-box}
body{margin:0;padding:20px 16px 40px;background:#fbfbf7;color:#161616;
     font-family:-apple-system,"Segoe UI",Arial,sans-serif;max-width:880px;margin:0 auto}
h1{font-size:27px;margin:0 0 2px}
.sub{font-size:14px;color:#777;margin-bottom:18px}
h2{font-size:18px;margin:24px 0 8px;border-bottom:2px solid #161616;padding-bottom:5px}
.row{display:flex;align-items:center;gap:12px;border:2px solid #e6e6e6;border-radius:11px;
     padding:10px 13px;margin-bottom:8px;background:#fff}
.row .ic{font-size:22px;width:30px;text-align:center}
.row .nm{flex:1;min-width:0}
.row .nm b{font-size:16px;display:block;word-break:break-word}
.row .nm span{font-size:12.5px;color:#888;direction:ltr;font-family:Consolas,monospace}
a.btn{display:inline-block;background:#1f8a4c;color:#fff;text-decoration:none;
      padding:9px 20px;border-radius:9px;font-size:15px;font-weight:700;white-space:nowrap}
a.btn.grey{background:#bbb;pointer-events:none}
a.btn.blue{background:#2b6cb0}
.folder{margin-top:6px}
.note{background:#f4f4ee;border-radius:9px;padding:11px 14px;font-size:14px;color:#555;
      margin-top:18px}
"""

ICONS = {".jpg": "🖼", ".jpeg": "🖼", ".png": "🖼", ".svg": "🖼", ".pdf": "📕",
         ".mp4": "🎬", ".wav": "🔊", ".mp3": "🔊", ".m4a": "🔊",
         ".txt": "📄", ".md": "📄", ".csv": "📊", ".lnk": "⚡", ".url": "🔗",
         ".html": "🌐"}


def page() -> bytes:
    rows = []
    for s in SERVICES:
        name, url, note = s
        ok = alive(url) if not url.endswith("8848/") else True
        rows.append(
            '<div class="row"><div class="ic">%s</div><div class="nm"><b>%s</b>'
            '<span>%s</span>%s</div><a class="btn blue%s" href="%s" target="_blank">פתח</a></div>'
            % ("🟢" if ok else "⚪", html.escape(name), url,
               ('<div style="font-size:13px;color:#666">%s</div>' % html.escape(note)) if note else "",
               "" if ok else " grey", url))
    svc = "".join(rows)

    items = []
    for d in desktop_items():
        q = urllib.parse.urlencode({"f": d["path"]})
        mb = d["size"] / 1048576.0
        items.append(
            '<div class="row"><div class="ic">%s</div><div class="nm"><b>%s</b>'
            '<span>%s · %s</span></div>'
            '<a class="btn" href="/open?%s">פתח</a></div>'
            % (ICONS.get(d["ext"], "📎"), html.escape(d["name"]),
               time.strftime("%d.%m %H:%M", time.localtime(d["mtime"])),
               ("%.1f MB" % mb) if mb >= 0.1 else ("%d KB" % (d["size"] // 1024)), q))
    files = "".join(items) or '<div class="row"><div class="nm">אין קבצים חדשים</div></div>'

    body = f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>המשלוחים</title><style>{CSS}</style></head><body>
<h1>המשלוחים</h1>
<div class="sub">כל מה שנמסר לך — לחיץ. {time.strftime('%d.%m.%Y %H:%M')}</div>

<h2>חלונות חיים</h2>
{svc}

<h2>קבצים על שולחן העבודה — 14 הימים האחרונים</h2>
<div class="row folder"><div class="ic">📁</div><div class="nm"><b>שולחן העבודה</b>
<span>{html.escape(DESKTOP)}</span></div>
<a class="btn" href="/open?{urllib.parse.urlencode({'f': DESKTOP})}">פתח תיקייה</a></div>
{files}

<div class="note"><b>למה זה עובד ולמה נתיב לא:</b> דפדפן לא יכול לפתוח
<code>D:\\...</code> מתוך דף — זה כלל אבטחה, לא באג. לכן נתיב הוא לעולם לא לינק.
<b>אבל שרת מקומי כן יכול</b> — כל כפתור "פתח" כאן שולח בקשה לתהליך הזה, והוא מפעיל את
הקובץ באפליקציה שלו. הלינק פותח את הדבר עצמו.</div>
</body></html>"""
    return body.encode("utf-8")


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, page())
            return
        if u.path == "/open":
            f = urllib.parse.parse_qs(u.query).get("f", [""])[0]
            if not f or not os.path.exists(f) or not within_roots(f):
                self._send(403, "<h2>לא מורשה</h2><p>%s</p>" % html.escape(f[:200]))
                return
            try:
                os.startfile(os.path.normpath(f))          # noqa: S606 - the whole point
            except AttributeError:
                subprocess.Popen(["explorer", os.path.normpath(f)])
            print("opened:", f, flush=True)
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_error(404)


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print("deliveries: http://127.0.0.1:%d/" % PORT, flush=True)
    S(("127.0.0.1", PORT), H).serve_forever()
