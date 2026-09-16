# -*- coding: utf-8 -*-
r"""
ahba_recorder.py -- ERAN: Iddo records "אה" and "בא" in his own voice.   Port 8917.

Iddo, 2026-09-11 18:22: "מה אמרנו לגבי אה ו-בה? תן לי להקליט ותן לו להתאמן עליהם".

WHY THE PHONE AND NOT THE PC (measured 2026-09-11 18:3x, not assumed)
  * KESHEV's engine (keshev-next\app\main.py) keeps its BRIO InputStream OPEN while
    PAUSED -- the PAUSED file is only checked inside process_full_segment(), after
    capture. The Windows consent store shows Python312 holding the mic right now.
  * The BRIO is the only real USB microphone on this PC (the Scarlett shows only an
    output endpoint; the rest are the WH-1000XM4 headset, virtual devices and the dead
    USBAudio1.0).
  * So ANY capture on the PC -- a native sounddevice stream, a browser getUserMedia --
    is a second stream on the BRIO while the engine holds it. Forbidden (ONE-MIC).
  * The phone microphone touches nothing on the PC: not the BRIO, not KESHEV, not his
    signed pause, not his audio output.

THE PHONE AUDIO LAW (MISTAKES.md rule 7, the $100 scar of 2026-09-09), obeyed literally
  * the mic is opt-in: a checkbox, OFF by default, and even then the mic opens only
    when he presses "הקלט";
  * getUserMedia({audio:true}) and nothing else (AHBA_RAW_CAPTURE=1 switches to
    ec/ns/agc OFF -- only on Iddo's word, see RECORD-AH-BA-20260911.md);
  * every track is stopped the moment he presses stop -- BEFORE any processing or
    upload -- and on auto-stop (6 s), page hide, and any error;
  * if the opened track is labelled Bluetooth / headset / hands-free it is released at
    once and nothing is kept.

THE PC NEVER RECORDS
  * the page served to a PC browser (a direct 127.0.0.1 request, or one arriving through
    tailscale serve from this PC's own tailnet IP) has no record button at all;
  * /api/save refuses anything that did not come from another tailnet device.
  This server itself never imports sounddevice and never opens an audio device.

THE LABEL LAW (MISTAKES.md rule 6): every take carries its speaker's name --
    food\t09-iddo-ahba\עידו-אה-t09-01.wav     (16 kHz mono 16-bit, trimmed like t06/t07)
    food\t09-iddo-ahba\raw\עידו-אה-t09-01-raw.wav   (untrimmed, the phone's own rate)
    food\t09-iddo-ahba\meta\עידו-אה-t09-01.json     (device label, settings, peak, clip count)
  Nothing is deleted: "מחק אחרון" moves a take to trash\.

PRIVACY: files stay on this PC (git-ignored: *.wav at the root, plus a local .gitignore).
Bound to 127.0.0.1 only; the phone reaches it through `tailscale serve` (tailnet only,
never funnel). No upload anywhere. ERAN-TRAIN-AH-BA.py copies them to the fleet when run.

    python ahba_recorder.py            (normally started by open_ahba_recorder.pyw)
"""
import base64
import ctypes
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))           # ...\eran-brain\booth
BRAIN = os.path.dirname(HERE)                                 # ...\eran-brain

PORT = int(os.environ.get("AHBA_PORT", "8917"))
SESSION = os.environ.get("AHBA_SESSION", "t09")
TARGET = int(os.environ.get("AHBA_TAKES", "20"))
SPEAKER = os.environ.get("AHBA_SPEAKER", "עידו")
TEST_MODE = os.environ.get("AHBA_TEST", "0") == "1"           # scratch instance only
RAW_CAPTURE = os.environ.get("AHBA_RAW_CAPTURE", "0") == "1"
DEFAULT_OUT = os.path.join(BRAIN, "food", "%s-iddo-ahba" % SESSION)
OUT = os.environ.get("AHBA_OUT", DEFAULT_OUT)
TS_HOST = os.environ.get("AHBA_TS_HOST", "<tailnet-host>")
PHONE_URL = "https://%s:%d/" % (TS_HOST, PORT)

