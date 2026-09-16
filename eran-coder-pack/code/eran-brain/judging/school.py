#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
school.py — ERAN'S SCHOOL, BLIND SITTING. Port 8855.

Sitting school-20260903: 21 Hebrew syllables, two clips each, A and B. One was
made by the teacher (Claude) operating the physics mouth by hand from the
measured manual; the other is ERAN's own leave-one-out prediction (class-only
MLP trained without that syllable). school-20260903-KEY.json says which is
which — this page never puts that in the HTML, never serves the KEY, never
shows a file name. Audio goes out only through blind URLs:

    /clip/<syl>/A.wav     /clip/<syl>/B.wav

A real file name, the KEY, a path — anything else — is a 404.

Every click appends TWO rows (one per clip) to iddo-verdicts.jsonl, the same
schema as the loop rows (loop.py record_vote). Append-only: the file is a log,
the last word per syllable wins. Refresh-safe: on load the page reads the log
and shows what is already rated.

    python school.py         then open http://127.0.0.1:8855/
Ports: 8853/8854 booth, 8890 loop, 8812 station — 8855 is ours.
"""
import html
import io
import json
import os
import http.server
import socketserver
import threading
import urllib.parse
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SITTING = "school-20260903"
CLIPS = os.path.join(ROOT, SITTING)
KEY_PATH = os.path.join(ROOT, SITTING + "-KEY.json")
VERDICTS = os.path.join(ROOT, "iddo-verdicts.jsonl")
LOG = os.path.join(ROOT, "school.log")
PORT = 8855
CHOICES = ("A", "B", "both", "none")

with io.open(KEY_PATH, encoding="utf-8") as _f:
    _KEY = json.load(_f)
# syl -> {"A": kind, "B": kind, ...}. Only the A/B kinds are ever used, and only
# when WRITING a verdict row. Nothing from here reaches the page.
PAIRS = {u: {"A": v["A"], "B": v["B"]} for u, v in _KEY["pairs"].items()}
UNITS = list(PAIRS.keys())          # page order = KEY order; round = 1-based index
N = len(UNITS)
del _KEY

# latin key -> Hebrew syllable with nikud. Unknown keys fall back to the key.
HEB = {
    "a": "אַ", "aya": "אַיָה", "ba": "בַּ", "va": "בַ", "ga": "גַ", "da": "דַ",
    "ha": "הַ", "wa": "וַ", "za": "זַ", "cha": "חַ", "kha": "כַ", "ta": "תַ",
    "ya": "יַ", "ka": "קַ", "la": "לַ", "ma": "מַ", "na": "נַ", "sa": "סַ",
    "pa": "פַּ", "fa": "פַ", "tza": "צַ", "qa": "קַ", "ra": "רַ", "sha": "שַׁ",
}
LOCK = threading.Lock()
GIF = bytes.fromhex('47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b')


def heb(syl):
    return HEB.get(syl, syl)


def clip_name(syl, label):
    return "ERAN-%s-%s.wav" % (syl, label)


def log(msg):
    try:
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now().isoformat(timespec="seconds"), msg))
    except OSError:
        pass


def load_state():
    """Last verdict per syllable for THIS sitting, read from the append-only log.
    Every vote writes an A row and a B row, so the last A row and last B row
    of a unit are always from the same (latest) click."""
    st = {}
    if not os.path.isfile(VERDICTS):
        return {}
    with io.open(VERDICTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("sitting") != SITTING or r.get("source") != "school":
                continue
            u, lab = r.get("unit"), r.get("blind_label")
            if u not in PAIRS or lab not in ("A", "B"):
                continue
            e = st.setdefault(u, {"A": False, "B": False, "none": False, "note": ""})
            e[lab] = bool(r.get("chosen"))
            e["none"] = bool(r.get("none_good"))
            e["note"] = r.get("note") or ""
    out = {}
    for u, e in st.items():
        if e["none"]:
            c = "none"
        elif e["A"] and e["B"]:
            c = "both"
        elif e["A"]:
            c = "A"
        elif e["B"]:
            c = "B"
        else:
            continue
        out[u] = {"choice": c, "note": e["note"]}
    return out


PAGE_TMPL = u"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>בית הספר של ערן — שיפוט עיוור</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#f7f4ec;color:#22281f;font-family:"Assistant","Segoe UI",Arial,sans-serif;
      padding:0 16px 60px;line-height:1.5;max-width:720px;margin:0 auto}
 .bar{position:sticky;top:0;background:#f7f4ec;padding:12px 0 10px;font-size:16px;z-index:5;
      border-bottom:1px solid #ddd7c6;margin-bottom:14px;display:flex;justify-content:space-between;
      align-items:center;gap:10px}
 .bar b{font-size:18px}
 .bar .pct{height:8px;flex:1;background:#e3ded0;border-radius:6px;overflow:hidden}
 .bar .pct i{display:block;height:100%;width:0;background:#2e6b45;transition:width .3s}
 h1{font-size:22px;margin:6px 0 4px}
 .sub{color:#6b7563;font-size:13.5px;margin-bottom:16px}
 .card{background:#fff;border:1px solid #ddd7c6;border-radius:14px;padding:14px 16px;margin-bottom:12px}
 .card.done{background:#e8f2e6;border-color:#bfd9bd}
 .n{font-size:13px;color:#6b7563}
 .syl{font-size:44px;font-weight:700;line-height:1.2;margin:2px 0 6px}
 .q{font-size:16px;margin-bottom:10px}
 .pl{display:flex;align-items:center;gap:10px;margin-bottom:8px}
 .pl .lab{font-size:26px;font-weight:700;width:34px;text-align:center;color:#2e6b45}
 audio{flex:1;min-width:0}
 .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
 button{flex:1;min-width:64px;font-family:inherit;font-size:17px;padding:12px 0;border-radius:11px;
        border:1px solid #c9c2ae;background:#fbfaf6;color:inherit;cursor:pointer}
 button:hover{background:#eee9dc}
 button.sel{background:#2e6b45;color:#fff;border-color:#2e6b45;font-weight:700}
 .note{width:100%;margin-top:10px;font-family:inherit;font-size:14px;padding:8px 10px;
       border:1px solid #ddd7c6;border-radius:9px;background:#fffdf8}
 .err{color:#a33;font-size:13px;margin-top:6px;display:none}
 .fin{text-align:center;color:#6b7563;font-size:14px;margin-top:20px}
 .ok{font-size:16px;margin-top:6px;font-weight:700;min-height:22px} .ok.yes{color:#2e8b57} .ok.no{color:#b00020}
</style></head><body>
<div class="bar"><b id="bar">נשפטו 0 מתוך __N__</b><span class="pct"><i id="pct"></i></span></div>
<h1>בית הספר של ערן</h1>
<div class="sub">__N__ הברות. לכל הברה שני קליפים, <b>א</b> ו-<b>ב</b>. אחד מהם — המורה הפעיל את הפה ביד;
 השני — ערן ניחש לבד. לא כתוב איזה זה איזה, וזו הכוונה. תשמע, ותגיד מה נשמע לך אמיתי.
 אפשר לרענן — מה שכבר נשפט נשאר.</div>
<div id="list">__CARDS__</div>
<div class="fin">כל לחיצה נשמרת מיד. אין כפתור סיום.</div>
<script>
const N=__N__; const STATE=__STATE__; const done={};
function bar(){
  const k=Object.keys(done).length;
  document.getElementById('bar').textContent='נשפטו '+k+' מתוך '+N;
  document.getElementById('pct').style.width=(100*k/N)+'%';
}
function apply(u,c,note){
  done[u]=c;
  const card=document.getElementById('c-'+u);
  card.classList.add('done');
  card.querySelectorAll('button').forEach(b=>b.classList.toggle('sel',b.dataset.c===c));
  if(note!==undefined) card.querySelector('.note').value=note;
  bar();
}
function saved(k,ok){const e=document.querySelector('#c-'+k+' .ok'); if(!e) return;
  e.textContent=ok?'נשמר בשרת ✔':'לא נשמר ✖ — לחץ שוב'; e.className='ok '+(ok?'yes':'no');}
function srv(n){const s=document.getElementById('srv'); if(s) s.textContent='נשמרו בשרת: '+n+' / '+N;}
function refreshCount(){fetch('/n',{cache:'no-store'}).then(r=>r.json()).then(j=>srv(j.n)).catch(()=>{});}
function send(k,c,note){
  const q='/k?'+new URLSearchParams({unit:k,choice:c,note:note}).toString();
  fetch(q,{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status))
   .then(j=>{saved(k,true); srv(j.n);})
   .catch(()=>{const im=new Image(); im.onload=()=>{saved(k,true); refreshCount();};
     im.onerror=()=>saved(k,false); im.src=q+'&img=1&t='+Date.now();});
}
function vote(u,c){
  const note=document.querySelector('#c-'+u+' .note').value;
  apply(u,c);
  send(u,c,note);
  const card=document.getElementById('c-'+u);
  const nx=card.nextElementSibling;
  if(nx&&nx.classList.contains('card')) nx.scrollIntoView({behavior:'smooth',block:'center'});
}
function noteChanged(u){
  if(!done[u]) return;   // the note travels with the verdict; saved on the next click
  send(u,done[u],document.querySelector('#c-'+u+' .note').value);
}
for(const u in STATE) apply(u,STATE[u].choice,STATE[u].note);
bar(); refreshCount();
</script></body></html>"""

