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
import base64
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

# ---------------------------------------------------------------------------
# 2026-09-12 -- claude-cli-SONNET-phonemicA, PHONE SIDE ONLY (Iddo's order:
# "finish the ALMA phone microphone so it is a full digital dictation
# device, easy to use, with everything selectable"). Scope drawn deliberately
# narrow: this touches ONLY the page served to the phone (PAGE_HTML below)
# plus three new static GET routes for PWA installability
# (/manifest.json, /sw.js, /icon-*.png). It does NOT touch a single line of
# the proxy/decode logic above this comment or the window-lock/typing
# contract in keshev_intake.py -- that is explicitly another agent's slice
# ("where the text lands and window locking"). The AUDIO PROTECTION LAW
# scar from 2026-09-09 (see the comment inside PAGE_HTML's JS) is preserved
# exactly: plain {audio:true}, stream released the instant a clip ends or
# an interruption is detected, no echoCancellation/noiseSuppression, never
# auto-resumes after a pause -- only his tap does.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# PWA installability -- so this opens from his home screen like an app,
# not a bookmark. Icons are baked in as base64 (same "one file, one origin"
# philosophy as the rest of this server): a small green mic glyph on the
# page's own dark background, generated once with Pillow, never re-fetched.
# ---------------------------------------------------------------------------
ICON_192_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAGfElEQVR4nO2dS44UVxBFq1s9KhAIMWINtpfgqRfCFlgHW2AhnnoJttfAEAmhnILKcqLq6s7/+9yIe47EhG5VvYp3z4vIypT67sXrt99PAKbc914AQE8QAKxBALAGAcAaBABrEACseei9gMycX74q8jrDt69FXgeeggAiId/7HshxDAQQC3uJNSHFehAgWOD3rBshpkGAJKFf+5mQ4TEIkDT0UyDDY6wFcAr+3OcfjL9lshPAPfTPcTYekWwEIPjb6jSYiJBeAIJ/rG5DchHSCkDwy9ZxSCpCOgEIft26DslESPUwHOGnxpYdgOD3qfeQoBuEFoDga9R/CCxC2BGI8OtwDnxvJaQAkQuelXPQPQk1AkUtsgvngCNRmA5A+ONwDnRQhRAgUkEh1p5Jj0BRighxRyLZDkD483AWPsgkBVAuGOTaUzkBVAsFOfdWSgDFAkHuPZYRQK0w4LHXEgIoFQS89ry7ACqFAM+9v3cvAPSldwbuXT846NAzC10EIPygkonmj0K4h//d+zeLv/P505eTI+eXr5o/NnHX8s+kuoZ/TeincJRhaCgBAogG31mEIaMATqd/yeC7ijA0kqDJRTDhjyGXEq0yU70DuIS/RzAdusFQuRN0vxOcgV6nsks3CCuAw+nfO4S93782tTNUTQCH8EMbamapigAu4Vc5fVXWUZNameIaIEno1NYTheICuJz+0J4a2aIDJDptVdelTFEBOP2hNqUzVkwAl/Crn7Lq61PLGiMQWFNEAJfTH3QolTk6QMLxIso6FTgsAKc/9KJE9ugAYM0hATj9oTdHM0gHAGt2C8DpDyocySIdAKxBALBmlwCMP6DG3kzSAcCazQJw+oMqe7JJBwBrEACs2SQA4w+oszWjdACwBgHAmtUCMP5AFLZklQ4A1iAAWIMAYM0qAZj/IRprM0sHAGsQAKxBALAGAcCaRQG4AIaorMkuHQCsQQCwBgHAGgQAaxAArEEAsGZWAL4ChegsZZgOsIHPn76cIhBlnQogAFiDAGANAiQbL9TXpwYCgDUIkOiUVV2XMggA1iBAktNWbT1RQIAEoVNZR0QQAKxBgBv+/vef//5FOX3Xvv/Wz+XCQ+8FKHA0GJcQvnv/pth6trzv3s/62y+/VlhRPO5evH773f1huCkB9oSkhQhbg1/y80Vk+PZ18meMQIWDUHskKvX6LuFfghFo4eTcE5QxpHPd4M8Pfz35vz8+/r74mlth7p+HDvA/U0E/EqBLaI+e2Edew330WQMd4CYYz4VmbycYuQ7wmmuEEmMO4S8gwOXiweVCuBU/w/1h5mfQ5AL4AiNQg1GoNZz+60GAjRIoizC3Pub+50GACeYCoyjB3JoI/zQIcEACBRGW1kH450GABZYC1FOCpfcm/MsgQCEJWoqw5v0If6H7AHwVOn+P4Jrrn5cO4BbBCP+6r0AvcCNsA2Ow1oTx9ne2hnJPRyH4hZ8GHeFm2FMULoCvIfz7OgACBBeB4E+DAEllIPSNBbjAGNRXBkJfPvwXEEBUCAJ/DARoBNcAsQXgRhhYc1/aKIDebMkqHQCsQQCwZvW3QCN8HQrKbB3V6QBgDQKANZsF4NsgUGVPNukAYM0uAegCoMbeTNIBwBoEAGt2C8AYBCocySIdAKw5JABdAHpzNIN0ALDmsAB0AehFiezRAcCaIgLQBaA1pTJHBwBriglAF4BWlMxa0Q6ABFCb0hljBAJrigtAF4Ba1MgWHQCsqSIAXQCiZKpaB0ACiJClqiMQEoB6hrgGAGuqC0AXAOXsNOkASACqmWk2AiEBKGaFawCwpqkAdAFQy0jzDoAEoJSNLiMQEoBKJrpdAyABKGSh60UwEsDQ+W/P3bsXALz3vrsAKoUAzz2XEECpIOC11zICqBUGPPZYSgDFAkHuvZUTQLVQkHNPJQVQLhjk2suHU4DC8ce5YzIIB1++A0QrJMTcsxACRCoonELtlfQIdAsjkTZDoOCH6wDRC52dIeiehBQgcsEzMgTei1Aj0C2MRBr1j0xoAUYQoU+9MxB2BMq+MaoMyWqcogNcQzeoW9dspBNgBBHK1jEraQUYQYRjdctOegFGEGFbnVywEeC5DeYhO8/QWwtwjXtXGIyDP2ItgGNXIPSPQQADGQj9NAiwIThRhCDw60GAg8HqLQVhPwYCVAxgKTkIeT0QoCIEV59UD8MBbAUBwBoEAGsQAKxBALAGAeDkzA+BT3hLDzyEkQAAAABJRU5ErkJggg=="
)
ICON_512_PNG = base64.b64decode(
    "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"
)


