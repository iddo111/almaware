"""Voice Ant Farm — dialogue GUI. Speak → queen encodes → speaks back."""
import io
import json
import struct
import sys
import wave
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from acoustic_units import (
    load_checkpoint, features, encode, synthesize_units, render_soft, Audio,
    resample_samples, EXEMPLAR_RATE, HOP_SECONDS, collapse_runs,
)

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
CORONATION = STATE / "coronation.json"  # crowned-queen pointer; wins if present
PORT = 8803
RAW = True   # 2026-08-13, Iddo's order "shut soft render": the soft path lowpassed
             # everything at 2.5 kHz (zero by 5 kHz), which flattered the output and hid
             # what the colony actually produces. Default is now RAW. Pass --soft to
             # restore the old cosmetic rendering; render_soft() itself is untouched.
CHECKPOINT_OVERRIDE = None  # --checkpoint serves a specific sealed checkpoint


def load_queen():
    if CHECKPOINT_OVERRIDE:
        path = Path(CHECKPOINT_OVERRIDE)
        ckpt = load_checkpoint(path)
        colony = {"queen_selection": {
            "selected_ant": f"{path.parent.parent.name}/{path.parent.name}",
            "criterion": "external selection — see state-big/queen/current.json",
        }, "ants": []}
        return ckpt, colony
    if CORONATION.exists():
        # Coronation record (state/coronation.json): points at a sealed
        # checkpoint anywhere in the project. state/queen/current.json stays
        # untouched — the hybrid POC validates it as a sealed artifact.
        record = json.loads(CORONATION.read_text("utf-8"))
        ckpt = load_checkpoint(ROOT / record["checkpoint_path"])
        colony = {"queen_selection": {
            "selected_ant": record["queen"],
            "criterion": record["criterion"],
        }, "ants": record.get("ants", []), "coronation": record}
        return ckpt, colony
    colony = json.loads((STATE / "queen" / "current.json").read_text("utf-8"))
    sel = colony["queen_selection"]
    ant_name = sel["selected_ant"]
    ckpt_path = STATE / ant_name / "current.json"
    ckpt = load_checkpoint(ckpt_path)
    return ckpt, colony


def queen_features(audio: Audio, ckpt: dict):
    """Frame features in the queen's own cochlea.

    format_version<=3 checkpoints with feature_spec version 1 use the legacy
    14-dim path unchanged. Version-2 specs (vowel-cochlea ants) use
    feature_space.extract + the checkpoint's own per-dimension scaler.
    """
    spec = ckpt.get("feature_spec") or {}
    if spec.get("version", 1) < 2:
        return features(audio)
    import feature_space as F
    samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    x = F.extract(spec["name"], samples).astype(np.float32)
    scaler = np.asarray(ckpt["frame_scaler"], dtype=np.float32)
    return x / scaler, HOP_SECONDS


