#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALMIDO — a live status window on 127.0.0.1:8877.

Iddo asked (2026-09-07 22:36, by microphone): "תעלה לי חלון עם מידע על ALMIDO".

Every request re-measures. Nothing here is cached, and nothing claims to be live
that is not: each door is probed when the page is drawn, and a door that does not
answer is drawn as DOWN, not omitted. That rule exists because earlier tonight a
page on this fleet rendered "חי · מתעדכן בכל רענון" over a search that had been
dead for five days -- true about the page, false about the thing behind it.

Port 8877 claimed in RAMCHAT before binding, per D:\\CLAUDE\\CLAUDE.md.
"""
import html
import http.server
import json
import os
import socket
import socketserver
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 8877
ROOT = os.path.dirname(os.path.abspath(__file__))

DOORS = [
    ("8447", "https://<tailnet-host>:8447/", "Qwen3-Coder-Next — ALMIDO's brain"),
    ("8449", "https://<tailnet-host>:8449/", "GLM coder harness"),
    ("8450", "https://<tailnet-host>:8450/", "raw Ollama passthrough"),
]

TOOLS = ["whoami", "ask_claude", "quorum_status", "quorum_debate",
         "brain_read", "brain_write", "ramchat_post", "ping", "audit_tail"]


def probe(url, timeout=6):
    """Real HTTP code, or the reason there is none. Never a guess."""
    t0 = time.time()
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return r.status, int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000)
    except Exception as e:
        return type(e).__name__, int((time.time() - t0) * 1000)


def file_age(path):
    try:
        m = os.path.getmtime(path)
        h = (time.time() - m) / 3600.0
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(m)), h
    except OSError:
        return None, None


def workspace_rows():
    d = os.path.join(ROOT, "workspace")
    out = []
    try:
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            if os.path.isfile(p):
                stamp, _ = file_age(p)
                out.append((n, os.path.getsize(p), stamp))
    except OSError:
        pass
    return out[-12:]


def page():
    rows = []
    for name, url, what in DOORS:
        code, ms = probe(url)
        ok = code == 200
        rows.append(
            f"<tr><td class='mono'>{html.escape(name)}</td>"
            f"<td>{html.escape(what)}</td>"
            f"<td class='{'ok' if ok else 'bad'}'>{html.escape(str(code))}</td>"
            f"<td class='mono'>{ms} ms</td></tr>")
    doors = "".join(rows)

    ws = workspace_rows()
    ws_html = "".join(
        f"<tr><td class='mono'>{html.escape(n)}</td><td class='mono'>{s:,} B</td>"
        f"<td class='mono'>{html.escape(t or '?')}</td></tr>" for n, s, t in ws
    ) or "<tr><td colspan='3' class='dim'>the coder has written nothing here yet</td></tr>"

    audit = os.path.join(os.path.dirname(ROOT), "iddo-harness", "state",
                         "almido-audit.jsonl")
    a_stamp, a_age = file_age(audit)
    if a_stamp is None:
        audit_line = "<span class='bad'>no audit file yet</span>"
    elif a_age > 48:
        audit_line = (f"<span class='warn'>last row {html.escape(a_stamp)} "
                      f"— {a_age/24:.1f} days ago</span>")
    else:
        audit_line = f"<span class='ok'>last row {html.escape(a_stamp)}</span>"

    tools = " · ".join(f"<code>{html.escape(t)}</code>" for t in TOOLS)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!doctype html><html lang="he"><head><meta charset="utf-8">
<title>ALMIDO</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{{font:15px/1.6 -apple-system,Segoe UI,Arial,sans-serif;background:#fff;color:#111;
      margin:0;padding:28px 22px;max-width:940px}}
 h1{{font-size:30px;margin:0 0 2px}} h2{{font-size:17px;margin:30px 0 8px;color:#333}}
 .sub{{color:#666;margin:0 0 4px}}
 .memorial{{background:#fffaf0;border-right:4px solid #d4a017;padding:12px 16px;
            margin:14px 0 22px;border-radius:5px}}
 table{{border-collapse:collapse;width:100%;margin:8px 0}}
 th,td{{text-align:right;padding:7px 10px;border-bottom:1px solid #eee;font-size:14px}}
 th{{color:#666;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
 .mono{{font-family:Consolas,monospace}}
 .ok{{color:#0a7d2e;font-weight:600}} .bad{{color:#c0392b;font-weight:600}}
 .warn{{color:#b8860b;font-weight:600}} .dim{{color:#999}}
 code{{background:#f4f4f4;padding:1px 6px;border-radius:3px;font-size:13px}}
 .open{{background:#fff5f5;border-right:4px solid #c0392b;padding:12px 16px;
        border-radius:5px;margin:8px 0}}
 .when{{color:#777;font-size:13px;margin-top:26px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body dir="rtl">
<h1>ALMIDO / עלמידו</h1>
<p class="sub">רתמת התכנות הסוכנית של עידו — גוף, מוח, ודלת</p>

<div class="memorial"><b>השם הוא זיכרון: עלמה ז"ל + עידו.</b><br>
<span class="dim">The name is a memorial — Alma z"l + Iddo. Never reword it.</span></div>

<h2>השרשרת / The chain</h2>
<p><b>גוף</b> (<code>qwen-code</code> CLI) ← <b>מוח</b> (qwen3-coder-next על eran4)
 ← <b>דלת</b> (9 כלי MCP). נמדד בביקורת שלב 1: השרשרת <span class="ok">עובדת</span> —
 כותבת קובץ, מריצה אותו, קוראת לדלת.</p>

<h2>הדלתות — נבדקות עכשיו, בכל רענון</h2>
<table><tr><th>פורט</th><th>מה</th><th>תשובה</th><th>זמן</th></tr>{doors}</table>

<h2>הכלים בדלת</h2><p>{tools}</p>

<h2>ביקורת / Audit</h2><p>{audit_line}<br>
<span class="dim">עלמידו כותב לשרשרת HMAC משלו ב-<code>iddo-harness\\state\\almido-audit.jsonl</code>
מאז 2026-09-06, אחרי שכתיבה בפורמט שגוי שברה את השרשרת החתומה של השער בשורה 33.</span></p>

<h2>מה שהסוכן כתב / The coder's workspace</h2>
<table><tr><th>קובץ</th><th>גודל</th><th>נכתב</th></tr>{ws_html}</table>

<h2>מצב הפגמים שנרשמו בשלב 1</h2>
<div class="open" style="background:#f4fbf6;border-right-color:#0a7d2e"><b>1. שער המדיניות — בנתיב, ומסרב.</b> נבדק 2026-09-07 22:48 מול קלטי דמה: <code>rm -rf eran-brain/state</code> → DENY · <code>ssh eran1 … stop eranb-life</code> → DENY. hook של PreToolUse ב-<code>~/.qwen/settings.json</code>. ה-README תוקן באותו ערב.</div>
<div class="open"><b>2. קובץ המפתח בכונן D אינו מוגן ב-ACL.</b> החלטה שלך, לא של הקוד.</div>
<div class="open"><b>3. הקטע השבור ב-<code>~/.iddo-harness/audit.jsonl</code></b>
(שורות 33+) לא תוקן ולא נמחק — הוא היסטוריה, בכוונה.</div>

<p class="when">נמדד עכשיו: {now} · כל רענון בודק מחדש · הדף הזה לא טוען שדבר חי
בלי לבדוק אותו</p>
</body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    try:
        with S(("0.0.0.0", PORT), H) as srv:   # 2026-09-08 03:28: was 127.0.0.1 -- dead from the phone and the Quest
            print(f"ALMIDO window on http://127.0.0.1:{PORT}/", flush=True)
            srv.serve_forever()
    except OSError as e:
        print(f"could not bind {PORT}: {e}", file=sys.stderr)
        sys.exit(1)
