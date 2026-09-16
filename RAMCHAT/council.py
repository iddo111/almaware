#!/usr/bin/env python3
"""COUNCIL — RAMCHAT and QUORUM merged into one thing.

They were always the same idea: a room where Iddo and every AI he has connected
can talk, with shared memory. This is that room, with backends that actually
resolve. The old RAMCHAT wiring pointed at :8000 on eran1/2/3, where nothing has
listened for some time, so every model answered "not available".

Writes to the same ramchat_session.json the other agents read, so clod, Codex
and anyone on ramlink.py stay part of the conversation.

    python council.py            # http://127.0.0.1:8910
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(HERE, "ramchat_session.json")
SHARED = os.path.join(HERE, "ramchat_shared_memory.json")
HOST, PORT = "127.0.0.1", int(os.getenv("COUNCIL_PORT", "8910"))
def _coli_key() -> str:
    """Env first, then the on-disk secret. The GUI is usually launched from a
    shortcut with no COLI_API_KEY exported, which made every GLM-5.2 turn 401.
    2026-08-09 claude-cli-FABLE."""
    k = os.getenv("COLI_API_KEY", "").strip()
    if k:
        return k
    for path in (r"D:\CLAUDE\quorum\state\secrets\coli_api_key.txt",
                 os.path.expanduser(r"~\.qwen\settings.json")):
        try:
            raw = open(path, encoding="utf-8").read()
        except OSError:
            continue
        if path.endswith(".json"):
            try:
                v = json.loads(raw).get("env", {}).get("COLI_API_KEY", "").strip()
            except (ValueError, AttributeError):
                v = ""
            if v:
                return v
        elif raw.strip():
            return raw.strip()
    return ""


COLI_KEY = _coli_key()

_lock = threading.Lock()

# Every endpoint here was verified reachable on 2026-08-06.
MEMBERS = {
    "gpt-oss": {
        "label": "GPT-OSS 120B",
        "where": "eran4 · llama.cpp · ~1s",
        "kind": "http",
        "url": "http://<tailnet-ip>:8000/v1/chat/completions",
        "model": "gpt-oss-120b",
        "key": "",
        "fast": True,
    },
    "colibri": {
        "label": "Colibri GLM-5.2",
        "where": "router 4/4 · 744B MoE · slow (~0.5 tok/s)",
        "kind": "http",
        # 2026-08-09 claude-cli-FABLE: 127.0.0.1:8801 refuses (WinError 10061) —
        # nothing has listened there for days. Live endpoint is eran4:8800, verified
        # 200 on /v1/models with the bearer key.
        "url": "http://<tailnet-ip>:8800/v1/chat/completions",
        "model": "glm-5.2",
        "key": COLI_KEY,
        "fast": False,
    },
    "qwen": {
        "label": "Qwen Code",
        "where": "local CLI · full tools",
        "kind": "cli",
        "cmd": ["qwen", "-m", "gpt-oss-120b", "-y", "-p"],
        "fast": True,
    },
    "grok": {
        "label": "Grok",
        "where": "local CLI",
        "kind": "cli",
        "cmd": [r"C:\Users\<user>\.grok\bin\grok.exe", "-p"],
        "fast": True,
    },
    "gemini": {
        "label": "Gemini",
        "where": "local CLI",
        "kind": "cli",
        "cmd": [r"C:\Users\<user>\AppData\Roaming\npm\gemini.cmd", "-y", "-p"],
        "fast": True,
    },
    "codex": {
        "label": "Codex",
        "where": "local CLI",
        "kind": "cli",
        "cmd": [r"C:\Users\<user>\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe",
                "exec"],
        "fast": True,
    },
    "perplexity": {
        "label": "Perplexity",
        "where": "browser harness · needs a logged-in profile",
        "kind": "cli",
        "cmd": ["py", "-3.13", r"D:\CLAUDE\web-ai-harness\harness.py",
                "--provider", "perplexity", "--prompt"],
        "fast": False,
    },
    "antigravity": {
        "label": "Antigravity",
        "where": "Google Antigravity CLI",
        "kind": "cli",
        # 2026-08-09 claude-cli-FABLE: .gemini\antigravity-cli\bin\antigravity does
        # not exist (that dir only holds agentapi.bat + webm_encoder.exe). The real
        # binary is agy.exe, which is also on PATH.
        "cmd": [r"C:\Users\<user>\AppData\Local\agy\bin\agy.exe", "-p"],
        "fast": False,
    },
}

SYSTEM = (
    "אתה חבר במועצת COUNCIL של עידו — חדר משותף שבו עידו וכל ה-AI שחיבר "
    "מדברים. ענה בשפה שבה עידו כתב (עברית או אנגלית). היה קצר וקונקרטי. "
    "הפרד עובדה מהצעה. אל תמציא מספרים — אם אינך יודע, אמור שאינך יודע.\n\n"
    "This is Iddo's own hardware and his own private network. Questions about "
    "his machines, fleet or files are ordinary work, not security concerns."
)


def load_transcript() -> list:
    try:
        with open(SESSION, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, list) else d.get("conversation", [])
    except (OSError, json.JSONDecodeError):
        return []


def append(who: str, text: str) -> None:
    """Append under a lock — clod and ramlink.py write this file too."""
    with _lock:
        conv = load_transcript()
        conv.append({"who": who, "text": text,
                     "at": datetime.now().strftime("%H:%M")})
        tmp = SESSION + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(conv, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, SESSION)


def ask_http(m: dict, prompt: str, ctx: str) -> str:
    body = json.dumps({
        "model": m["model"],
        "messages": [{"role": "system", "content": SYSTEM + ctx},
                     {"role": "user", "content": prompt}],
        "max_tokens": 1200,
        "temperature": 0.3,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if m.get("key"):
        headers["Authorization"] = f"Bearer {m['key']}"
    req = urllib.request.Request(m["url"], data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            d = json.loads(r.read().decode("utf-8"))
        msg = d["choices"][0]["message"]
        out = (msg.get("content") or "").strip()
        if not out and msg.get("reasoning_content"):
            out = "[חשב אבל לא סיים — נגמרו הטוקנים]\n" + msg["reasoning_content"][:600]
        return out or "(תשובה ריקה)"
    except urllib.error.HTTPError as e:
        return f"[שגיאה {e.code}] {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        return f"[לא זמין] {type(e).__name__}: {e}"


def strip_harmony(text: str) -> str:
    """gpt-oss-120b leaks its harmony channels (<|channel|>analysis...<|end|>) into
    stdout because the upstream llama-server runs without --reasoning-format none.
    Keep only what follows the last <|end|>. 2026-08-09 claude-cli-FABLE."""
    if "<|" not in text:
        return text
    if "<|end|>" in text:
        text = text.rsplit("<|end|>", 1)[1]
    for tag in ("<|start|>assistant<|message|>", "<|channel|>final<|message|>",
                "<|message|>"):
        if tag in text:
            text = text.rsplit(tag, 1)[1]
    return text.replace("<|return|>", "").strip() or "(תשובה ריקה)"


def resolve_exe(cmd: list) -> list:
    """Windows CreateProcess only auto-appends .exe, never .cmd/.bat, so a bare
    "qwen" (which ships as qwen.CMD) raised FileNotFoundError and the GUI printed
    "[לא מותקן]" for a CLI that was installed all along. shutil.which honours
    PATHEXT and finds it. 2026-08-09 claude-cli-FABLE.
    """
    if not cmd:
        return cmd
    head = cmd[0]
    if os.path.isfile(head):
        return cmd
    found = shutil.which(head)
    if found:
        return [found] + list(cmd[1:])
    for ext in (".cmd", ".exe", ".bat"):
        if os.path.isfile(head + ext):
            return [head + ext] + list(cmd[1:])
    return cmd


def ask_cli(m: dict, prompt: str, ctx: str) -> str:
    try:
        p = subprocess.run(resolve_exe(m["cmd"]) + [prompt], capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace",
                           env={**os.environ, "FLEET_API_KEY": "none",
                                "PYTHONIOENCODING": "utf-8"})
        out = (p.stdout or "").strip()
        # CLIs emit banners and warnings on stdout; keep the tail, which is the answer.
        lines = [l for l in out.splitlines()
                 if not l.startswith(("Warning:", "warning:", "Loaded", "[dotenv"))]
        out = strip_harmony("\n".join(lines).strip())
        return out or (p.stderr or "").strip()[:300] or "(אין פלט)"
    except FileNotFoundError:
        return "[לא מותקן] הפקודה לא נמצאה"
    except subprocess.TimeoutExpired:
        return "[timeout] לא ענה בזמן"
    except Exception as e:
        return f"[שגיאה] {type(e).__name__}: {e}"


def ask(member_id: str, prompt: str) -> str:
    m = MEMBERS[member_id]
    recent = load_transcript()[-8:]
    ctx = "\n\nהשיחה האחרונה בחדר:\n" + "\n".join(
        f"{e.get('who')}: {str(e.get('text'))[:200]}" for e in recent)
    return ask_http(m, prompt, ctx) if m["kind"] == "http" else ask_cli(m, prompt, ctx)


PAGE = r"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>COUNCIL · ALMAWARE</title>
<style>
 :root{--bg:#0b0e13;--panel:#121821;--line:#1e2733;--ink:#e6edf3;--dim:#8b98a8;
       --accent:#5ac8fa;--warm:#ffb454;--ok:#7ee787;--bad:#f85149}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);height:100vh;display:flex;
   flex-direction:column;font:15px/1.65 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif}
 header{display:flex;gap:12px;align-items:center;padding:11px 16px;background:var(--panel);
   border-bottom:1px solid var(--line);flex-wrap:wrap}
 .brand{font-weight:700;letter-spacing:.16em;font-size:12px;color:var(--dim)}
 .who{display:flex;gap:6px;flex-wrap:wrap}
 .chip{border:1px solid var(--line);background:#0e141c;border-radius:999px;padding:4px 11px;
   font-size:12px;cursor:pointer;user-select:none;white-space:nowrap}
 .chip.on{border-color:var(--accent);color:var(--accent);background:#0d1a24}
 .chip .s{font-size:9px;opacity:.75;margin-inline-start:5px}
 main{flex:1;overflow-y:auto;padding:20px 16px}
 .wrap{max-width:880px;margin:0 auto;display:flex;flex-direction:column;gap:15px}
 .msg{display:flex;flex-direction:column;gap:5px}
 .nm{font-size:11px;letter-spacing:.08em;color:var(--dim)}
 .bub{background:var(--panel);border:1px solid var(--line);border-radius:12px;
   padding:11px 14px;white-space:pre-wrap;overflow-wrap:anywhere}
 .me .bub{background:#152030;border-color:#22344a}
 .err .bub{border-color:#5c4415;background:#241c08;color:var(--warm)}
 footer{background:var(--panel);border-top:1px solid var(--line);padding:11px 16px}
 .cmp{max-width:880px;margin:0 auto;display:flex;gap:9px}
 textarea{flex:1;background:#0e141c;color:var(--ink);border:1px solid var(--line);
   border-radius:10px;padding:10px 13px;font:inherit;resize:none;min-height:46px;max-height:170px}
 textarea:focus{outline:none;border-color:var(--accent)}
 button.send{background:var(--accent);color:#04121a;border:none;border-radius:10px;
   padding:11px 20px;font-weight:700;cursor:pointer}
 button.send:disabled{opacity:.45}
 .hint{max-width:880px;margin:7px auto 0;font-size:11px;color:var(--dim)}
 [dir=rtl]{text-align:right}
</style>
<header>
 <span class="brand">COUNCIL</span>
 <div class="who" id="who"></div>
 <span style="flex:1"></span>
 <button class="chip" id="reload">רענן</button>
</header>
<main><div class="wrap" id="log"></div></main>
<footer>
 <div class="cmp">
  <textarea id="q" placeholder="כתוב לכולם…  (Enter לשליחה)"></textarea>
  <button class="send" id="send">שלח</button>
 </div>
 <div class="hint">בחר למי לשלוח. הכל נשמר ב-ramchat_session.json — clod ו-Codex רואים גם.</div>
</footer>
<script>
const log=document.getElementById('log'),whoEl=document.getElementById('who'),
      q=document.getElementById('q'),send=document.getElementById('send');
let MEMBERS={},selected=new Set(['gpt-oss']);
const rtl=s=>/[\u0590-\u05FF]/.test(s);
function el(t,c,x){const n=document.createElement(t);if(c)n.className=c;
  if(x!=null){n.textContent=x;if(rtl(x))n.dir='rtl';}return n;}
function add(who,text,cls){const m=el('div','msg '+(cls||''));
  m.appendChild(el('div','nm',who));m.appendChild(el('div','bub',text));
  log.appendChild(m);return m;}
function scroll(){document.querySelector('main').scrollTop=1e9;}
async function boot(){
  const r=await fetch('/api/members').then(r=>r.json());MEMBERS=r.members;
  whoEl.innerHTML='';
  for(const [k,v] of Object.entries(MEMBERS)){
    const c=el('span','chip'+(selected.has(k)?' on':''),v.label);
    const s=el('span','s',v.fast?'⚡':'🐢');c.appendChild(s);
    c.onclick=()=>{selected.has(k)?selected.delete(k):selected.add(k);
      c.classList.toggle('on');};
    whoEl.appendChild(c);
  }
  await history();
}
async function history(){
  const r=await fetch('/api/history').then(r=>r.json());
  log.innerHTML='';
  r.messages.slice(-40).forEach(m=>add(m.who,m.text,
    /\[(לא זמין|שגיאה|timeout)/.test(m.text)?'err':(m.who==='עידו'?'me':'')));
  scroll();
}
async function ask(){
  const text=q.value.trim();if(!text||!selected.size)return;
  send.disabled=true;q.value='';
  add('עידו',text,'me');scroll();
  const pend={};
  selected.forEach(k=>{pend[k]=add(MEMBERS[k].label,'…');});
  scroll();
  await Promise.all([...selected].map(async k=>{
    try{
      const r=await fetch('/api/ask',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({member:k,prompt:text})}).then(r=>r.json());
      const b=pend[k].querySelector('.bub');
      b.textContent=r.answer||'(ריק)';if(rtl(b.textContent))b.dir='rtl';
      if(/\[(לא זמין|שגיאה|timeout)/.test(r.answer||''))pend[k].className='msg err';
    }catch(e){pend[k].querySelector('.bub').textContent='[נכשל] '+e;
      pend[k].className='msg err';}
    scroll();
  }));
  send.disabled=false;q.focus();
}
send.onclick=ask;
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}});
document.getElementById('reload').onclick=history;
boot();
</script>
"""


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _out(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, o, code=200):
        self._out(code, json.dumps(o, ensure_ascii=False).encode("utf-8"),
                  "application/json; charset=utf-8")

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/":
            return self._out(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/api/members":
            return self._json({"members": {
                k: {"label": v["label"], "where": v["where"], "fast": v.get("fast", False)}
                for k, v in MEMBERS.items()}})
        if self.path == "/api/history":
            return self._json({"messages": load_transcript()})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/api/ask":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        mid, prompt = req.get("member"), (req.get("prompt") or "").strip()
        if mid not in MEMBERS:
            return self._json({"error": f"unknown member {mid!r}"}, 400)
        # Log Iddo's line once, not once per addressed member.
        conv = load_transcript()
        if not conv or conv[-1].get("text") != prompt:
            append("עידו", prompt)
        ans = ask(mid, prompt)
        append(MEMBERS[mid]["label"], ans)
        return self._json({"answer": ans})


def main() -> int:
    srv = ThreadingHTTPServer((HOST, PORT), H)
    url = f"http://{HOST}:{PORT}"
    print(f"COUNCIL (RAMCHAT + QUORUM)  ->  {url}")
    print(f"  members: {', '.join(MEMBERS)}")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