CARD_TMPL = u"""<div class="card" id="c-{u}" data-unit="{u}">
 <div class="n">{i} מתוך {n}</div>
 <div class="syl">{h}</div>
 <div class="q">איזה מהשניים הוא {h} אמיתי?</div>
 <div class="pl"><span class="lab">א</span><audio controls preload="none" src="/clip/{u}/A.wav"></audio></div>
 <div class="pl"><span class="lab">ב</span><audio controls preload="none" src="/clip/{u}/B.wav"></audio></div>
 <div class="row">
  <button data-c="A" onclick="vote('{u}','A')">א</button>
  <button data-c="B" onclick="vote('{u}','B')">ב</button>
  <button data-c="both" onclick="vote('{u}','both')">שניהם</button>
  <button data-c="none" onclick="vote('{u}','none')">אף אחד</button>
 </div>
 <input class="note" placeholder="הערה (לא חובה)" maxlength="500" onchange="noteChanged('{u}')">
 <div class="ok"></div>
</div>
"""


def page():
    cards = "".join(CARD_TMPL.format(u=u, i=i, n=N, h=html.escape(heb(u)))
                    for i, u in enumerate(UNITS, 1))
    state = json.dumps(load_state(), ensure_ascii=False).replace("</", "<\\/")
    return (PAGE_TMPL.replace("__N__", str(N))
            .replace("__CARDS__", cards)
            .replace("__STATE__", state))


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

    def _404(self):
        return self._s("404", "text/plain; charset=utf-8", 404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/n":
            return self._s(json.dumps({"n": len(load_state())}), "application/json; charset=utf-8")
        if p == "/k":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            d = {k: v[0] for k, v in qs.items()}
            return self._vote(d)
        if p in ("/", "/index.html"):
            return self._s(page())
        if p.startswith("/clip/"):
            # exactly /clip/<known syl>/A.wav or B.wav — nothing else resolves
            parts = p.split("/")
            if len(parts) == 4 and parts[2] in PAIRS and parts[3] in ("A.wav", "B.wav"):
                fp = os.path.join(CLIPS, clip_name(parts[2], parts[3][0]))
                if os.path.isfile(fp):
                    with open(fp, "rb") as fh:
                        return self._s(fh.read(), "audio/wav")
        return self._404()

    def _vote(self, d):
        u, c = d.get("unit"), d.get("choice")
        if u not in PAIRS or c not in CHOICES:
            return self._s("bad vote", "text/plain; charset=utf-8", 400)
        note = str(d.get("note") or "").strip()[:500]
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        rnd = UNITS.index(u) + 1
        rows = []
        for lab in ("A", "B"):
            rows.append({"ts": ts, "judge": "iddo", "sitting": SITTING, "round": rnd,
                         "blind_label": lab, "clip": clip_name(u, lab), "unit": u,
                         "chosen": (c == "both") or (c == lab), "source": "school",
                         "kind": PAIRS[u][lab], "sigma": None,
                         "none_good": (c == "none"), "note": note})
        # same open call as loop.py record_vote, so line endings match the file
        with LOCK:
            with io.open(VERDICTS, "a", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if d.get("img"):
            return self._s(GIF, "image/gif")
        return self._s(json.dumps({"ok": True, "n": len(load_state()), "rows": len(rows)}),
                       "application/json; charset=utf-8")


    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if p != "/vote":
            return self._404()
        try:
            d = json.loads(raw.decode("utf-8"))
        except ValueError:
            return self._s("bad json", "text/plain; charset=utf-8", 400)
        return self._vote(d)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    try:
        srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    except OSError as e:
        log("bind failed on %d: %s" % (PORT, e))
        raise
    log("school: %d pairs -> http://127.0.0.1:%d/" % (N, PORT))
    print("school: %d pairs  ->  http://127.0.0.1:%d/" % (N, PORT), flush=True)
    srv.serve_forever()
