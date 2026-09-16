#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
booth.py — IDDO'S VERDICT SITTING. Port 8853.

Born 2026-09-01 08:03, after SIX consecutive ear-rejections of clips the metric
had approved — two of which had crossed their win bars. His ruling: "כולם לא
שווים כלום". The measuring space does not measure what he hears, so the only
honest next step is to LEARN his ear instead of arguing with it.

Blind by construction: the page shows clip01..clip24 and nothing else. No score,
no syllable name, no provenance. Four of them are REAL HUMAN takes planted as
anchors — if his ratings do not separate the humans from the machine, the whole
sitting is void and we say so out loud instead of training on noise.

Every click appends one line to sitting-<date>.jsonl. Refresh-safe: re-rating a
clip overwrites its row in memory and appends a corrected line — the file is a
log, the last word wins.

    python booth.py         then open http://127.0.0.1:8853/
"""
import io
import json
import os
import http.server
import socketserver
import urllib.parse
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(ROOT, "sitting2-clips")
OUT = os.path.join(ROOT, "sitting2-%s.jsonl" % datetime.now().strftime("%Y%m%d"))
PORT = 8854

N = len([f for f in os.listdir(CLIPS) if f.endswith(".wav")]) if os.path.isdir(CLIPS) else 0

PAGE_TMPL = u"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ישיבת הפסקים — האוזן של עידו</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#f7f4ec;color:#22281f;font-family:"Assistant","Segoe UI",Arial,sans-serif;
      padding:18px 16px 60px;line-height:1.5}
 @media (prefers-color-scheme:dark){body{background:#12180f;color:#e6ebe0}
   .card{background:#1b2318 !important;border-color:#2f3a2a !important}
   .done{background:#1d2c20 !important}}
 h1{font-size:22px;margin-bottom:4px}
 .sub{color:#6b7563;font-size:13.5px;margin-bottom:16px}
 .bar{position:sticky;top:0;background:inherit;padding:8px 0 12px;font-size:14px;z-index:5}
 .card{background:#fff;border:1px solid #ddd7c6;border-radius:14px;padding:14px 16px;margin-bottom:12px}
 .card.done{background:#e8f2e6}
 .n{font-size:13px;color:#6b7563;margin-bottom:8px}
 audio{width:100%;margin-bottom:10px}
 .row{display:flex;gap:8px;flex-wrap:wrap}
 button{flex:1;min-width:58px;font-family:inherit;font-size:17px;padding:12px 0;border-radius:11px;
        border:1px solid #c9c2ae;background:#fbfaf6;color:inherit;cursor:pointer}
 button:hover{background:#eee9dc}
 button.sel{background:#2e6b45;color:#fff;border-color:#2e6b45;font-weight:700}
 .k{font-size:12px;color:#6b7563;margin-top:6px}
 .fin{background:#2e6b45;color:#fff;border:none;border-radius:12px;padding:14px;width:100%;
      font-size:16px;margin-top:16px;cursor:pointer}
</style></head><body>
<h1>ישיבת הפסקים</h1>
<div class="sub">__N__ קליפים עיוורים. תן לכל אחד ציון 1–5 באוזן בלבד.
 <b>1</b> = רעש/כלום · <b>3</b> = משהו · <b>5</b> = נשמע אנושי.<br>
 אין שמות, אין ציונים, אין רמזים — וזו הכוונה.</div>
<div class="bar" id="bar">0 / __N__</div>
<div id="list"></div>
<button class="fin" onclick="finish()">סיימתי — שמור את הישיבה</button>
<script>
const N=__N__; const done={};
const L=document.getElementById('list');
for(let i=1;i<=N;i++){
  const id=String(i).padStart(2,'0');
  const d=document.createElement('div'); d.className='card'; d.id='c'+i;
  d.innerHTML=`<div class="n">${i} מתוך ${N}</div>
   <audio controls preload="none" src="/clip/${id}"></audio>
   <div class="row">
     ${[1,2,3,4,5].map(v=>`<button onclick="rate(${i},${v},this)">${v}</button>`).join('')}
   </div>
   <div class="k">1 רעש · 5 אנושי</div>`;
  L.appendChild(d);
}
function rate(i,v,btn){
  done[i]=v;
  const card=document.getElementById('c'+i);
  card.classList.add('done');
  card.querySelectorAll('button').forEach(b=>b.classList.remove('sel'));
  btn.classList.add('sel');
  document.getElementById('bar').textContent=Object.keys(done).length+' / '+N;
  fetch('/rate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({clip:i,score:v})});
  const nx=document.getElementById('c'+(i+1));
  if(nx) nx.scrollIntoView({behavior:'smooth',block:'center'});
}
function finish(){
  fetch('/finish',{method:'POST'}).then(r=>r.text()).then(t=>{
    document.body.innerHTML='<h1>נשמר. תודה, עידו. 🕯️</h1><div class="sub">'+t+'</div>';
  });
}
</script></body></html>"""
PAGE = PAGE_TMPL.replace("__N__", str(N))


class H(http.server.BaseHTTPRequestHandler):
    def _s(self, body, ctype="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
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
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            return self._s(PAGE)
        if p.startswith("/clip/"):
            name = "clip%s.wav" % p.rsplit("/", 1)[-1]
            fp = os.path.join(CLIPS, name)
            if os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    return self._s(fh.read(), "audio/wav")
        return self._s("404", "text/plain; charset=utf-8", 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if p == "/rate":
            d = json.loads(raw.decode("utf-8"))
            rec = {"ts": datetime.now().isoformat(timespec="seconds"),
                   "judge": "iddo", "sitting": os.path.basename(OUT),
                   "clip": "clip%02d" % int(d["clip"]), "score": int(d["score"])}
            with io.open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return self._s("ok", "text/plain; charset=utf-8")
        if p == "/finish":
            return self._s("הפסקים נשמרו ב-%s" % os.path.basename(OUT),
                           "text/plain; charset=utf-8")
        return self._s("404", "text/plain; charset=utf-8", 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    print("booth: %d clips  ->  http://127.0.0.1:%d/" % (N, PORT), flush=True)
    srv.serve_forever()