def _pwa_manifest():
    return {
        "name": "קשב — הטלפון כמיקרופון",
        "short_name": "קשב מיק",
        "description": "הכתבה דיגיטלית מהטלפון של עידו",
        "start_url": "/",
        "id": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "dir": "rtl",
        "lang": "he",
        "background_color": "#0b0f13",
        "theme_color": "#0b0f13",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
        ],
    }


# Service worker: caches the app shell for a fast/offline open, and -- the
# part that matters for "never lose a clip silently" -- registers a
# Background Sync handler so a clip queued while the phone had no signal
# gets flushed even if he never reopens the tab, the moment Android tells
# Chrome connectivity is back. It talks to the SAME IndexedDB the page uses
# (`alma-mic-queue`, store `clips`) and calls the SAME /api/stt + /api/type
# routes -- no new server contract, nothing the PC-side owner needs to add.
SW_JS = r"""// alma-mic service worker -- phone side only, 2026-09-12
const CACHE = 'alma-mic-shell-v1';
const SHELL = ['/', '/manifest.json', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', function(e){
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(SHELL); }).catch(function(){}));
});

self.addEventListener('activate', function(e){
  e.waitUntil(
    caches.keys().then(function(keys){
      return Promise.all(keys.filter(function(k){ return k !== CACHE; }).map(function(k){ return caches.delete(k); }));
    }).then(function(){ return self.clients.claim(); })
  );
});

// App shell only, network-first for everything else (never cache /api/*
// responses -- STT results and window lists must always be fresh).
self.addEventListener('fetch', function(e){
  var url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.pathname.indexOf('/api/') === 0) return;
  e.respondWith(
    caches.match(e.request).then(function(hit){
      var net = fetch(e.request).then(function(resp){
        if (resp && resp.ok) { caches.open(CACHE).then(function(c){ c.put(e.request, resp.clone()); }); }
        return resp;
      }).catch(function(){ return hit; });
      return hit || net;
    })
  );
});

// ---- Background Sync: flush the offline queue without the page open ----
function openDB(){
  return new Promise(function(resolve, reject){
    var req = indexedDB.open('alma-mic-queue', 1);
    req.onupgradeneeded = function(){ req.result.createObjectStore('clips', {keyPath:'id', autoIncrement:true}); };
    req.onsuccess = function(){ resolve(req.result); };
    req.onerror = function(){ reject(req.error); };
  });
}
function allClips(db){
  return new Promise(function(resolve, reject){
    var tx = db.transaction('clips', 'readonly');
    var req = tx.objectStore('clips').getAll();
    req.onsuccess = function(){ resolve(req.result || []); };
    req.onerror = function(){ reject(req.error); };
  });
}
function putClip(db, clip){
  return new Promise(function(resolve, reject){
    var tx = db.transaction('clips', 'readwrite');
    tx.objectStore('clips').put(clip);
    tx.oncomplete = function(){ resolve(); };
    tx.onerror = function(){ reject(tx.error); };
  });
}

function swFlush(){
  return openDB().then(function(db){
    return allClips(db).then(function(clips){
      var chain = Promise.resolve();
      clips.sort(function(a,b){ return a.id - b.id; }).forEach(function(c){
        chain = chain.then(function(){ return swFlushOne(db, c); });
      });
      return chain;
    });
  }).catch(function(){ /* no DB yet -- nothing queued, nothing lost */ });
}

function swFlushOne(db, clip){
  if (clip.status === 'QUEUED') {
    return fetch('/api/stt', {method:'POST', headers:{'Content-Type': clip.mime || 'audio/webm'}, body: clip.blob})
      .then(function(r){ return r.json().then(function(j){ return [r.ok, j]; }); })
      .then(function(pair){
        var ok = pair[0], j = pair[1];
        if (ok && j.text) {
          clip.status = clip.autoSend ? 'READY_TO_SEND' : 'READY';
          clip.text = j.text;
        } else if (ok) {
          clip.status = 'FAILED'; clip.error = j.reason || 'no_speech';
        } else {
          return; // network/server hiccup -- leave QUEUED, try again next sync
        }
        return putClip(db, clip);
      }).catch(function(){ /* offline again -- leave QUEUED */ });
  }
  if (clip.status === 'READY_TO_SEND') {
    return fetch('/api/type', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text: clip.text, auto_enter: !!clip.autoEnter})})
      .then(function(r){ if (r.ok) { clip.status = 'SENT'; return putClip(db, clip); } })
      .catch(function(){ /* still no locked window / no signal -- retry next sync */ });
  }
  return Promise.resolve();
}

self.addEventListener('sync', function(e){
  if (e.tag === 'alma-mic-flush') { e.waitUntil(swFlush()); }
});
// Some Android/Chrome builds fire periodicsync instead when registered;
// harmless to also listen for it under the same tag.
self.addEventListener('periodicsync', function(e){
  if (e.tag === 'alma-mic-flush') { e.waitUntil(swFlush()); }
});
"""


