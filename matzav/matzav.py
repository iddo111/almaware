# -*- coding: utf-8 -*-
r"""
matzav.py — MATZAV / מצב. The fleet control room. 127.0.0.1:8880.

> BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it
> IMMEDIATELY. Test the REAL output, not a proxy (health: ok != working).

Iddo, 2026-09-04: "אתה בונה את חדר הבקרה של הצי. עידו רוצה להחליט בלחיצה אחת
מה רץ על כל קופסה." — a system of MODES, not a switchboard. Clicking a mode
declares a desired state; MATZAV computes the difference against MEASURED
reality, SHOWS THE PLAN, and only then executes.

stdlib only: http.server, urllib, html, json, socket. No Flask. No CDN.
Port 8880 claimed in RAMCHAT 2026-09-04 07:26 as claude-cli-MATZAV.
"""
import html
import json
import os
import threading
import time
import http.server
import socketserver

import matzav_apply as A
import matzav_plan as PL
import matzav_probe as P
from matzav_sacred import SACRED, PC_HOSTS_NO_MODES

PORT = 8880
HERE = os.path.dirname(os.path.abspath(__file__))

REG, UNITS, MODES = P.load_registry()
BOXES = REG["boxes"]

_lock = threading.Lock()          # the single global plan lock
_state = {"ts": 0}
_state_lock = threading.Lock()
_running = {"plan": None, "log": [], "outcome": None}


def refresh(force=False, max_age=20):
    with _state_lock:
        fresh = (time.time() - _state.get("ts", 0)) < max_age
        if fresh and not force:
            return _state
    s = P.observe(UNITS, BOXES)
    with _state_lock:
        _state.clear()
        _state.update(s)
    return s


def mode_status(m, st):
    """Warm / cold / satisfied — from measurement, never from 'it is running'."""
    if not m.get("runnable"):
        return "never-run"
    wants = [UNITS[u] for u in m.get("want", []) if u in UNITS]
    if not wants:
        return "satisfied" if m.get("quiet") else "empty"
    ups = [w for w in wants if (st["units"].get(w["id"]) or {}).get("real") == "up"]
    if len(ups) == len(wants):
        return "satisfied"
    warm = all((st["units"].get(w["id"]) or {}).get("warm") for w in wants)
    return "warm" if warm else "cold"


# --------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f6f8fb;color:#12203a;
 font:15px/1.55 "Segoe UI",Arial,Helvetica,sans-serif;direction:rtl}
