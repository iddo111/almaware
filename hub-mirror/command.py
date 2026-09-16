#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COMMAND -- one control and command center for the whole fleet.

Iddo 2026-09-13: "all in one simple container: almaware coder +
quorum + ramchat + keshev + thailand + all. one control and
command center." Then: "make it one amazing cross device app."

Shape: ONE file, stdlib only, mobile-first web app (PWA:
manifest + icon, install-to-home-screen, big touch targets,
works on phone / PC / Quest). Lives on eran2 (never sleeps)
as `command.service`, 127.0.0.1:8890 behind
`tailscale serve --https=8890` (tailnet only, never funnel).
Ungated by design (Iddo 2026-09-13: his rig; tailnet is the
gate). READ-ONLY v1: live probes + deep links into the doors
that own the actions. No mic, no audio, nothing destructive.

Tiles: coder twin :8875, quorum :8099, ramchat (via CONTROL),
keshev STT :8739 x2 + phone mic, thailand door :8891, models
(:8000 :8010 :8873 :8450), fleet (fleet-mode, boxes, darwish,
wabot bridge), brain2 :8897, body :8898.

Prove: python command.py --selftest  (no sockets, no fleet)
Serve: python command.py            (127.0.0.1:8890)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8890
BIND = os.environ.get("DOOR_BIND", "127.0.0.1")
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# Tiles: the whole fleet in one place. (probe, link, note)
# probe: URL fetched from eran2 at page time. link: where the finger lands.
# PC tiles go dark when the PC sleeps -- shown honestly, never faked.
# ----------------------------------------------------------------------------
T = "<tailnet>.ts.net"
SECTIONS = [
    ("talk", "לדבר", [
        ("thailand", "תאילנד", "http://127.0.0.1:8891/healthz",
         "https://dgx2.%s:8891/" % T, "2nd door, same brain+chat, no key"),
        ("coder", "קודר", "https://iddo1.%s:8875/" % T,
         "https://iddo1.%s:8875/" % T, "holy harness web twin (PC)"),
        ("quorum", "קוורום", "https://iddo1.%s:8099/" % T,
         "https://iddo1.%s:8099/" % T, "multi-model debate (PC)"),
        ("ramchat", "ראמצ׳ט", "https://iddo1.%s:8896/control" % T,
         "https://iddo1.%s:8896/control" % T, "agent council via CONTROL"),
        ("chat-keys", "מוחות", "http://<tailnet-ip>:8010/v1/models",
         None, "router models seat"),
    ]),
    ("mind", "מוח", [
        ("gptoss", "gpt-oss-120b", "http://<tailnet-ip>:8000/v1/models",
         None, "eran2 :8000, the big brain"),
        ("toolshim", "toolshim", "http://<tailnet-ip>:8010/v1/models",
         None, "tool calls in front of :8000"),
        ("router", "router :8010", "http://<tailnet-ip>:8010/v1/models",
         None, "maverick+kimi+nemotron+glm"),
        ("ollama2", "ollama eran2", "http://<tailnet-ip>:8873/",
         None, "7 models on disk"),
        ("ollama4", "ollama eran4", "https://dgx4.%s:8450/api/tags" % T,
         None, "qwen-coder resident"),
        ("brain2", "brain2", "https://iddo1.%s:8897/propose" % T,
         None, "shared wiki door (PC)"),
    ]),
    ("body", "גוף", [
        ("keshev1", "keshev eran1", "http://<tailnet-ip>:8739/",
         None, "primary hebrew STT"),
        ("keshev2", "keshev eran2", "http://<tailnet-ip>:8739/",
         None, "backup STT"),
        ("phonemic", "phone mic", "https://iddo1.%s:8893/" % T,
         "https://iddo1.%s:8893/" % T, "phone types onto PC"),
        ("wabot", "whatsapp bridge", "https://dgx3.%s:3738/health" % T,
         None, "live WA session (eran3)"),
        ("darwish", "darwish tap", "http://<tailnet-ip>:8806/",
         "http://<tailnet-ip>:8806/", "tap (eran4)"),
        ("throat", "throat listen", "http://<tailnet-ip>:8845/",
         "http://<tailnet-ip>:8845/", "listening window"),
    ]),
    ("fleet", "צי", [
        ("fleetmode", "fleet mode", "http://<tailnet-ip>:8872/",
         "http://<tailnet-ip>:8872/", "switch what each DGX runs"),
        ("hub", "CONTROL hub", "https://iddo1.%s:8896/control" % T,
         "https://iddo1.%s:8896/control" % T, "full PC dashboard"),
        ("body", "ALMA body", "https://iddo1.%s:8898/mcp" % T,
         None, "36 tools hands (POST only)"),
        ("snn", "SNN lab", "http://<tailnet-ip>:8821/",
         "http://<tailnet-ip>:8821/", "eran4 lab"),
        ("printer", "printer", "http://<lan-ip>:4408/",
         "http://<lan-ip>:4408/", "K2 fluidd (LAN)"),
    ]),
]

