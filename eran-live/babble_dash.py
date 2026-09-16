"""babble_dash.py — LIVE dashboard of ERAN babbling as he trains. 100% ours.

Reloads checkpoints/latest.pt each refresh (reflects live training), samples ~fresh
babble, serves a self-refreshing page. CPU-only (never touches the training GPU).

Run:  python -s babble_dash.py         → http://localhost:8782
"""
import os, sys, json, html
os.environ["CUDA_VISIBLE_DEVICES"] = ""      # force CPU — do NOT disturb Eran's GPU training
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import torch
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tokenizer import tokenizer
from model import build_model

PORT = 8782
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)
CKPT = os.path.join(CFG["checkpoint_dir"], "latest.pt")

_model = build_model(CFG["model"]).to("cpu")
_model.eval()


def babble(n_chars=320, temp=0.95):
    step = 0
    if os.path.exists(CKPT):
        ck = torch.load(CKPT, map_location="cpu", weights_only=False)
        _model.load_state_dict(ck["model"])
        step = int(ck.get("step", 0))
    start = torch.tensor([[tokenizer.bos_id]], dtype=torch.long)
    with torch.no_grad():
        out = _model.generate(start, max_new_tokens=n_chars, temperature=temp, top_k=40)
    return step, tokenizer.decode(out[0].tolist())


PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="8">
<title>ERAN · babble · live</title>
<style>
 body{{margin:0;background:#05070d;color:#cdeaff;font-family:'Segoe UI',system-ui,sans-serif;
   min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}}
 .halo{{position:fixed;inset:0;background:radial-gradient(circle at 50% 40%,rgba(34,211,238,.10),transparent 60%);pointer-events:none}}
 h1{{margin:0;font-weight:800;letter-spacing:1px;color:#7dd3fc;text-shadow:0 0 24px rgba(56,189,248,.7)}}
 .step{{font-family:ui-monospace,Consolas,monospace;font-size:15px;color:#6ee7b7}}
 .dot{{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;
   box-shadow:0 0 10px #22c55e;animation:p 1.4s infinite}}
 @keyframes p{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
 .babble{{max-width:760px;width:88%;background:rgba(13,22,38,.72);border:1px solid rgba(56,189,248,.25);
   border-radius:16px;padding:26px 30px;font-size:22px;line-height:1.7;white-space:pre-wrap;
   box-shadow:0 0 60px rgba(30,64,175,.35) inset,0 10px 40px rgba(0,0,0,.5);min-height:200px}}
 .cap{{opacity:.55;font-size:12px}}
</style></head><body>
<div class="halo"></div>
<h1>👶 ער"ן מדבר</h1>
<div class="step"><span class="dot"></span> step {step:,} · live · מתרענן כל 8 שניות</div>
<div class="babble">{text}</div>
<div class="cap">byte-LM על הקול של עידו · CPU-sample · אפס Whisper · {port}</div>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_response(404); self.end_headers(); return
        try:
            step, text = babble()
        except Exception as e:
            step, text = 0, f"(sampling… {e})"
        body = PAGE.format(step=step, text=html.escape(text), port=PORT).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"[babble_dash] PROTO-ERAN babble live → http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
