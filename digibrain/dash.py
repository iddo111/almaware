#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dash.py -- Targ trainer: 4 colored boxes, pictures behind. :8894.
Net stats from state.json + HUMAN mode: tap a box, picture reveals,
score tracked. Truth drawn from hardware per round. Stdlib only."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(APP, "state.json")
PORT = 8894
BIND = os.environ.get("DOOR_BIND", "127.0.0.1")
BOXES = [("sun", "#c8792f"), ("mountain", "#5b7fa6"),
         ("water", "#3f7d6b"), ("tree", "#6b8f3e")]
PICS = {
    "sun": "<svg viewBox='0 0 100 100'><circle cx='50' cy='50' r='22' fill='#e8a33d'/><g stroke='#e8a33d' stroke-width='4'><line x1='50' y1='8' x2='50' y2='20'/><line x1='50' y1='80' x2='50' y2='92'/><line x1='8' y1='50' x2='20' y2='50'/><line x1='80' y1='50' x2='92' y2='50'/></g></svg>",
    "mountain": "<svg viewBox='0 0 100 100'><polygon points='10,85 40,30 60,60 75,40 95,85' fill='#5b7fa6'/><polygon points='40,30 48,44 40,52 32,44' fill='#fff'/></svg>",
    "water": "<svg viewBox='0 0 100 100'><path d='M10,60 q12,-15 25,0 t25,0 t25,0' stroke='#3f7d6b' stroke-width='6' fill='none'/><path d='M10,80 q12,-15 25,0 t25,0 t25,0' stroke='#3f7d6b' stroke-width='6' fill='none'/></svg>",
    "tree": "<svg viewBox='0 0 100 100'><rect x='46' y='60' width='8' height='28' fill='#6b4a2f'/><circle cx='50' cy='42' r='24' fill='#6b8f3e'/></svg>",
}
_human = {"round": 0, "truth": 0, "score": 0, "played": 0}

PAGE = """<!doctype html><html lang="he" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#141a12">
<title>טרג · targ trainer</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#141a12;color:#efe9dc;
font:16px/1.5 -apple-system,"Segoe UI",Arial,sans-serif}
header{padding:14px}h1{font-size:1.1rem;margin:0}
.sub{font-size:.75rem;color:#a9b39f}
main{padding:0 14px 30px;max-width:720px}
h2{font-size:.95rem;color:#cfe0c2}
.cards{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:10px 0}
.card{background:#223129;border-radius:10px;padding:10px;text-align:center}
.card b{font-size:1.25rem;display:block}
.card span{font-size:.7rem;color:#a9b39f}
#boxes{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0}
.box{border-radius:14px;min-height:120px;display:flex;align-items:center;
justify-content:center;font-size:1.4rem;font-weight:700;color:#fff;border:none}
.box svg{width:84px;height:84px}
#hscore{font-size:.9rem;margin:6px 2px}
pre{background:#223129;border-radius:10px;padding:10px;font-size:12px;
direction:ltr;text-align:left;overflow:auto}
</style></head><body>
<header><h1>טרג · מאמן</h1>
<div class="sub" id="sub">4 קופסאות · תמונה מאחורי כל אחת</div></header>
<main>
<h2>המוח (רשת)</h2>
<div class="cards">
<div class="card"><b id="r">–</b><span>סיבוב</span></div>
<div class="card"><b id="z">–</b><span>z (chance 25%)</span></div>
<div class="card"><b id="b">–</b><span>best deck /25</span></div>
</div>
<pre id="s">…</pre>
<h2>אתה (אדם) · לחץ על קופסה</h2>
<div id="hscore">0/0</div>
<div id="boxes"></div>
</main>
<script>
var RID=0;
function esc(s){return (s||"").replace(/&/g,"&amp;")
.replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function net(){fetch("/api/state").then(function(r){return r.json();})
.then(function(d){
document.getElementById("r").textContent=d.round;
document.getElementById("z").textContent=d.z;
document.getElementById("b").textContent=d.best_deck;
document.getElementById("s").textContent=
"last: net="+d.last.guess+" truth="+d.last.truth+
(d.last.hit?" HIT":" miss")+" · rate "+d.hit_rate;});}
function round(){fetch("/api/human/new").then(function(r){return r.json();})
.then(function(d){RID=d.round;var h="";
d.boxes.forEach(function(b,i){
h+="<button class='box' style='background:"+b[1]+"' onclick='guess("+i+")'>?</button>";});
document.getElementById("boxes").innerHTML=h;
document.getElementById("hscore").textContent=
d.score+"/"+d.played+" · round "+d.round;});}
function guess(i){fetch("/api/human/guess",{method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({round:RID,box:i})}).then(function(r){return r.json();})
.then(function(d){var h="";
d.boxes.forEach(function(b,j){
h+="<button class='box' style='background:"+b[1]+"'>"+(d.truth===j?d.pic:"?")+"</button>";});
document.getElementById("boxes").innerHTML=h;
document.getElementById("hscore").textContent=
d.score+"/"+d.played+(d.hit?" · HIT":" · miss")+" · next…";
setTimeout(round,2500);});}
net();setInterval(net,4000);round();
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    server_version = "targ-dash/1.0"

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

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj),
                   "application/json; charset=utf-8")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        return self.rfile.read(max(0, min(n, 65536)))

    def do_GET(self):
        import urllib.parse
        u = urllib.parse.urlparse(self.path)
        if u.path == "/healthz":
            return self._json({"ok": True, "port": PORT})
        if u.path == "/api/state":
            try:
                with open(STATE, encoding="utf-8") as f:
                    st = f.read()
            except OSError:
                st = ('{"round":0,"z":0,"best_deck":0,"hit_rate":0,'
                      '"last":{"guess":"?","truth":"?","hit":0}}')
            return self._send(200, st,
                              "application/json; charset=utf-8")
        if u.path == "/api/human/new":
            import os as _os
            tb = _os.getrandom(1, _os.GRND_RANDOM)[0] % 4
            _human["round"] += 1
            _human["truth"] = tb
            return self._json({"round": _human["round"],
                               "boxes": BOXES,
                               "score": _human["score"],
                               "played": _human["played"]})
        if u.path == "/":
            return self._send(200, PAGE)
        return self._send(404, "nope")

    def do_POST(self):
        import urllib.parse
        if urllib.parse.urlparse(self.path).path == \
                "/api/human/guess":
            try:
                p = json.loads(self._body().decode("utf-8") or "{}")
            except ValueError:
                return self._json({"error": "bad"}, 400)
            if int(p.get("round", -1)) != _human["round"]:
                return self._json({"error": "stale round"}, 400)
            box = int(p.get("box", -1))
            if box not in (0, 1, 2, 3):
                return self._json({"error": "bad box"}, 400)
            hit = int(box == _human["truth"])
            _human["played"] += 1
            _human["score"] += hit
            name = BOXES[_human["truth"]][0]
            return self._json({"hit": hit, "truth": _human["truth"],
                               "pic": PICS[name], "boxes": BOXES,
                               "score": _human["score"],
                               "played": _human["played"]})
        return self._json({"error": "nope"}, 404)


if __name__ == "__main__":
    srv = ThreadingHTTPServer((BIND, PORT), H)
    print("TARG up on http://%s:%d/" % (BIND, PORT), flush=True)
    srv.serve_forever()