UNITS = {"ah": "אה", "ba": "בא"}
HEB2UNIT = {v: k for k, v in UNITS.items()}
SR = 16000
MIN_S, MAX_S = 0.25, 1.5          # trimmed take (booth.py caps at 1.4 s)
RAW_MAX_S = 8.0

NAME_RE = re.compile(r"^(?P<spk>[^-/\\]+)-(?P<heb>אה|בא)-(?P<sess>t\d{2})-(?P<take>\d{2,3})\.wav$")
LOCK = threading.Lock()
LOG_PATH = os.path.join(OUT, "recorder.log")


# ----------------------------------------------------------------------------- setup
def log(msg):
    line = "%s %s" % (datetime.now().isoformat(timespec="seconds"), msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except Exception:
            pass


def below_normal():
    """Nothing on this PC outranks a live human (PC rule)."""
    try:
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)   # BELOW_NORMAL
    except Exception:
        pass


def claim_session():
    """Refuse a session id that anyone else already used; leave a marker so booth.py's
    next_talker() never hands this id out again."""
    if not re.fullmatch(r"t\d{2}", SESSION):
        raise SystemExit("bad session id %r (expected t09, t10, ...)" % SESSION)
    if TEST_MODE or os.path.abspath(OUT) != os.path.abspath(DEFAULT_OUT):
        return
    staged = os.path.join(HERE, "staged", SESSION)
    marker = os.path.join(staged, "CLAIMED-BY-ahba_recorder.txt")
    if os.path.isdir(staged) and not os.path.exists(marker):
        raise SystemExit("REFUSING: session %s already exists in booth\\staged -- pick another "
                         "id with AHBA_SESSION" % SESSION)
    if os.path.exists(os.path.join(HERE, SESSION + "-raw")):
        raise SystemExit("REFUSING: booth\\%s-raw exists -- that id was started on another day"
                         % SESSION)
    train = os.path.join(BRAIN, "food", "train")
    if os.path.isdir(train) and any(("_%s_" % SESSION) in n for n in os.listdir(train)):
        raise SystemExit("REFUSING: food\\train already has %s files" % SESSION)
    os.makedirs(staged, exist_ok=True)
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf-8") as f:
            f.write("Session %s is CLAIMED (2026-09-11) by ahba_recorder.py: Iddo's own 'ah' and "
                    "'ba' takes.\nThe takes live in eran-brain\\food\\%s-iddo-ahba\\ -- NOT here.\n"
                    "This folder exists only so booth.py never hands out %s again.\n"
                    % (SESSION, SESSION, SESSION))


def own_tailnet_ips():
    ips = set()
    try:
        r = subprocess.run(["tailscale", "ip"], capture_output=True, text=True, timeout=6,
                           creationflags=0x08000000)
        ips = {x.strip() for x in r.stdout.split() if x.strip()}
    except Exception:
        pass
    return ips


OWN_IPS = set()


def origin_of(handler):
    """'phone' = another tailnet device through tailscale serve; 'pc' = this PC."""
    if TEST_MODE and (handler.headers.get("X-Ahba-Test-Origin") == "phone"
                      or "as=phone" in (urlparse(handler.path).query or "")):
        return "phone"                  # scratch test instance only (AHBA_TEST=1)
    xff = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if not xff:
        return "pc"                     # a direct 127.0.0.1 request is this PC
    if xff in OWN_IPS or xff.startswith("127."):
        return "pc"
    return "phone"


