#!/usr/bin/env python3
# ============================================================
#  ALMAWARE HUB  ·  All-In-One Master Dashboard
#  One local surface that shows the whole ALMAWARE ecosystem at a glance.
#  Pure stdlib (no deps, ALMAWARE-pure). Read-only status + links + one safe
#  "Ensure Suite" action (reuses the audited watchdog). Never kills anything.
#
#  Run:  python hub_server.py       ->  http://127.0.0.1:8000
#  לזכרה של עלמה ז"ל · ALMAWARE
# ============================================================
import http.server, socketserver, socket, json, os, subprocess, time, html
import urllib.request

PORT = 8000
ERAN_METRICS = r"D:\CLAUDE\eran-live\logs\metrics.jsonl"
WATCHDOG_LOG = r"D:\CLAUDE\almaware-watchdog\watchdog.log"
WATCHDOG_PS1 = r"D:\CLAUDE\almaware-watchdog\ensure-almaware-suite.ps1"
# DGX section reads the eran-dashboard's sanitized /status.json (read-only).
DGX_STATUS_URL = os.environ.get("ALMA_DGX_STATUS_URL", "http://127.0.0.1:8788/status.json")
DGX_STATUS_FILE = r"D:\CLAUDE\almaware-cockpit\status.json"  # fallback if the dashboard is down

def port_up(p, host="127.0.0.1", t=0.35):
    try:
        with socket.create_connection((host, p), t): return True
    except Exception:
        return False

def file_fresh(path, max_age_s):
    try:
        age = time.time() - os.path.getmtime(path)
        return age <= max_age_s, int(age)
    except Exception:
        return False, None

# --- registry: section -> [tiles] -----------------------------------------
# each tile: name, kind(service|training|app|model|device), probe()-> (state,detail), url
def svc(port, name):
    def probe():
        return ("up" if port_up(port) else "down"), (":%d" % port)
    return probe