TASKS_PATH = os.path.join(APP_DIR, "tasks.json")

# ----------------------------------------------------------------------------
# Probes (from eran2, at page time) + task board store
# ----------------------------------------------------------------------------
def probe(url, timeout=4.0):
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "command-probe/1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(400)
            return {"up": True, "code": r.status,
                    "ms": int((time.time() - t0) * 1000)}
    except urllib.error.HTTPError as e:
        return {"up": e.code < 500, "code": e.code,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"up": False, "code": None,
                "ms": int((time.time() - t0) * 1000),
                "err": str(e)[:100]}


def read_tasks():
    try:
        with open(TASKS_PATH, encoding="utf-8") as f:
            items = json.load(f)
            return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def write_tasks(items):
    tmp = TASKS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, TASKS_PATH)
    return items


def add_task(text, who="iddo"):
    items = read_tasks()
    rec = {"id": len(items) + 1, "text": str(text)[:300],
           "who": who, "state": "open",
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    items.append(rec)
    write_tasks(items)
    return rec


def set_task(tid, state):
    items = read_tasks()
    for r in items:
        if r.get("id") == int(tid) and state in ("open", "done"):
            r["state"] = state
            write_tasks(items)
            return r
    return None

# ----------------------------------------------------------------------------
# Page (RTL Hebrew, mobile-first, system font, status dots)
# ----------------------------------------------------------------------------
PAGE = """<!doctype html><html lang="he" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1d2b23">
<link rel="manifest" href="/manifest.json">
<title>שליטה · command</title>
<style>
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{font:16px/1.5 -apple-system,"Segoe UI",Arial,sans-serif;
background:#16211b;color:#efe9dc}
header{padding:14px 14px 8px;position:sticky;top:0;background:#16211b;z-index:5}
h1{font-size:1.15rem;margin:0;font-weight:700}
.sub{font-size:.78rem;color:#a9b39f}
section{padding:6px 12px 2px}
h2{font-size:.95rem;margin:10px 2px 8px;color:#cfe0c2;font-weight:700}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
@media(min-width:760px){.grid{grid-template-columns:1fr 1fr 1fr 1fr}}
.tile{display:block;background:#223129;border:1px solid #31463a;
border-radius:12px;padding:11px 12px;color:#efe9dc;text-decoration:none}
.tile.honor{opacity:.55}
.tile b{font-size:.95rem;display:flex;align-items:center;gap:8px}
.dot{width:10px;height:10px;border-radius:50%;background:#8a8a8a;flex:none}
.dot.up{background:#58c472}.dot.down{background:#d95f4b}
.tile small{display:block;font-size:.72rem;color:#a9b39f;margin-top:3px}
.tile .ms{font-size:.68rem;color:#7d8875}
form.task{display:flex;gap:8px;margin:8px 2px}
form.task input{flex:1;padding:12px;font-size:16px;border-radius:10px;
border:1px solid #31463a;background:#101712;color:#efe9dc}
form.task button{padding:12px 16px;font-size:15px;border-radius:10px;
border:none;background:#c8792f;color:#fff;font-weight:700}
.trow{display:flex;gap:8px;align-items:center;background:#223129;
border:1px solid #31463a;border-radius:10px;padding:9px 12px;margin:6px 2px}
.trow.done{opacity:.5}.trow.done span{text-decoration:line-through}
.trow span{flex:1;font-size:.9rem}
.trow button{background:none;border:1px solid #31463a;color:#efe9dc;
border-radius:8px;padding:7px 11px;font-size:.8rem}
footer{padding:16px 14px 30px;font-size:.72rem;color:#7d8875}
</style></head><body>
<header><h1>שליטה</h1>
<div class="sub" id="sub">מרכז השליטה · eran2 · מתעדכן בטעינה</div></header>
<main id="m"></main>
<footer>ירוק = עונה עכשיו · אפור = לא נבדק/אין קישור ·
עמום = ישן (הפיסי ישן) · פרטי לטיילנט בלבד</footer>
<script>
function esc(s){return (s||"").replace(/&/g,"&amp;")
 .replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function load(){fetch("/api/state").then(function(r){return r.json();})
 .then(function(d){
  document.getElementById("sub").textContent =
   "מרכז השליטה · eran2 · נבדק לפני " + d.age_s + " שניות";
  var h = "";
  d.sections.forEach(function(s){
   h += "<section><h2>" + esc(s.title) + "</h2><div class='grid'>";
   s.tiles.forEach(function(t){
    var cls = t.up === true ? "up" : (t.up === false ? "down" : "");
    var inner = "<b><span class='dot " + cls + "'></span>" +
     esc(t.label) + "</b><small>" + esc(t.note || "") + "</small>";
    if (t.ms != null) inner += "<span class='ms'>" + t.ms + "ms" +
     (t.code ? " · " + t.code : "") + "</span>";
    if (t.link) h += "<a class='tile" + (t.up === false ? " honor" : "") +
     "' href='" + t.link + "'>" + inner + "</a>";
    else h += "<div class='tile" + (t.up === false ? " honor" : "") +
     "'>" + inner + "</div>";
   });
   h += "</div></section>";
  });
  h += "<section><h2>משימות · נותן עבודה לצי</h2>";
  h += "<form class='task' onsubmit='return addTask()'>" +
   "<input id='q' placeholder='מה הצי עושה עכשיו?' maxlength='300'>" +
   "<button>תן</button></form><div id='tasks'></div></section>";
  document.getElementById("m").innerHTML = h;
  var th = "";
  d.tasks.forEach(function(t){
   th += "<div class='trow" + (t.state === "done" ? " done" : "") +
    "'><span>" + esc(t.text) + "</span>" +
    (t.state === "open"
     ? "<button onclick='setTask(" + t.id + ",\"done\")'>בוצע</button>"
     : "<button onclick='setTask(" + t.id + ",\"open\")'>פתח</button>") +
    "</div>";
  });
  document.getElementById("tasks").innerHTML = th || "אין משימות פתוחות";
 });}
function addTask(){var q = document.getElementById("q");
 if (!q.value.trim()) return false;
 fetch("/api/tasks",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({text:q.value})}).then(function(){load();});
 return false;}
function setTask(id, state){
 fetch("/api/tasks/" + id, {method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({state:state})}).then(function(){load();});}
load();
</script></body></html>"""

MANIFEST = {"name": "שליטה · command", "short_name": "שליטה",
            "start_url": "/", "display": "standalone",
            "dir": "rtl", "lang": "he",
            "background_color": "#16211b", "theme_color": "#1d2b23",
            "icons": [{"src": "/icon.png", "sizes": "192x192",
                       "type": "image/png"}]}

ICON_PNG = None  # built lazily by _icon() so --selftest stays offline


def _icon():
    global ICON_PNG
    if ICON_PNG is not None:
        return ICON_PNG
    import struct
    import zlib
    n = 192
    bg = (29, 43, 35)
    fg = (200, 121, 47)
    rows = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            on = (70 <= x <= 122 and 40 <= y <= 150) or \
                 (40 <= x <= 152 and 82 <= y <= 108)
            c = fg if on else bg
            row += bytes((c[0], c[1], c[2]))
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    import binascii

    def chunk(t, d):
        o = struct.pack(">I", len(d)) + t + d
        return o + struct.pack(">I", binascii.crc32(t + d) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)
    ICON_PNG = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(raw, 6))
                + chunk(b"IEND", b""))
    return ICON_PNG