def wav_bytes_to_audio(data: bytes) -> Audio:
    buf = io.BytesIO(data)
    with wave.open(buf, "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        rate = w.getframerate()
        pcm = w.readframes(w.getnframes())
    if sw == 2:
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    elif sw == 4:
        samples = np.frombuffer(pcm, dtype="<i4").astype(np.float32) / 2147483648
    else:
        samples = np.frombuffer(pcm, dtype=np.uint8).astype(np.float32) / 128 - 1.0
    if ch > 1:
        samples = samples.reshape(-1, ch).mean(axis=1)
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    canonical = rate.to_bytes(4, "little") + np.clip(
        np.rint(samples * 32767), -32768, 32767
    ).astype("<i2").tobytes()
    pcm_sha = hashlib.sha256(canonical).hexdigest()
    return Audio(samples, rate, sha, pcm_sha)


def samples_to_wav(samples: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    pcm = np.clip(np.rint(samples * 32767), -32768, 32767).astype("<i2")
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


QUEEN_CKPT = None
COLONY_DATA = None
CORONATION_MTIME = None


def get_queen():
    """Cached queen; hot-reloads when state/coronation.json changes.

    The tournament (tournament.py) crowns by atomically rewriting the
    coronation file — no server restart. If a new record fails to load the
    sitting queen keeps serving; the dialogue is never left broken.
    """
    global QUEEN_CKPT, COLONY_DATA, CORONATION_MTIME
    mtime = CORONATION.stat().st_mtime if CORONATION.exists() else None
    if QUEEN_CKPT is None or mtime != CORONATION_MTIME:
        try:
            QUEEN_CKPT, COLONY_DATA = load_queen()
            CORONATION_MTIME = mtime
        except Exception:
            if QUEEN_CKPT is None:
                raise                      # nothing to fall back to
    return QUEEN_CKPT, COLONY_DATA


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voice Ant Farm — Dialogue</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#f8f7f4;--surface:#fff;--border:#ddd8cf;
  --text:#1a1918;--dim:#7a756b;--accent:#2d6a4f;--accent-l:#d8f3dc;
  --hot:#c1121f;--hot-bg:#fde8ea;--ok:#2d6a4f;--ok-bg:#d8f3dc;
  --mono:Consolas,'Courier New',monospace;
  --ui:'Segoe UI',system-ui,sans-serif;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#131312;--surface:#1c1c1a;--border:#333;
  --text:#e5e3de;--dim:#8a867d;--accent:#52b788;--accent-l:#1a2e24;
  --hot:#ef6461;--hot-bg:#2d1618;--ok:#52b788;--ok-bg:#1a2e24;
}}
body{font-family:var(--ui);background:var(--bg);color:var(--text);
  display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:1.5rem}
h1{font-family:var(--mono);font-size:1.1rem;color:var(--accent);margin-bottom:.3rem}
.subtitle{font-size:.78rem;color:var(--dim);margin-bottom:1.5rem}

.mic-area{display:flex;flex-direction:column;align-items:center;gap:1rem;margin-bottom:1.5rem}
#mic-btn{
  width:120px;height:120px;border-radius:50%;border:3px solid var(--accent);
  background:var(--surface);cursor:pointer;font-size:2.5rem;
  transition:all .2s;display:flex;align-items:center;justify-content:center;
  box-shadow:0 2px 8px rgba(0,0,0,.08);
}
#mic-btn:hover{transform:scale(1.05)}
#mic-btn.recording{border-color:var(--hot);background:var(--hot-bg);animation:pulse 1s infinite}
#mic-btn.processing{border-color:var(--dim);opacity:.6;cursor:wait}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(193,18,31,.3)}50%{box-shadow:0 0 0 12px rgba(193,18,31,0)}}
#status{font-size:.82rem;color:var(--dim);min-height:1.2em;font-family:var(--mono)}

.result{width:100%;max-width:700px}
.result-card{
  background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:1rem 1.2rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.05);
}
.result-card h3{font-family:var(--mono);font-size:.82rem;color:var(--accent);
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:.6rem}
.unit-strip{display:flex;flex-wrap:wrap;gap:2px;direction:ltr}
.unit-block{
  width:18px;height:28px;border-radius:3px;font-size:.55rem;
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-family:var(--mono);font-weight:700;cursor:pointer;
  transition:transform .1s;
}
.unit-block:hover{transform:scaleY(1.3)}

.stats-row{display:flex;gap:1.5rem;flex-wrap:wrap;margin-top:.5rem}
.stat{display:flex;flex-direction:column}
.stat .label{font-size:.65rem;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.stat .val{font-family:var(--mono);font-size:.95rem;font-weight:600}
.stat .val.ok{color:var(--ok)}

.colony-bar{
  width:100%;max-width:700px;background:var(--surface);
  border:1px solid var(--border);border-radius:8px;
  padding:.8rem 1rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.05);
  display:flex;gap:1.2rem;align-items:center;flex-wrap:wrap;
  font-size:.75rem;font-family:var(--mono);
}
.colony-bar .ant{display:flex;align-items:center;gap:.3rem}
.ant-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.queen-tag{font-size:.6rem;background:var(--ok-bg);color:var(--ok);
  padding:.1em .4em;border-radius:2px;font-weight:700}

