"""babble_audio_dash.py — LIVE *audio* dashboard: HEAR Eran babble, auto-updating.

Mirrors babble_dash.py (which shows text) but for SOUND. A background thread
re-samples fresh babble from checkpoints/latest.pt every SAMPLE_EVERY seconds
using the exact listen.py pipeline (reload ckpt -> generate audio tokens ->
decode through the cochlea -> babble_latest.wav). The page polls /status and
auto-swaps + plays the newest babble with no full-page reload.

CPU-only on purpose (mic/training always win the GPU). The dashboard itself is
100% ours (stdlib http.server + vanilla JS); it reuses eran-audio's own
model + cochlea, same as listen.py.

Run:  python babble_audio_dash.py        -> http://localhost:8784
      (do NOT use -s: soundfile lives in the user site-packages)
"""
import os
import sys
import json
import time
import threading
import datetime

os.environ["CUDA_VISIBLE_DEVICES"] = ""   # CPU only — never contend with mic/training GPU

import numpy as np
import torch
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from model import build_model
from train import load_config, model_cfg_from, CKPT_DIR
from cochlea import Cochlea
import soundfile as sf

PORT = 8784
SAMPLE_EVERY = 25          # seconds between fresh babbles
LATEST = os.path.join(HERE, "babble_latest.wav")

cfg = load_config()
codec = cfg["codec"]
K = codec["n_codebooks"]
FR = codec["frame_rate"]
SR = codec["sample_rate"]
_lst = cfg.get("listen", {})
GEN_SECONDS = float(_lst.get("gen_seconds", 4.0))
TEMP = float(_lst.get("temperature", 0.95))
TOPK = int(_lst.get("top_k", 100))

torch.set_num_threads(min(4, os.cpu_count() or 2))   # faster CPU babble, still leaves cores for the mic

_model = None
_coch = None
_lock = threading.Lock()
_state = {"step": 0, "ts": 0, "dur": 0.0, "sampling": False, "err": "starting…", "have": False}


