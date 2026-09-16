# -*- coding: utf-8 -*-
"""
PHONE MIC WEB -- the page Iddo actually opens on his phone.

Built 2026-09-07 per his order (said twice, then he slept: "finish it, don't
ask"). 09-06's attempt (native APK + a PWA served from eran4/dgx4, RAMCHAT
posts 549-635) got the STT contract and the PC-typing leg right but died on a
hard mixed-content wall: an HTTPS page is not allowed by any browser to fetch
plain-HTTP backends, and both the STT decoder and the PC intake sidecar are
plain HTTP. That thread went cold at RAMCHAT post 635 (PARTIAL, never fixed).

THE FIX: same-origin. This one small stdlib server is BOTH the page and the
only thing the phone's browser ever talks to. Everything else -- eran1's STT,
the already-running PC intake sidecar -- is called from PYTHON, server to
server, where "mixed content" does not apply at all. Zero CORS headers
needed anywhere, because there is only one origin.

  phone (Chrome, HTTPS via `tailscale serve`)
    |  MediaRecorder (NOT webkitSpeechRecognition -- ours or nothing)
    v  POST /api/stt   (webm/opus blob)
  this process on the PC, 127.0.0.1:8893 only (tailscale serve terminates TLS
  and reverse-proxies to loopback -- see RUN-PHONEMIC-WEB.cmd)
    |  ffmpeg subprocess: webm/opus -> raw s16le 16kHz mono
    |  app/decoder.py's transcribe_hebrew_pcm() -- THE SAME function the live
    |  desktop mic uses, imported not reimplemented, so auth / hallucination
    |  filtering / retry-then-fallback behave identically. KESHEV_STT_URL is
    |  pointed at eran1's LAN address below (the PC's own :8737 is not
    |  running tonight -- KESHEV is deliberately off -- so this skips the
    |  wasted two-timeout wait decoder.py's default would otherwise cost).
    v  text shown to Iddo -- HE taps send. Nothing types itself.
    |  POST /api/type -> proxied to 127.0.0.1:8892/type (keshev_intake.py,
    v  a SEPARATE already-running process, never restarted by this file)
  the window he locked

Never touches PC audio, never starts/stops/imports app/main.py or gui6.py
(the live mic), never restarts eran1 or eran4. BELOW_NORMAL priority.
Binds ONLY 127.0.0.1:8893 -- the phone reaches it exclusively through
`tailscale serve`, which is what turns this into a real https:// origin
(mic capture is refused by every mobile browser on plain http://).
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))              # ...\keshev-next\intake
KESHEV_ROOT = os.path.dirname(BASE_DIR)                              # ...\keshev-next
APP_DIR = os.path.join(KESHEV_ROOT, "app")
STATE_DIR = os.path.join(KESHEV_ROOT, "state")

# eran1's STT decoder answers on its LAN address but NOT its Tailscale one --
# measured 2026-09-07: <lan-ip>:8737/health -> 200 in 81ms, while
# <tailnet-ip>:8737 -> "Connection refused" (curl -v). That is fine: THIS
# process runs on the PC, which has LAN access, so the phone never needs to
# reach eran1 directly -- only this proxy does, and it uses the address that
# actually answers. Overriding KESHEV_STT_URL here also skips app/decoder.py's
# default of 127.0.0.1:8737, which is not listening tonight (KESHEV is off)
# and would otherwise cost two wasted 10s timeouts before its own fallback
# reached the same eran1 address anyway.
os.environ.setdefault("KESHEV_STT_URL", "http://<lan-ip>:8737/v1/transcribe")

sys.path.insert(0, APP_DIR)
import decoder as keshev_decoder  # noqa: E402 -- byte-identical STT contract to the live mic

import ctypes.wintypes as wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentProcess.argtypes = []
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.SetPriorityClass.restype = wintypes.BOOL
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000

PORT = int(os.environ.get("PHONEMIC_WEB_PORT", "8893"))
BIND_LOOPBACK = "127.0.0.1"

INTAKE_BASE = "http://127.0.0.1:8892"
INTAKE_TOKEN_PATH = os.path.join(STATE_DIR, "intake.token")

LOG_PATH = os.path.join(STATE_DIR, "phonemic_web.log")

MIN_AUDIO_MS = 250  # shorter than this is a mis-tap, not speech


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def set_priority_below_normal():
    try:
        ok = kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        log(f"SetPriorityClass BELOW_NORMAL -> {bool(ok)}")
    except Exception as e:
        log(f"could not set BELOW_NORMAL priority: {e}")


def _find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    # winget's default install path, measured present 2026-09-07
    guess = (r"C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages"
             r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
             r"\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe")
    return guess if os.path.exists(guess) else None


FFMPEG = _find_ffmpeg()


def webm_to_pcm16(blob: bytes) -> bytes:
    """Whatever the phone's MediaRecorder produced (webm/opus on Chrome,
    mp4/aac on Safari) -> raw s16le 16kHz mono -- the exact body
    app/decoder.py's transcribe_hebrew_pcm() sends on as Content-Type:
    audio/x-raw, unchanged from what the live desktop mic sends."""
    if not FFMPEG:
        raise RuntimeError("ffmpeg not found on PATH")
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
        input=blob, capture_output=True, timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exit {proc.returncode}: {proc.stderr.decode('utf-8', 'ignore')[:400]}")
    return proc.stdout


_intake_token_cache = None


def _intake_token():
    global _intake_token_cache
    if _intake_token_cache is None:
        with open(INTAKE_TOKEN_PATH, "r", encoding="utf-8") as f:
            _intake_token_cache = f.read().strip()
    return _intake_token_cache


def intake_call(method, path, body=None, timeout=10):
    """Server-to-server call to the ALREADY-RUNNING intake sidecar (:8892).
    The token never reaches the phone -- it is added here, not in JS."""
    url = INTAKE_BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Alma-Token": _intake_token(), "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 599, {"error": str(e)}


PAGE_HTML = r"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>קשב מהטלפון</title>
<style>
  :root{color-scheme:dark;}
  *{box-sizing:border-box;}
  body{background:#0b0f13;color:#E8F0F5;font-family:"Segoe UI",Arial,sans-serif;
       margin:0;padding:16px;max-width:520px;margin:0 auto;}
  h1{font-size:19px;margin:4px 0 10px;}
  #status{font-size:13px;color:#8aa0b0;margin-bottom:12px;line-height:1.6;min-height:20px;}
  #lockRow{display:flex;gap:8px;margin-bottom:14px;}
  select{flex:1;font-size:15px;padding:10px;border-radius:8px;background:#151b21;
         color:#E8F0F5;border:1px solid #2a3540;min-width:0;}
  button{font-size:16px;padding:10px 14px;border-radius:8px;border:none;
         background:#1b5e20;color:#fff;}
  #micBtn{display:block;width:100%;height:170px;font-size:26px;font-weight:bold;
          border-radius:24px;background:#1b5e20;color:#fff;border:none;margin:14px 0;
          touch-action:none;user-select:none;-webkit-user-select:none;}
  #micBtn.rec{background:#b71c1c;}
  #micBtn small{display:block;font-size:13px;font-weight:normal;opacity:.8;margin-top:6px;}
  #heard{background:#151b21;border-radius:12px;padding:16px;font-size:22px;
         min-height:56px;margin:12px 0;line-height:1.5;}
  #sendBtn{width:100%;height:60px;font-size:19px;background:#0d47a1;margin-top:4px;}
  #sendBtn:disabled{background:#2a3540;color:#66757f;}
  .row{display:flex;gap:8px;align-items:center;margin:10px 0;font-size:14px;color:#8aa0b0;}
</style>
</head>
<body>
<h1>קשב &mdash; הטלפון כמיקרופון</h1>
<div id="status">טוען&hellip;</div>
<div id="lockRow">
  <select id="winSelect"><option>טוען חלונות&hellip;</option></select>
  <button id="lockBtn">נעל&nbsp;&#128274;</button>
</div>
<button id="micBtn">&#127908; החזק ודבר<small>hold the button, speak, let go</small></button>
<div id="heard">&hellip;</div>
<div class="row"><label><input type="checkbox" id="autoEnter" checked> Enter אחרי השליחה</label></div>
<button id="sendBtn" disabled>שלח לחלון הנעול &#9166;</button>

<script>
(function(){
  var statusEl = document.getElementById('status');
  var winSelect = document.getElementById('winSelect');
  var lockBtn = document.getElementById('lockBtn');
  var micBtn = document.getElementById('micBtn');
  var heardEl = document.getElementById('heard');
  var sendBtn = document.getElementById('sendBtn');
  var autoEnter = document.getElementById('autoEnter');

  var heardText = '';
  var stream = null, recorder = null, chunks = [];

  function setStatus(t){ statusEl.textContent = t; }

  function refreshStatus(){
    fetch('/api/status').then(function(r){ return r.json(); }).then(function(j){
      setStatus(j.locked ? ('נעול על: ' + j.title) : 'לא נעול על שום חלון \u2014 בחר חלון למטה ולחץ נעל');
    }).catch(function(){ setStatus('שגיאת חיבור לשרת'); });
  }

  function loadWindows(){
    fetch('/api/windows').then(function(r){ return r.json(); }).then(function(j){
      winSelect.innerHTML = '';
      (j.windows || []).forEach(function(w){
        if (!w.title) return;
        var opt = document.createElement('option');
        opt.value = w.hwnd;
        opt.textContent = (w.elevated ? '\u{1F6AB} ' : '') + w.title + '  [' + w.process_name + ']';
        if (w.elevated) opt.disabled = true;
        winSelect.appendChild(opt);
      });
    }).catch(function(){ winSelect.innerHTML = '<option>שגיאה בטעינת חלונות</option>'; });
  }

  lockBtn.onclick = function(){
    var hwnd = parseInt(winSelect.value, 10);
    if (!hwnd) return;
    fetch('/api/lock', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({hwnd: hwnd})})
      .then(function(r){ return r.json().then(function(j){ return [r.ok, j]; }); })
      .then(function(pair){
        var ok = pair[0], j = pair[1];
        setStatus(ok ? ('נעול על: ' + j.title) : ('נעילה נכשלה: ' + (j.error || '')));
      });
  };

  function startRec(){
    var go = function(){
      chunks = [];
      var opts = {};
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        opts.mimeType = 'audio/webm;codecs=opus';
      }
      recorder = new MediaRecorder(stream, opts);
      recorder.ondataavailable = function(e){ if (e.data && e.data.size) chunks.push(e.data); };
      recorder.onstop = onRecStop;
      recorder.start();
      micBtn.classList.add('rec');
      heardEl.textContent = '\u{1F399}\uFE0F מקליט\u2026';
      sendBtn.disabled = true;
    };
    // ------------------------------------------------------------------
    // 2026-09-09 09:20 -- THE $100 SCAR, and it cost him his music.
    // This page used to ask for {echoCancellation:true, noiseSuppression:true}
    // and then HOLD the stream for the whole life of the page. On Android those
    // flags make Chrome open the communications audio path, and a held
    // communications stream flips a Bluetooth headset out of A2DP into HFP --
    // telephone quality. His WH-1000XM4 dropped to a phone call and stayed
    // there. Same species as 2026-08-09 on the PC, where opening the headset as
    // a microphone wrecked his sound.
    //
    // Two rules now, and neither is negotiable (AUDIO PROTECTION LAW):
    //   1. plain {audio:true} -- nothing that asks Android for the voice path.
    //   2. the stream is opened per clip and RELEASED the moment the clip ends
    //      (releaseMic). Push-to-talk means the microphone is open only while
    //      his finger is down -- which is also the only honest kind of privacy.
    // ------------------------------------------------------------------
    navigator.mediaDevices.getUserMedia({audio:true})
      .then(function(s){ stream = s; go(); })
      .catch(function(e){ releaseMic(); heardEl.textContent = 'אין גישה למיקרופון: ' + e; });
  }

  function releaseMic(){
    // Every track, every time. A track left live is a microphone left open, and
    // on Android that is his music in telephone quality.
    if (stream) {
      try { stream.getTracks().forEach(function(t){ t.stop(); }); } catch(e){}
    }
    stream = null;
  }

  function stopRec(){
    if (recorder && recorder.state !== 'inactive') { recorder.stop(); }
    else { releaseMic(); }
    micBtn.classList.remove('rec');
  }

  function onRecStop(){
    heardEl.textContent = '\u23F3 שולח לזיהוי\u2026';
    var blob = new Blob(chunks, {type: (recorder.mimeType || 'audio/webm')});
    releaseMic();          // the clip is finished: give the microphone back NOW
    fetch('/api/stt', {method:'POST', headers:{'Content-Type': blob.type}, body: blob})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if (j.text) {
          heardText = j.text;
          heardEl.textContent = j.text;
          sendBtn.disabled = false;
        } else {
          heardText = '';
          heardEl.textContent = '(לא זוהה דיבור \u2014 נסה שוב) ' + (j.reason || '');
          sendBtn.disabled = true;
        }
      })
      .catch(function(e){ heardEl.textContent = 'שגיאה: ' + e; sendBtn.disabled = true; });
  }

  micBtn.addEventListener('pointerdown', function(e){ e.preventDefault(); startRec(); });
  micBtn.addEventListener('pointerup', stopRec);
  micBtn.addEventListener('pointercancel', stopRec);
  micBtn.addEventListener('pointerleave', stopRec);

  sendBtn.onclick = function(){
    if (!heardText) return;
    sendBtn.disabled = true;
    var text = heardText;
    fetch('/api/type', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text: text, auto_enter: autoEnter.checked})})
      .then(function(r){ return r.json().then(function(j){ return [r.ok, j]; }); })
      .then(function(pair){
        var ok = pair[0], j = pair[1];
        if (ok) { heardEl.textContent = '\u2705 נשלח: ' + text; heardText = ''; }
        else { heardEl.textContent = '\u274C ' + (j.error || j.error_he || ''); sendBtn.disabled = false; }
      });
  };

  refreshStatus();
  loadWindows();
})();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "PhoneMicWeb/1.0"

    def log_message(self, fmt, *args):
        log(f"{self.address_string()} - {fmt % args}")

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _send_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        return self.rfile.read(length) if length > 0 else b""

    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                self._send_html(200, PAGE_HTML)
                return
            if self.path == "/api/health":
                self._send_json(200, {"ok": True, "service": "phone-mic-web", "pid": os.getpid(),
                                       "ffmpeg": bool(FFMPEG)})
                return
            if self.path == "/api/windows":
                st, resp = intake_call("GET", "/windows")
                self._send_json(st, resp)
                return
            if self.path == "/api/status":
                st, resp = intake_call("GET", "/status")
                self._send_json(st, resp)
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            log(f"GET {self.path} error: {e}\n{traceback.format_exc()}")
            self._send_json(500, {"error": str(e)})

    def do_POST(self):
        try:
            if self.path == "/api/lock":
                try:
                    body = json.loads(self._read_body() or b"{}")
                except Exception:
                    body = {}
                st, resp = intake_call("POST", "/lock", body)
                self._send_json(st, resp)
                return
            if self.path == "/api/unlock":
                st, resp = intake_call("POST", "/unlock")
                self._send_json(st, resp)
                return
            if self.path == "/api/type":
                try:
                    body = json.loads(self._read_body() or b"{}")
                except Exception:
                    body = {}
                st, resp = intake_call("POST", "/type", body)
                self._send_json(st, resp)
                return
            if self.path == "/api/stt":
                raw = self._read_body()
                if not raw:
                    self._send_json(400, {"error": "empty audio body"})
                    return
                t0 = time.time()
                try:
                    pcm = webm_to_pcm16(raw)
                except Exception as e:
                    log(f"ffmpeg decode error: {e}")
                    self._send_json(502, {"error": f"audio decode failed: {e}"})
                    return
                duration_ms = len(pcm) // 32
                if duration_ms < MIN_AUDIO_MS:
                    self._send_json(200, {"ok": True, "text": "", "reason": "too_short",
                                           "duration_ms": duration_ms})
                    return
                ok, text, lang, avg_logprob = keshev_decoder.transcribe_hebrew_pcm(pcm)
                latency_ms = round((time.time() - t0) * 1000, 1)
                log(f"STT ok={ok} text={text!r} lang={lang} avg_logprob={avg_logprob} "
                    f"in_bytes={len(raw)} pcm_bytes={len(pcm)} duration_ms={duration_ms} "
                    f"latency_ms={latency_ms}")
                self._send_json(200 if ok else 502, {
                    "ok": ok, "text": text, "lang": lang, "avg_logprob": avg_logprob,
                    "duration_ms": duration_ms, "latency_ms": latency_ms,
                })
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            log(f"POST {self.path} error: {e}\n{traceback.format_exc()}")
            self._send_json(500, {"error": str(e)})


def main():
    set_priority_below_normal()
    log(f"phone-mic-web starting, pid={os.getpid()}, ffmpeg={FFMPEG!r}, "
        f"KESHEV_STT_URL={os.environ.get('KESHEV_STT_URL')!r}")
    httpd = ThreadingHTTPServer((BIND_LOOPBACK, PORT), Handler)
    log(f"bound {BIND_LOOPBACK}:{PORT} (reach it via `tailscale serve`, not directly)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
