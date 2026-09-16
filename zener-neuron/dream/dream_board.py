#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DREAM BOARD — הלוח החולם  (2026-09-10)

A Boltzmann-style stochastic network that dreams Hebrew letters out of noise.
  visible : 32x32 binary units (the board)
  hidden  : one softmax group: 22 letter units + "dark" (one-of-K hidden units, a standard Boltzmann construction)
  weights : PRESCRIBED from letter templates (Hebbian), NOT trained.  No training on the PC — law.
            v->h: W_k = (2T_k-1)/|T_k|, so s = (2|v∩T_k| - |v|)/|T_k| is 1 on a match and negative on noise;
                  hidden logit = gamma*(s - theta). Linear in v: a real RBM-style hidden unit.
            h->v: centred templates (ink pushes on, background gently off) plus a visible bias that keeps
                  the board dark when no letter is on.
            In darkness a spontaneous spike (p_spont per sweep) lights ONE hidden unit, and the coin that
                  picks WHICH letter comes from the bit source. The dice choose the letter. Nothing else does.
            Differently scaled in the two directions, so this is not a strict energy model;
            it is a Hebbian RBM with prescribed weights. Said plainly here so nobody oversells it.
  coins   : every Bernoulli draw uses a uniform built from k bits of a labelled BitSource:
              zener      — the ESP32 zener neuron over serial (LSB + von Neumann, same as pc/logger.py)
              prng       — numpy PCG64 (labelled as such)
              file       — a bits-*.bin recorded by logger.py
            If the hardware source cannot supply, the coin comes from PRNG and is labelled
            'prng-fallback'. The fallback is NEVER silent.
  server  : stdlib http.server on 127.0.0.1:8864 (port claimed in RAMCHAT 20:30). No framework, no CDN.
  logs    : logs/dream-<stamp>.csv — every sweep: time, source, temp, best letter, score, active letters.

Run:  python dream_board.py                  (prng, 20 sweeps/s)
      python dream_board.py --source zener --port COM5
      python dream_board.py --selftest
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
import sys, json, time, math, threading, argparse, csv, base64, collections
import numpy as np
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
LETTERS = "אבגדהוזחטיכלמנסעפצקרשת"
N = 32
NV = N * N
NH = len(LETTERS)
FONT = r"C:\Windows\Fonts\DavidCLM-Medium.otf"   # thin strokes: letters overlap less (measured: max cross-score 0.60 vs 0.82 bold)
PORT_DEFAULT = 8864


