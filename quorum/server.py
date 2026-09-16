# לזכרה של עלמה ז״ל
"""QUORUM · server — stdlib HTTP front door for the שקלא-וטריא arena.

100% ours: http.server only, no Flask/frameworks. Bright Hebrew/RTL UI.

ALMAWARE standards:
  * ENABLED gate — the server boots always (so you can see status), but /debate
    refuses to reach any model while config.is_enabled() is False; it streams a
    clean 'disabled' event instead. Born inert.
  * failure-is-a-value — handlers catch everything; a broken request becomes a JSON
    error or an SSE error frame, never a 500 traceback to the socket.
  * Loopback-only bind by default + _authorized() gate (loopback / Tailscale / token).

Run:  python server.py   →   http://127.0.0.1:8099
"""
from __future__ import annotations

import asyncio
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Hebrew-safe console: Windows' default cp1252 stdout can't encode עברית and would
# crash our boot prints. Force UTF-8 (failure-is-a-value: ignore if unsupported).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
import ai_clients as c
import shakla
import registry
import rooms
import workers

# registry lists worker-donated models / routes worker: ids through the queue;
# a module attribute avoids a circular import.
registry.workers_module = workers

import os

_HERE = config.BASE_DIR   # frozen-aware: the exe dir in the installed MSI build
STATIC_DIR = os.path.join(_HERE, "static")
UI_DIR = os.path.join(_HERE, "ui")          # Track B owns: room.html
WORKER_DIR = os.path.join(_HERE, "worker")  # Track C owns: index.html, worker.js, sw.js, …

# PWA-worker protocol adapter: worker.js authenticates by worker_id only (its
# contract has no body token); workers.py requires a per-worker token. The
# mapping lives server-side. In-memory on purpose — a restart drops workers.py's
# registry too, and the worker's 404-triggered rejoin handles both together.
_WORKER_TOKENS: dict[str, str] = {}
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}


def _int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _room_event(m: dict) -> dict:
    """rooms.py message → Room-API-v1 event (the shape ui\\room.html renders).
    Everything rooms.py stores is a complete message, so done is always True."""
    if m.get("kind") == "error":
        return {"seq": m["seq"], "ts": m["ts"], "kind": "error",
                "mid": str(m["seq"]), "note": m.get("text", "")}
    role = m.get("kind") if m.get("kind") in ("human", "ai", "system") else "system"
    return {"seq": m["seq"], "ts": m["ts"], "kind": "message",
            "mid": str(m["seq"]), "role": role,
            "author": m.get("from", ""), "model": m.get("model") or None,
            "round": 0, "text": m.get("text", ""), "done": True}


