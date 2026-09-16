#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dash.py -- watch page for the vipassana mind. eran1 :8892.
Reads state.json, serves RTL Hebrew live view (poll /api/state).
Stdlib only. Tailnet via `tailscale serve --https=8892`."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(APP, "state.json")
PORT = 8892
BIND = os.environ.get("DOOR_BIND", "127.0.0.1")

PAGE = """<!doctype html><html lang="he" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#101418">
<title>ויפאסנה · vipassana</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#101418;color:#e8e4d8;
font:16px/1.55 -apple-system,"Segoe UI",Arial,sans-serif}
header{padding:14px;position:sticky;top:0;background:#101418}
h1{font-size:1.1rem;margin:0}
.sub{font-size:.75rem;color:#8b93a0}
main{padding:0 14px 30px;max-width:720px}
.cards{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:10px 0}
.card{background:#1a212b;border-radius:10px;padding:10px;text-align:center}
.card b{font-size:1.25rem;display:block}
.card span{font-size:.7rem;color:#8b93a0}
pre{background:#1a212b;border-radius:10px;padding:12px;white-space:pre-wrap;
font-size:13.5px;direction:ltr;text-align:left;max-height:220px;overflow:auto}
.bars{font-family:ui-monospace,monospace;font-size:11px;direction:ltr;
background:#1a212b;border-radius:10px;padding:12px;overflow-x:auto;
white-space:pre;color:#7fd08a}
</style></head><body>
<header><h1>ויפאסנה</h1>
<div class="sub" id="sub">מוח קטן מתבונן בעצמו · eran1</div></header>
<main>
<div class="cards">
<div class="card"><b id="r">–</b><span>סיבוב</span></div>
<div class="card"><b id="l">–</b><span>loss</span></div>
<div class="card"><b id="e">–</b><span>אנטרופיה</span></div>
</div>
<pre id="s">…</pre>
<div class="bars" id="h">…</div>
</main>
<script>
function bar(v,mx){var n=Math.round(v/mx*24);var s="";
for(var i=0;i<n;i++)s+="|";return s;}
function load(){fetch("/api/state").then(function(r){return r.json();})
.then(function(d){
document.getElementById("sub").textContent=
"סיבוב "+d.round+" · "+d.ts+" · "+d.device;
document.getElementById("r").textContent=d.round;
document.getElementById("l").textContent=d.loss;
document.getElementById("e").textContent=d.gen.entropy;
document.getElementById("s").textContent=d.sample;
var h="entropy / round (collapse = flatline)\\n";
var mx=0.1;d.history.forEach(function(p){if(p.ent>mx)mx=p.ent;});
d.history.forEach(function(p){
h+=(p.fed?"OM! ":"    ")+("r"+p.r+" ").slice(-6)+" "+bar(p.ent,mx)+" "+p.ent+"\\n";});
document.getElementById("h").textContent=h;
var m=document.querySelector("main");});}
setInterval(load,3000);load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    server_version = "vipass-dash/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            import json as j
            self._send(200, j.dumps({"ok": True}),
                       "application/json")
            return
        if self.path == "/api/state":
            try:
                with open(STATE, encoding="utf-8") as f:
                    st = f.read()
            except OSError:
                st = ('{"round":0,"loss":null,"gen":{"entropy":0},'
                      '"sample":"…meditating…","device":"?","ts":"",'
                      '"history":[]}')
            self._send(200, st, "application/json; charset=utf-8")
            return
        if self.path == "/":
            self._send(200, PAGE)
            return
        self._send(404, "nope")


if __name__ == "__main__":
    srv = ThreadingHTTPServer((BIND, PORT), H)
    print("DASH up on http://%s:%d/" % (BIND, PORT), flush=True)
    srv.serve_forever()