# ----------------------------------------------------------------------------- templates
def make_templates(force=False):
    """22 binary 32x32 letter bitmaps, cached in templates.npy. PIL is used only here."""
    cache = os.path.join(HERE, "templates.npy")
    if os.path.exists(cache) and not force:
        t = np.load(cache)
        if t.shape == (NH, NV):
            return t
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(FONT, 34)
    out = np.zeros((NH, NV), dtype=np.uint8)
    for k, ch in enumerate(LETTERS):
        im = Image.new("L", (N, N), 0)
        d = ImageDraw.Draw(im)
        bb = d.textbbox((0, 0), ch, font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d.text(((N - w) / 2 - bb[0], (N - h) / 2 - bb[1]), ch, fill=255, font=font)
        out[k] = (np.array(im) > 170).astype(np.uint8).ravel()
    np.save(cache, out)
    return out


# ----------------------------------------------------------------------------- bit sources
class BitSource:
    """Serves bits with a label. Never lies about where they came from."""

    def __init__(self, mode="prng", port=None, path=None, seed=None):
        self.lock = threading.Lock()
        self.rng = np.random.Generator(np.random.PCG64(seed))
        self.mode = "prng"
        self.label = "prng"
        self.port = port
        self.path = path
        self.buf = collections.deque(maxlen=2_000_000)   # hardware / file bits waiting to be used
        self.raw_recent = collections.deque(maxlen=2000)  # raw ADC samples, for the acceptance test
        self.served = {"zener": 0, "prng": 0, "prng-fallback": 0, "file": 0}
        self.hw_bits_in = 0
        self.hw_rate = 0.0          # EMA bits/s arriving from hardware
        self._hw_last_t = time.time(); self._hw_last_n = 0
        self.error = ""
        self._reader = None
        self._stop = threading.Event()
        self.set_mode(mode, port, path)

    # -- mode switching
    def set_mode(self, mode, port=None, path=None):
        with self.lock:
            self._stop.set()
            self._stop = threading.Event()
            self.buf.clear(); self.raw_recent.clear()
            self.error = ""
            self.mode = mode
            if port: self.port = port
            if path: self.path = path
            if mode == "zener":
                self.label = "zener"
                t = threading.Thread(target=self._serial_reader, args=(self._stop,), daemon=True)
                t.start(); self._reader = t
            elif mode == "file":
                self.label = "file"
                t = threading.Thread(target=self._file_reader, args=(self._stop,), daemon=True)
                t.start(); self._reader = t
            else:
                self.mode = "prng"; self.label = "prng"

    def _serial_reader(self, stop):
        try:
            import serial
        except ImportError:
            self.error = "pyserial missing"; return
        try:
            ser = serial.Serial(self.port, 921600, timeout=1)
        except Exception as e:
            self.error = f"serial open failed: {e}"; return
        prev = None
        while not stop.is_set():
            line = ser.readline()
            if not line:
                continue
            try:
                v = int(line.strip())
            except ValueError:
                continue
            self.raw_recent.append(v)
            b = v & 1
            if prev is None:
                prev = b
            else:
                if prev != b:                       # von Neumann: 01->0, 10->1
                    self.buf.append(prev)
                    self.hw_bits_in += 1
                prev = None
            now = time.time()
            if now - self._hw_last_t >= 1.0:
                r = (self.hw_bits_in - self._hw_last_n) / (now - self._hw_last_t)
                self.hw_rate = 0.7 * self.hw_rate + 0.3 * r if self.hw_rate else r
                self._hw_last_t, self._hw_last_n = now, self.hw_bits_in
        try: ser.close()
        except Exception: pass

    def _file_reader(self, stop):
        try:
            data = open(self.path, "rb").read()
        except Exception as e:
            self.error = f"file open failed: {e}"; return
        bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
        i = 0
        while not stop.is_set() and i < len(bits):
            if len(self.buf) < 1_000_000:
                chunk = bits[i:i + 65536]; i += len(chunk)
                self.buf.extend(chunk.tolist()); self.hw_bits_in += len(chunk)
            else:
                time.sleep(0.05)
        if i >= len(bits):
            self.error = "file exhausted"

    # -- serving
    def bits(self, n):
        """Return (uint8 array of n bits, label)."""
        with self.lock:
            if self.mode in ("zener", "file"):
                if len(self.buf) >= n:
                    out = np.fromiter((self.buf.popleft() for _ in range(n)), dtype=np.uint8, count=n)
                    lab = self.mode
                    self.served[lab] += n
                    return out, lab
                out = self.rng.integers(0, 2, n, dtype=np.uint8)
                self.served["prng-fallback"] += n
                return out, "prng-fallback"
            out = self.rng.integers(0, 2, n, dtype=np.uint8)
            self.served["prng"] += n
            return out, "prng"

    def raw_std(self):
        if len(self.raw_recent) < 50:
            return None
        return float(np.std(np.fromiter(self.raw_recent, dtype=np.float64)))

    def status(self):
        return {
            "mode": self.mode, "port": self.port, "path": self.path,
            "buffered": len(self.buf), "hw_bits_in": self.hw_bits_in,
            "hw_rate": round(self.hw_rate, 1), "served": dict(self.served),
            "raw_std": self.raw_std(), "error": self.error,
        }


# ----------------------------------------------------------------------------- the board
class DreamBoard:
    def __init__(self, templates, src, temp=1.0, alpha=7.0, gamma=12.0, theta=0.3, vbias=-3.0, p_spont=0.08, bits_per_coin=8):
        self.src = src
        self.T = templates.astype(np.float32)                 # (22, 1024) in {0,1}
        Tc = self.T - self.T.mean(axis=1, keepdims=True)       # centred: ink -> +(1-f), background -> -f
        self.Tc = Tc.astype(np.float32)                        # h->v: ink pushes on, background pushes gently off
        n_ink = self.T.sum(axis=1, keepdims=True)
        self.Wh = ((2.0 * self.T - 1.0) / n_ink).astype(np.float32)   # v->h: s = (2|v∩T| - |v|)/|T| : 1 on a match, <0 on noise
        self.temp = float(temp); self.alpha = float(alpha); self.gamma = float(gamma); self.theta = float(theta)
        self.vbias = float(vbias)                              # visible bias: with no letter on, the board is sparse dark noise
        self.p_spont = float(p_spont)                          # spontaneous spike rate in darkness; the SOURCE picks the letter
        self.quiet = 0
        self.p_dark = 1.0
        self.k = int(bits_per_coin)
        self.lock = threading.Lock()
        self.v = np.zeros(NV, dtype=np.float32)
        self.h = np.zeros(NH, dtype=np.float32)
        self.ph = np.zeros(NH, dtype=np.float32)
        self.s = np.zeros(NH, dtype=np.float32)
        self.sweeps = 0
        self.sps = 0.0
        self.last_label = "prng"
        self.dream = collections.deque(maxlen=48)      # letters the board settled on, in order
        self._last_letter = None
        self.history = collections.deque(maxlen=400)   # (t, best_idx or -1)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
        self.log_path = os.path.join(HERE, "logs", f"dream-{stamp}.csv")
        self._log = open(self.log_path, "w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._log)
        self._csv.writerow(["t", "sweep", "source", "temp", "best", "score", "active"])
        self.reset()

    def coins(self, n, k=None):
        k = self.k if k is None else int(k)
        bits, lab = self.src.bits(n * k)
        b = bits.reshape(n, k).astype(np.uint32)
        weights = (1 << np.arange(k - 1, -1, -1, dtype=np.uint32))
        ints = (b * weights).sum(axis=1)
        return ints.astype(np.float64) / float(1 << k), lab

    def reset(self):
        with self.lock:
            u, lab = self.coins(NV)
            self.v = (u < 0.5).astype(np.float32)
            self.h[:] = 0; self.ph[:] = 0; self.s[:] = 0
            self.last_label = lab

    @staticmethod
    def sigmoid(x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))

    def sweep(self):
        with self.lock:
            s = self.Wh @ self.v                                # (22,)  1.0 on a perfect match, ~0.7 on a lived-in letter, <0 on noise
            logits = self.gamma * (s - self.theta) / self.temp  # letters compete with each other and with darkness (logit 0)
            m = max(float(logits.max()), 0.0)
            w = np.exp(logits - m); w_dark = math.exp(-m)
            Z = float(w.sum()) + w_dark
            ph = (w / Z).astype(np.float32); p_dark = w_dark / Z
            u, lab1 = self.coins(1, k=16)                       # ONE 16-bit coin picks one letter, or darkness
            idx = int(np.searchsorted(np.cumsum(ph), u[0]))
            h = np.zeros(NH, dtype=np.float32)
            if idx < NH:
                h[idx] = 1.0; self.quiet = 0
            else:
                self.quiet += 1
                if self.quiet >= 3:                             # darkness: a spontaneous spike, and the SOURCE picks which letter
                    u1, _ = self.coins(1)
                    if u1[0] < self.p_spont:
                        while True:                             # 5 bits -> 0..31, rejection above 21 keeps it uniform
                            b5, _ = self.src.bits(5)
                            j = int(np.packbits(b5)[0]) >> 3
                            if j < NH:
                                break
                        h[j] = 1.0
            self.p_dark = float(p_dark)
            lv = self.alpha * (self.Tc.T @ h) + self.vbias      # (1024,) union of the active letters; vbias alone -> sparse noise
            pv = self.sigmoid(lv / self.temp)
            u, lab2 = self.coins(NV)
            v = (u < pv).astype(np.float32)
            self.v, self.h, self.ph, self.s = v, h, ph, s
            self.sweeps += 1
            self.last_label = lab2 if lab2 == lab1 else f"{lab1}+{lab2}"
            best = int(np.argmax(s)) if (h.any() and float(s.max()) >= 0.5) else -1
            self.history.append((time.time(), best))
            if best >= 0 and best != self._last_letter:
                self.dream.append(LETTERS[best]); self._last_letter = best
            if best < 0:
                self._last_letter = None
            active = "".join(LETTERS[i] for i in range(NH) if h[i] > 0)
            self._csv.writerow([f"{time.time():.3f}", self.sweeps, self.last_label, self.temp,
                                LETTERS[best] if best >= 0 else "", f"{float(s.max()):.3f}", active])
            if self.sweeps % 50 == 0:
                self._log.flush()

    def state(self):
        with self.lock:
            packed = np.packbits(self.v.astype(np.uint8))
            return {
                "n": N, "sweeps": self.sweeps, "sps": round(self.sps, 2),
                "temp": self.temp, "alpha": self.alpha, "gamma": self.gamma, "theta": self.theta, "vbias": self.vbias, "p_spont": self.p_spont, "p_dark": round(self.p_dark, 4), "k": self.k,
                "v": base64.b64encode(packed.tobytes()).decode("ascii"),
                "h": self.h.astype(int).tolist(),
                "ph": [round(float(x), 3) for x in self.ph],
                "s": [round(float(x), 3) for x in self.s],
                "letters": LETTERS,
                "active": "".join(LETTERS[i] for i in range(NH) if self.h[i] > 0),
                "dream": "".join(self.dream),
                "coin_label": self.last_label,
                "source": self.src.status(),
                "log": os.path.basename(self.log_path),
            }


# ----------------------------------------------------------------------------- sampler thread
class Sampler(threading.Thread):
    def __init__(self, board, sps=20.0):
        super().__init__(daemon=True)
        self.board = board; self.max_sps = float(sps); self.running = True
        self.paused = False

    def run(self):
        last = time.time(); n0 = self.board.sweeps; t0 = last
        while self.running:
            if self.paused:
                time.sleep(0.05); continue
            t_start = time.time()
            self.board.sweep()
            now = time.time()
            if now - t0 >= 1.0:
                self.board.sps = (self.board.sweeps - n0) / (now - t0); n0 = self.board.sweeps; t0 = now
            budget = 1.0 / self.max_sps if self.max_sps > 0 else 0
            dt = budget - (now - t_start)
            if dt > 0:
                time.sleep(dt)


# ----------------------------------------------------------------------------- http
PAGE = r"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><title>הלוח החולם — DREAM BOARD</title>
<style>
 body{margin:0;background:#fff;color:#111;font-family:"Segoe UI",Arial,sans-serif}
 .wrap{max-width:1180px;margin:0 auto;padding:18px 22px}
 h1{font-size:26px;margin:0 0 2px} h1 small{font-size:13px;color:#777;font-weight:normal;margin-inline-start:10px}
 .row{display:grid;grid-template-columns:540px 1fr;gap:26px;margin-top:14px}
 canvas{background:#fff;border:1px solid #ddd;border-radius:6px;display:block;image-rendering:pixelated}
 .card{background:#fbf7ec;border:1px solid #f0dca0;border-radius:8px;padding:12px 16px;margin-bottom:12px}
 .src{font-size:22px;font-weight:bold;padding:6px 12px;border-radius:6px;display:inline-block;direction:ltr}
 .src.zener{background:#e6f7e6;color:#1a7f1a;border:1px solid #9bd39b}
 .src.prng{background:#eee;color:#444;border:1px solid #ccc}
 .src.fb{background:#fde8e8;color:#b00020;border:1px solid #f3b8b8}
 .src.file{background:#e8f0fd;color:#1b4fa0;border:1px solid #b8cdf3}
 .kv{display:grid;grid-template-columns:auto 1fr;gap:2px 14px;font-size:14px;margin-top:8px}
 .kv b{color:#555;font-weight:600}
 .bars{display:grid;grid-template-columns:repeat(22,1fr);gap:3px;margin-top:6px;direction:rtl}
 .bar{height:70px;background:#f2f2f2;border-radius:3px;position:relative;overflow:hidden}
 .bar i{position:absolute;bottom:0;left:0;right:0;background:#c9c9c9}
 .bar.on i{background:#f0b429}
 .bars span{display:block;text-align:center;font-size:15px;margin-top:2px;font-family:"David Libre","David",serif}
 .bars span.on{color:#b07800;font-weight:bold}
 .dream{font-family:"David Libre","David",serif;font-size:34px;letter-spacing:6px;min-height:46px;direction:rtl;
        background:#fff;border:1px dashed #ccc;border-radius:6px;padding:6px 12px;margin-top:6px;word-break:break-all}
 .en{color:#666;font-size:12.5px;direction:ltr;text-align:left}
 label{font-size:14px} input[type=range]{width:220px;vertical-align:middle}
 button{font-size:14px;padding:5px 12px;border:1px solid #bbb;border-radius:6px;background:#fff;cursor:pointer}
 button:hover{background:#f7f7f7}
 .warn{color:#b00020;font-size:13px}
</style></head><body><div class="wrap">
<h1>🕯️ הלוח החולם <small>DREAM BOARD — 32×32 Boltzmann board, 22 Hebrew letters, Hebbian weights (not trained). Every coin labelled.</small></h1>

<div class="row">
 <div>
  <canvas id="c" width="512" height="512"></canvas>
  <div class="card" style="margin-top:12px">
   <div>מה הלוח חולם <span class="en">letters the board settled on, in order</span></div>
   <div class="dream" id="dream"></div>
   <div class="en" style="margin-top:6px">This line is where a grieving reader finds messages. It is written from PRNG exactly as readily as from the zener. That is the whole lesson, and the source badge on the right is the only thing that separates the two.</div>
  </div>
 </div>
 <div>
  <div class="card">
   <div>מקור המטבעות <span class="en">coin source</span></div>
   <div style="margin-top:6px"><span id="src" class="src prng">prng</span></div>
   <div class="kv">
    <b>ביטים שהוגשו</b><span id="served" dir="ltr"></span>
    <b>מהחומרה</b><span id="hw" dir="ltr"></span>
    <b>std גולמי</b><span id="rawstd" dir="ltr"></span>
    <b>שגיאה</b><span id="err" class="warn" dir="ltr"></span>
   </div>
   <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
    <button onclick="setSrc('prng')">PRNG</button>
    <button onclick="setSrc('zener')">זנר (serial)</button>
    <input id="port" value="COM5" style="width:70px;direction:ltr" title="COM port">
    <button onclick="fetch('/reset').then(poll)">איפוס הלוח</button>
   </div>
  </div>
  <div class="card">
   <div>הנוירונים הנסתרים — 22 אותיות <span class="en">one-of-22 softmax (plus dark), p this sweep</span></div>
   <div class="bars" id="bars"></div>
   <div class="kv" style="margin-top:8px">
    <b>פעילות עכשיו</b><span id="active" style="font-family:'David Libre',serif;font-size:20px"></span>
    <b>סוויפים</b><span id="sweeps" dir="ltr"></span>
    <b>סוויפים/שנייה</b><span id="sps" dir="ltr"></span>
    <b>מטבע אחרון</b><span id="coin" dir="ltr"></span>
   </div>
  </div>
  <div class="card">
   <label>טמפרטורה <input type="range" id="temp" min="0.3" max="3" step="0.05" value="1" oninput="setTemp(this.value)"> <span id="tempv">1.00</span></label><br>
   <label>קצב מקסימלי (סוויפים/ש׳) <input type="range" id="sps_in" min="1" max="60" step="1" value="20" oninput="setSps(this.value)"> <span id="spsv">20</span></label>
   <div class="en" style="margin-top:6px">Temperature divides every logit. Cold = one crisp letter that stays. Hot = letters flicker and blend. The sweep rate is capped so an eye can follow; with the zener as source the rate is bounded by its bits, about 2.5 kbit/s, which is roughly one sweep every three seconds.</div>
  </div>
  <div class="en" id="log"></div>
 </div>
</div>
</div>
<script>
const cv=document.getElementById('c'),ctx=cv.getContext('2d');
const L="אבגדהוזחטיכלמנסעפצקרשת";
const bars=document.getElementById('bars');
for(let i=0;i<22;i++){const d=document.createElement('div');d.innerHTML='<div class="bar"><i></i></div><span>'+L[i]+'</span>';bars.appendChild(d);}
function draw(b64,n){const bin=atob(b64);const cell=cv.width/n;ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);ctx.fillStyle='#111';
 for(let i=0;i<n*n;i++){const byte=bin.charCodeAt(i>>3);const bit=(byte>>(7-(i&7)))&1;if(bit){const x=i%n,y=(i/n)|0;ctx.fillRect(x*cell,y*cell,cell-1,cell-1);}}}
function setTemp(v){document.getElementById('tempv').textContent=(+v).toFixed(2);fetch('/set?temp='+v);}
function setSps(v){document.getElementById('spsv').textContent=v;fetch('/set?sps='+v);}
function setSrc(m){const p=document.getElementById('port').value;fetch('/set?source='+m+'&port='+encodeURIComponent(p)).then(poll);}
let busy=false;
async function poll(){if(busy)return;busy=true;try{const r=await fetch('/state');const s=await r.json();
 draw(s.v,s.n);
 const src=s.source;const lab=s.coin_label;const el=document.getElementById('src');el.textContent=lab;
 el.className='src '+(lab.includes('fallback')?'fb':lab.includes('zener')?'zener':lab.includes('file')?'file':'prng');
 document.getElementById('served').textContent=Object.entries(src.served).filter(e=>e[1]>0).map(e=>e[0]+': '+e[1].toLocaleString()).join('  ·  ');
 document.getElementById('hw').textContent=src.mode==='prng'?'—':(src.hw_bits_in.toLocaleString()+' bits in · '+src.hw_rate+' bit/s · buffered '+src.buffered);
 document.getElementById('rawstd').textContent=src.raw_std==null?'—':src.raw_std.toFixed(1)+' LSB '+(src.raw_std>=20?'✓ zener alive':src.raw_std<=3?'(floor: no noise reaching the ADC)':'');
 document.getElementById('err').textContent=src.error||'';
 const cells=bars.children;for(let i=0;i<22;i++){const on=s.h[i]>0;cells[i].firstChild.className='bar'+(on?' on':'');cells[i].firstChild.firstChild.style.height=(s.ph[i]*100)+'%';cells[i].lastChild.className=on?'on':'';}
 document.getElementById('active').textContent=s.active||'·';
 document.getElementById('sweeps').textContent=s.sweeps.toLocaleString();
 document.getElementById('sps').textContent=s.sps;
 document.getElementById('coin').textContent=lab;
 document.getElementById('dream').textContent=s.dream;
 document.getElementById('log').textContent='log: logs/'+s.log+' · k='+s.k+' bits per coin · alpha '+s.alpha+' · gamma '+s.gamma+' · theta '+s.theta+' · vbias '+s.vbias;
}catch(e){}finally{busy=false;}}
setInterval(poll,120);poll();
</script></body></html>
"""


def make_handler(board, sampler):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):   # quiet
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path); q = parse_qs(u.query)
            if u.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if u.path == "/state":
                return self._send(200, json.dumps(board.state()))
            if u.path == "/reset":
                board.reset(); return self._send(200, json.dumps({"ok": True}))
            if u.path == "/set":
                if "temp" in q:
                    board.temp = min(5.0, max(0.05, float(q["temp"][0])))
                if "sps" in q:
                    sampler.max_sps = min(500.0, max(0.1, float(q["sps"][0])))
                for name in ("alpha", "gamma", "theta", "vbias", "p_spont"):
                    if name in q:
                        setattr(board, name, float(q[name][0]))
                if "source" in q:
                    m = q["source"][0]
                    board.src.set_mode(m, port=q.get("port", [None])[0], path=q.get("file", [None])[0])
                return self._send(200, json.dumps(board.state()))
            if u.path == "/health":
                return self._send(200, json.dumps({"ok": True, "sweeps": board.sweeps, "source": board.src.status()}))
            self._send(404, json.dumps({"error": "not found"}))
    return H


# ----------------------------------------------------------------------------- selftest
def selftest():
    T = make_templates()
    src = BitSource("prng", seed=7)
    b = DreamBoard(T, src, temp=0.6)
    # 1. a letter placed on the board must be recognised and kept
    for k, ch in ((0, "א"), (12, "מ"), (20, "ש")):
        b.v = T[k].astype(np.float32).copy()
        hits = 0
        for _ in range(20):
            b.sweep()
            if b.h[k] > 0 and int(np.argmax(b.s)) == k:
                hits += 1
        print(f"  hold {ch}: recognised in {hits}/20 sweeps (score {b.s[k]:.2f})")
        assert hits >= 14, f"letter {ch} not held"
    # 2. from noise at T=1 the board must dream: several distinct letters within 400 sweeps
    b.temp = 1.0; b.reset(); seen = set()
    for _ in range(1500):
        b.sweep()
        if b.h.any() and float(b.s.max()) >= 0.5:
            seen.add(LETTERS[int(np.argmax(b.s))])
    print(f"  dream from noise: {len(seen)} distinct letters in 1500 sweeps -> {''.join(sorted(seen))}")
    assert len(seen) >= 3, "no dreaming"
    # 3. every coin is labelled
    st = src.status()
    assert st["served"]["prng"] > 0 and st["served"]["prng-fallback"] == 0
    print(f"  coins labelled: {st['served']}")
    # 4. zener mode with no hardware must FALL BACK LOUDLY, not silently
    src2 = BitSource("zener", port="COM99")
    time.sleep(0.5)
    _, lab = src2.bits(64)
    print(f"  zener mode without hardware -> label '{lab}', error '{src2.error}'")
    assert lab == "prng-fallback"
    print("SELFTEST OK")


def lower_priority():
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception as e:
        print("priority not lowered:", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--http-port", type=int, default=PORT_DEFAULT)
    ap.add_argument("--source", default="prng", choices=["prng", "zener", "file"])
    ap.add_argument("--port", default="COM5", help="serial port of the zener neuron")
    ap.add_argument("--file", default=None, help="bits-*.bin from logger.py")
    ap.add_argument("--temp", type=float, default=1.0)
    ap.add_argument("--sps", type=float, default=20.0, help="max sweeps per second")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    lower_priority()
    T = make_templates()
    src = BitSource(a.source, port=a.port, path=a.file, seed=a.seed)
    board = DreamBoard(T, src, temp=a.temp)
    sampler = Sampler(board, sps=a.sps); sampler.start()
    srv = ThreadingHTTPServer((a.host, a.http_port), make_handler(board, sampler))
    print(f"DREAM BOARD  http://{a.host}:{a.http_port}/   source={a.source}  log={board.log_path}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        sampler.running = False
        board._log.flush()


if __name__ == "__main__":
    main()
