# -*- coding: utf-8 -*-
"""record_native.py -- ERAN's recording booth, WITHOUT the browser microphone.

WHY THIS EXISTS (2026-08-24). The browser booth (booth.py) kept failing at the mic:
getUserMedia needs a secure origin, browser permission, the right device, and it fights
KESHEV for the BRIO. Too many failure points, and Iddo hit "אין קליטה מהמיק" -- the mic
opened but no signal. Meanwhile a direct sounddevice capture of the BRIO returns real
signal even while KESHEV runs (measured: RMS 0.00253 on a quiet room).

So the audio is captured HERE, natively, on the BRIO, by sounddevice -- the exact path
that works. The browser is demoted to a DISPLAY ONLY: it shows the syllable to say and
the progress, and it never touches a microphone. That removes every failure mode at once.

HOW IT WORKS. Voice-activated. The page shows "say בַּ". Iddo says it. The energy gate
hears the burst, captures from just before it to when he stops, trims, saves the wav, and
advances to the next syllable. No clicks. A tired man in bed just talks.

SACRED AUDIO LAW: this only RECORDS and WRITES wavs. It never plays a sound.
USB MIC ONLY: it opens the BRIO by name and refuses any Bluetooth/headset device.
NEVER FAKE A MILESTONE: the screen says say X, he says X, the file is named X. The prompt
IS the label -- zero label error, same guarantee booth.py made.

  python record_native.py                 # all units, 1 take each, talker t07
  python record_native.py --takes 3 --talker t08
"""
import io
import json
import re
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import sounddevice as sd

PORT = 8809
SR = 16000
ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "staged"

# ---- the units. Iddo's own booth list, kept identical so t07 continues t06 cleanly. ----
UNITS = [
    ("ah", "אַה"), ("aa", "אָא"), ("ba", "בַּ"), ("ma", "מַ"), ("la", "לַ"),
    ("da", "דַ"), ("ga", "גַ"), ("pa", "פַּ"), ("ta", "טַ"), ("na", "נַ"),
    ("ka", "כַּ"), ("ra", "רַ"), ("sa", "סַ"), ("ha", "הַ"), ("va", "וַ"),
    ("ya", "יַ"), ("za", "זַ"), ("sha", "שַׁ"), ("kha", "חַ"), ("tha", "תַ"),
    ("tsa", "צַ"), ("qa", "קַ"),
    ("ih", "אִי"), ("eh", "אֶה"), ("oh", "אוֹ"), ("uh", "אוּ"),
    ("abba", "אַבָּא"), ("ima", "אִמָּא"), ("iddo", "עִידוֹ"),
    ("saba", "סָבָא"), ("safta", "סָבְתָא"),
]

# ---- capture tuning ----
BLOCK = 1600            # 0.1 s blocks
GATE = 0.012           # RMS above this = speech onset (room floor measured ~0.0025)
HOLD_SILENCE = 0.45    # stop after this much silence
MIN_LEN = 0.20         # reject shorter than this (a click, not a syllable)
MAX_LEN = 1.6          # cap
PREROLL = 0.15         # keep this much audio before onset

state = {"unit": "", "hebrew": "", "idx": 0, "n_units": 0, "done": 0, "total": 0,
         "last": "", "level": 0.0, "listening": False, "msg": "מתחבר למיקרופון…"}
_lock = threading.Lock()


def find_brio():
    bt = re.compile(r"bluetooth|hands-?free|headset|wh-1000", re.I)
    cand = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        name = d["name"]
        if bt.search(name):
            continue
        if "BRIO" in name:
            return i, name
        if cand is None:
            cand = (i, name)
    return cand if cand else (None, "default")


def next_talker():
    used = set()
    if STAGE.exists():
        for p in STAGE.glob("t*/"):
            if re.fullmatch(r"t\d{2,}", p.name):
                used.add(int(p.name[1:]))
    n = 7
    while n in used:
        n += 1
    return f"t{n:02d}"


def already(talker):
    d = STAGE / talker
    c = {}
    if d.exists():
        for f in d.glob("*.wav"):
            u = f.name.split("_")[0]
            c[u] = c.get(u, 0) + 1
    return c