audio{width:100%;max-width:700px;margin-bottom:1rem;border-radius:8px}
#history{width:100%;max-width:700px}
.history-item{
  background:var(--surface);border:1px solid var(--border);border-radius:6px;
  padding:.8rem 1rem;margin-bottom:.6rem;
}
.history-item .ts{font-size:.65rem;color:var(--dim);font-family:var(--mono)}
</style>
</head>
<body>
<h1>Voice Ant Farm</h1>
<p class="subtitle" id="subtitle">speak — the queen listens — speaks back</p>

<div class="colony-bar" id="colony-bar">loading colony...</div>

<div class="mic-area">
  <button id="mic-btn" title="Hold to record">🎤</button>
  <div id="status">press and hold to speak</div>
</div>

<div class="result" id="result" style="display:none">
  <audio id="playback" controls></audio>
  <div class="result-card">
    <h3>Unit Sequence</h3>
    <div class="unit-strip" id="unit-strip"></div>
    <div class="stats-row" id="stats-row"></div>
  </div>
</div>

<div id="history"></div>

<script>
const UNIT_COLORS = [];
for(let i=0;i<64;i++){
  const h = (i*137.508)%360;
  UNIT_COLORS.push(`hsl(${h},55%,48%)`);
}

const btn = document.getElementById('mic-btn');
const status = document.getElementById('status');
const result = document.getElementById('result');
const playback = document.getElementById('playback');
const unitStrip = document.getElementById('unit-strip');
const statsRow = document.getElementById('stats-row');
const history = document.getElementById('history');

let audioCtx, mediaStream, recorder, chunks;
let recording = false;

fetch('/api/colony').then(r=>r.json()).then(d=>{
  const bar = document.getElementById('colony-bar');
  document.getElementById('subtitle').textContent =
    `speak — the queen listens with ${d.units} ears (${d.cochlea}) — speaks back`;
  const rows = d.ants.map(a=>{
    const isQ = a.ant === d.queen;
    const score = a.cos_top1!==undefined ? (100*a.cos_top1).toFixed(1)+'%'
                : a.heldout_error!==undefined ? a.heldout_error.toFixed(3) : '';
    return `<span class="ant">
      <span class="ant-dot" style="background:${isQ?'var(--ok)':'var(--dim)'}"></span>
      ${a.ant} (${score})
      ${isQ?'<span class="queen-tag">QUEEN</span>':''}
    </span>`;
  });
  if(!d.ants.some(a=>a.ant===d.queen)){
    rows.unshift(`<span class="ant"><span class="ant-dot" style="background:var(--ok)"></span>
      ${d.queen}<span class="queen-tag">QUEEN</span></span>`);
  }
  rows.push(`<span class="ant" style="color:var(--dim)">ckpt ${(d.checkpoint_sha256||'').slice(0,12)}</span>`);
  bar.innerHTML = rows.join('');
});

async function initMic(){
  try{
    status.textContent = 'requesting mic...';
    mediaStream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true}});
    audioCtx = new AudioContext();
    status.textContent = 'mic ready — press and hold to speak (rate: '+audioCtx.sampleRate+'Hz)';
    btn.style.borderColor = 'var(--ok)';
  }catch(e){
    status.textContent = 'MIC ERROR: '+e.message;
    btn.style.borderColor = 'var(--hot)';
    btn.style.opacity = '0.5';
    console.error('mic init failed:', e);
  }
}
initMic();

btn.addEventListener('mousedown', startRec);
btn.addEventListener('mouseup', stopRec);
btn.addEventListener('mouseleave', stopRec);
btn.addEventListener('touchstart', e=>{e.preventDefault();startRec()});
btn.addEventListener('touchend', e=>{e.preventDefault();stopRec()});
document.addEventListener('keydown', e=>{if(e.code==='Space'&&!e.repeat&&!recording)startRec()});
document.addEventListener('keyup', e=>{if(e.code==='Space')stopRec()});

