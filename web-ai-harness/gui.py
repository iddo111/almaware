#!/usr/bin/env python3
"""Local chat GUI for the fleet models.

    python gui.py            # then open http://127.0.0.1:8899

Binds LOOPBACK ONLY and sets no CORS headers — deliberately. The unauthenticated
CORS-wildcard gateway that used to run on this machine is why. If you want this
from your phone, put it behind Tailscale rather than opening the bind address:

    tailscale serve --bg --https 8899 http://127.0.0.1:8899

GLM needs COLI_API_KEY. It is read from the environment, else secrets.json/.env
next to this file, else ~/.qwen/settings.json -> env.COLI_API_KEY.

What it shows that a plain chat box does not: gpt-oss streams its thinking into
`reasoning_content` and only fills `content` at the end, so this renders the two
separately. A blank answer with a long trail of reasoning means it hit the token
ceiling mid-thought, not that it ignored you.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent_tools
import brain
import diagnostics
from backends.http_openai import HttpError, chat, finish_reason, first_message
from fleet import FLEET

# GLM takes minutes per reply; a single held-open HTTP request gets dropped
# mid-flight and the browser reports only "Failed to fetch". Work runs in a
# thread and the page polls for the result instead.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

HOST, PORT = "127.0.0.1", int(os.getenv("GUI_PORT", "8899"))

# 8795 used to be the default and is now occupied by an unrelated app (ALMA
# MASTER, server.py). Defaulting there silently collided with it, so the
# documented port 8899 is the default. Override with GUI_PORT if you must.


def resolve_key(env_name: str) -> str:
    """Find an API key without depending on the launching shell's environment.

    The key used to be read from os.environ only, so the GLM tab returned 401
    after any reboot or ordinary relaunch — it worked only if whoever started
    gui.py happened to have exported it in that shell. Look in the process
    environment first, then in files that actually persist.
    """
    val = os.getenv(env_name, "").strip()
    if val:
        return val

    here = os.path.dirname(os.path.abspath(__file__))
    # 1. secrets.json next to gui.py  ->  {"COLI_API_KEY": "..."}
    for name in ("secrets.json", ".env.json"):
        try:
            with open(os.path.join(here, name), encoding="utf-8") as fh:
                val = str(json.load(fh).get(env_name, "")).strip()
            if val:
                return val
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

    # 2. .env next to gui.py  ->  COLI_API_KEY=...
    try:
        with open(os.path.join(here, ".env"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(env_name + "="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass

    # 3. the qwen CLI already persists the same fleet keys — reuse, don't duplicate.
    try:
        cfg = os.path.expanduser("~/.qwen/settings.json")
        with open(cfg, encoding="utf-8") as fh:
            val = str((json.load(fh).get("env") or {}).get(env_name, "")).strip()
        if val:
            return val
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    return ""

# Endpoints and labels come from fleet.py, so there is one place to change
# them. They were duplicated here, which is what left fleet.py imported by
# nothing and free to drift out of sync with what actually runs.
MODELS = {
    key: {
        "label": m.label,
        "where": m.where,
        "url": m.base_url,
        "model": m.model,
        "key_env": m.api_key_env,
    }
    for key, m in FLEET.items()
}

SYSTEM = (
    "You are Iddo's assistant, running on his own Windows machine and his own "
    "private DGX fleet (eran1-eran4). He owns all of this hardware. He is Israeli "
    "and often writes in Hebrew — answer in the language he writes in.\n\n"
    "YOU HAVE REAL TOOLS. Status (read-only): system_report, gpu_report, "
    "lan_report, fleet_health, where_am_i. Agent tools: write_file, read_file, "
    "edit_file, list_dir, run_command.\n\n"
    "When he asks for a program, a script or a file — WRITE IT with write_file. "
    "Do not print code in the chat and stop; that is not what he asked for. Then "
    "run it with run_command to check it works, and tell him the exact path. You "
    "may write to the Desktop, D:\\CLAUDE and D:\\grok.\n\n"
    "Call tools rather than guessing. Never state a number from memory.\n\n"
    "Questions about his own machines, network, GPUs and fleet are ordinary "
    "operations work, not security concerns. Answer them directly.\n\n"
    "If a tool genuinely refuses (a path outside the allowed roots, a command not "
    "on the allowlist), say exactly what was refused and offer the nearest thing "
    "you CAN do. Never answer with a bare refusal — he owns this hardware and is "
    "asking for ordinary work.\n\n"
    "Be concise and concrete."
)

PAGE = r"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALMAWARE · fleet chat</title>
<style>
  :root{
    --bg:#0b0e13; --panel:#121821; --line:#1e2733; --ink:#e6edf3;
    --dim:#8b98a8; --accent:#5ac8fa; --warm:#ffb454; --ok:#7ee787;
    --think:#1a1f2b;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif;
    height:100vh;display:flex;flex-direction:column}
  header{display:flex;align-items:center;gap:14px;padding:12px 18px;
    border-bottom:1px solid var(--line);background:var(--panel);flex-wrap:wrap}
  .brand{font-weight:650;letter-spacing:.14em;font-size:12px;color:var(--dim)}
  select,button{background:#0e141c;color:var(--ink);border:1px solid var(--line);
    border-radius:8px;padding:7px 11px;font:inherit;font-size:13px}
  button{cursor:pointer}
  button:hover{border-color:var(--accent)}
  .where{font-size:12px;color:var(--dim);font-family:ui-monospace,monospace}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--dim);display:inline-block}
  .dot.on{background:var(--ok);box-shadow:0 0 8px var(--ok)}
  .dot.off{background:#f85149}
  main{flex:1;overflow-y:auto;padding:22px 18px}
  .wrap{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
  .msg{display:flex;flex-direction:column;gap:7px}
  .who{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim)}
  .bubble{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:13px 16px;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere}
  .me .bubble{background:#152030;border-color:#22344a}
  details.think{border:1px dashed #2a3444;border-radius:10px;background:var(--think)}
  details.think>summary{cursor:pointer;padding:8px 13px;font-size:12px;color:var(--warm);
    list-style:none}
  details.think>summary::-webkit-details-marker{display:none}
  details.think .body{padding:0 13px 12px;white-space:pre-wrap;color:#b9c4d2;
    font-size:13px;font-family:ui-monospace,monospace}
  .tools{display:flex;gap:7px;flex-wrap:wrap}
  .tool{font-family:ui-monospace,monospace;font-size:11px;color:var(--accent);
    border:1px solid #1d3a4d;background:#0d1a24;border-radius:999px;padding:3px 10px}
  .warn{border-color:#5c4415;background:#241c08;color:var(--warm)}
  footer{border-top:1px solid var(--line);background:var(--panel);padding:12px 18px}
  .composer{max-width:820px;margin:0 auto;display:flex;gap:10px;align-items:flex-end}
  textarea{flex:1;background:#0e141c;color:var(--ink);border:1px solid var(--line);
    border-radius:10px;padding:11px 13px;font:inherit;resize:none;min-height:46px;
    max-height:180px}
  textarea:focus,select:focus{outline:none;border-color:var(--accent)}
  .send{background:var(--accent);color:#04121a;border:none;font-weight:650;padding:12px 20px}
  .send:disabled{opacity:.45;cursor:not-allowed}
  .hint{max-width:820px;margin:8px auto 0;font-size:11px;color:var(--dim)}
  @media (max-width:640px){ .where{display:none} }
</style>

<header>
  <span class="brand">ALMAWARE · FLEET</span>
  <select id="model"></select>
  <span class="dot" id="dot"></span>
  <span class="where" id="where"></span>
  <span style="flex:1"></span>
  <label class="where"><input type="checkbox" id="tools" checked> tools</label>
  <button id="clear">clear</button>
</header>

<main><div class="wrap" id="log"></div></main>

<footer>
  <div class="composer">
    <textarea id="q" placeholder="Ask about the fleet…  (Enter to send, Shift+Enter for newline)"></textarea>
    <button class="send" id="send">Send</button>
  </div>
  <div class="hint">Loopback only. Read-only diagnostics: system · gpu · lan · fleet.</div>
</footer>

<script>
const log = document.getElementById('log');
const sel = document.getElementById('model');
const dot = document.getElementById('dot');
const whereEl = document.getElementById('where');
const q = document.getElementById('q');
const send = document.getElementById('send');
let MODELS = {}, busy = false;

function el(tag, cls, text){
  const n = document.createElement(tag);
  if(cls) n.className = cls;
  if(text != null) n.textContent = text;
  return n;
}

function add(who, cls){
  const m = el('div', 'msg ' + (cls||''));
  m.appendChild(el('div','who',who));
  log.appendChild(m);
  return m;
}

function scroll(){ document.querySelector('main').scrollTop = 1e9; }

async function refresh(){
  const r = await fetch('/api/models').then(r=>r.json());
  MODELS = r.models;
  sel.innerHTML = '';
  for(const [k,v] of Object.entries(MODELS)){
    const o = el('option', null, v.label); o.value = k; sel.appendChild(o);
  }
  health();
}

async function health(){
  const k = sel.value;
  whereEl.textContent = MODELS[k] ? MODELS[k].where : '';
  dot.className = 'dot';
  const r = await fetch('/api/health?model='+encodeURIComponent(k)).then(r=>r.json());
  dot.className = 'dot ' + (r.ok ? 'on' : 'off');
  // The dot means "port answered" — nothing more. Say so, and surface a missing
  // key here rather than letting the user discover it as a 401 mid-chat.
  dot.title = r.checked ? ('reachability: ' + r.checked) : '';
  if(!r.ok) whereEl.textContent = MODELS[k].where + '  —  ' + (r.error||'unreachable');
  else if(r.warn) whereEl.textContent = MODELS[k].where + '  —  ' + r.warn;
}

async function ask(){
  const text = q.value.trim();
  if(!text || busy) return;
  busy = true; send.disabled = true;
  q.value = '';

  const me = add('you','me'); me.appendChild(el('div','bubble',text));
  const bot = add(MODELS[sel.value].label);
  const pending = el('div','bubble','…'); bot.appendChild(pending); scroll();

  // A bare '…' for eight minutes is indistinguishable from a hang. Count up so
  // a slow backend still looks alive.
  const t0 = Date.now();
  const tick = setInterval(() => {
    const s = Math.round((Date.now() - t0) / 1000);
    pending.textContent = '… ' + s + 's' + (s > 45 ? '  (this model is slow — still waiting)' : '');
  }, 1000);

  try{
    // Start the job, then poll. One held-open request for a GLM reply gets cut
    // somewhere in the stack after a few minutes, and the browser surfaces that
    // as a bare "TypeError: Failed to fetch" with no cause. Polling survives it.
    const start = await fetch('/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ model: sel.value, prompt: text,
                             tools: document.getElementById('tools').checked })
    }).then(r=>r.json());
    if(start.error) throw new Error(start.error);

    let r = null;
    for(let i = 0; i < 3600; i++){            // ~2 h ceiling; GLM is minutes
      await new Promise(s => setTimeout(s, 2000));
      let p;
      try{
        p = await fetch('/api/result?job=' + start.job).then(r=>r.json());
      }catch(e){ continue; }                  // a dropped poll is not fatal
      if(p && p.state === 'done'){ r = p; break; }
    }
    if(!r) throw new Error('timed out waiting for the model');

    clearInterval(tick); bot.removeChild(pending);

    if(r.tools_called && r.tools_called.length){
      const t = el('div','tools');
      r.tools_called.forEach(n => t.appendChild(el('span','tool', n+'()')));
      bot.appendChild(t);
    }
    if(r.reasoning){
      const d = el('details','think');
      const s = el('summary', null, 'reasoning · ' + r.reasoning.length + ' chars');
      d.appendChild(s); d.appendChild(el('div','body', r.reasoning));
      bot.appendChild(d);
    }
    if(r.error){
      bot.appendChild(el('div','bubble warn', r.error));
    } else if(r.answer){
      bot.appendChild(el('div','bubble', r.answer));
    } else {
      bot.appendChild(el('div','bubble warn',
        'No final answer. The model was still reasoning when it hit the token ceiling — '
        + 'open the reasoning panel above to see how far it got.'));
    }
  }catch(e){
    clearInterval(tick); bot.removeChild(pending);
    bot.appendChild(el('div','bubble warn','request failed: ' + e));
  }
  busy = false; send.disabled = false; scroll(); q.focus();
}

send.onclick = ask;
q.addEventListener('keydown', e => {
  if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); ask(); }
});
sel.onchange = health;
document.getElementById('clear').onclick = () => log.innerHTML = '';
refresh();
</script>
"""