def _seed():
    """A few real frames of Eran's heard world, snapped to a frame boundary."""
    cache = os.path.join(HERE, "tokens_cache.npy")
    if os.path.exists(cache):
        s = np.load(cache)
        if s.size > 64:
            off = int(torch.randint(0, max(1, s.size - 64), (1,)).item())
            off = (off // K) * K
            return s[off:off + 10 * K].astype(np.int64)
    return np.array([0], dtype=np.int64)


def sample_once():
    """Reload latest checkpoint, babble a few fresh seconds, write babble_latest.wav atomically."""
    global _model, _coch
    ckpt = os.path.join(CKPT_DIR, "latest.pt")
    if not os.path.exists(ckpt):
        _state["err"] = "אין עדיין checkpoint — תן לער\"ן להתאמן קצת"
        return
    ck = torch.load(ckpt, map_location="cpu", weights_only=False)
    mcfg = ck.get("cfg") or model_cfg_from(cfg)
    if _model is None:
        _model = build_model(mcfg).to("cpu")
    _model.load_state_dict(ck["model"])
    _model.eval()
    step = int(ck.get("step", 0))

    n_tokens = int(GEN_SECONDS * FR) * K
    seed = _seed()
    idx = torch.tensor(seed[None, :], dtype=torch.long)
    with torch.no_grad():
        out = _model.generate(idx, max_new_tokens=n_tokens, temperature=TEMP, top_k=TOPK)
    gen = out[0].tolist()[len(seed):]
    gen = gen[: (len(gen) // K) * K]

    if _coch is None:
        _coch = Cochlea(device="cpu", cfg=cfg)   # loads EnCodec once (slow first time)
    wav = _coch.decode(torch.tensor(gen, dtype=torch.long))

    tmp = LATEST + ".tmp.wav"
    sf.write(tmp, wav, SR)
    os.replace(tmp, LATEST)                       # atomic swap — never serve a half-written file
    babbles = os.path.join(HERE, "babbles")
    os.makedirs(babbles, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sf.write(os.path.join(babbles, f"babble_step{step}_{ts}.wav"), wav, SR)

    _state.update(step=step, ts=int(time.time()), dur=round(len(wav) / SR, 1),
                  err=None, have=True)
    print(f"[babble_audio_dash] step {step:,}: babbled {_state['dur']}s -> {LATEST}")


def sampler_loop():
    while True:
        with _lock:
            _state["sampling"] = True
        try:
            sample_once()
        except Exception as e:
            _state["err"] = f"{type(e).__name__}: {e}"
            print(f"[babble_audio_dash] sample error: {e}")
        finally:
            _state["sampling"] = False
        time.sleep(SAMPLE_EVERY)


PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ער"ן · באבל · אודיו · חי</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;background:#05070d;color:#cdeaff;font-family:'Segoe UI',system-ui,sans-serif;
   min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px}
 .halo{position:fixed;inset:0;pointer-events:none;
   background:radial-gradient(circle at 50% 38%,rgba(34,211,238,.12),transparent 60%)}
 h1{margin:0;font-weight:800;letter-spacing:1px;color:#7dd3fc;text-shadow:0 0 26px rgba(56,189,248,.7)}
 .step{font-family:ui-monospace,Consolas,monospace;font-size:15px;color:#6ee7b7}
 .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;
   box-shadow:0 0 10px #22c55e;animation:p 1.4s infinite}
 .dot.wait{background:#f59e0b;box-shadow:0 0 10px #f59e0b}
 @keyframes p{0%,100%{opacity:1}50%{opacity:.25}}
 .card{position:relative;width:88%;max-width:560px;background:rgba(13,22,38,.72);
   border:1px solid rgba(56,189,248,.25);border-radius:20px;padding:34px 30px;text-align:center;
   box-shadow:0 0 60px rgba(30,64,175,.35) inset,0 12px 44px rgba(0,0,0,.5)}
 #face{font-size:74px;line-height:1;transition:transform .12s}
 #face.on{animation:breathe 2.2s ease-in-out infinite}
 @keyframes breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}
 .bars{display:flex;gap:5px;justify-content:center;align-items:flex-end;height:44px;margin:18px 0 6px}
 .bars i{width:6px;background:linear-gradient(#22d3ee,#3b82f6);border-radius:3px;height:8px}
 .bars.on i{animation:eq .9s ease-in-out infinite}
 .bars i:nth-child(2){animation-delay:.1s}.bars i:nth-child(3){animation-delay:.2s}
 .bars i:nth-child(4){animation-delay:.3s}.bars i:nth-child(5){animation-delay:.15s}
 .bars i:nth-child(6){animation-delay:.25s}.bars i:nth-child(7){animation-delay:.05s}
 @keyframes eq{0%,100%{height:8px}50%{height:40px}}
 button{margin-top:8px;background:#0ea5e9;color:#04121f;border:0;border-radius:12px;
   padding:14px 26px;font-size:17px;font-weight:800;cursor:pointer;box-shadow:0 6px 20px rgba(14,165,233,.5)}
 button:active{transform:translateY(1px)}
 .cap{opacity:.55;font-size:12px;max-width:560px;text-align:center;line-height:1.6}
 .err{color:#fca5a5;font-size:13px;min-height:16px}
</style></head><body>
<div class="halo"></div>
<h1>👶 ער"ן מבבל · חי</h1>
<div class="step"><span id="dot" class="dot"></span> <span id="stepline">מתחיל…</span></div>
<div class="card">
  <div id="face">🐣</div>
  <div id="bars" class="bars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
  <button id="go">🔊 הפעל האזנה</button>
  <div class="err" id="err"></div>
</div>
<div class="cap">byte-audio · EnCodec cochlea · דגימת CPU (המיק תמיד מנצח על ה-GPU) ·
  מתעדכן לבד כל ~25ש׳ · פורט 8784</div>
<audio id="au" loop></audio>
<script>
 const au=document.getElementById('au'), go=document.getElementById('go'),
       face=document.getElementById('face'), bars=document.getElementById('bars'),
       dot=document.getElementById('dot'), stepline=document.getElementById('stepline'),
       errEl=document.getElementById('err');
 let enabled=false, lastTs=0;
 go.onclick=()=>{ enabled=true; go.style.display='none'; au.muted=false; poll(true); };
 function playing(on){ face.classList.toggle('on',on); bars.classList.toggle('on',on); }
 au.onplay=()=>playing(true); au.onpause=()=>playing(false); au.onended=()=>playing(false);
 async function poll(force){
   try{
     const s=await (await fetch('/status',{cache:'no-store'})).json();
     dot.className='dot'+(s.sampling?' wait':'');
     stepline.textContent = s.have
       ? `step ${s.step.toLocaleString()} · ${s.dur}ש׳ · ${s.sampling?'דוגם באבל חדש…':'חי'}`
       : (s.err||'דוגם באבל ראשון…');
     errEl.textContent = (s.err&&s.have)?('⚠ '+s.err):'';
     if(enabled && s.have && (s.ts!==lastTs || force)){
       lastTs=s.ts;
       au.src='/latest.wav?ts='+s.ts;
       au.play().catch(()=>{});
     }
   }catch(e){ errEl.textContent='⚠ '+e; }
 }
 setInterval(()=>poll(false),3000); poll(false);
</script>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype, extra=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/status":
            self._send(json.dumps(_state).encode("utf-8"), "application/json")
        elif path == "/latest.wav":
            if os.path.exists(LATEST):
                with open(LATEST, "rb") as f:
                    self._send(f.read(), "audio/wav")
            else:
                self.send_response(404); self.end_headers()
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    threading.Thread(target=sampler_loop, daemon=True).start()
    print(f"[babble_audio_dash] ERAN audio babble live -> http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