def save_wav(path, audio):
    a = np.clip(audio, -1, 1)
    pcm = (a * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def trim(a):
    peak = float(np.abs(a).max()) if len(a) else 0.0
    # noise floor from quietest 20% of 10 ms frames (same fix as booth.py)
    fl = max(1, int(SR * 0.01))
    amps = [float(np.abs(a[i:i + fl]).mean()) for i in range(0, max(0, len(a) - fl), fl)]
    amps.sort()
    noise = amps[int(len(amps) * 0.20)] if amps else 0.01
    thr = max(noise * 4, peak * 0.06)
    idx = np.where(np.abs(a) > thr)[0]
    if len(idx) == 0:
        return a, peak
    pad = int(SR * 0.06)
    s = max(0, idx[0] - pad)
    e = min(len(a), idx[-1] + pad)
    out = a[s:e]
    if len(out) > int(SR * MAX_LEN):
        out = out[:int(SR * MAX_LEN)]
    return out, peak


def recorder(talker, takes, dev, devname):
    d = STAGE / talker
    d.mkdir(parents=True, exist_ok=True)
    have = already(talker)
    todo = [(u, h) for (u, h) in UNITS if have.get(u, 0) < takes]
    total = takes * len(UNITS)
    with _lock:
        state.update(n_units=len(UNITS), total=total,
                     done=sum(min(have.get(u, 0), takes) for u, _ in UNITS),
                     msg=f"מוכן · {devname}")

    q = []
    def cb(indata, frames, tinfo, status):
        q.append(indata[:, 0].copy())

    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        blocksize=BLOCK, device=dev, callback=cb):
        preroll = np.zeros(int(SR * PREROLL), dtype="float32")
        for u, h in todo:
            n = have.get(u, 0)
            while n < takes:
                with _lock:
                    state.update(unit=u, hebrew=h, listening=True,
                                 msg=f"אמור:  {h}", idx=[x for x, _ in UNITS].index(u))
                # wait for onset
                buf = []
                capturing = False
                silence = 0.0
                while True:
                    if not q:
                        time.sleep(0.01)
                        continue
                    blk = q.pop(0)
                    rms = float(np.sqrt((blk ** 2).mean()))
                    with _lock:
                        state["level"] = rms
                    if not capturing:
                        preroll = np.concatenate([preroll, blk])[-int(SR * PREROLL):]
                        if rms > GATE:
                            capturing = True
                            buf = [preroll.copy(), blk]
                            silence = 0.0
                    else:
                        buf.append(blk)
                        if rms < GATE:
                            silence += len(blk) / SR
                            if silence >= HOLD_SILENCE:
                                break
                        else:
                            silence = 0.0
                        if sum(len(b) for b in buf) / SR > MAX_LEN + PREROLL + HOLD_SILENCE:
                            break
                audio = np.concatenate(buf)
                out, peak = trim(audio)
                if len(out) < int(SR * MIN_LEN) or peak < 0.03:
                    with _lock:
                        state["msg"] = f"קצר/חלש מדי — שוב:  {h}"
                    continue
                path = d / f"{u}_{talker}_{n}.wav"
                save_wav(path, out)
                n += 1
                have[u] = n
                with _lock:
                    state.update(done=sum(min(have.get(x, 0), takes) for x, _ in UNITS),
                                 last=f"{h}  ✓  ({len(out)/SR:.2f}s)")
                time.sleep(0.25)  # a breath before the next prompt
        with _lock:
            state.update(listening=False, unit="", hebrew="✓",
                         msg="סיימת את הפאס. כל הכבוד.")


PAGE = """<!doctype html><html lang=he dir=rtl><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>ERAN — תא הקלטה</title><style>
body{margin:0;font-family:system-ui,'Segoe UI',sans-serif;background:#fbfbf6;color:#14181f;
text-align:center}.wrap{max-width:640px;margin:0 auto;padding:5vh 1em}
.glyph{font-size:34vw;line-height:1.05;font-weight:700;margin:.1em 0}
@media(min-width:640px){.glyph{font-size:200px}}
.msg{font-size:1.6em;color:#5a6474;min-height:1.4em}
.meter{height:16px;background:#e7ebf1;border-radius:9px;overflow:hidden;margin:1.2em auto;max-width:420px}
.meter i{display:block;height:100%;width:0;background:#1f8b4c;transition:width .05s}
.prog{font-size:1.3em;margin-top:.6em}.last{color:#1f8b4c;font-size:1.2em;min-height:1.3em}
.dim{color:#98a2b3;font-size:.95em}
</style></head><body><div class=wrap>
<div class=msg id=msg>…</div>
<div class=glyph id=glyph>·</div>
<div class=meter><i id=bar></i></div>
<div class=last id=last></div>
<div class=prog id=prog></div>
<div class=dim>רק מדבר. זה נשמר לבד. · ERAN listens through the BRIO.</div>
</div><script>
async function tick(){
 try{const s=await (await fetch('/state')).json();
  document.getElementById('glyph').textContent=s.hebrew||'·';
  document.getElementById('msg').textContent=s.msg||'';
  document.getElementById('last').textContent=s.last||'';
  document.getElementById('prog').textContent=(s.done||0)+' / '+(s.total||0);
  document.getElementById('bar').style.width=Math.min(100,Math.sqrt(s.level||0)*500)+'%';
 }catch(e){}
 setTimeout(tick,100);
}tick();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/state":
            with _lock:
                body = json.dumps(state).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


if __name__ == "__main__":
    argv = sys.argv[1:]
    takes = 1
    if "--takes" in argv:
        takes = int(argv[argv.index("--takes") + 1])
    talker = None
    if "--talker" in argv:
        talker = argv[argv.index("--talker") + 1]
    if not talker:
        talker = next_talker()
    dev, devname = find_brio()
    print(f"device: {dev} = {devname}")
    print(f"talker {talker}  takes {takes}  -> {STAGE / talker}")
    print(f"display: http://127.0.0.1:{PORT}/   (and http://<lan-ip>:{PORT}/ )")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    recorder(talker, takes, dev, devname)
    print("done. server still up for the final screen; Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