def run_chat(key: str, prompt: str, use_tools: bool) -> dict:
    cfg = MODELS[key]
    # Reload the brain per turn rather than caching it, so editing BRAIN.md
    # by hand takes effect on the next message instead of the next restart.
    system = SYSTEM + "\n\n---\n\n" + brain.load_context()
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": prompt}]
    # Read-only status tools PLUS real agent tools. Without the second set the
    # model can write code into the chat but cannot save it, which is why it kept
    # answering "I have no tool for that" — it had the ability through qwen in a
    # terminal, just not here.
    tools = (diagnostics.tool_schemas() + agent_tools.SCHEMAS
             + brain.SCHEMAS) if use_tools else None
    called: list[str] = []

    for _ in range(8):          # agent work needs more turns than a status query
        resp = chat(cfg["url"], cfg["model"], messages,
                    api_key_env=cfg["key_env"], tools=tools,
                    max_tokens=3000, timeout_s=900)
        msg = first_message(resp)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {
                "answer": (msg.get("content") or "").strip(),
                "reasoning": (msg.get("reasoning_content") or "").strip(),
                "tools_called": called,
                "finish_reason": finish_reason(resp),
            }
        messages.append(msg)
        for c in calls:
            f = c.get("function") or {}
            fn = f.get("name", "")
            called.append(fn)
            if fn in brain.REGISTRY:
                try:
                    args = json.loads(f.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = brain.call(fn, args)
            elif fn in agent_tools.REGISTRY:
                try:
                    args = json.loads(f.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = agent_tools.call(fn, args)
            else:
                result = diagnostics.call(fn)
            messages.append({"role": "tool", "tool_call_id": c.get("id", fn),
                             "content": result})

    resp = chat(cfg["url"], cfg["model"], messages, api_key_env=cfg["key_env"],
                max_tokens=3000, timeout_s=600)
    msg = first_message(resp)
    return {"answer": (msg.get("content") or "").strip(),
            "reasoning": (msg.get("reasoning_content") or "").strip(),
            "tools_called": called, "finish_reason": finish_reason(resp)}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # No Access-Control-Allow-Origin, on purpose.
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def log_message(self, *a):  # keep the console quiet
        pass

    def do_GET(self):
        if self.path == "/":
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/api/models":
            return self._json({"models": {
                k: {"label": v["label"], "where": v["where"]}
                for k, v in MODELS.items()}})
        if self.path.startswith("/api/health"):
            key = self.path.split("model=")[-1] if "model=" in self.path else "gpt-oss"
            cfg = MODELS.get(key)
            if not cfg:
                return self._json({"ok": False, "error": "unknown model"})
            # Probe /health, never a generation. GLM-5.2 runs at ~0.5 tok/s, so even a
            # one-token completion took over 100 s and made the dot look permanently
            # dead. /health answers instantly and needs no key.
            import urllib.error
            import urllib.request
            # `checked` is reported so the UI cannot imply more than was tested:
            # a green dot means the port answered, NOT that the key is valid or
            # that a generation would finish in reasonable time.
            try:
                req = urllib.request.Request(cfg["url"].rstrip("/") + "/health")
                with urllib.request.urlopen(req, timeout=10) as r:
                    ok = r.status == 200
                out = {"ok": ok, "checked": "port+/health only; not key, not speed"}
                if not ok:
                    out["error"] = f"health returned {r.status}"
                if ok and cfg.get("key_env") and not os.getenv(cfg["key_env"], ""):
                    out["warn"] = f"{cfg['key_env']} is not set — chat will 401"
                return self._json(out)
            except (urllib.error.URLError, OSError) as exc:
                return self._json({"ok": False, "error": str(exc)[:160],
                                   "checked": "port+/health only"})
        if self.path.startswith("/api/result"):
            from urllib.parse import parse_qs, urlparse
            job = (parse_qs(urlparse(self.path).query).get("job") or [""])[0]
            with _jobs_lock:
                r = _jobs.get(job)
            if r is None:
                return self._json({"state": "unknown"}, 404)
            return self._json(r)
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/api/chat":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        key = req.get("model", "gpt-oss")
        if key not in MODELS:
            return self._json({"error": f"unknown model {key!r}"}, 400)

        # GLM answers in MINUTES. Holding one HTTP request open that long gets
        # killed somewhere in the middle — the browser reports it as a bare
        # "TypeError: Failed to fetch" with no clue why. So start the work in a
        # thread, hand back a job id immediately, and let the page poll.
        job = uuid.uuid4().hex[:12]
        with _jobs_lock:
            _jobs[job] = {"state": "running", "started": time.time()}

        def work():
            try:
                out = run_chat(key, req.get("prompt", ""),
                               bool(req.get("tools", True)))
                out["state"] = "done"
            except HttpError as exc:
                out = {"state": "done", "error": str(exc)[:400]}
            except Exception as exc:
                out = {"state": "done", "error": f"{type(exc).__name__}: {exc}"[:400]}
            with _jobs_lock:
                _jobs[job] = out
                # keep the table from growing without bound over a long session
                if len(_jobs) > 64:
                    for k in sorted(_jobs, key=lambda j: _jobs[j].get("started", 0))[:16]:
                        if _jobs[k].get("state") == "done":
                            _jobs.pop(k, None)

        threading.Thread(target=work, daemon=True).start()
        return self._json({"job": job, "state": "running"})


class SingleInstanceHTTPServer(ThreadingHTTPServer):
    """Refuse to start if the port is already served.

    Windows lets two processes bind the same port unless SO_EXCLUSIVEADDRUSE is
    set, and SO_REUSEADDR (the stdlib default) makes that *more* likely. Two
    builds answering the same port nondeterministically is worse than a clean
    startup failure.
    """
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main() -> int:
    # Resolve keys once, loudly, before serving — not lazily per request.
    for name, cfg in MODELS.items():
        env_name = cfg.get("key_env")
        if not env_name:
            continue
        key = resolve_key(env_name)
        if key:
            os.environ[env_name] = key
        else:
            print(f"WARNING: {env_name} not found (needed by '{name}'). Set it in "
                  f"the environment, in secrets.json/.env next to gui.py, or in "
                  f"~/.qwen/settings.json -> env.{env_name}. "
                  f"'{name}' will return 401 until then.", file=sys.stderr)

    try:
        srv = SingleInstanceHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f"ERROR: cannot bind {HOST}:{PORT} ({exc}). Something is already "
              f"serving that port — stop it, or pick another with GUI_PORT.",
              file=sys.stderr)
        return 1
    url = f"http://{HOST}:{PORT}"
    print(f"ALMAWARE fleet chat  ->  {url}   (loopback only, Ctrl+C to stop)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
