"""THE HAND — capture Iddo's real strokes, with time, so the painter can learn them.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"אני רוצה שהמודל ציור יעבוד כרגע על המסך, זה בסדר"* +
*"כמו הרעד האנושי"*.

The draughtsman already has a tremor and **it is fake**: `sin(u*9 + t*2.3)`. A sine wave
pretending to be a hand. A real tremor is not periodic — it is a hand correcting itself,
faster where the line is sure and slower where it hesitates. You cannot invent that. You
have to measure it.

So this records the only thing worth learning from: **the gesture in time.**
Every pointer sample keeps

    x, y      where the nib was, in canvas pixels
    t         milliseconds since the stroke began  -> speed, and therefore hesitation
    p         pressure 0..1 if the device reports it (pen does; mouse gives 0.5)
    tx, ty    tilt, if the device reports it

A stroke on paper gives only the final line. This gives **how the line was made**, which is
the whole difference between a hand and a plotter.

Nothing is uploaded. Files land in `strokes/` next to this file, one JSON per stroke.

    python hand.py            ->  http://127.0.0.1:8847/
"""
from __future__ import annotations

import http.server
import io
import json
import os
import socketserver
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "strokes")
PORT = 8847

PAGE = r"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>היד — לאסוף משיכות</title><style>
*{box-sizing:border-box;-webkit-user-select:none;user-select:none;touch-action:none}
body{margin:0;background:#f6f5f1;color:#1a1a1a;font-family:-apple-system,"Segoe UI",Arial,sans-serif;
     display:flex;flex-direction:column;height:100vh;overflow:hidden}
header{padding:9px 14px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;
       border-bottom:2px solid #ddd;background:#fff}
h1{font-size:17px;margin:0}
.stat{font-size:14px;color:#555;font-variant-numeric:tabular-nums}
.stat b{color:#1a1a1a}
button{border:2px solid #ccc;background:#fff;border-radius:9px;padding:6px 13px;
       font-size:14px;cursor:pointer}
button:active{background:#eee}
#wrap{flex:1;position:relative}
canvas{position:absolute;inset:0;width:100%;height:100%;background:#fff;
       box-shadow:inset 0 0 0 1px #e3e3e3}
#pen{font-size:13px;padding:2px 9px;border-radius:20px;background:#eee;color:#555}
#pen.real{background:#1f8a4c;color:#fff}
</style></head><body>
<header>
  <h1>היד</h1>
  <span class="stat">משיכות: <b id="n">0</b></span>
  <span class="stat">נקודות: <b id="pts">0</b></span>
  <span id="pen">עכבר — בלי לחץ אמיתי</span>
  <button id="clear">נקה מסך</button>
  <span class="stat" id="msg"></span>
</header>
<div id="wrap"><canvas id="c"></canvas></div>
<script>
const c = document.getElementById('c'), g = c.getContext('2d');
let W=0, H=0;
function fit(){ const r=c.getBoundingClientRect(), d=window.devicePixelRatio||1;
  W=r.width; H=r.height; c.width=W*d; c.height=H*d; g.setTransform(d,0,0,d,0,0);
  g.lineCap='round'; g.lineJoin='round'; g.strokeStyle='#111'; }
new ResizeObserver(fit).observe(c); fit();

let drawing=false, pts=[], t0=0, nStrokes=0, nPts=0, sawPen=false;
const el = id => document.getElementById(id);

function down(e){ if(e.button!==undefined && e.button!==0) return;
  drawing=true; pts=[]; t0=performance.now(); c.setPointerCapture(e.pointerId); add(e); }
function add(e){
  const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];   // full sample rate
  for (const s of evs){
    const r=c.getBoundingClientRect();
    pts.push({x:+(s.clientX-r.left).toFixed(2), y:+(s.clientY-r.top).toFixed(2),
              t:+(performance.now()-t0).toFixed(1),
              p:+(s.pressure??0.5).toFixed(3),
              tx:s.tiltX|0, ty:s.tiltY|0});
  }
  if (e.pointerType==='pen' && !sawPen){ sawPen=true;
    el('pen').textContent='עט — לחץ אמיתי ✓'; el('pen').className='real'; }
  const n=pts.length;
  if(n>1){ const a=pts[n-2], b=pts[n-1];
    g.lineWidth = 0.7 + 4.2*(b.p||0.5);
    g.beginPath(); g.moveTo(a.x,a.y); g.lineTo(b.x,b.y); g.stroke(); }
  el('pts').textContent = nPts + n;
}
function up(){ if(!drawing) return; drawing=false;
  if(pts.length < 3){ pts=[]; return; }                 // a tap is not a stroke
  const body = JSON.stringify({w:Math.round(W), h:Math.round(H),
    pointer: sawPen?'pen':'mouse-or-touch', points:pts});
  nStrokes++; nPts+=pts.length; el('n').textContent=nStrokes; el('pts').textContent=nPts;
  fetch('/stroke',{method:'POST',headers:{'Content-Type':'application/json'},body})
    .then(r=>r.json()).then(j=>{ el('msg').textContent='נשמר '+j.file; })
    .catch(e=>{ el('msg').textContent='שגיאת שמירה: '+e; });
  pts=[];
}
c.addEventListener('pointerdown',down);
c.addEventListener('pointermove',e=>{ if(drawing) add(e); });
c.addEventListener('pointerup',up);
c.addEventListener('pointercancel',up);
c.addEventListener('pointerleave',up);
el('clear').onclick=()=>{ g.clearRect(0,0,W,H); el('msg').textContent='המסך נוקה — המשיכות שמורות'; };
</script></body></html>"""


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
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"))
        elif self.path == "/count":
            n = len([f for f in os.listdir(OUT) if f.endswith(".json")])
            self._send(200, json.dumps({"strokes": n}).encode(), "application/json")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/stroke":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", "0"))
        try:
            d = json.loads(self.rfile.read(n))
        except Exception:                                          # noqa: BLE001
            self._send(400, b'{"error":"bad json"}', "application/json")
            return
        os.makedirs(OUT, exist_ok=True)
        name = "%s-%04d.json" % (time.strftime("%Y%m%d"),
                                 len([f for f in os.listdir(OUT) if f.endswith(".json")]) + 1)
        d["saved_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        io.open(os.path.join(OUT, name), "w", encoding="utf-8").write(
            json.dumps(d, ensure_ascii=False))
        pts = d.get("points", [])
        dur = pts[-1]["t"] if pts else 0
        print("stroke %s  %d points  %.0f ms  %s" % (name, len(pts), dur, d.get("pointer")),
              flush=True)
        self._send(200, json.dumps({"file": name, "points": len(pts)}).encode(),
                   "application/json")


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("the hand is open: http://127.0.0.1:%d/   -> %s" % (PORT, OUT), flush=True)
    S(("127.0.0.1", PORT), H).serve_forever()