# ----------------------------------------------------------------------------- takes
def take_files(unit=None):
    rows = []
    if not os.path.isdir(OUT):
        return rows
    for n in os.listdir(OUT):
        m = NAME_RE.match(n)
        if not m or m.group("sess") != SESSION:
            continue
        u = HEB2UNIT[m.group("heb")]
        if unit and u != unit:
            continue
        rows.append((u, int(m.group("take")), n))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def wav_info(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def state():
    rows = take_files()
    counts = {u: sum(1 for r in rows if r[0] == u) for u in UNITS}
    takes = []
    for u, t, n in sorted(rows, key=lambda r: os.path.getmtime(os.path.join(OUT, r[2])),
                          reverse=True):
        meta = {}
        mp = os.path.join(OUT, "meta", n[:-4] + ".json")
        if os.path.exists(mp):
            try:
                with open(mp, encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                meta = {}
        takes.append({"name": n, "unit": u, "take": t,
                      "seconds": round(wav_info(os.path.join(OUT, n)), 3),
                      "peak": meta.get("peak_raw"), "device": meta.get("track_label")})
    return {"app": "ahba-recorder", "session": SESSION, "speaker": SPEAKER, "target": TARGET,
            "counts": counts, "takes": takes, "out": OUT, "phone_url": PHONE_URL}


def check_wav(data, want_rate=None, min_s=None, max_s=None):
    with wave.open(io.BytesIO(data), "rb") as w:
        ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    if ch != 1 or sw != 2:
        raise ValueError("wav must be mono 16-bit (got %d ch, %d bytes)" % (ch, sw))
    if want_rate and rate != want_rate:
        raise ValueError("wav rate %d != %d" % (rate, want_rate))
    secs = n / float(rate)
    if min_s is not None and secs < min_s:
        raise ValueError("take too short (%.2f s)" % secs)
    if max_s is not None and secs > max_s:
        raise ValueError("take too long (%.2f s)" % secs)
    return rate, secs


def atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def save_take(body):
    unit = body.get("unit")
    if unit not in UNITS:
        raise ValueError("unit must be ah or ba")
    wav16 = base64.b64decode(body.get("wav16") or "")
    raw = base64.b64decode(body.get("raw") or "")
    _, secs = check_wav(wav16, want_rate=SR, min_s=MIN_S, max_s=MAX_S)
    raw_rate, raw_secs = check_wav(raw, min_s=0.2, max_s=RAW_MAX_S)
    if not (8000 <= raw_rate <= 96000):
        raise ValueError("raw rate %d out of range" % raw_rate)
    with LOCK:
        taken = [t for _, t, _ in take_files(unit)]
        take = (max(taken) + 1) if taken else 1
        name = "%s-%s-%s-%02d.wav" % (SPEAKER, UNITS[unit], SESSION, take)
        atomic_write(os.path.join(OUT, name), wav16)
        atomic_write(os.path.join(OUT, "raw", name[:-4] + "-raw.wav"), raw)
        meta = dict(body.get("meta") or {})
        meta.update({"name": name, "speaker": SPEAKER, "unit": unit, "heb": UNITS[unit],
                     "session": SESSION, "take": take, "seconds": round(secs, 4),
                     "raw_rate": raw_rate, "raw_seconds": round(raw_secs, 4),
                     "saved": datetime.now().isoformat(timespec="seconds"),
                     "generator": "ahba_recorder.py (phone getUserMedia -> AudioWorklet PCM -> "
                                  "OfflineAudioContext 16 kHz -> booth.py trim)"})
        atomic_write(os.path.join(OUT, "meta", name[:-4] + ".json"),
                     json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
        with open(os.path.join(OUT, "MANIFEST.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": "save", "name": name, "unit": unit, "take": take,
                                "seconds": round(secs, 4), "at": meta["saved"]},
                               ensure_ascii=False) + "\n")
    return name


def undo_take(unit):
    if unit not in UNITS:
        raise ValueError("unit must be ah or ba")
    with LOCK:
        rows = take_files(unit)
        if not rows:
            raise ValueError("no take to remove")
        _, take, name = rows[-1]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        trash = os.path.join(OUT, "trash")
        os.makedirs(trash, exist_ok=True)
        moves = [(os.path.join(OUT, name), os.path.join(trash, "%s-%s" % (stamp, name))),
                 (os.path.join(OUT, "raw", name[:-4] + "-raw.wav"),
                  os.path.join(trash, "%s-%s-raw.wav" % (stamp, name[:-4]))),
                 (os.path.join(OUT, "meta", name[:-4] + ".json"),
                  os.path.join(trash, "%s-%s.json" % (stamp, name[:-4])))]
        for a, b in moves:
            if os.path.exists(a):
                os.replace(a, b)
        with open(os.path.join(OUT, "MANIFEST.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": "trash", "name": name, "unit": unit, "take": take,
                                "at": datetime.now().isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
    return name


def qr_svg():
    try:
        import segno
        buf = io.BytesIO()
        segno.make(PHONE_URL, error="m").save(buf, kind="svg", scale=7, border=2,
                                              dark="#1f2a1c", light="#ffffff")
        return buf.getvalue()
    except Exception as e:
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="40">'
                '<text x="4" y="24">QR unavailable: %s</text></svg>' % type(e).__name__).encode()


# ----------------------------------------------------------------------------- page
PAGE = r"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ערן · הקלטת אה ובא</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#fbfaf5;color:#1f2a1c;font-family:"Assistant","Segoe UI",Arial,sans-serif;
      padding:16px 14px 60px;line-height:1.5;max-width:640px;margin:0 auto}
 h1{font-size:23px} h2{font-size:18px;margin-bottom:6px}
 .sub{color:#66705f;font-size:13.5px;margin:2px 0 14px}
 .card{background:#fff;border:1px solid #e1dccb;border-radius:14px;padding:14px 16px;margin-bottom:12px}
 .warn{background:#fff7e6;border-color:#f0d9a6;font-size:14.5px}
 .qr{display:block;width:230px;height:230px;margin:10px auto}
 .url{direction:ltr;text-align:center;font-family:Consolas,monospace;font-size:14px;word-break:break-all}
 .consent{display:flex;gap:10px;align-items:center;font-size:17px;padding:12px 4px}
 .consent input{width:26px;height:26px}
 .tabs{display:flex;gap:10px;margin:6px 0}
 .tab{flex:1;font:inherit;font-size:22px;padding:12px 0;border-radius:12px;border:2px solid #cfc8b3;
      background:#fff;color:inherit;cursor:pointer}
 .tab.sel{border-color:#2e6b45;background:#e7f2ea;font-weight:700}
 .tab b{display:block;font-size:15px;font-weight:600;color:#2e6b45}
 .glyph{font-size:96px;text-align:center;font-weight:700;line-height:1.2;margin:4px 0}
 .meter{height:18px;border-radius:9px;background:#ece8dc;overflow:hidden;margin:8px 0}
 .meter div{height:100%;width:0;background:#4f9a66;transition:width .06s}
 .meter div.warm{background:#d8a13a} .meter div.hot{background:#c0392b}
 .clip{color:#fff;background:#c0392b;text-align:center;border-radius:8px;padding:4px;font-weight:700}
 .rec{display:block;width:100%;font:inherit;font-size:26px;padding:22px 0;border-radius:18px;border:none;
      background:#2e6b45;color:#fff;cursor:pointer;margin:10px 0}
 .rec.on{background:#c0392b} .rec:disabled{background:#a9b5a4;cursor:default}
 .msg{min-height:48px;font-size:16px;padding:6px 2px}
 .msg.bad{color:#b03a2e;font-weight:600} .msg.ok{color:#2e6b45;font-weight:600}
 .row{display:flex;gap:10px} .row button{flex:1;font:inherit;font-size:16px;padding:12px 0;border-radius:11px;
      border:1px solid #cfc8b3;background:#fff;color:inherit;cursor:pointer}
 .row button:disabled{opacity:.45}
 audio{width:100%;margin-top:10px}
 .t{display:flex;gap:8px;align-items:center;border-top:1px solid #eee8d8;padding:7px 0;font-size:14px}
 .t .n{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .t button{font:inherit;padding:6px 12px;border-radius:9px;border:1px solid #cfc8b3;background:#fff;cursor:pointer}
 .big{font-size:20px;font-weight:700}
</style></head><body>
<h1>ערן · הקלטת אה ובא</h1>
<div class="sub">ישיבה <b id="sess"></b> · הקול שלך יהיה הרפרנס של ערן · נשמר רק במחשב ובצי</div>

<section id="pc" hidden>
 <div class="card">
  <h2>מקליטים מהטלפון</h2>
  <p>במחשב, קשב מחזיק את מיקרופון הבריו, גם כשהוא מושהה. זרם שני על אותו מיקרופון אסור, ולכן במחשב אין כאן כפתור הקלטה.</p>
  <p style="margin-top:8px">סרוק עם הטלפון:</p>
  <img class="qr" src="/qr.svg" alt="QR">
  <div class="url" id="purl"></div>
 </div>
</section>

<section id="phone" hidden>
 <div class="card warn">🎧 אוזניות בלוטות׳ מחוברות לטלפון? נתק אותן לפני שמקליטים. אחרת המוזיקה יורדת לאיכות טלפון, וההקלטה נפסלת.
 המיקרופון נפתח רק כשאתה לוחץ <b>הקלט</b>, ונסגר ברגע שאתה לוחץ <b>עצור</b>.</div>
 <label class="consent"><input type="checkbox" id="micok"> מותר לפתוח את מיקרופון הטלפון להקלטה הזו</label>
 <div class="tabs">
  <button class="tab sel" data-u="ah">אה <b id="c-ah">0/20</b></button>
  <button class="tab" data-u="ba">בא <b id="c-ba">0/20</b></button>
 </div>
 <div class="glyph" id="glyph">אה</div>
 <div class="meter"><div id="bar"></div></div>
 <div class="clip" id="clipflag" hidden>חתוך! חזק מדי</div>
 <button class="rec" id="rec" disabled>● הקלט</button>
 <div class="msg" id="msg">סמן את התיבה. לחץ הקלט, אמור את ההברה פעם אחת, לחץ עצור.</div>
 <div class="row"><button id="play" disabled>▶ שמע את האחרון</button><button id="undo" disabled>🗑 מחק אחרון</button></div>
</section>

<section class="card">
 <h2>הטייקים <span class="big" id="tot"></span></h2>
 <audio id="aud" controls preload="none" hidden></audio>
 <div id="list"></div>
</section>

<script>
const CFG = __CFG__;
const $ = id => document.getElementById(id);
const IS_PHONE_UA = /Android|iPhone|iPad|Mobile|Quest|OculusBrowser/i.test(navigator.userAgent);
const CAN_RECORD = IS_PHONE_UA && CFG.origin === "phone";
window.__micOpens = 0;             // the page-load test asserts this stays 0
let unit = "ah", busy = false, recording = false, lastName = null, lastUnit = null;
let stream = null, ctx = null, src = null, node = null, mute = null, chunks = [];
let peakAll = 0, clipN = 0, autoStop = null, trackInfo = {};

$("sess").textContent = CFG.session;
$("purl").textContent = CFG.phone_url;
$(CAN_RECORD ? "phone" : "pc").hidden = false;

function msg(t, cls){ $("msg").textContent = t; $("msg").className = "msg" + (cls ? " " + cls : ""); }
function isBad(label){ return /bluetooth|hands-?free|headset|\bsco\b|wh-1000|buds|airpods|אוזני/i.test(label || ""); }

// Every track, every time. A live track is an open microphone, and on Android that is
// his music in telephone quality (2026-09-09, $100).
function release(){
  if (autoStop){ clearTimeout(autoStop); autoStop = null; }
  if (stream){ try { stream.getTracks().forEach(t => t.stop()); } catch(e){} }
  stream = null;
  try { if (src) src.disconnect(); if (node) node.disconnect(); if (mute) mute.disconnect(); } catch(e){}
  src = node = mute = null;
  if (ctx){ const c = ctx; ctx = null; c.close().catch(() => {}); }
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden && (recording || stream)){ recording = false; release(); setRecBtn(); msg("העמוד הוסתר, ההקלטה בוטלה והמיקרופון נסגר."); }
});
window.addEventListener("pagehide", release);

function setRecBtn(){
  $("rec").textContent = recording ? "■ עצור" : "● הקלט";
  $("rec").classList.toggle("on", recording);
  $("rec").disabled = !$("micok").checked || busy;
}
$("micok").checked = false;
$("micok").onchange = setRecBtn;

document.querySelectorAll(".tab").forEach(b => b.onclick = () => {
  if (recording || busy) return;
  unit = b.dataset.u;
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("sel", x === b));
  $("glyph").textContent = CFG.heb[unit];
});

const WORKLET = "class Cap extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('cap',Cap);";

function onChunk(f32){
  chunks.push(f32);
  let pk = 0, s = 0;
  for (let i = 0; i < f32.length; i++){ const a = Math.abs(f32[i]); if (a > pk) pk = a; s += f32[i]*f32[i]; if (a >= 0.99) clipN++; }
  if (pk > peakAll) peakAll = pk;
  const db = 20*Math.log10(Math.sqrt(s/Math.max(1, f32.length)) + 1e-9);
  $("bar").style.width = Math.max(0, Math.min(100, (db + 60)/60*100)) + "%";
  $("bar").className = pk >= 0.99 ? "hot" : (pk >= 0.7 ? "warm" : "");
  if (clipN > 0) $("clipflag").hidden = false;
}

async function startTake(){
  if (!CAN_RECORD || busy || recording || !$("micok").checked) return;
  busy = true; setRecBtn(); chunks = []; peakAll = 0; clipN = 0; $("clipflag").hidden = true;
  try {
    const constraints = CFG.raw_capture
      ? {audio:{echoCancellation:false, noiseSuppression:false, autoGainControl:false}}
      : {audio:true};
    window.__micOpens++;
    stream = await navigator.mediaDevices.getUserMedia(constraints);
    const tr = stream.getAudioTracks()[0];
    trackInfo = {label: tr ? tr.label : "", settings: (tr && tr.getSettings) ? tr.getSettings() : {}};
    if (isBad(trackInfo.label)){
      release(); msg("⛔ נפתח מיקרופון של אוזניות (" + trackInfo.label + "). נתק את הבלוטות׳ ונסה שוב. לא הוקלט.", "bad"); return;
    }
    ctx = new AudioContext();
    src = ctx.createMediaStreamSource(stream);
    mute = ctx.createGain(); mute.gain.value = 0;
    if (ctx.audioWorklet){
      await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], {type:"application/javascript"})));
      node = new AudioWorkletNode(ctx, "cap");
      node.port.onmessage = e => { if (recording) onChunk(e.data); };
    } else {
      node = ctx.createScriptProcessor(4096, 1, 1);
      node.onaudioprocess = e => { if (recording) onChunk(new Float32Array(e.inputBuffer.getChannelData(0))); };
    }
    src.connect(node); node.connect(mute); mute.connect(ctx.destination);
    recording = true;
    msg("🔴 מקליט. אמור \"" + CFG.heb[unit] + "\" ולחץ עצור.");
    autoStop = setTimeout(stopTake, 6000);
  } catch(e){
    release(); msg("אין גישה למיקרופון: " + e, "bad");
  } finally { busy = false; setRecBtn(); }
}

async function stopTake(){
  if (!recording) return;
  recording = false;
  const rate = ctx ? ctx.sampleRate : 48000;
  release();                                   // the microphone goes back NOW
  setRecBtn(); $("bar").style.width = "0%";
  const n = chunks.reduce((a, c) => a + c.length, 0);
  const raw = new Float32Array(n); let o = 0; for (const c of chunks){ raw.set(c, o); o += c.length; }
  chunks = [];
  if (n < rate*0.25){ msg("⏱️ קצר מדי. נסה שוב."); return; }
  if (clipN > 0 || peakAll >= 0.99){ msg("📢 חתוך (" + clipN + " דגימות בתקרה). לא נשמר. הרחק קצת את הטלפון או דבר חלש יותר, ונסה שוב.", "bad"); return; }
  if (peakAll < 0.03){ msg("🔇 שקט מדי. לא נשמר. קרב את הטלפון ונסה שוב.", "bad"); return; }
  busy = true; setRecBtn(); msg("שומר…");
  try {
    const off = new OfflineAudioContext(1, Math.ceil(n/rate*16000), 16000);   // no device is opened
    const buf = off.createBuffer(1, n, rate); buf.copyToChannel(raw, 0);
    const s = off.createBufferSource(); s.buffer = buf; s.connect(off.destination); s.start();
    const r16 = (await off.startRendering()).getChannelData(0);
    const t = trim(r16, 16000);
    if (t.out.length < 16000*0.25){ msg("⏱️ אחרי חיתוך השקט נשאר פחות מרבע שנייה. נסה שוב."); return; }
    const body = {unit, wav16: await b64(toWav(t.out, 16000)), raw: await b64(toWav(raw, rate)),
      meta: {track_label: trackInfo.label, track_settings: trackInfo.settings, ua: navigator.userAgent,
             constraints: CFG.raw_capture ? "ec/ns/agc OFF" : "{audio:true}", context_rate: rate,
             peak_raw: +peakAll.toFixed(4), clip_samples: clipN, noise_floor: +t.noise.toFixed(5),
             client_time: new Date().toISOString()}};
    const r = await fetch("/api/save", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
    const j = await r.json().catch(() => ({error:"bad reply"}));
    if (!r.ok){ msg("שמירה נכשלה: " + (j.error || r.status), "bad"); return; }
    lastName = j.name; lastUnit = unit; $("play").disabled = false; $("undo").disabled = false;
    msg("✓ נשמר " + j.name + " (" + (t.out.length/16000).toFixed(2) + " שנ׳)", "ok");
    await refresh();
  } catch(e){ msg("שגיאה: " + e, "bad"); }
  finally { busy = false; setRecBtn(); }
}
$("rec").onclick = () => recording ? stopTake() : startTake();

function b64(blob){ return new Promise(res => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(",")[1]); fr.readAsDataURL(blob); }); }

function toWav(f32, sr){
  const n = f32.length, b = new ArrayBuffer(44 + n*2), v = new DataView(b);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0,"RIFF"); v.setUint32(4, 36 + n*2, true); w(8,"WAVEfmt "); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true);
  v.setUint32(28, sr*2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36,"data"); v.setUint32(40, n*2, true);
  for (let i = 0; i < n; i++){ const s = Math.max(-1, Math.min(1, f32[i])); v.setInt16(44 + i*2, s < 0 ? s*0x8000 : s*0x7fff, true); }
  return new Blob([b], {type:"audio/wav"});
}

// booth.py trim(), VERBATIM (fix of 2026-08-24), so t09 is cut exactly like t06 and t07.
function trim(f32, sr){
  let peak = 0; for (const v of f32) peak = Math.max(peak, Math.abs(v));
  const fl = Math.max(1, Math.round(sr*0.01)), amps = [];
  for (let i = 0; i + fl <= f32.length; i += fl){ let s = 0; for (let j = i; j < i + fl; j++) s += Math.abs(f32[j]); amps.push(s/fl); }
  amps.sort((x, y) => x - y);
  const noise = amps.length ? amps[Math.floor(amps.length*0.20)] : 0.01;
  const thr = Math.max(noise*4, peak*0.06), pad = Math.round(sr*0.06);
  let a = 0, b = f32.length - 1;
  while (a < f32.length && Math.abs(f32[a]) < thr) a++;
  while (b > a && Math.abs(f32[b]) < thr) b--;
  if (a >= b){ const t2 = peak*0.10; a = 0; b = f32.length - 1;
    while (a < f32.length && Math.abs(f32[a]) < t2) a++;
    while (b > a && Math.abs(f32[b]) < t2) b--; }
  a = Math.max(0, a - pad); b = Math.min(f32.length - 1, b + pad);
  let out = f32.slice(a, b + 1);
  const max = Math.round(sr*1.4);
  if (out.length > max) out = out.slice(0, max);
  return {out, peak, noise};
}

function play(name){
  const a = $("aud"); a.hidden = false;
  a.src = "/take/" + encodeURIComponent(name) + "?t=" + Date.now();
  a.play().catch(() => {});
}
$("play").onclick = () => { if (lastName) play(lastName); };
$("undo").onclick = async () => {
  const u = lastUnit || unit;
  if (!confirm("להעביר לפח את הטייק האחרון של " + CFG.heb[u] + "?")) return;
  const r = await fetch("/api/undo", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({unit:u})});
  const j = await r.json().catch(() => ({}));
  msg(r.ok ? ("🗑 הועבר לפח: " + j.name) : ("לא הצליח: " + (j.error || r.status)), r.ok ? "" : "bad");
  lastName = null; $("play").disabled = true; $("undo").disabled = true;
  refresh();
};

async function refresh(){
  const r = await fetch("/api/state", {cache:"no-store"}); const s = await r.json();
  for (const u of ["ah", "ba"]) $("c-" + u).textContent = s.counts[u] + "/" + s.target;
  $("tot").textContent = "· אה " + s.counts.ah + "/" + s.target + " · בא " + s.counts.ba + "/" + s.target;
  const L = $("list"); L.innerHTML = "";
  for (const t of s.takes){
    const d = document.createElement("div"); d.className = "t";
    d.innerHTML = '<span class="n"></span><span></span><button>▶</button>';
    d.children[0].textContent = t.name; d.children[1].textContent = t.seconds.toFixed(2) + " שנ׳";
    d.children[2].onclick = () => play(t.name);
    L.appendChild(d);
  }
  if (!s.takes.length) L.textContent = "עוד אין טייקים.";
}
refresh();
</script></body></html>"""


# ----------------------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    server_version = "ahba-recorder"

    def log_message(self, fmt, *args):      # pythonw has no stderr
        log("%s %s" % (self.headers.get("X-Forwarded-For") or self.client_address[0], fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            cfg = {"session": SESSION, "target": TARGET, "heb": UNITS, "phone_url": PHONE_URL,
                   "raw_capture": RAW_CAPTURE, "origin": origin_of(self)}
            page = PAGE.replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
            return self._send(200, page, "text/html; charset=utf-8")
        if p == "/api/state":
            return self._send(200, state())
        if p == "/qr.svg":
            return self._send(200, qr_svg(), "image/svg+xml")
        if p.startswith("/take/"):
            name = unquote(p[len("/take/"):])
            m = NAME_RE.match(name)
            fp = os.path.join(OUT, name)
            if m and os.path.isfile(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "audio/wav")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        if n > 8_000_000:
            return self._send(413, {"error": "too large"})
        try:
            body = json.loads((self.rfile.read(n) if n else b"{}").decode("utf-8"))
        except ValueError:
            return self._send(400, {"error": "bad json"})
        try:
            if p == "/api/save":
                if origin_of(self) != "phone":
                    log("REFUSED save from the PC (ONE-MIC: the BRIO belongs to KESHEV)")
                    return self._send(403, {"error": "recording from the PC is locked -- use the phone"})
                name = save_take(body)
                log("saved %s" % name)
                return self._send(200, {"name": name, "counts": state()["counts"]})
            if p == "/api/undo":
                name = undo_take(body.get("unit"))
                log("trashed %s" % name)
                return self._send(200, {"name": name})
        except (ValueError, wave.Error) as e:
            return self._send(400, {"error": str(e)})
        return self._send(404, {"error": "not found"})


class Server(ThreadingHTTPServer):
    allow_reuse_address = False          # Windows SO_REUSEADDR lets a second process steal a port
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    global OWN_IPS
    below_normal()
    claim_session()
    os.makedirs(OUT, exist_ok=True)
    gi = os.path.join(OUT, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write("# Iddo's voice never enters git.\n*\n")
    OWN_IPS = own_tailnet_ips()
    httpd = Server(("127.0.0.1", PORT), Handler)
    log("ahba-recorder up on 127.0.0.1:%d  session=%s  out=%s  own_tailnet=%s  test=%s  raw_capture=%s"
        % (PORT, SESSION, OUT, sorted(OWN_IPS), TEST_MODE, RAW_CAPTURE))
    httpd.serve_forever()


if __name__ == "__main__":
    main()