def _sse_frame(event: str, data: dict) -> bytes:
    return (f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n").encode("utf-8")


PAGE = r"""<!doctype html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<title>QUORUM · שקלא וטריא — ALMAWARE</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f4f8;color:#1a1a2e;margin:0;padding:20px}
 h1{color:#2a6f97;margin:0 0 4px;font-size:26px}
 .sub{color:#5a8;font-size:13px;margin-bottom:14px}
 .bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
 #models{display:flex;gap:8px;flex-wrap:wrap;min-height:34px}
 label.m{background:#e8f4f8;border:1px solid #b8d4e8;border-radius:20px;padding:6px 12px;cursor:pointer}
 label.local{border-color:#7fb069}
 textarea{flex:1;min-width:280px;background:#fff;border:1px solid #b8d4e8;border-radius:10px;padding:12px;font-size:16px}
 button{background:#ff6b6b;color:#fff;border:0;border-radius:10px;padding:12px 22px;font-size:16px;cursor:pointer}
 button.stop{background:#c94c4c}
 select{background:#fff;border:1px solid #b8d4e8;border-radius:8px;padding:4px 8px}
 #cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:14px}
 .col{background:#fff;border:1px solid #b8d4e8;border-radius:12px;padding:14px;white-space:pre-wrap;line-height:1.55;box-shadow:0 1px 3px rgba(0,0,0,.05)}
 .col h3{margin:0 0 8px;color:#2a6f97;font-size:15px}
 .col.synth{border-color:#f4a261;background:#fff7ec;grid-column:1/-1}
 .roster{grid-column:1/-1}
 .chip{display:inline-block;background:#e8f4f8;border:1px solid #b8d4e8;border-radius:14px;padding:4px 10px;font-size:12px;margin:2px}
 .chip.err{background:#fde;border-color:#c94c4c;color:#c94c4c}
 .banner{background:#fff3cd;border:1px solid #ffe08a;border-radius:10px;padding:10px 14px;margin-bottom:12px;color:#7a5b00;font-size:14px}
 button.arm{background:#2f9e44;margin-inline-start:10px;padding:8px 18px;font-size:15px}
 button.arm:hover{background:#2b8a3e}
</style></head><body>
<h1>🗳️ QUORUM · שקלא וטריא</h1>
<div class="sub">מוחות AI מתנצחים בצורה תלמודית — עמדות ← קושיא/תירוץ/ראיה/דחייה ← מסקנה · לזכרה של עלמה ז״ל</div>
<div id="gate" class="banner" style="display:none"></div>
<div id="models" class="bar"><span class="sub">טוען מודלים…</span></div>
<div class="bar">
 <label>🔁 סבבים <select id="rounds"><option>1</option><option>2</option><option selected>3</option><option>4</option><option>5</option></select></label>
</div>
<div class="bar">
 <textarea id="q" rows="3" placeholder="כתוב שאלה / סוגיה לדיון — המודלים יטענו, יקשו ויתרצו…"></textarea>
 <button id="go" onclick="start()">פתח דיון ←</button>
 <button class="stop" onclick="stop()">⏹ עצור</button>
</div>
<div id="cols"></div>
<script>
let MODELS=[], ctrl=null;
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
async function load(){
 try{
  const h=await (await fetch('/health')).json();
  const g=document.getElementById('gate');
  if(!h.enabled){g.style.display='block';
   g.innerHTML='⚠️ '+esc(h.note)+' <button class="arm" onclick="armQuorum()">הפעל · Enable</button>';}
  else{g.style.display='none';}
  MODELS=await (await fetch('/models')).json();
  const bar=document.getElementById('models');bar.innerHTML='';
  if(!MODELS.length){bar.innerHTML='<span class="sub">לא זוהו מודלים (CLIs לא מותקנים?)</span>';return;}
  MODELS.forEach(m=>{const l=document.createElement('label');l.className='m'+(m.type==='ollama'?' local':'');
   l.innerHTML=`<input type=checkbox value="${m.id}" ${m.default?'checked':''}> ${esc(m.label)}`;bar.appendChild(l);});
 }catch(e){document.getElementById('models').innerHTML='<span class="chip err">שגיאה בטעינה</span>';}
}
function colFor(agent,synth){
 const id='c-'+String(agent).replace(/[^a-zA-Z0-9]/g,'_');
 let el=document.getElementById(id);
 if(!el){const cols=document.getElementById('cols');
  cols.insertAdjacentHTML('beforeend',`<div class="col${synth?' synth':''}" id="${id}"><h3>${synth?'🟠 מסקנה':'🧠 '+esc(agent)}</h3><div class="b"></div></div>`);
  el=document.getElementById(id);}
 return el.querySelector('.b');
}
function roster(){let r=document.getElementById('roster');
 if(!r){document.getElementById('cols').insertAdjacentHTML('afterbegin','<div class="col roster" id="roster"></div>');r=document.getElementById('roster');}
 return r;}
function stop(){if(ctrl){try{ctrl.abort()}catch(e){}}ctrl=null;}
async function armQuorum(){
 try{const r=await (await fetch('/api/enable',{method:'POST'})).json();
  if(r.ok){await load();}
  else{document.getElementById('gate').textContent='⚠️ '+(r.note||'enable refused');}
 }catch(e){document.getElementById('gate').textContent='⚠️ enable failed: '+e;}
}
async function start(){
 const topic=document.getElementById('q').value.trim();if(!topic)return;
 const models=[...document.querySelectorAll('#models input:checked')].map(c=>c.value);
 if(models.length<2){alert('בחר לפחות שני מודלים כדי שיהיה עם מי להתווכח');return;}
 const rounds=parseInt(document.getElementById('rounds').value||'3',10);
 stop();document.getElementById('cols').innerHTML='';roster().innerHTML='<span class="chip">⚖️ הדיון מתכנס…</span>';
 ctrl=new AbortController();
 const res=await fetch('/debate',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({topic,models,rounds}),signal:ctrl.signal});
 const rd=res.body.getReader(),dec=new TextDecoder();let buf='';
 for(;;){let r;try{r=await rd.read()}catch(e){break}if(r.done)break;
  buf+=dec.decode(r.value,{stream:true});let i;
  while((i=buf.indexOf('\n\n'))>=0){const f=buf.slice(0,i);buf=buf.slice(i+2);
   let ev='message',data='';f.split('\n').forEach(l=>{if(l.startsWith('event:'))ev=l.slice(6).trim();else if(l.startsWith('data:'))data+=l.slice(5).trim();});
   let d={};try{d=JSON.parse(data||'{}')}catch(e){}
   if(ev==='plan'){roster().innerHTML=`<span class="chip">שקלא וטריא · ${d.rounds} סבבים · ${(d.agents||[]).map(a=>esc(a.model)).join(' · ')}</span>`;}
   else if(ev==='status'&&d.state==='round-start'){roster().insertAdjacentHTML('beforeend',`<span class="chip"><b>סבב ${d.round}</b> · ${esc(d.label||'')}</span>`);}
   else if(ev==='delta'){const b=colFor(d.agent,d.agent==='synth');if(b)b.textContent+=d.text;}
   else if(ev==='error'){roster().insertAdjacentHTML('beforeend',`<span class="chip err">${esc(d.note||'error')}</span>`);}
   else if(ev==='done'){roster().insertAdjacentHTML('beforeend',`<span class="chip">✅ ${d.elapsed||'?'}s · מסקנה: ${esc(d.synth_model||'—')}</span>`);}
  }}
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.ctrlKey)start();});
load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def _peer_ip(self) -> str:
        ip = self.client_address[0] if self.client_address else ""
        # A dual-stack listener reports IPv4 peers as ::ffff:a.b.c.d — normalise
        # so the octet tests below see the real address.
        if ip.startswith("::ffff:") and "." in ip:
            ip = ip[len("::ffff:"):]
        return ip

    def _is_loopback(self) -> bool:
        ip = self._peer_ip()
        return ip in ("127.0.0.1", "::1") or ip.startswith("127.")

    def _authorized(self) -> bool:
        ip = self._peer_ip()
        if self._is_loopback():
            return True
        try:
            o = ip.split(".")
            if len(o) == 4 and o[0] == "100" and 64 <= int(o[1]) <= 127:
                return True  # Tailscale CGNAT
            # Private LAN (opt-in, config.ALLOW_LAN). Other devices on Iddo's own
            # network — phones, laptops — so "one click → a worker" works off this
            # machine. Still never the public internet.
            if config.ALLOW_LAN and len(o) == 4:
                a, b = int(o[0]), int(o[1])
                if (a == 10
                        or (a == 172 and 16 <= b <= 31)
                        or (a == 192 and b == 168)
                        or (a == 169 and b == 254)):   # link-local / APIPA
                    return True
        except Exception:
            pass
        if config.TOKEN:
            given = self.headers.get("X-Token") or ""
            if not given and "token=" in (self.path or ""):
                from urllib.parse import urlparse, parse_qs
                given = (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
            if given == config.TOKEN:
                return True
        return False

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _sse_open(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _sse(self, event, data) -> bool:
        try:
            self.wfile.write(_sse_frame(event, data))
            self.wfile.flush()
            return True
        except Exception:
            return False

    # ── helpers for the /api surface ────────────────────────────────────────

    def _json(self, code: int, value):
        self._send(code, json.dumps(value, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _query(self) -> dict:
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        return {k: v[0] for k, v in q.items() if v}

    def _file(self, root: str, name: str, fallback_note: str = ""):
        """Serve one file from <root> (frontend/worker tracks own the files;
        this server only delivers them). Traversal-proof."""
        safe = os.path.normpath(name).replace("\\", "/").lstrip("/")
        if safe.startswith(".."):
            self._json(404, {"error": "not found"}); return
        full = os.path.normpath(os.path.join(root, safe))
        if not full.startswith(os.path.normpath(root)) or not os.path.isfile(full):
            self._json(404, {"error": "not found",
                             "note": fallback_note or f"{safe} does not exist yet"})
            return
        ext = os.path.splitext(full)[1].lower()
        try:
            with open(full, "rb") as f:
                body = f.read()
        except Exception:
            self._json(500, {"error": "unreadable"}); return
        self._send(200, body, _MIME.get(ext, "application/octet-stream"))

    def _static(self, name: str, fallback_note: str = ""):
        self._file(STATIC_DIR, name, fallback_note)

    def _api_get(self, path: str) -> bool:
        """All GET /api/* routes. Returns True when handled."""
        q = self._query()
        if path == "/api/health":
            self._json(200, {
                "ok": True,
                "enabled": config.is_enabled(),
                "host": config.HOST, "port": config.PORT,
                "models": registry.probe_all(),
                "workers": workers.stats(),
                "rooms": rooms.stats(),
            }); return True
        if path == "/api/models":
            self._json(200, {"ok": True, "models": registry.list_models()})
            return True
        if path == "/api/rooms":
            self._json(200, {"ok": True, "rooms": rooms.list_rooms()})
            return True
        if path.startswith("/api/rooms/"):
            rest = path[len("/api/rooms/"):]
            if rest.endswith("/events"):
                rid = rest[: -len("/events")].strip("/")
                since = _int(q.get("since"), 0)
                wait = _float(q.get("wait"), 0.0)
                user = str(q.get("user") or "").strip()
                if user:
                    rooms.touch(rid, user)      # presence heartbeat
                r = rooms.events(rid, since=since, wait=wait)
                if r.get("ok"):
                    # Room-API-v1 shape (ui\room.html) alongside the native
                    # messages/typing shape — both are cheap, callers pick.
                    r["events"] = [_room_event(m) for m in r.get("messages", [])]
                    r["users"] = rooms.members_presence(rid)
                self._json(200 if r.get("ok") else 404, r); return True
            rid = rest.strip("/")
            since = _int(q.get("since"), 0)
            r = rooms.get_room(rid, since=since)
            self._json(200 if r.get("ok") else 404, r); return True
        if path == "/api/workers":
            self._json(200, {"ok": True, "workers": workers.list_workers(),
                             "stats": workers.stats()}); return True
        if path.startswith("/api/jobs/"):
            r = workers.job_status(path[len("/api/jobs/"):].strip("/"))
            self._json(200 if r.get("ok") else 404, r); return True
        return False

    def _api_post(self, path: str, d: dict) -> bool:
        """All POST /api/* routes. Returns True when handled."""
        if path == "/api/judge":
            # THE JUDGE. shakla argues; this rules. Post the `done` payload of a
            # finished debate ({topic, transcript}) and get back the verdict
            # ledger: one line per claim, held / partly / rejected / CANNOT RULE,
            # with the gate that decided it.
            #
            # NOT gated on config.ENABLED, and that is correct rather than an
            # oversight: the gate exists so that nothing REACHES A MODEL before
            # the operator says so, and the judge reaches no model at all. It is
            # Z3 plus a grounded extension over text already in hand. An inert
            # QUORUM can still rule on a transcript it argued yesterday.
            try:
                from judge import quorum_bridge
                res = quorum_bridge.judge_transcript(
                    str(d.get("topic") or ""),
                    d.get("transcript") or [],
                    source=str(d.get("debate_id") or "POST /api/judge"))
                case = res["case"]
                self._json(200, {
                    "ok": True,
                    "z3": res["z3"],
                    "tally": res["tally"],
                    "rejected_total": res["rejected_total"],
                    "rejected_why": res["rejected_why"],
                    "rejected_what": res["rejected_what"],
                    "claims": [{"id": c.id, "by": c.by, "text": c.text_he}
                               for c in case.claims],
                    "verdicts": [v.to_dict() for v in res["verdicts"]],
                })
            except Exception as e:                    # failure-is-a-value
                self._json(200, {"ok": False, "error": "judge",
                                 "note": str(e)[:300]})
            return True
        if path == "/api/enable":
            # Born-inert arming step: flips the runtime gate for THIS process
            # only (no persistence). Deliberately stricter than _authorized() —
            # a tailnet/LAN viewer may watch status but may not arm the engine.
            if not self._is_loopback():
                self._json(403, {"ok": False, "enabled": config.is_enabled(),
                                 "note": "enable is loopback-only — click it on this machine"})
                return True
            config.ENABLED = True
            self._json(200, {"ok": True, "enabled": config.is_enabled()})
            return True
        if path == "/api/chat":
            model = str(d.get("model") or "")
            messages = d.get("messages")
            if not isinstance(messages, list):
                prompt = str(d.get("prompt") or "").strip()
                messages = [{"role": "user", "content": prompt}] if prompt else []
            r = registry.chat(model, messages,
                              timeout=float(d.get("timeout") or 0),
                              max_tokens=int(d.get("max_tokens") or 0))
            self._json(200, r); return True
        if path == "/api/rooms":
            # Room-API-v1 ({name,user} — ui\room.html) and native ({title,creator})
            r = rooms.create_room(str(d.get("title") or d.get("name") or ""),
                                  creator=str(d.get("creator") or d.get("user") or ""))
            self._json(200, r); return True
        if path.startswith("/api/rooms/"):
            rest = path[len("/api/rooms/"):]
            if rest.endswith("/join"):
                r = rooms.join_room(rest[: -len("/join")].strip("/"),
                                    str(d.get("name") or d.get("user") or ""))
                if r.get("ok"):
                    room = r.get("room") or {}
                    r["id"] = room.get("id")      # Room-API-v1 top-level aliases
                    r["name"] = room.get("name")
                    r["seq"] = room.get("seq", 0)
                self._json(200 if r.get("ok") else 404, r); return True
            if rest.endswith("/messages"):
                rid = rest[: -len("/messages")].strip("/")
                r = rooms.post_message(rid,
                                       sender=str(d.get("from") or d.get("sender") or ""),
                                       text=str(d.get("text") or ""),
                                       ask=d.get("ask"))
                self._json(200 if r.get("ok") else 404, r); return True
            if rest.endswith("/say"):
                # Room-API-v1 send (ui\room.html): models → ask fan-out.
                # mode "shakla" answers as chat for now — stated, not faked.
                rid = rest[: -len("/say")].strip("/")
                r = rooms.post_message(rid,
                                       sender=str(d.get("user") or ""),
                                       text=str(d.get("text") or ""),
                                       ask=d.get("models"))
                if r.get("ok") and str(d.get("mode") or "") == "shakla":
                    r["note"] = "shakla mode in rooms not implemented yet — answered as chat"
                self._json(200 if r.get("ok") else 404, r); return True
            if rest.endswith("/stop"):
                # Honest no-op: rooms has no server-side cancellation yet.
                # In-flight model turns finish; nothing new is launched.
                self._json(200, {"ok": True,
                                 "note": "stop is a no-op: in-flight turns run to completion"})
                return True
            return False
        # ── PWA-worker protocol (worker\worker.js) → workers.py adapter ──────
        if path == "/api/worker/join":
            caps = dict(d.get("caps")) if isinstance(d.get("caps"), dict) else {}
            if caps.get("model") and not caps.get("models"):
                caps["models"] = [str(caps["model"])]
            r = workers.register(str(d.get("name") or ""), caps)
            _WORKER_TOKENS[r["worker_id"]] = r["token"]
            self._json(200, {"ok": True, "worker_id": r["worker_id"],
                             "poll_ms": 3000, "heartbeat_ms": 20000})
            return True
        if path == "/api/worker/heartbeat":
            wid = str(d.get("worker_id") or "")
            tok = _WORKER_TOKENS.get(wid, "")
            r = workers.heartbeat(wid, tok)
            if not r.get("ok"):
                self._json(404, r); return True   # 404 triggers worker rejoin
            workers.update_caps(wid, tok, model=d.get("model"),
                                ready=bool(d.get("model_ready")))
            self._json(200, r); return True
        if path == "/api/worker/pull":
            wid = str(d.get("worker_id") or "")
            r = workers.lease(wid, _WORKER_TOKENS.get(wid, ""), wait=0)
            if not r.get("ok"):
                self._json(404, r); return True   # 404 triggers worker rejoin
            job = r.get("job")
            task = None
            if job:
                task = {"task_id": job["job_id"],
                        "kind": "chat" if job["kind"] == "generate" else job["kind"],
                        "payload": job["payload"]}
            self._json(200, {"ok": True, "task": task}); return True
        if path == "/api/worker/result":
            wid = str(d.get("worker_id") or "")
            jid = str(d.get("task_id") or "")
            r = workers.finish_job(jid, wid, _WORKER_TOKENS.get(wid, ""),
                                   bool(d.get("ok")),
                                   {"text": str(d.get("output") or "")},
                                   error=str(d.get("error") or ""))
            self._json(200 if r.get("ok") else 404, r); return True
        if path == "/api/workers/register":
            r = workers.register(str(d.get("name") or ""),
                                 d.get("capabilities"))
            self._json(200, r); return True
        if path == "/api/workers/heartbeat":
            r = workers.heartbeat(str(d.get("worker_id") or ""),
                                  str(d.get("token") or ""))
            self._json(200 if r.get("ok") else 403, r); return True
        if path == "/api/workers/lease":
            r = workers.lease(str(d.get("worker_id") or ""),
                              str(d.get("token") or ""),
                              wait=float(d.get("wait") or 20))
            self._json(200 if r.get("ok") else 403, r); return True
        if path == "/api/jobs":
            r = workers.submit_job(str(d.get("kind") or ""), d.get("payload"),
                                   requires=d.get("requires"),
                                   lease_timeout=float(d.get("lease_timeout") or 0))
            self._json(200 if r.get("ok") else 400, r); return True
        if path.startswith("/api/jobs/") and path.endswith("/result"):
            jid = path[len("/api/jobs/"): -len("/result")].strip("/")
            r = workers.finish_job(jid,
                                   str(d.get("worker_id") or ""),
                                   str(d.get("token") or ""),
                                   bool(d.get("ok")),
                                   d.get("result"),
                                   error=str(d.get("error") or ""))
            self._json(200 if r.get("ok") else 403, r); return True
        return False

    def do_GET(self):
        if not self._authorized():
            self._send(403, '{"error":"forbidden: localhost/Tailscale only"}', "application/json"); return
        path = self.path.split("?")[0]
        try:
            if path.startswith("/api/"):
                if not self._api_get(path):
                    self._json(404, {"error": "not found"})
                return
        except Exception as e:  # noqa: BLE001 — failure-is-a-value
            self._json(500, {"error": "server", "note": str(e)[:300]}); return
        if path in ("/room", "/room/", "/app", "/app/"):
            self._file(UI_DIR, "room.html",
                       "rooms UI not deployed — ui/room.html missing")
        elif path == "/worker":
            # 301 is load-bearing: index.html references worker.js / sw.js
            # RELATIVELY; served at /worker (no slash) they'd resolve to
            # /worker.js → 404. The slash fixes the base URL + SW scope.
            self.send_response(301)
            self.send_header("Location", "/worker/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/worker/":
            self._file(WORKER_DIR, "index.html",
                       "worker page not deployed — worker/index.html missing")
        elif path.startswith("/worker/"):
            self._file(WORKER_DIR, path[len("/worker/"):])
        elif path.startswith("/static/"):
            self._static(path[len("/static/"):])
        elif path == "/":
            self._send(200, PAGE)
        elif path == "/health":
            self._send(200, json.dumps({"ok": True, "enabled": config.is_enabled(),
                                        "note": ("" if config.is_enabled() else config.disabled_note())},
                                       ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/models":
            try:
                models = [{"id": m["id"], "label": m["label"],
                           "type": (m["provider"] if m["provider"] in {"ollama", "alma", "fleet"} else "cli"),
                           "default": m["default"]} for m in c.detect_models()]
            except Exception:
                models = []
            self._send(200, json.dumps(models, ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, '{"error":"not found"}', "application/json")

    def do_POST(self):
        if not self._authorized():
            self._send(403, '{"error":"forbidden"}', "application/json"); return
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send(400, '{"error":"bad json"}', "application/json"); return
        if not isinstance(d, dict):
            self._send(400, '{"error":"body must be a JSON object"}', "application/json"); return
        path = self.path.split("?")[0]
        try:
            if path.startswith("/api/"):
                if not self._api_post(path, d):
                    self._json(404, {"error": "not found"})
                return
        except Exception as e:  # noqa: BLE001 — failure-is-a-value
            self._json(500, {"error": "server", "note": str(e)[:300]}); return
        if path == "/debate":
            self._handle_debate(d)
        else:
            self._send(404, '{"error":"not found"}', "application/json")

    def _handle_debate(self, d):
        topic = (d.get("topic") or d.get("prompt") or "").strip()
        models = d.get("models") or []
        rounds = d.get("rounds", config.DEFAULT_ROUNDS)
        self._sse_open()
        cancel = asyncio.Event()

        async def drive():
            try:
                async for ev in shakla.run_shakla(topic, model_ids=models, num_rounds=rounds, cancel=cancel):
                    if ev["event"].startswith("_"):   # internal sentinels never go to the wire
                        continue
                    if not self._sse(ev["event"], ev["data"]):
                        cancel.set(); break
            except Exception as e:  # noqa: BLE001 — failure-is-a-value
                self._sse("error", {"agent": "server", "note": str(e)[:300], "error": "backend"})

        try:
            asyncio.run(drive())
        except Exception:
            pass

    def log_message(self, *a):
        pass


def main():
    print(f"[QUORUM] שקלא-וטריא server on {config.HOST}:{config.PORT}")
    print(f"[QUORUM] ENABLED={config.is_enabled()} "
          + ("" if config.is_enabled() else "→ inert: /debate will refuse to reach models"))
    if config.HOST in ("127.0.0.1", "::1", "localhost"):
        print("[QUORUM] bind=loopback-only. For phone/Tailscale set QUORUM_HOST=0.0.0.0")
    else:
        print(f"[QUORUM] bind={config.HOST} (all interfaces) · "
              f"LAN callers {'ADMITTED' if config.ALLOW_LAN else 'REJECTED 403 — set allow_lan'}")
    # Model discovery can involve local CLI enumeration and a private Harness
    # health request.  It belongs on /models and must never delay the loopback
    # listener or make startup health depend on an optional provider.
    print("[QUORUM] model discovery available at /models")
    print("[QUORUM] v2 API: /api/health /api/enable /api/models /api/chat /api/rooms /api/workers /api/jobs")
    print("[QUORUM] pages: / (debate arena) · /room + /app (rooms UI) · /worker/ (federation worker PWA)")
    ThreadingHTTPServer((config.HOST, config.PORT), H).serve_forever()


if __name__ == "__main__":
    main()