function startRec(){
  if(recording || !mediaStream) return;
  recording = true;
  btn.classList.add('recording');
  status.textContent = 'listening...';
  chunks = [];
  const source = audioCtx.createMediaStreamSource(mediaStream);
  const proc = audioCtx.createScriptProcessor(4096,1,1);
  proc.onaudioprocess = e => { if(recording) chunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
  source.connect(proc); proc.connect(audioCtx.destination);
  btn._source = source; btn._proc = proc;
}

function stopRec(){
  if(!recording) return;
  recording = false;
  btn.classList.remove('recording');
  btn.classList.add('processing');
  status.textContent = 'queen is thinking...';
  if(btn._source){btn._source.disconnect();btn._proc.disconnect()}
  const all = new Float32Array(chunks.reduce((a,c)=>a+c.length,0));
  let off=0; for(const c of chunks){all.set(c,off);off+=c.length}
  if(all.length < 800){
    status.textContent = 'too short — hold longer';
    btn.classList.remove('processing');
    return;
  }
  const wav = float32ToWav(all, audioCtx.sampleRate);
  sendAudio(wav);
}

function float32ToWav(samples, rate){
  const len = samples.length;
  const buf = new ArrayBuffer(44 + len*2);
  const v = new DataView(buf);
  const w = (o,str)=>{for(let i=0;i<str.length;i++)v.setUint8(o+i,str.charCodeAt(i))};
  w(0,'RIFF'); v.setUint32(4,36+len*2,true); w(8,'WAVE');
  w(12,'fmt '); v.setUint32(16,16,true); v.setUint16(20,1,true);
  v.setUint16(22,1,true); v.setUint32(24,rate,true);
  v.setUint32(28,rate*2,true); v.setUint16(32,2,true); v.setUint16(34,16,true);
  w(36,'data'); v.setUint32(40,len*2,true);
  for(let i=0;i<len;i++){
    let s=Math.max(-1,Math.min(1,samples[i]));
    v.setInt16(44+i*2, s<0?s*0x8000:s*0x7FFF, true);
  }
  return new Blob([buf],{type:'audio/wav'});
}

async function sendAudio(blob){
  try{
    const resp = await fetch('/api/listen',{method:'POST',body:blob,
      headers:{'Content-Type':'audio/wav'}});
    if(!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    showResult(data);
  }catch(e){
    status.textContent = 'error: '+e.message;
  }
  btn.classList.remove('processing');
}

function showResult(data){
  result.style.display = '';
  playback.src = '/api/audio/'+data.id;
  playback.play().catch(()=>{});
  unitStrip.innerHTML = '';
  const runs = data.runs || [];
  runs.forEach(r=>{
    const el = document.createElement('div');
    el.className = 'unit-block';
    el.style.background = UNIT_COLORS[r.unit%64];
    el.textContent = r.unit;
    el.title = `unit ${r.unit} (${r.start_s}s–${r.end_s}s)`;
    const w = Math.max(18, Math.min(40, Math.round((r.end_s-r.start_s)*80)));
    el.style.width = w+'px';
    unitStrip.appendChild(el);
  });
  statsRow.innerHTML = `
    <div class="stat"><span class="label">Units</span><span class="val">${data.total_frames}</span></div>
    <div class="stat"><span class="label">Unique</span><span class="val ok">${data.unique_units}/${data.units||64}</span></div>
    <div class="stat"><span class="label">Duration</span><span class="val">${data.duration_s.toFixed(1)}s</span></div>
    <div class="stat"><span class="label">Runs</span><span class="val">${runs.length}</span></div>
  `;
  status.textContent = `queen heard ${data.unique_units} unique units in ${data.duration_s.toFixed(1)}s`;
  const item = document.createElement('div');
  item.className = 'history-item';
  item.innerHTML = `<span class="ts">${new Date().toLocaleTimeString()}</span> — ${data.unique_units} units, ${data.duration_s.toFixed(1)}s`;
  history.prepend(item);
}
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    audio_cache: dict = {}

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "":
            self._html(HTML_PAGE)
        elif path == "/api/colony":
            self._colony()
        elif path.startswith("/api/audio/"):
            self._serve_audio(path.split("/")[-1])
        else:
            self._err(404, "not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/listen":
            self._listen()
        else:
            self._err(404, "not found")

    def _html(self, content):
        b = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(b))
        self.end_headers()
        self.wfile.write(b)

    def _json(self, obj):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(b))
        self.end_headers()
        self.wfile.write(b)

    def _err(self, code, msg):
        b = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", len(b))
        self.end_headers()
        self.wfile.write(b)

    def _colony(self):
        ckpt, colony = get_queen()
        ants = []
        for a in colony.get("ants", []):
            if "heldout_error_after" in a:      # legacy colony record
                ants.append({
                    "ant": a["ant"],
                    "seed": a["seed"],
                    "heldout_error": a["heldout_error_after"],
                    "eval_error": a.get("evaluation", {}).get("error_after"),
                    "improved": a["improved_over_baseline"],
                })
            else:                               # coronation record
                ants.append(a)
        payload = {
            "queen": colony["queen_selection"]["selected_ant"],
            "criterion": colony["queen_selection"]["criterion"],
            "units": ckpt.get("units", 64),
            "checkpoint_sha256": ckpt["checkpoint_sha256"],
            "cochlea": (ckpt.get("feature_spec") or {}).get("name", "legacy14"),
            "ants": ants,
        }
        if "coronation" in colony:
            payload["coronation"] = colony["coronation"]
        self._json(payload)

    def _listen(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0 or length > 10_000_000:
            return self._err(400, "bad audio size")
        data = self.rfile.read(length)
        try:
            audio = wav_bytes_to_audio(data)
        except Exception as e:
            return self._err(400, f"bad wav: {e}")
        ckpt, colony = get_queen()
        centers = np.asarray(ckpt["centers"], dtype=np.float32)
        x, hop_sec = queen_features(audio, ckpt)
        ids = encode(x, centers)
        runs = collapse_runs(ids, hop_sec)
        ns = f"{ckpt['checkpoint_sha256']}:unit_id"
        out_samples = synthesize_units(ids, ns, ckpt)
        if not RAW:
            out_samples = render_soft(out_samples, ckpt["exemplar_rate"])
        out_wav = samples_to_wav(out_samples, ckpt["exemplar_rate"])
        audio_id = f"r{len(Handler.audio_cache)}"
        Handler.audio_cache[audio_id] = out_wav
        unique = len(set(int(u) for u in ids))
        self._json({
            "id": audio_id,
            "runs": runs,
            "total_frames": int(len(ids)),
            "unique_units": unique,
            "units": int(ckpt.get("units", 64)),
            "queen": colony["queen_selection"]["selected_ant"],
            "checkpoint_sha256": ckpt["checkpoint_sha256"],
            "cochlea": (ckpt.get("feature_spec") or {}).get("name", "legacy14"),
            "duration_s": round(len(out_samples) / ckpt["exemplar_rate"], 2),
            "render": "raw" if RAW else "soft",
        })

    def _serve_audio(self, audio_id):
        data = Handler.audio_cache.get(audio_id)
        if not data:
            return self._err(404, "no such audio")
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)


def main():
    global RAW, CHECKPOINT_OVERRIDE
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", type=int, default=PORT)
    ap.add_argument("--raw", action="store_true",
                    help="raw rendering, no lowpass/fades (this is now the DEFAULT)")
    ap.add_argument("--soft", action="store_true",
                    help="restore the old cosmetic soft render (hann OLA + 2.5kHz lowpass)")
    ap.add_argument("--checkpoint", default=None,
                    help="serve this sealed checkpoint instead of state/ queen")
    args = ap.parse_args()
    # Default is RAW (module-level RAW = True, Iddo 2026-08-13). --soft is the only
    # way back to the lowpassed render; --raw is kept so old launch commands still work.
    RAW = False if args.soft else True
    CHECKPOINT_OVERRIDE = args.checkpoint
    port = args.port
    ckpt, colony = load_queen()
    queen = colony["queen_selection"]["selected_ant"]
    render = "raw (square)" if RAW else "soft (hann OLA + 2.5kHz lowpass)"
    print(f"ant farm dialogue — queen={queen}, units={ckpt.get('units', 64)}, render={render}")
    print(f"http://127.0.0.1:{port}/")
    server = HTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