PAGE_HTML = r"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#0b0f13">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon-192.png">
<link rel="icon" href="/icon-192.png">
<title>קשב מהטלפון</title>
<style>
  :root{color-scheme:dark;}
  *{box-sizing:border-box;}
  body{background:#0b0f13;color:#E8F0F5;font-family:"Segoe UI",Arial,sans-serif;
       margin:0;padding:16px;max-width:520px;margin:0 auto;-webkit-tap-highlight-color:transparent;}
  h1{font-size:19px;margin:4px 0 10px;display:flex;align-items:center;justify-content:space-between;gap:8px;}
  h1 span.t{flex:1;}
  #gearBtn{background:#151b21;border:1px solid #2a3540;border-radius:10px;width:40px;height:40px;
           font-size:18px;padding:0;flex:none;}
  #status{font-size:13px;color:#8aa0b0;margin-bottom:10px;line-height:1.6;min-height:20px;}
  #callBanner{background:#5d3b00;color:#ffd699;border:1px solid #a86a00;border-radius:10px;
              padding:10px 12px;font-size:14px;margin-bottom:10px;line-height:1.5;}
  #lockRow{display:flex;gap:8px;margin-bottom:14px;}
  select{flex:1;font-size:15px;padding:10px;border-radius:8px;background:#151b21;
         color:#E8F0F5;border:1px solid #2a3540;min-width:0;}
  button{font-size:16px;padding:10px 14px;border-radius:8px;border:none;
         background:#1b5e20;color:#fff;}
  #micBtn{display:flex;flex-direction:column;align-items:center;justify-content:center;
          width:100%;height:170px;font-size:22px;font-weight:bold;
          border-radius:24px;background:#1b5e20;color:#fff;border:none;margin:14px 0;
          touch-action:manipulation;user-select:none;-webkit-user-select:none;gap:6px;}
  #micBtn.rec{background:#b71c1c;}
  #micBtn.paused{background:#5d3b00;color:#ffd699;}
  #micBtn .glyph{font-size:40px;}
  #micBtn .sub{font-size:13px;font-weight:normal;opacity:.85;}
  #micTimer{font-variant-numeric:tabular-nums;font-size:15px;}
  #secondaryRow{display:flex;gap:8px;margin:4px 0 10px;}
  #secondaryRow button{flex:1;background:#151b21;border:1px solid #2a3540;color:#E8F0F5;}
  #secondaryRow button:disabled{opacity:.4;}
  #queueBadge{display:inline-block;background:#0d47a1;color:#fff;font-size:12px;
              border-radius:999px;padding:3px 10px;margin-bottom:8px;}
  #heard{background:#151b21;border-radius:12px;padding:16px;font-size:22px;
         min-height:56px;margin:12px 0;line-height:1.5;}
  #heard.err{color:#ff8a80;}
  #sendRow{display:flex;gap:8px;}
  #sendBtn{flex:2;height:60px;font-size:19px;background:#0d47a1;}
  #sendBtn:disabled{background:#2a3540;color:#66757f;}
  #discardBtn{flex:1;height:60px;font-size:16px;background:#3a1414;color:#ff8a80;}
  #discardBtn:disabled{opacity:.4;}
  .row{display:flex;gap:8px;align-items:center;margin:10px 0;font-size:14px;color:#8aa0b0;}
  #settingsPanel{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;
                 align-items:flex-end;justify-content:center;z-index:20;}
  #settingsCard{background:#10161c;border-radius:18px 18px 0 0;padding:18px;width:100%;
                max-width:520px;max-height:82vh;overflow-y:auto;}
  #settingsCard h2{font-size:16px;margin:0 0 12px;}
  .field{margin-bottom:14px;}
  .field label{display:block;font-size:13px;color:#8aa0b0;margin-bottom:6px;}
  .field select{width:100%;}
  .hint{font-size:11px;color:#5a6a76;margin-top:4px;}
  .checkline{display:flex;align-items:flex-start;gap:8px;font-size:14px;margin-bottom:14px;}
  #closeSettings{width:100%;background:#1b5e20;margin-top:6px;}
  [hidden]{display:none!important;}
</style>
</head>
<body>
<h1><span class="t">קשב &mdash; הטלפון כמיקרופון</span><button id="gearBtn" title="הגדרות">&#9881;&#65039;</button></h1>
<div id="status">טוען&hellip;</div>
<div id="callBanner" hidden>&#9208;&#65039; ההקלטה הוקפאה אוטומטית &mdash; יתכן שיחה נכנסת או שהמסך ננעל. לחץ על המיקרופון כדי להמשיך.</div>

<div id="lockRow">
  <select id="winSelect"><option>טוען חלונות&hellip;</option></select>
  <button id="lockBtn">נעל&nbsp;&#128274;</button>
</div>

<div id="queueBadge" hidden></div>

<button id="micBtn">
  <span class="glyph" id="micGlyph">&#127908;</span>
  <span class="sub" id="micLabel">לחץ כדי להתחיל להקליט</span>
  <span id="micTimer" hidden>0:00</span>
</button>

<div id="secondaryRow">
  <button id="pauseBtn" disabled>&#9208;&#65039; השהה</button>
</div>

<div id="heard">&hellip;</div>
<div class="row"><label><input type="checkbox" id="autoEnter" checked> Enter אחרי השליחה</label></div>
<div id="sendRow">
  <button id="sendBtn" disabled>שלח לחלון הנעול &#9166;</button>
  <button id="discardBtn" disabled>&#128465;&#65039; מחק</button>
</div>

<div id="settingsPanel" hidden>
  <div id="settingsCard">
    <h2>הגדרות (נשמר בטלפון הזה בלבד)</h2>

    <div class="field">
      <label for="setDecoder">מנוע זיהוי דיבור</label>
      <select id="setDecoder">
        <option value="auto">אוטומטי (ברירת מחדל)</option>
        <option value="eran1">eran1</option>
        <option value="eran2">eran2</option>
        <option value="pc">המחשב (KESHEV)</option>
      </select>
      <div class="hint">נשלח לשרת כהעדפה &mdash; הבחירה בפועל בין המנועים היא בצד המחשב.</div>
    </div>

    <div class="field">
      <label for="setLang">שפת ההכתבה</label>
      <select id="setLang">
        <option value="he">עברית</option>
        <option value="en">English</option>
      </select>
    </div>

    <div class="checkline">
      <input type="checkbox" id="setAutoSend">
      <label for="setAutoSend">שלח אוטומטית בלי לבדוק (ברירת מחדל: כבוי &mdash; תמיד רואים את הטקסט לפני שליחה)</label>
    </div>

    <div class="field">
      <label for="setOnCall">כשיש שיחה נכנסת / הפרעה באמצע הקלטה</label>
      <select id="setOnCall">
        <option value="send">שמור ושלח את מה שכבר הוקלט</option>
        <option value="discard">מחק את הקטע האחרון</option>
      </select>
    </div>

    <button id="closeSettings">סגור</button>
  </div>
</div>

<script>
(function(){
  var statusEl = document.getElementById('status');
  var callBanner = document.getElementById('callBanner');
  var winSelect = document.getElementById('winSelect');
  var lockBtn = document.getElementById('lockBtn');
  var micBtn = document.getElementById('micBtn');
  var micGlyph = document.getElementById('micGlyph');
  var micLabel = document.getElementById('micLabel');
  var micTimer = document.getElementById('micTimer');
  var pauseBtn = document.getElementById('pauseBtn');
  var queueBadge = document.getElementById('queueBadge');
  var heardEl = document.getElementById('heard');
  var sendBtn = document.getElementById('sendBtn');
  var discardBtn = document.getElementById('discardBtn');
  var autoEnter = document.getElementById('autoEnter');
  var gearBtn = document.getElementById('gearBtn');
  var settingsPanel = document.getElementById('settingsPanel');
  var closeSettings = document.getElementById('closeSettings');
  var setDecoder = document.getElementById('setDecoder');
  var setLang = document.getElementById('setLang');
  var setAutoSend = document.getElementById('setAutoSend');
  var setOnCall = document.getElementById('setOnCall');

  // ---------------- settings: per-device, localStorage only ----------------
  var SETTINGS_KEY = 'almaMic.settings.v1';
  var settings = {decoder:'auto', lang:'he', autoSend:false, onCall:'send'};
  (function loadSettings(){
    try {
      var raw = localStorage.getItem(SETTINGS_KEY);
      if (raw) { var s = JSON.parse(raw); for (var k in settings) { if (k in s) settings[k] = s[k]; } }
    } catch(e){}
    setDecoder.value = settings.decoder;
    setLang.value = settings.lang;
    setAutoSend.checked = !!settings.autoSend;
    setOnCall.value = settings.onCall;
  })();
  function saveSettings(){
    settings.decoder = setDecoder.value;
    settings.lang = setLang.value;
    settings.autoSend = setAutoSend.checked;
    settings.onCall = setOnCall.value;
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch(e){}
  }
  [setDecoder, setLang, setAutoSend, setOnCall].forEach(function(el){ el.addEventListener('change', saveSettings); });
  gearBtn.onclick = function(){ settingsPanel.hidden = false; };
  closeSettings.onclick = function(){ settingsPanel.hidden = true; };

  // ---------------- recording state ----------------
  var isRecording = false;      // true ONLY while a MediaRecorder is actively capturing
  var stream = null, recorder = null, chunks = [];
  var timerStart = 0, timerHandle = null;
  var discardNextClip = false;  // set right before an on-call "discard" stop

  function setStatus(t){ statusEl.textContent = t; }

  function refreshStatus(){
    fetch('/api/status').then(function(r){ return r.json(); }).then(function(j){
      setStatus(j.locked ? ('נעול על: ' + j.title) : 'לא נעול על שום חלון — בחר חלון למטה ולחץ נעל');
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

  // ---------------- mic UI states ----------------
  function setMicIdle(){
    isRecording = false;
    micBtn.classList.remove('rec'); micBtn.classList.remove('paused');
    micGlyph.textContent = '\u{1F399}️';
    micLabel.textContent = 'לחץ כדי להתחיל להקליט';
    micTimer.hidden = true;
    pauseBtn.disabled = true;
    stopTimerDisplay();
  }
  function setMicRecording(){
    micBtn.classList.add('rec'); micBtn.classList.remove('paused');
    micGlyph.textContent = '\u{1F534}';
    micLabel.textContent = 'מקליט… לחץ לעצירה';
    micTimer.hidden = false;
    pauseBtn.disabled = false;
    startTimerDisplay();
  }
  function setMicPausedBySystem(){
    micBtn.classList.remove('rec'); micBtn.classList.add('paused');
    micGlyph.textContent = '⏸️';
    micLabel.textContent = 'מושהה — לחץ כדי להמשיך';
    micTimer.hidden = true;
    pauseBtn.disabled = true;
    stopTimerDisplay();
  }
  function startTimerDisplay(){
    timerStart = Date.now();
    stopTimerDisplay();
    timerHandle = setInterval(function(){
      var s = Math.floor((Date.now() - timerStart) / 1000);
      var m = Math.floor(s / 60); s = s % 60;
      micTimer.textContent = m + ':' + (s < 10 ? '0' : '') + s;
    }, 250);
  }
  function stopTimerDisplay(){ if (timerHandle) { clearInterval(timerHandle); timerHandle = null; } }

  // ---------------- getUserMedia / MediaRecorder ----------------
  function startRecording(){
    if (isRecording) return;
    callBanner.hidden = true;
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
      isRecording = true;
      setMicRecording();
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
    // Two rules now, and neither is negotiable (AUDIO PROTECTION LAW), and
    // 2026-09-12 adds a third that follows from the same law:
    //   1. plain {audio:true} -- nothing that asks Android for the voice path.
    //   2. the stream is opened per clip and RELEASED the moment the clip ends
    //      (releaseMic) -- the mic is open only while he is actively recording.
    //   3. ANY interruption signal (page hidden, screen locked, a track ending
    //      on its own -- see handleInterruption below) releases it immediately
    //      too, and NEVER auto-resumes. Only his own tap opens it again.
    // ------------------------------------------------------------------
    navigator.mediaDevices.getUserMedia({audio:true})
      .then(function(s){
        stream = s;
        s.getTracks().forEach(function(t){
          t.addEventListener('ended', function(){ handleInterruption('track-ended'); });
        });
        go();
      })
      .catch(function(e){ releaseMic(); setMicIdle(); heardEl.textContent = 'אין גישה למיקרופון: ' + e; });
  }

  function releaseMic(){
    // Every track, every time. A track left live is a microphone left open, and
    // on Android that is his music in telephone quality.
    if (stream) {
      try { stream.getTracks().forEach(function(t){ t.stop(); }); } catch(e){}
    }
    stream = null;
  }

  function stopRecording(){
    if (recorder && recorder.state !== 'inactive') { recorder.stop(); }
    else { isRecording = false; releaseMic(); setMicIdle(); }
  }

  function onRecStop(){
    releaseMic();               // the clip is finished: give the microphone back NOW
    isRecording = false;
    var blob = new Blob(chunks, {type: (recorder && recorder.mimeType) || 'audio/webm'});
    if (discardNextClip) {
      discardNextClip = false;
      setMicIdle();
      heardEl.textContent = '\u{1F5D1}️ הקטע האחרון נמחק (הפרעה)';
      return;
    }
    setMicIdle();
    queueClip(blob);
  }

  micBtn.addEventListener('click', function(){ if (isRecording) { stopRecording(); } else { startRecording(); } });
  pauseBtn.addEventListener('click', function(){ if (isRecording) stopRecording(); });

  // ---------------- auto-pause on call / interruption ----------------
  function handleInterruption(reason){
    if (isRecording) {
      if (settings.onCall === 'discard') { discardNextClip = true; }
      stopRecording();          // finalizes the segment -> onRecStop -> queue or discard
    } else {
      releaseMic();              // belt and braces: never leave a stream open
    }
    setMicPausedBySystem();
    callBanner.hidden = false;
  }
  document.addEventListener('visibilitychange', function(){
    if (document.hidden) { handleInterruption('hidden'); }
    else { flushQueue(); refreshStatus(); loadWindows(); }
  });
  window.addEventListener('pagehide', function(){ handleInterruption('pagehide'); });

  // ---------------- offline-safe queue (IndexedDB) ----------------
  var DB_NAME = 'alma-mic-queue', STORE = 'clips';
  function openDB(){
    return new Promise(function(resolve, reject){
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function(){ req.result.createObjectStore(STORE, {keyPath:'id', autoIncrement:true}); };
      req.onsuccess = function(){ resolve(req.result); };
      req.onerror = function(){ reject(req.error); };
    });
  }
  function dbAdd(clip){
    return openDB().then(function(db){ return new Promise(function(resolve, reject){
      var tx = db.transaction(STORE, 'readwrite');
      var req = tx.objectStore(STORE).add(clip);
      req.onsuccess = function(){ resolve(req.result); };
      req.onerror = function(){ reject(req.error); };
    }); });
  }
  function dbPut(clip){
    return openDB().then(function(db){ return new Promise(function(resolve, reject){
      var tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(clip);
      tx.oncomplete = function(){ resolve(); };
      tx.onerror = function(){ reject(tx.error); };
    }); });
  }
  function dbDelete(id){
    return openDB().then(function(db){ return new Promise(function(resolve, reject){
      var tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = function(){ resolve(); };
      tx.onerror = function(){ reject(tx.error); };
    }); });
  }
  function dbAll(){
    return openDB().then(function(db){ return new Promise(function(resolve, reject){
      var tx = db.transaction(STORE, 'readonly');
      var req = tx.objectStore(STORE).getAll();
      req.onsuccess = function(){ resolve(req.result || []); };
      req.onerror = function(){ reject(req.error); };
    }); });
  }

  function requestBackgroundSync(){
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      navigator.serviceWorker.ready.then(function(reg){ return reg.sync.register('alma-mic-flush'); }).catch(function(){});
    }
  }

  // Statuses: QUEUED (blob only, not yet decoded) -> READY (has text, his tap
  // decides) or READY_TO_SEND (auto-send is on) -> deleted once truly SENT.
  // FAILED (decode came back empty/error) is kept, never silently dropped.
  function queueClip(blob){
    var clip = {
      status: 'QUEUED', blob: blob, mime: blob.type || 'audio/webm', createdAt: Date.now(),
      lang: settings.lang, decoder: settings.decoder, autoSend: settings.autoSend, autoEnter: autoEnter.checked
    };
    return dbAdd(clip).then(function(){ flushQueue(); renderQueue(); }).catch(function(e){
      heardEl.classList.add('err'); heardEl.textContent = 'שגיאה בשמירת ההקלטה: ' + e;
    });
  }

  var flushing = false;
  function flushQueue(){
    if (flushing) return;
    flushing = true;
    dbAll().then(function(clips){
      clips.sort(function(a, b){ return a.id - b.id; });
      var chain = Promise.resolve();
      clips.forEach(function(c){ chain = chain.then(function(){ return flushOne(c); }); });
      return chain;
    }).catch(function(){}).then(function(){
      flushing = false;
      renderQueue();
      dbAll().then(function(clips){
        var stillPending = clips.some(function(c){ return c.status === 'QUEUED' || c.status === 'READY_TO_SEND'; });
        if (stillPending) requestBackgroundSync();
      }).catch(function(){});
    });
  }

  function flushOne(clip){
    if (clip.status === 'QUEUED') {
      var headers = {'Content-Type': clip.mime};
      if (clip.lang) headers['X-Alma-Lang'] = clip.lang;
      if (clip.decoder) headers['X-Alma-Decoder'] = clip.decoder;
      return fetch('/api/stt', {method:'POST', headers: headers, body: clip.blob})
        .then(function(r){ return r.json().then(function(j){ return [r.ok, j]; }); })
        .then(function(pair){
          var ok = pair[0], j = pair[1];
          if (ok && j.text) {
            clip.text = j.text;
            clip.status = clip.autoSend ? 'READY_TO_SEND' : 'READY';
            return dbPut(clip);
          } else if (ok) {
            clip.status = 'FAILED'; clip.error = j.reason || 'לא זוהה דיבור';
            return dbPut(clip);
          }
          // network/server hiccup -- leave QUEUED, next flush (or the
          // service worker's Background Sync) will retry it.
        })
        .catch(function(){ /* offline -- leave QUEUED */ })
        .then(function(){ if (clip.status === 'READY_TO_SEND') { return flushOne(clip); } });
    }
    if (clip.status === 'READY_TO_SEND') {
      return fetch('/api/type', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({text: clip.text, auto_enter: !!clip.autoEnter})})
        .then(function(r){ return r.json().then(function(j){ return [r.ok, j]; }); })
        .then(function(pair){
          var ok = pair[0];
          if (ok) { return dbDelete(clip.id); }
          clip.status = 'READY'; clip.error = pair[1].error || pair[1].error_he || '';
          return dbPut(clip);   // could not send (e.g. no window locked yet) -- fall back to
        })                      // manual review, never silently lost.
        .catch(function(){ /* offline -- leave READY_TO_SEND, retry later */ });
    }
    return Promise.resolve();
  }

  // ---------------- review UI: the oldest clip that needs his attention ----------------
  function renderQueue(){
    dbAll().then(function(clips){
      clips.sort(function(a, b){ return a.id - b.id; });
      var pending = clips.filter(function(c){ return c.status !== 'SENT'; });
      if (pending.length === 0) { queueBadge.hidden = true; }
      else { queueBadge.hidden = false; queueBadge.textContent = pending.length + ' בהמתנה בתור'; }

      if (isRecording) return; // don't clobber the live "recording..." view

      var showable = clips.find(function(c){ return c.status === 'READY' || c.status === 'FAILED'; });
      if (showable) {
        heardEl.classList.toggle('err', showable.status === 'FAILED');
        if (showable.status === 'READY') { heardEl.textContent = showable.text; sendBtn.disabled = false; }
        else { heardEl.textContent = '⚠️ ' + (showable.error || 'זיהוי נכשל') + ' (מחק, או המתן לניסיון נוסף)'; sendBtn.disabled = true; }
        discardBtn.disabled = false;
        window.__currentClipId = showable.id;
      } else if (clips.some(function(c){ return c.status === 'QUEUED' || c.status === 'READY_TO_SEND'; })) {
        heardEl.classList.remove('err');
        heardEl.textContent = '⏳ מזהה דיבור… (' + pending.length + ' בתור)';
        sendBtn.disabled = true; discardBtn.disabled = true; window.__currentClipId = null;
      } else {
        heardEl.classList.remove('err');
        heardEl.textContent = '…';
        sendBtn.disabled = true; discardBtn.disabled = true; window.__currentClipId = null;
      }
    }).catch(function(){});
  }

  sendBtn.onclick = function(){
    var id = window.__currentClipId;
    if (!id) return;
    sendBtn.disabled = true;
    dbAll().then(function(clips){
      var clip = clips.find(function(c){ return c.id === id; });
      if (!clip) return;
      clip.autoEnter = autoEnter.checked;
      clip.status = 'READY_TO_SEND';
      return dbPut(clip).then(function(){ return flushOne(clip); });
    }).then(renderQueue);
  };
  discardBtn.onclick = function(){
    var id = window.__currentClipId;
    if (!id) return;
    dbDelete(id).then(renderQueue);
  };

  // ---------------- reconnect triggers ----------------
  window.addEventListener('online', function(){ setStatus('החיבור חזר — שולח מה שהצטבר…'); flushQueue(); refreshStatus(); });
  setInterval(flushQueue, 15000);

  // ---------------- PWA install + offline shell ----------------
  if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(function(){}); }

  // ---------------- test-only hooks. These NEVER open a real microphone: ----
  // simulateActiveRecording fakes a stream object so interruption handling
  // can be proven without navigator.mediaDevices.getUserMedia ever being
  // called, and injectFakeClip pushes a synthetic Blob straight into the
  // queue so the offline/reconnect path can be proven against a mocked
  // fetch instead of a real recording.
  window.__almaMicTest = {
    getState: function(){ return {isRecording: isRecording, hasStream: !!stream, settings: settings}; },
    forceInterruption: function(reason){ handleInterruption(reason || 'test'); },
    simulateActiveRecording: function(){
      isRecording = true;
      stream = {getTracks: function(){ return [{stopped:false, stop: function(){ this.stopped = true; }}]; }, __fakeTracks:null};
      stream.__fakeTracks = stream.getTracks();
      setMicRecording();
    },
    injectFakeClip: function(){
      var blob = new Blob(['test-clip-bytes'], {type:'audio/webm'});
      return queueClip(blob);
    },
    flushNow: flushQueue,
    dbAll: dbAll
  };

  setMicIdle();
  refreshStatus();
  loadWindows();
  flushQueue();
  renderQueue();
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

    def _send_bytes(self, status, content_type, data, cache_seconds=0):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cache_seconds:
            self.send_header("Cache-Control", f"public, max-age={cache_seconds}")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

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
            # ---- PWA installability assets (phone-side only, 2026-09-12) ----
            if self.path == "/manifest.json":
                body = json.dumps(_pwa_manifest(), ensure_ascii=False).encode("utf-8")
                self._send_bytes(200, "application/manifest+json; charset=utf-8", body)
                return
            if self.path == "/sw.js":
                self._send_bytes(200, "application/javascript; charset=utf-8", SW_JS.encode("utf-8"))
                return
            if self.path == "/icon-192.png":
                self._send_bytes(200, "image/png", ICON_192_PNG, cache_seconds=86400)
                return
            if self.path == "/icon-512.png":
                self._send_bytes(200, "image/png", ICON_512_PNG, cache_seconds=86400)
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
