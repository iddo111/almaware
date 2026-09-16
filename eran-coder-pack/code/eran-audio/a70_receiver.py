#!/usr/bin/env python3
"""A70 audio relay receiver for project ERAN (the "room-ear").

Turns Iddo's Samsung Galaxy A70 into an always-on microphone that streams audio
to this PC. The phone opens http://<lan-ip>:18190/ in Chrome (the recorder
PWA is served by GET /), taps START, and the page POSTs ~10s audio chunks to
POST /audio. Each chunk is transcoded to 16 kHz mono WAV with ffmpeg and dropped
into D:\\CLAUDE\\eran-audio\\heard_a70\\, which is on Eran's extra_audio_dirs list,
so the cochlea/data.py picks it up automatically as part of his "heard world".

This is a SEPARATE server from dispatch-fix/pc-listener.py (port 18180). It does
NOT touch that, the Hebrew mic, or any GPU. Pure stdlib + ffmpeg subprocess.

Run with the SAME interpreter the mic uses, sandbox-safe:
  C:\\Users\\iddo1\\AppData\\Local\\Programs\\Python\\Python312\\python.exe -s a70_receiver.py

Endpoints:
  GET  /ping   -> "pong"
  GET  /       -> the recorder PWA HTML (START/STOP, chunk counter)
  GET  /health -> JSON {ok, saved, last, ffmpeg}
  POST /audio  -> body = webm/opus or wav blob; saved as 16k mono wav

Per Iddo's conventions: no emoji in code/logs, ASCII output, defensive, never crash.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
ROOT = pathlib.Path(r"D:\CLAUDE\eran-audio")
HEARD = ROOT / "heard_a70"
HEARD.mkdir(parents=True, exist_ok=True)
LOG_PATH = ROOT / "a70_receiver.log"

PORT = int(os.environ.get("A70_PORT", "18190"))
BIND = os.environ.get("A70_BIND", "0.0.0.0")  # LAN-reachable for the phone

FFMPEG = os.environ.get(
    "A70_FFMPEG",
    r"C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe",
)
# Fall back to ffmpeg on PATH if the pinned build moves.
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
MAX_BODY = 50 * 1024 * 1024  # 50 MB hard cap per chunk (a 10s opus chunk is ~100 KB)

# in-process counters (best-effort, for /health and status)
_lock = threading.Lock()
_state = {"saved": 0, "rejected": 0, "last": ""}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [a70-receiver] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("a70-receiver")


def ts_name() -> str:
    """a70_YYYYMMDD_HHMMSS_microsec.wav"""
    now = dt.datetime.now()
    return "a70_{}_{:06d}.wav".format(now.strftime("%Y%m%d_%H%M%S"), now.microsecond)


def transcode_to_wav(raw: bytes, out_path: pathlib.Path) -> tuple[bool, str]:
    """Decode an arbitrary audio blob (webm/opus, ogg, mp4, wav...) and write a
    16 kHz mono PCM s16 WAV. ffmpeg sniffs the input format itself ('-' stdin).
    Retries 3x on decode errors. Returns (ok, detail)."""
    tmp = None
    try:
        # Validate: reject obviously corrupted blobs (<44 bytes = empty, or very large)
        if len(raw) < 44:
            return False, "input too small ({}B, min 44B)".format(len(raw))
        if len(raw) > 100 * 1024 * 1024:  # 100MB sanity cap
            return False, "input too large ({}B)".format(len(raw))

        # Write the incoming bytes to a temp file. Piping via stdin works for most
        # formats, but webm/opus from MediaRecorder is non-seekable on a pipe and
        # ffmpeg sometimes fails to read its cues; a real file is robust.
        fd, tmp = tempfile.mkstemp(suffix=".bin", dir=str(out_path.parent))
        with os.fdopen(fd, "wb") as f:
            f.write(raw)

        # Single decode attempt. ffmpeg on a fixed input file is deterministic:
        # a decode error ("Invalid data" / "could not find codec") on this exact
        # blob will recur identically on every retry, so retrying only burdens the
        # server thread with ~0.3s of dead latency per corrupt chunk. Fail fast;
        # the phone re-records and resends the next chunk instead.
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-i", tmp,
            "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le",
            "-f", "wav",
            str(out_path),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        if proc.returncode == 0:
            if out_path.exists() and out_path.stat().st_size > 44:
                return True, "ok"
            return False, "ffmpeg produced empty wav"

        err = (proc.stderr or b"").decode("utf-8", "replace").strip()[:200]
        return False, "ffmpeg rc={} {}".format(proc.returncode, err)
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timeout"
    except Exception as exc:  # noqa: BLE001
        return False, "transcode exception: {}".format(exc)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# the recorder PWA, served at GET /
# --------------------------------------------------------------------------- #
RECORDER_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no" />
<meta name="theme-color" content="#ffffff" />
<title>אוזן החדר של ערן · ALMAWARE</title>
<link rel="manifest" href="/manifest.webmanifest" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-title" content="אוזן ערן" />
<style>
  :root{
    --bg:#ffffff; --ink:#16181d; --muted:#6b7280; --line:#e7e9ee; --card:#f7f8fa;
    --blue:#2563eb; --green:#16a34a; --red:#dc2626; --amber:#d97706;
    --shadow:0 1px 2px rgba(16,24,40,.06),0 8px 24px rgba(16,24,40,.08);
    --radius:18px;
    --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Rubik,"Heebo",Arial,sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);font-family:var(--font)}
  body{min-height:100dvh;display:flex;flex-direction:column;align-items:center;
       padding:max(16px,env(safe-area-inset-top)) 16px max(16px,env(safe-area-inset-bottom))}
  .wrap{width:100%;max-width:560px;display:flex;flex-direction:column;gap:16px}
  header{display:flex;align-items:center;gap:10px;margin-top:4px}
  header .dot{width:11px;height:11px;border-radius:50%;background:var(--blue)}
  header h1{font-size:18px;font-weight:800;margin:0;letter-spacing:-.2px}
  .status{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted);
          background:var(--card);border:1px solid var(--line);border-radius:999px;
          padding:7px 12px;align-self:flex-start}
  .status .led{width:9px;height:9px;border-radius:50%;background:#cbd5e1;flex:none}
  .status.ok .led{background:var(--green)} .status.bad .led{background:var(--red)}
  .status.warn .led{background:var(--amber)}
  .mic-card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
            padding:24px 18px 20px;display:flex;flex-direction:column;align-items:center;gap:16px;
            box-shadow:var(--shadow)}
  .mic-btn{--size:168px;width:var(--size);height:var(--size);border-radius:50%;border:0;cursor:pointer;
           color:#fff;font-family:var(--font);background:var(--blue);
           box-shadow:0 10px 30px rgba(37,99,235,.35);
           display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;
           transition:transform .08s ease, background .15s ease;user-select:none;-webkit-user-select:none}
  .mic-btn .ico{font-size:52px;line-height:1}
  .mic-btn .lbl{font-size:16px;font-weight:800;letter-spacing:.2px}
  .mic-btn:active{transform:scale(.97)}
  .mic-btn.rec{background:var(--red);box-shadow:0 10px 34px rgba(220,38,38,.42);
               animation:pulse 1.4s ease-in-out infinite}
  @keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.04)}}
  .stat{font-variant-numeric:tabular-nums;font-size:15px;font-weight:700;color:var(--muted);
        min-height:22px;text-align:center}
  .stat.rec{color:var(--red)}
  .help{font-size:12.5px;color:var(--muted);text-align:center;margin:0;line-height:1.6}
  .big{font-size:34px;font-weight:800;font-variant-numeric:tabular-nums}
  footer{margin-top:6px;text-align:center;font-size:12px;color:var(--muted)}
</style>
</head>
<body>
  <div class="wrap">
    <header><span class="dot"></span><h1>אוזן החדר של ערן</h1></header>
    <div class="status" id="status"><span class="led"></span><span id="statusText">בודק חיבור לשרת…</span></div>

    <div class="mic-card">
      <button class="mic-btn" id="mic" aria-label="התחל/עצור האזנה">
        <span class="ico" id="ico">&#127908;</span>
        <span class="lbl" id="lbl">התחל האזנה</span>
      </button>
      <div class="big" id="count">0</div>
      <div class="stat" id="stat">קטעי אודיו שנשלחו לערן</div>
      <p class="help" id="help">
        לחץ &laquo;התחל&raquo; ואשר גישה למיקרופון.<br>
        הטלפון יקליט את הסביבה בקטעים של ~10 שניות וישלח אותם ל‑PC.<br>
        השאר את המסך דולק. לעצירה — לחץ שוב.
      </p>
    </div>
    <footer>ALMAWARE &middot; ERAN room-ear &middot; v1</footer>
  </div>

<script>
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const el = { status:$("status"), statusText:$("statusText"), mic:$("mic"),
               ico:$("ico"), lbl:$("lbl"), count:$("count"), stat:$("stat"), help:$("help") };

  const BASE = location.origin;       // served from the PC itself
  const CHUNK_MS = 10000;             // ~10s chunks
  let stream = null, rec = null, running = false, sent = 0, ok = 0, fail = 0;

  function setStatus(kind, text){ el.status.className = "status" + (kind?(" "+kind):""); el.statusText.textContent = text; }
  function setRunning(on){
    running = on;
    el.mic.classList.toggle("rec", on);
    el.ico.innerHTML = on ? "&#9632;" : "&#127908;";          // square : mic
    el.lbl.textContent = on ? "עצור האזנה" : "התחל האזנה";
    el.stat.classList.toggle("rec", on);
    el.stat.textContent = on ? "מאזין ושולח לערן…" : "קטעי אודיו שנשלחו לערן";
  }
  function updateCount(){ el.count.textContent = String(sent); el.stat.textContent =
    running ? ("מאזין… נשלחו " + ok + (fail? (" · נכשלו "+fail):"")) : "קטעי אודיו שנשלחו לערן"; }

  async function ping(){
    try { const r = await fetch(BASE + "/ping", {cache:"no-store"});
          if ((await r.text()).trim() === "pong") { setStatus("ok","מחובר ל‑PC של ערן"); return true; } }
    catch(e){}
    setStatus("bad","אין חיבור ל‑PC. ודא שהשרת רץ ושאתם באותו Wi‑Fi.");
    return false;
  }

  function pickMime(){
    const c = ["audio/webm;codecs=opus","audio/webm","audio/mp4","audio/ogg;codecs=opus","audio/ogg"];
    for (const m of c){ if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m; }
    return "";
  }

  async function upload(blob, mime){
    try {
      const r = await fetch(BASE + "/audio", { method:"POST",
        headers: { "Content-Type": mime || "application/octet-stream" }, body: blob });
      if (r.ok) { ok++; } else { fail++; }
    } catch(e){ fail++; }
    sent++; updateCount();
  }

  // Re-arm a fresh MediaRecorder per chunk: onstop -> upload that chunk -> start next.
  // This gives a self-contained, decodable webm per chunk (vs one growing stream).
  let mime = "";
  function armOnce(){
    if (!running || !stream) return;
    let parts = [];
    try { rec = mime ? new MediaRecorder(stream, {mimeType:mime}) : new MediaRecorder(stream); }
    catch(e){ rec = new MediaRecorder(stream); }
    mime = rec.mimeType || mime || "audio/webm";
    rec.ondataavailable = (ev)=>{ if (ev.data && ev.data.size) parts.push(ev.data); };
    rec.onstop = () => {
      const blob = new Blob(parts, {type: mime});
      parts = [];
      if (blob.size) upload(blob, mime);
      if (running) armOnce();             // immediately start the next chunk
    };
    rec.start();
    setTimeout(()=>{ try{ if (rec && rec.state !== "inactive") rec.stop(); }catch(e){} }, CHUNK_MS);
  }

  async function start(){
    if (running) return;
    if (!(navigator.mediaDevices && window.MediaRecorder)) { setStatus("bad","הדפדפן לא תומך בהקלטה"); return; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount:1, echoCancellation:false, noiseSuppression:false, autoGainControl:true } });
    } catch(e){ setStatus("bad","אין הרשאת מיקרופון. אשר גישה."); return; }
    mime = pickMime();
    setRunning(true); updateCount();
    armOnce();
    // keep the screen awake if the browser allows it
    try { if (navigator.wakeLock) navigator.wakeLock.request("screen").catch(()=>{}); } catch(e){}
  }
  function stop(){
    running = false;
    try { if (rec && rec.state !== "inactive") rec.stop(); } catch(e){}
    if (stream){ stream.getTracks().forEach(t=>t.stop()); stream = null; }
    setRunning(false); updateCount();
  }

  el.mic.addEventListener("click", ()=>{ running ? stop() : start(); });
  // re-acquire wakelock after the tab is re-shown
  document.addEventListener("visibilitychange", ()=>{
    if (document.visibilityState === "visible" && running) {
      try { if (navigator.wakeLock) navigator.wakeLock.request("screen").catch(()=>{}); } catch(e){}
    }
  });

  ping();
  setInterval(()=>{ if (!running) ping(); }, 15000);
})();
</script>
</body>
</html>
"""

