"""
chat_server.py - a tiny LOCAL window to TALK (type) to text-Eran.

You type a line; Eran (the live byte-level model) continues it in his own babble.
Honest: Eran is age-zero (~3M params, vocab 260). He does NOT converse - he
echoes/continues in Iddo's style. This is really him, not a chatbot, not a voice.

- Loads a COPY of checkpoints/latest.pt (so it never races the live trainer's write).
- Runs on CPU (never touches the trainer's GPU / the mic).
- Reloads automatically when the checkpoint advances, so you always talk to the
  freshest Eran.
- Serves an RTL Hebrew page at http://127.0.0.1:8792

Run:  pythonw -s chat_server.py     (detached)  |  python -s chat_server.py (foreground)
"""
import os, sys, json, shutil, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import torch

# Cap CPU threads: Eran is tiny (~3M params) so a few threads generate a reply in
# a second or two, while leaving cores for the live mic + trainer. Uncapped, torch
# grabbed every core and thrashed against the other always-on ALMA processes,
# making /say take 40s+ on a loaded box (2026-07-05). Snappy > greedy here.
try:
    torch.set_num_threads(max(1, min(4, (os.cpu_count() or 8) // 4)))
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tokenizer import tokenizer            # byte-level, vocab 260
from model import build_model

PORT = 8792
DEVICE = "cpu"                              # never fight the trainer for GPU

with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8") as f:
    CFG = json.load(f)
CKPT = os.path.join(CFG["checkpoint_dir"], "latest.pt")
BLOCK = int(CFG["model"]["block_size"])

_lock = threading.Lock()
_state = {"model": None, "step": 0, "mtime": 0.0}


def _load_if_new():
    """(Re)load Eran from a safe copy of latest.pt when it changes."""
    if not os.path.exists(CKPT):
        if _state["model"] is None:
            _state["model"] = build_model(CFG["model"]).to(DEVICE).eval()
        return
    mt = os.path.getmtime(CKPT)
    if _state["model"] is not None and mt <= _state["mtime"]:
        return
    tmp = os.path.join(tempfile.gettempdir(), "eran_chat_latest.pt")
    try:
        shutil.copyfile(CKPT, tmp)                         # copy -> no partial-write race
        ck = torch.load(tmp, map_location=DEVICE, weights_only=False)
        m = build_model(CFG["model"]).to(DEVICE)
        m.load_state_dict(ck["model"])
        m.eval()
        _state["model"] = m
        _state["step"] = int(ck.get("step", 0))
        _state["mtime"] = mt
        print(f"[chat] loaded Eran @ step {_state['step']}", flush=True)
    except Exception as e:
        print(f"[chat] reload skipped ({e}); keeping current Eran", flush=True)
        if _state["model"] is None:
            _state["model"] = build_model(CFG["model"]).to(DEVICE).eval()


def eran_reply(user_text: str, max_new=96, temp=0.85):
    with _lock:
        _load_if_new()
        model, step = _state["model"], _state["step"]
        prompt = [tokenizer.bos_id] + tokenizer.encode(user_text or "")
        if len(prompt) > BLOCK:
            prompt = prompt[-BLOCK:]
        idx = torch.tensor([prompt], dtype=torch.long, device=DEVICE)
        with torch.no_grad():
            out = model.generate(idx, max_new_tokens=max_new, temperature=temp, top_k=40)
        new_ids = out[0].tolist()[len(prompt):]
        reply = tokenizer.decode(new_ids).strip()
        return reply, step


PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>שיחה עם ערן</title>
<style>
 body{background:#0f1115;color:#e8eef7;font-family:system-ui,Arial;margin:0;padding:16px;max-width:760px;margin-inline:auto}
 h1{font-size:20px;margin:.2em 0}
 .note{color:#f0b429;font-size:13px;margin-bottom:12px;line-height:1.5}
 #log{background:#171b22;border:1px solid #263042;border-radius:12px;padding:12px;height:60vh;overflow:auto}
 .msg{margin:8px 0;padding:8px 12px;border-radius:12px;max-width:85%;white-space:pre-wrap;word-break:break-word}
 .me{background:#1d4ed8;margin-inline-start:auto}
 .eran{background:#243244}
 .who{font-size:11px;opacity:.6;margin-bottom:2px}
 form{display:flex;gap:8px;margin-top:12px}
 input{flex:1;padding:12px;border-radius:10px;border:1px solid #334;background:#0c0e12;color:#e8eef7;font-size:16px}
 button{padding:12px 18px;border:0;border-radius:10px;background:#1d4ed8;color:#fff;font-size:16px;cursor:pointer}
 button:disabled{opacity:.5}
</style></head><body>
<h1>🧠 שיחה עם ערן \xb7 <span id="step">…</span></h1>
<div class="note">גיל אפס — ערן מבלבל את המילים שלך, עדיין לא משוחח. זה באמת הוא — לא צ״אטבוט, לא קול מזויף.</div>
<div id="log"></div>
<form id="f"><input id="t" autocomplete="off" placeholder="תכתוב לערן…" autofocus><button id="b">שלח</button></form>
<script>
const log=document.getElementById('log'),t=document.getElementById('t'),b=document.getElementById('b'),f=document.getElementById('f');
function add(cls,who,txt){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML='<div class="who">'+who+'</div>'+txt.replace(/</g,'&lt;');log.appendChild(d);log.scrollTop=log.scrollHeight;}
f.onsubmit=async e=>{e.preventDefault();const v=t.value.trim();if(!v)return;add('me','אתה',v);t.value='';b.disabled=true;
 try{const r=await fetch('/say',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:v})});const j=await r.json();
 document.getElementById('step').textContent='step '+j.step;add('eran','ערן',j.reply||'…');}catch(err){add('eran','ערן','[שגיאה]');}b.disabled=false;t.focus();};
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.rstrip("/") != "/say":
            self.send_error(404); return
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            data = {}
        reply, step = eran_reply(str(data.get("text", "")))
        out = json.dumps({"reply": reply, "step": step}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


if __name__ == "__main__":
    _load_if_new()
    print(f"[chat] ערן chat on http://127.0.0.1:{PORT}  (step {_state['step']}, device={DEVICE})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