def eran_probe():
    try:
        with open(ERAN_METRICS, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 2048))
            tail = f.read().decode("utf-8", "ignore").strip().splitlines()
        d = json.loads(tail[-1])
        fresh, age = file_fresh(ERAN_METRICS, 600)  # 10 min = live
        step = d.get("step"); loss = d.get("loss")
        det = "step %s · loss %s · %s" % (
            f"{int(step):,}" if step else "?",
            (f"{loss:.3f}" if isinstance(loss,(int,float)) else "?"),
            ("live" if fresh else ("STALE %dh" % (age//3600) if age else "stale")))
        return ("up" if fresh else "warn"), det
    except Exception:
        return "down", "no metrics"

def watchdog_probe():
    try:
        fresh, age = file_fresh(WATCHDOG_LOG, 300)
        return ("up" if fresh else "warn"), ("log %ds ago" % age if age is not None else "no log")
    except Exception:
        return "warn", "watchdog probe error"

def _dgx_read_status():
    """Return parsed DGX status dict from the eran-dashboard, or None.
    Tries the live /status.json endpoint first, then a local file fallback.
    Fully guarded: never raises."""
    try:
        req = urllib.request.Request(DGX_STATUS_URL, headers={"User-Agent": "alma-hub"})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8", "ignore")), True
    except Exception:
        pass
    try:
        with open(DGX_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.loads(f.read()), False
    except Exception:
        return None, False

def dgx_summary_probe():
    """Overall DGX fleet health as a single tile."""
    try:
        data, live = _dgx_read_status()
        if not data:
            return "down", "eran-dashboard unreachable"
        nodes = data.get("nodes") or []
        summ = data.get("summary") or {}
        online = summ.get("online", sum(1 for n in nodes if n.get("online")))
        total = summ.get("total", len(nodes))
        training = summ.get("training", sum(1 for n in nodes if n.get("train")))
        tmax = summ.get("gtemp_max")
        gov = summ.get("gov_worst", 0)
        src = "live" if live else "cached"
        det = "%s/%s online · %s training" % (online, total, training)
        if tmax is not None:
            det += " · max %s°C" % tmax
        det += " · %s" % src
        state = "up" if (total and online == total) else ("warn" if online else "down")
        if gov and gov >= 2:
            state = "warn"
        return state, det
    except Exception:
        return "down", "dgx probe error"

def dgx_node_probe(node_name):
    """Per-node DGX tile: temp, util, training flag."""
    def probe():
        try:
            data, live = _dgx_read_status()
            if not data:
                return "down", "no data"
            for n in (data.get("nodes") or []):
                if n.get("name") == node_name:
                    if not n.get("online", False):
                        return "down", "offline"
                    t = n.get("gtemp"); u = n.get("gutil"); tr = n.get("train")
                    sev = n.get("gov_sev", 0)
                    det = "%s°C · GPU %s%%%s" % (
                        t if t is not None else "?",
                        u if u is not None else "?",
                        " · training" if tr else "")
                    st = "up"
                    if sev and sev >= 2:
                        st = "warn"
                    elif isinstance(t, (int, float)) and t >= 85:
                        st = "warn"
                    return st, det
            return "down", "not reported"
        except Exception:
            return "down", "node probe error"
    return probe

REGISTRY = {
  "① ערן — Eran (live brain)": [
     ("Eran training",        "training", eran_probe, "http://127.0.0.1:8788"),
     ("Eran stats dashboard", "service",  svc(8788,"eran-dash"), "http://127.0.0.1:8788"),
     ("Eran private dash",    "service",  svc(8790,"eran-local"), "http://127.0.0.1:8790"),
  ],
  "② DGX fleet — ערן bodies": [
     ("DGX fleet",   "device", dgx_summary_probe,         "http://127.0.0.1:8788/status.json"),
     ("eran1",       "device", dgx_node_probe("eran1"),   ""),
     ("eran2",       "device", dgx_node_probe("eran2"),   ""),
     ("eran3",       "device", dgx_node_probe("eran3"),   ""),
     ("eran4",       "device", dgx_node_probe("eran4"),   ""),
  ],
  "③ Always-on services": [
     ("Ollama (brains)",  "service", svc(11434,"ollama"), "http://127.0.0.1:11434"),
     ("Quorum council",   "service", svc(8099,"quorum"),  "http://127.0.0.1:8099"),
     ("GIST dashboard",   "service", svc(8092,"gist"),    "http://127.0.0.1:8092"),
     ("Watchdog",         "service", watchdog_probe, ""),
  ],
  "④ Apps": [
     ("Aiko / RAM chat",       "app", svc(8795,"aiko"), "http://127.0.0.1:8795"),
     ("Alma Multi-Messenger",  "app", (lambda: ("warn","wa-mcp bridge (owner-only)")), ""),
     ("Revital (photo)",       "app", (lambda: ("warn","scaffold · gated on GO")), ""),
     ("AI Multimedia Center",  "app", (lambda: ("warn","GUI · launcher path stale")), ""),
     ("Safa-Achat (one lang)", "app", (lambda: ("warn","design only")), ""),
  ],
  "⑤ Models / harness": [
     ("Master-Modeler",  "model", (lambda: ("up","control plane · 13/13")), ""),
     ("Meta-Selector",   "model", (lambda: ("up","gate · 6/6")), ""),
     ("Perets (3-brain)","model", (lambda: ("warn","FSDP smoke ok · cable-blocked")), ""),
  ],
  "⑥ OS / devices": [
     ("ALMA-OS T-Deck",  "device", (lambda: ("up","builds clean · 4.7% flash")), ""),
     ("ALMA-OS Jetson",  "device", (lambda: ("warn","flash frozen 7% · check")), ""),
     ("Semicom camera",  "device", (lambda: ("up","RTSP/ONVIF · the eye")), ""),
  ],
}

DOT = {"up":"#1f8a4c","warn":"#b9770a","down":"#d7263d"}

def render():
    rows = []
    try:
        for section, tiles in REGISTRY.items():
            cards = []
            for name, kind, probe, url in tiles:
                try:
                    state, detail = probe()
                except Exception:
                    state, detail = "down", "probe error"
                try:
                    link = ('<a href="%s" target="_blank">open ↗</a>' % html.escape(url, quote=True)) if url else ""
                    cards.append(
                      '<div class="card"><span class="dot" style="background:%s"></span>'
                      '<div class="cn"><b>%s</b><span class="cd">%s</span></div>%s</div>'
                      % (DOT.get(state,"#999"), html.escape(str(name)), html.escape(str(detail)), link))
                except Exception:
                    cards.append('<div class="card"><span class="dot" style="background:#999"></span>'
                                 '<div class="cn"><b>?</b><span class="cd">render error</span></div></div>')
            rows.append('<h2>%s</h2><div class="grid">%s</div>' % (html.escape(str(section)), "".join(cards)))
    except Exception as e:
        return '<h2>hub render error</h2><div class="grid"><div class="card">%s</div></div>' % html.escape(str(e))
    return "".join(rows)

PAGE = """<!doctype html><html lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALMAWARE HUB</title>
<style>
:root{--ink:#12232e;--muted:#5b7180;--edge:#dfe7ec;--terra:#d7263d;--cream:#fbf7f0}
body{margin:0;background:var(--cream);color:var(--ink);font-family:"Segoe UI",Arial,sans-serif}
header{padding:16px 22px;background:#fff;border-bottom:1px solid var(--edge);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{margin:0;font-size:20px} h1 b{color:var(--terra)}
.sub{color:var(--muted);font-size:13px}
button{font:inherit;font-size:13px;border:1px solid var(--edge);background:#fff;border-radius:9px;padding:6px 13px;cursor:pointer}
button:hover{background:#f4f8fb} .stamp{margin-left:auto;color:var(--muted);font-size:12px}
main{max-width:1200px;margin:0 auto;padding:16px 22px 50px}
h2{font-size:15px;color:var(--muted);margin:20px 0 8px;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.card{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid var(--edge);border-radius:12px;padding:10px 13px}
.dot{width:11px;height:11px;border-radius:50%;flex:none;box-shadow:0 0 0 3px rgba(0,0,0,.04)}
.cn{display:flex;flex-direction:column;line-height:1.3} .cn b{font-size:14px}
.cd{font-size:12px;color:var(--muted)} .card a{margin-left:auto;font-size:12px;color:var(--terra);text-decoration:none}
footer{text-align:center;color:var(--muted);font-size:12px;padding:18px}
</style></head><body>
<header><h1>ALMAWARE <b>HUB</b></h1><span class="sub">All-In-One · one surface, whole ecosystem</span>
<button onclick="ensure()">⟳ Ensure Suite</button><span class="stamp" id="stamp"></span></header>
<main id="app">{body}</main>
<footer>לזכרה של עלמה ז"ל · auto-refresh 5s</footer>
<script>
async function tick(){try{const r=await fetch('/api');const j=await r.json();
document.getElementById('app').innerHTML=j.html;
document.getElementById('stamp').textContent='updated '+new Date().toLocaleTimeString();}catch(e){}}
async function ensure(){await fetch('/ensure',{method:'POST'});setTimeout(tick,2500);}
setInterval(tick,5000);
</script></body></html>"""

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, ct="text/html; charset=utf-8", code=200):
        try:
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # client went away mid-response; ignore, keep server alive
            pass
        except Exception:
            pass
    def do_GET(self):
        try:
            if self.path.startswith("/api"):
                self._send(json.dumps({"html": render()}), "application/json")
            else:
                self._send(PAGE.replace("{body}", render()))
        except Exception:
            try:
                self._send('{"ok":false,"err":"internal"}', "application/json", 500)
            except Exception:
                pass
    def do_POST(self):
        try:
            if self.path.startswith("/ensure"):
                try:
                    exe = "pwsh"
                    subprocess.Popen([exe,"-NoProfile","-ExecutionPolicy","Bypass","-File",WATCHDOG_PS1,"-Once"],
                                     creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                except Exception:
                    pass
                self._send('{"ok":true}', "application/json")
            else:
                self._send('{"ok":false}', "application/json", 404)
        except Exception:
            pass

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as httpd:
        print("ALMAWARE HUB on http://127.0.0.1:%d" % PORT)
        httpd.serve_forever()