MANIFEST = json.dumps({
    "name": "Eran Room-Ear",
    "short_name": "Eran Ear",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#ffffff",
    "icons": [],
}, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "EranA70/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log.info("%s - " + fmt, self.client_address[0], *args)

    def _send(self, code: int, body, ctype: str = "text/plain; charset=utf-8") -> None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001 — client hung up; never crash
            log.debug("send failed: %s", exc)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/ping":
            self._send(200, "pong")
            return
        if path == "/" or path == "/index.html":
            self._send(200, RECORDER_HTML, "text/html; charset=utf-8")
            return
        if path == "/manifest.webmanifest":
            self._send(200, MANIFEST, "application/manifest+json; charset=utf-8")
            return
        if path == "/health":
            with _lock:
                st = dict(_state)
            st["ok"] = True
            st["ffmpeg"] = FFMPEG
            self._send(200, json.dumps(st, ensure_ascii=False), "application/json; charset=utf-8")
            return
        self._send(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/audio":
            self._send(404, "not found")
            return
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            n = 0
        if n <= 0:
            self._send(400, "empty body")
            return
        if n > MAX_BODY:
            self._send(413, "payload too large")
            with _lock:
                _state["rejected"] += 1
            return
        try:
            raw = self.rfile.read(n)
        except Exception as exc:  # noqa: BLE001
            log.warning("read body failed: %s", exc)
            self._send(400, "read error")
            return
        if not raw:
            self._send(400, "empty body")
            return

        out = HEARD / ts_name()
        ok, detail = transcode_to_wav(raw, out)
        if not ok:
            with _lock:
                _state["rejected"] += 1
            log.warning("reject %d bytes -> %s", len(raw), detail)
            # 200 anyway so the phone keeps streaming; the bad chunk is just dropped.
            self._send(200, "dropped: " + detail)
            return
        with _lock:
            _state["saved"] += 1
            _state["last"] = out.name
        log.info("saved %s (%d bytes in -> %d bytes wav)", out.name, len(raw), out.stat().st_size)
        self._send(200, "ok " + out.name)


def main() -> int:
    # Force allow_reuse_address off (same rationale as pc-listener): a duplicate
    # spawn should fail fast with EADDRINUSE instead of silently stacking listeners.
    ThreadingHTTPServer.allow_reuse_address = False
    try:
        server = ThreadingHTTPServer((BIND, PORT), Handler)
    except OSError as e:
        log.error("port %d already bound (%s) — another receiver owns it, exiting", PORT, e)
        return 0
    log.info("ERAN A70 room-ear receiver on http://%s:%d  (saving 16k mono wav -> %s)",
             BIND, PORT, HEARD)
    log.info("ffmpeg: %s", FFMPEG)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutdown via KeyboardInterrupt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