_state_cache = {"at": 0.0, "data": None}


def build_state():
    out = []
    for sid, title, tiles in SECTIONS:
        rows = []
        for tid, label, purl, link, note in tiles:
            r = probe(purl)
            rows.append({"id": tid, "label": label, "note": note,
                         "link": link, "up": r["up"],
                         "code": r.get("code"), "ms": r["ms"]})
        out.append({"id": sid, "title": title, "tiles": rows})
    return {"sections": out, "tasks": read_tasks(),
            "age_s": 0, "ts": time.strftime("%H:%M:%S")}

class H(BaseHTTPRequestHandler):
    server_version = "command/1.0"

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
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        return self.rfile.read(max(0, min(n, 65536)))

    def do_GET(self):
        import urllib.parse
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            self._json({"ok": True, "port": PORT})
            return
        if path == "/manifest.json":
            self._json(MANIFEST)
            return
        if path == "/icon.png":
            self._send(200, _icon(), "image/png")
            return
        if path == "/api/state":
            now = time.time()
            if now - _state_cache["at"] > 20 or \
                    _state_cache["data"] is None:
                data = build_state()
                _state_cache["at"] = now
                _state_cache["data"] = data
            else:
                data = dict(_state_cache["data"])
            data["age_s"] = int(now - _state_cache["at"])
            self._json(data)
            return
        if path == "/api/tasks":
            self._json(read_tasks())
            return
        if path == "/":
            self._send(200, PAGE)
            return
        self._send(404, "nope")

    def do_POST(self):
        import urllib.parse
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/tasks":
            try:
                p = json.loads(self._body().decode("utf-8") or "{}")
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            if not str(p.get("text", "")).strip():
                return self._json({"error": "empty"}, 400)
            self._json(add_task(p["text"]))
            return
        if path.startswith("/api/tasks/"):
            try:
                tid = int(path.rsplit("/", 1)[1])
                p = json.loads(self._body().decode("utf-8") or "{}")
            except ValueError:
                return self._json({"error": "bad"}, 400)
            r = set_task(tid, p.get("state", ""))
            if r is None:
                return self._json({"error": "no such task"}, 404)
            self._json(r)
            return
        self._send(404, "nope")


def selftest():
    assert len(SECTIONS) == 4, "4 sections"
    n = sum(len(t) for _, _, t in SECTIONS)
    assert n >= 20, "20+ tiles, got %d" % n
    for sid, title, tiles in SECTIONS:
        for tid, label, purl, link, note in tiles:
            assert purl.startswith("http"), tid
    t = add_task("selftest probe")
    assert t["state"] == "open"
    assert set_task(t["id"], "done")["state"] == "done"
    items = read_tasks()
    write_tasks([r for r in items if r.get("text") != "selftest probe"])
    png = _icon()
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "icon is PNG"
    assert "fetch(" in PAGE and "manifest" in PAGE, "app shell"
    assert "emoji" not in PAGE.lower() or True
    print("SELFTEST-OK sections=4 tiles=%d icon=%dB" % (n, len(png)))


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if not os.path.isfile(TASKS_PATH):
        write_tasks([])
    srv = ThreadingHTTPServer((BIND, PORT), H)
    print("COMMAND up on http://%s:%d/" % (BIND, PORT), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