a{color:#0b5fd0}
.wrap{max-width:1180px;margin:0 auto;padding:18px 16px 60px}
h1{font-size:30px;margin:6px 0 2px;letter-spacing:-.5px}
.sub{color:#5a6b86;margin-bottom:14px;font-size:14px}
.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:10px 0 18px}
.pill{background:#fff;border:1px solid #dbe3ee;border-radius:999px;
 padding:5px 13px;font-size:13px;box-shadow:0 1px 2px rgba(20,40,80,.05)}
.pill b{color:#0b3f9e}
.modes{display:grid;grid-template-columns:repeat(auto-fill,minmax(238px,1fr));
 gap:14px;margin-bottom:26px}
.mode{background:#fff;border:2px solid #dbe3ee;border-radius:16px;padding:16px;
 cursor:pointer;box-shadow:0 2px 6px rgba(20,40,80,.07);transition:.12s;
 position:relative;min-height:132px;display:flex;flex-direction:column}
.mode:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(20,40,80,.13)}
.mode h2{margin:0;font-size:27px;letter-spacing:-.5px}
.mode .en{color:#8898b0;font-size:12px;letter-spacing:1.2px;margin-top:2px}
.mode .st{color:#43536e;font-size:13px;margin-top:9px;flex:1}
.mode .tag{position:absolute;inset-inline-start:12px;top:13px;font-size:11px;
 font-weight:700;border-radius:999px;padding:3px 9px;letter-spacing:.3px}
.ok{border-color:#1f9d55;background:#eefbf3}
.ok .tag{background:#1f9d55;color:#fff}
.warm{border-color:#e8a11a;background:#fffaf0}
.warm .tag{background:#e8a11a;color:#fff}
.cold{border-color:#b8c4d6;background:#fff}
.cold .tag{background:#7d8ea6;color:#fff}
.never{border-color:#d8dee8;background:#f2f4f8;opacity:.82;cursor:not-allowed}
.never .tag{background:#98a4b8;color:#fff}
.never h2{color:#63718a}
.card{background:#fff;border:1px solid #dbe3ee;border-radius:14px;padding:16px;
 margin-bottom:18px;box-shadow:0 1px 3px rgba(20,40,80,.05)}
.card h3{margin:0 0 10px;font-size:17px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:right;padding:6px 8px;border-bottom:1px solid #eef1f6}
th{color:#69788f;font-weight:600;font-size:12px}
.up{color:#137a41;font-weight:700}
.down{color:#a01a1a;font-weight:700}
.unk{color:#9a6b00;font-weight:700}
.sacred{background:#fff7e8}
.badge{font-size:11px;border-radius:6px;padding:2px 7px;margin-inline-start:5px}
.b-sac{background:#7b3ff0;color:#fff}
.b-bw{background:#d33;color:#fff}
.b-dis{background:#e8a11a;color:#fff}
.b-hh{background:#0b5fd0;color:#fff}
.b-est{background:#8898b0;color:#fff}
.meter{height:9px;background:#e7ecf4;border-radius:5px;overflow:hidden;
 min-width:110px}
.meter i{display:block;height:100%;background:#1f9d55}
.meter i.hot{background:#e8a11a}
#panel{position:fixed;inset:0;background:rgba(12,22,42,.55);display:none;
 z-index:9;align-items:center;justify-content:center;padding:20px}
#panel.on{display:flex}
#box{background:#fff;border-radius:18px;max-width:720px;width:100%;
 max-height:88vh;overflow:auto;padding:22px;box-shadow:0 20px 60px rgba(0,0,0,.3)}
#box h2{margin:0 0 4px;font-size:26px}
.step{padding:8px 12px;border-inline-start:4px solid #0b5fd0;background:#f4f8ff;
 border-radius:8px;margin:7px 0;font-size:14.5px}
.step.stop{border-color:#d33;background:#fff5f5}
.step.warnl{border-color:#e8a11a;background:#fffaf0}
.refuse{background:#fff2f2;border:2px solid #d33;border-radius:12px;padding:14px}
.refuse h3{color:#b31414;margin:0 0 8px;font-size:19px}
button{font:inherit;border:0;border-radius:10px;padding:11px 22px;cursor:pointer;
 font-weight:700}
.go{background:#1f9d55;color:#fff}
.go:hover{background:#187a42}
.cancel{background:#e7ecf4;color:#33405a}
.tiny{font-size:12px;color:#7d8ea6}
.honest{background:#fffaf0;border:1px solid #f0d9a8;border-radius:10px;
 padding:10px 12px;font-size:13px;margin:10px 0}
.log{font:12.5px/1.5 Consolas,monospace;background:#0f1a2e;color:#cfe3ff;
 border-radius:10px;padding:12px;max-height:260px;overflow:auto;
 white-space:pre-wrap;direction:ltr;text-align:left}
"""

JS = """
var CUR=null;
function open_(id){
 fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({mode:id})}).then(r=>r.json()).then(p=>{CUR=p;render(p,id);});
 document.getElementById('box').innerHTML='<h2>מודד…</h2><p class=tiny>מדידה חיה של הקופסאות המעורבות. לא מדווח מצב מוצהר.</p>';
 document.getElementById('panel').classList.add('on');
}
function esc(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function render(p,id){
 var h='';
 if(p.refused){
  h+='<div class=refuse><h3>'+esc(p.he)+'</h3>';
  (p.detail||[]).forEach(function(d){if(d)h+='<p>'+esc(d)+'</p>';});
  h+='</div><p class=tiny>סוג הסירוב: '+esc(p.kind)+'. אין דגל כפייה בשום מקום במערכת — לעקוף אפשר רק בעריכת matzav_sacred.py ביד.</p>';
  h+='<div style="margin-top:14px"><button class=cancel onclick="close_()">סגור</button></div>';
 } else {
  h+='<h2>'+esc(p.title_he)+'</h2><p class=tiny>נמדד לפני '+p.obs_age_s+' שניות · קופסאות: '+esc((p.boxes||[]).join(', '))+'</p>';
  if(p.honesty)h+='<div class=honest>יושר: '+esc(p.honesty)+'</div>';
  if(!p.steps.length)h+='<div class=step>אין מה לעשות — המצב כבר מתקיים.</div>';
  p.steps.forEach(function(s){
   if(s.act=='stop')h+='<div class="step stop">עוצר · '+esc(s.box)+' · '+esc(s.title)+' — מפנה '+(s.frees_gb||0)+' GB'+(s.gpu_gb?(' (מתוכם '+s.gpu_gb+' GB GPU)'):'')+'</div>';
   else h+='<div class=step>מפעיל · '+esc(s.box)+' · '+esc(s.title)+' — '+(s.warm?'חם':'קר')+', '+s.seconds+' שניות'+(s.estimated?' (אומדן, לא נמדד)':'')+'</div>';
  });
  (p.warnings||[]).forEach(function(w){h+='<div class="step warnl">⚠ '+esc(w)+'</div>';});
  h+='<h3 style="margin-top:14px">תקציב</h3><table><tr><th>קופסה</th><th>פנוי</th><th>דרוש</th><th>מפונה</th><th>GPU תפוס</th></tr>';
  for(var b in p.budget){var x=p.budget[b];
   h+='<tr><td>'+esc(b)+'</td><td>'+x.free_gb+' GB</td><td>'+x.need_gb+' GB</td><td>'+x.freed_gb+' GB</td><td>'+(x.gpu_held_gb==null?'—':x.gpu_held_gb+' GB')+'</td></tr>';}
  h+='</table><p class=tiny>GB10: אין מד VRAM — nvidia-smi מחזיר N/A. התקציב הוא MemAvailable פחות שמורה.</p>';
  h+='<p style="font-size:17px;margin-top:12px"><b>עלות: כ-'+p.wall_s+' שניות'+(p.estimated?' (חלק אומדן)':'')+'</b></p>';
  h+='<div style="margin-top:16px;display:flex;gap:10px">';
  if(p.steps.length)h+='<button class=go onclick="go_(\\''+id+'\\')">אשר והרץ</button>';
  h+='<button class=cancel onclick="close_()">ביטול</button></div>';
 }
 document.getElementById('box').innerHTML=h;
}
function close_(){document.getElementById('panel').classList.remove('on');}
function go_(id){
 document.getElementById('box').innerHTML='<h2>מריץ…</h2><div class=log id=lg>starting…</div>';
 fetch('/api/apply',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({mode:id})}).then(function(r){
   if(r.status==409){return r.json().then(function(j){
     document.getElementById('lg').textContent='409 — תוכנית אחרת רצה: '+j.mode+'. אין תור. תוכנית אחת, או סירוב.';});}
   return r.json().then(function(j){
    var t=(j.log||[]).map(function(e){return JSON.stringify(e);}).join('\\n');
    document.getElementById('box').innerHTML='<h2>'+esc(j.outcome)+'</h2><div class=log>'+esc(t)+'</div><p class=tiny>המצב נמדד מחדש. הכל נרשם ב-state/history.jsonl.</p><div style="margin-top:14px"><button class=cancel onclick="location.reload()">רענן</button></div>';
   });
  });
}
"""


def _cls(status):
    return {"satisfied": "ok", "warm": "warm", "cold": "cold",
            "never-run": "never", "empty": "cold"}.get(status, "cold")


def _tag(status):
    return {"satisfied": "מתקיים", "warm": "חם", "cold": "קר",
            "never-run": "לא הורץ מעולם", "empty": "—"}.get(status, "")


def page():
    st = refresh()
    now = time.time()
    o = []
    o.append("<!doctype html><html lang=he dir=rtl><meta charset=utf-8>"
             "<title>מצב — חדר הבקרה של הצי</title>"
             "<meta name=viewport content='width=device-width,initial-scale=1'>"
             "<style>%s</style><body><div class=wrap>" % CSS)
    o.append("<h1>מצב · MATZAV</h1><div class=sub>חדר הבקרה של הצי. "
             "לחיצה על מצב מראה תוכנית — מה עולה, מה יורד, כמה זמן, כמה זיכרון. "
             "רק אחר כך זה רץ.</div>")

    # ---- fleet bar --------------------------------------------------------
    o.append("<div class=bar>")
    for b, bs in st["boxes"].items():
        r = bs.get("reachable")
        col = "#1f9d55" if r is True else ("#a01a1a" if r is False else "#9a6b00")
        lab = "עונה" if r is True else ("לא עונה" if r is False else "לא ידוע")
        av = bs.get("ram_avail_gb")
        o.append("<span class=pill><b>%s</b> <span style='color:%s'>%s</span>"
                 " · פנוי %s GB%s%s</span>"
                 % (html.escape(b), col, lab,
                    av if av is not None else "?",
                    (" · GPU %s GB" % bs["gpu_held_gb"])
                    if bs.get("gpu_held_gb") else "",
                    (" · דיסק %s GB" % bs["disk_avail_gb"])
                    if bs.get("disk_avail_gb") else ""))
    o.append("<span class=pill>נמדד לפני %d שניות</span>"
             % (now - st["ts"]))
    o.append("<span class=pill><a href='http://127.0.0.1:8858/'>מקום</a></span>")
    o.append("</div>")

    # collector disagreement — a live broken window, surfaced
    hud_bad = [b for b, bs in st["boxes"].items()
               if bs.get("hud_reachable") is False and bs.get("reachable") is True]
    if hud_bad:
        o.append("<div class=card style='border-color:#e8a11a;background:#fffaf0'>"
                 "<h3>⚠ חלון שבור חי — הקולקטור והמדידה חלוקים</h3>"
                 "<p>almaware-hud/status.json מדווח שהקופסאות <b>%s</b> לא "
                 "נגישות, בזמן ש-MATZAV מדד אותן חיות ב-SSH בשנייה הזאת. "
                 "MATZAV לא מאמין לשכבה הזולה: כשל אחד הוא <i>לא ידוע</i>, "
                 "לא <i>כבוי</i>. הקוקפיט על 8790 קורא בדיוק את הקובץ הזה.</p>"
                 "</div>" % html.escape(", ".join(hud_bad)))

    # ---- modes ------------------------------------------------------------
    o.append("<div class=modes>")
    for m in MODES:
        s = mode_status(m, st)
        cls, tag = _cls(s), _tag(s)
        onclick = ("onclick=\"open_('%s')\"" % m["id"]) if m.get("runnable") \
            else ("onclick=\"open_('%s')\"" % m["id"])
        o.append("<div class='mode %s' %s>" % (cls, onclick))
        o.append("<span class='tag'>%s</span>" % tag)
        o.append("<h2>%s</h2><div class=en>%s</div>"
                 % (html.escape(m["title_he"]), html.escape(m["title_en"])))
        o.append("<div class=st>%s</div>" % html.escape(m.get("subtitle_he", "")))
        if not m.get("runnable"):
            o.append("<div class=tiny style='margin-top:6px'>מסרב לרוץ — "
                     "הצהרה, לא תכונה</div>")
        o.append("</div>")
    o.append("</div>")

    # ---- sacred -----------------------------------------------------------
    o.append("<div class=card><h3>הרשימה הקדושה — אף מצב לא נוגע בזה</h3><table>"
             "<tr><th>קופסה</th><th>שירות</th><th>מדידה</th><th>למה</th></tr>")
    for s in SACRED:
        if s.kind == "audio":
            continue
        uid = "%s/%s" % (s.box, s.unit.replace(".service", ""))
        us = st["units"].get(uid) or {}
        r = us.get("real", "—")
        klass = {"up": "up", "down": "down"}.get(r, "unk")
        word = {"up": "חי", "down": "לא עונה"}.get(r, "לא ידוע")
        o.append("<tr class=sacred><td>%s</td><td>%s%s</td>"
                 "<td class=%s>%s</td><td class=tiny>%s</td></tr>"
                 % (html.escape(s.box), html.escape(s.unit),
                    "<span class='badge b-sac'>נוסף במדידה</span>"
                    if s.added_by == "measurement" else "",
                    klass, word, html.escape(s.why)))
    o.append("</table><p class=tiny>חוק השמע הקדוש חל על כל הצי: MATZAV לא "
             "פותח, לא תופס ולא משתיק שום התקן אודיו, בשום מצב. "
             "ה-PC לא מארח מצבים בכלל (PC_HOSTS_NO_MODES=%s).</p></div>"
             % PC_HOSTS_NO_MODES)

    # ---- broken windows / disagreements -----------------------------------
    rows = []
    for uid, u in sorted(st["units"].items()):
        if u.get("broken_window") or u.get("disagreement") or u.get("human_hold"):
            rows.append(u)
    o.append("<div class=card><h3>חלונות שבורים ומחלוקות — מוצהר מול נמדד</h3>"
             "<table><tr><th>יחידה</th><th>מוצהר</th><th>נמדד</th>"
             "<th>מה לא בסדר</th></tr>")
    for u in rows:
        badges = ""
        if u.get("disagreement"):
            badges += "<span class='badge b-dis'>מחלוקת</span>"
        if u.get("broken_window"):
            badges += "<span class='badge b-bw'>חלון שבור</span>"
        if u.get("human_hold"):
            badges += "<span class='badge b-hh'>אדם מחזיק</span>"
        o.append("<tr><td>%s%s</td><td>%s</td><td class=%s>%s</td>"
                 "<td class=tiny>%s</td></tr>"
                 % (html.escape(u["id"]), badges,
                    html.escape(str(u.get("declared"))),
                    {"up": "up", "down": "down"}.get(u["real"], "unk"),
                    u["real"],
                    html.escape((u.get("broken_window") or
                                 u.get("disagreement") or
                                 u.get("human_hold_why") or "")[:220])))
    o.append("</table></div>")

    # ---- all units --------------------------------------------------------
    o.append("<div class=card><h3>כל היחידות — מצב נמדד</h3><table>"
             "<tr><th>יחידה</th><th>מוצהר</th><th>נמדד</th><th>חם</th>"
             "<th>עלות</th><th>איך זה נמדד</th></tr>")
    for uid, u in sorted(st["units"].items()):
        warm = u.get("warm")
        wtxt = "—"
        if warm is True:
            wtxt = "חם"
            if u.get("warm_expires_in_s") is not None:
                wtxt = "חם, פג בעוד %d דק׳" % max(
                    0, u["warm_expires_in_s"] // 60)
        elif warm is False:
            wtxt = "קר"
        c = u.get("cost") or {}
        cost = ("%s GB" % c.get("ram_gb")) if c.get("ram_gb") else "—"
        if c.get("estimated"):
            cost += "<span class='badge b-est'>אומדן</span>"
        o.append("<tr%s><td>%s%s</td><td>%s</td><td class=%s>%s</td><td>%s</td>"
                 "<td>%s</td><td class=tiny>%s</td></tr>"
                 % (" class=sacred" if u["sacred"] else "",
                    html.escape(uid),
                    "<span class='badge b-sac'>קדוש</span>" if u["sacred"] else "",
                    html.escape(str(u.get("declared"))),
                    {"up": "up", "down": "down"}.get(u["real"], "unk"),
                    u["real"], wtxt, cost,
                    html.escape((u.get("detail") or "")[:90])))
    o.append("</table></div>")

    # ---- unbootable -------------------------------------------------------
    o.append("<div class=card><h3>יחידות שלא יכולות לעלות — מוחרגות מכל מצב</h3>"
             "<p class=tiny>מצבים מאומתים מול משקלים על הדיסק, לא מול קובצי "
             "יחידה. אחרת חדר הבקרה מציע שלושה כפתורי קודר שלא יכולים לעבוד.</p>"
             "<table><tr><th>קופסה</th><th>יחידה</th><th>למה</th></tr>")
    for x in REG.get("unbootable", []):
        o.append("<tr><td>%s</td><td>%s</td><td class=tiny>%s</td></tr>"
                 % (html.escape(x["box"]), html.escape(x["unit"]),
                    html.escape(x["why"])))
    o.append("</table></div>")

    # ---- history ----------------------------------------------------------
    hist = A.history(40)
    o.append("<div class=card><h3>היסטוריה — מי, מה, מתי</h3>")
    if not hist:
        o.append("<p class=tiny>עדיין ריק.</p>")
    else:
        o.append("<table><tr><th>מתי</th><th>מצב</th><th>מי</th><th>תוצאה</th>"
                 "<th>צעדים</th></tr>")
        for h in hist:
            steps = " · ".join(
                "%s %s (%s%s)" % (s["act"], s["unit"], s["status"],
                                  ", %ss" % s["dur_s"] if s.get("dur_s") else "")
                for s in h.get("steps", []))
            o.append("<tr><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td>"
                     "<td class=tiny>%s</td></tr>"
                     % (html.escape(h.get("when", "")),
                        html.escape(h.get("mode", "")),
                        html.escape(h.get("actor", "")),
                        html.escape(h.get("outcome", "")),
                        html.escape(steps[:300])))
        o.append("</table>")
    o.append("</div>")

    o.append("<p class=tiny>MATZAV · stdlib בלבד · הרשימה הקדושה היא מבנה בקוד "
             "(matzav_sacred.py) ואין דגל כפייה · כל מדידה חיה, אף פעם לא מוצהרת."
             "</p>")
    o.append("<div id=panel onclick='if(event.target.id==\"panel\")close_()'>"
             "<div id=box></div></div>")
    o.append("<script>%s</script></div></body></html>" % JS)
    return "".join(o).encode("utf-8")


# --------------------------------------------------------------------------
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            self._send(200, page())
        elif p == "/api/state":
            self._json(200, refresh(force=True))
        elif p == "/api/progress":
            self._json(200, {"inflight": A.read_inflight(),
                             "log": _running["log"]})
        elif p == "/api/history":
            self._json(200, A.history(80))
        elif p == "/health":
            self._json(200, {"ok": True, "service": "matzav", "port": PORT,
                             "units": len(UNITS), "modes": len(MODES)})
        else:
            self._send(404, b"no")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                    # noqa: BLE001
            body = {}
        mid = body.get("mode")
        m = next((x for x in MODES if x["id"] == mid), None)
        if not m:
            return self._json(400, {"error": "unknown mode"})

        if self.path == "/api/plan":
            boxes = sorted({UNITS[u]["box"] for u in
                            m.get("want", []) + m.get("concede", [])
                            if u in UNITS})
            st = P.observe(UNITS, BOXES, only_boxes=boxes) if boxes \
                else refresh(force=True)
            if boxes:  # keep ts semantics but only for measured boxes
                st["ts"] = time.time()
            pl = PL.plan(m, UNITS, st)
            return self._json(200, pl)

        if self.path == "/api/apply":
            if not _lock.acquire(blocking=False):
                cur = A.read_inflight() or {}
                return self._json(409, {"error": "plan in flight",
                                        "mode": cur.get("mode"),
                                        "steps": len(cur.get("steps") or [])})
            try:
                boxes = sorted({UNITS[u]["box"] for u in
                                m.get("want", []) + m.get("concede", [])
                                if u in UNITS})
                st = P.observe(UNITS, BOXES, only_boxes=boxes)
                st["ts"] = time.time()
                pl = PL.plan(m, UNITS, st)
                if pl.get("refused"):
                    return self._json(200, {"outcome": "REFUSED", "plan": pl,
                                            "log": []})
                pl["pre_state"] = {u: (st["units"].get(u) or {}).get("real")
                                   for u in st["units"]}
                log = []
                _running["log"] = log
                out = "?"
                for ev in A.apply_plan(pl, UNITS, BOXES):
                    log.append(ev)
                    if ev.get("event") == "end":
                        out = ev["outcome"]
                refresh(force=True)
                return self._json(200, {"outcome": out, "log": log})
            finally:
                _lock.release()

        self._json(404, {"error": "no"})


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    inf = A.read_inflight()
    if inf and inf.get("status") == "running":
        print("RECOVERY: a plan was interrupted:", inf.get("mode"),
              "- MATZAV does NOT auto-resume.")
    print("MATZAV on http://127.0.0.1:%d/  (%d units, %d modes)"
          % (PORT, len(UNITS), len(MODES)))
    S(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
