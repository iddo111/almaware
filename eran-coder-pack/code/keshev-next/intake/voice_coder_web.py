# -*- coding: utf-8 -*-
"""
VOICE CODER WEB -- hold a button on the phone, speak Hebrew, send it straight
into the Qwen3-Coder-480B. Iddo's ask 2026-09-09 09:13 ("puppeteering").

Same-origin, same shape as phone_mic_web.py (:8893): this one process is both
the page and the only thing the phone talks to. Two server-side legs:

  POST /api/stt    -> phone_mic_web.webm_to_pcm16 + keshev_decoder.transcribe_hebrew_pcm
                      (imported, not copied: byte-identical STT to the live mic)
  POST /api/coder  -> http://127.0.0.1:8875/chat  (taste480 -- keeps its memory,
                      ALMA-RECALL, ALMAWARE standard, RAMCHAT, QUORUM grounding)

The text is shown to Iddo first; HE taps send. Nothing auto-sends.
Binds 127.0.0.1:8894 only -- reached via `tailscale serve --https=8894`.
BELOW_NORMAL. Never opens the PC mic, never restarts taste480 / phone-mic / intake.
"""
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from phone_mic_web import (  # noqa: E402
    webm_to_pcm16, keshev_decoder, MIN_AUDIO_MS, set_priority_below_normal, FFMPEG, STATE_DIR,
)

PORT = int(os.environ.get("VOICECODER_WEB_PORT", "8894"))
BIND_LOOPBACK = "127.0.0.1"
TASTE_CHAT = "http://127.0.0.1:8875/chat"
TASTE_HISTORY = "http://127.0.0.1:8875/history"
CODER_TIMEOUT = 600  # the 480B answers at ~10 tok/s; a long reply is minutes, not seconds
LOG_PATH = os.path.join(STATE_DIR, "voice_coder_web.log")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def taste_call(method, url, body=None, timeout=CODER_TIMEOUT):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 599, {"error": f"{type(e).__name__}: {e}"}


PAGE_HTML = r"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>הקודר בקול</title>
<style>
  :root{color-scheme:dark;}
  *{box-sizing:border-box;}
  html,body{height:100%;}
  body{background:#0b0f13;color:#E8F0F5;font-family:"Segoe UI",Arial,sans-serif;
       margin:0 auto;padding:12px 14px 16px;max-width:560px;display:flex;flex-direction:column;}
  h1{font-size:18px;margin:2px 0 2px;}
  .sub{font-size:12px;color:#8aa0b0;margin-bottom:8px;}
  #thread{flex:1;min-height:120px;overflow-y:auto;border-top:1px solid #1f2a33;padding:8px 0;}
  .msg{max-width:92%;margin:8px 0;padding:10px 12px;border-radius:12px;font-size:15px;line-height:1.5;
       overflow-wrap:anywhere;}
  .msg.user{background:#1f2a33;margin-inline-start:auto;}
  .msg.assistant{background:#151b21;border:1px solid #1f2a33;margin-inline-end:auto;}
  .msg.pending{opacity:.6;font-style:italic;}
  .ptext{white-space:pre-wrap;word-break:break-word;}
  pre.code{background:#0b0f13;border:1px solid #1f2a33;padding:9px;border-radius:8px;overflow-x:auto;
       font-family:ui-monospace,Consolas,monospace;font-size:12.5px;margin:8px 0;
       direction:ltr;text-align:left;white-space:pre;}
  .meta{font-size:11px;color:#66757f;margin-top:5px;}
  #micBtn{display:none;width:100%;height:120px;font-size:24px;font-weight:bold;
          border-radius:20px;background:#1b5e20;color:#fff;border:none;margin:10px 0 8px;
          touch-action:none;user-select:none;-webkit-user-select:none;}
  #micBtn.rec{background:#b71c1c;}
  body.micon #micBtn{display:block;}
  #micRow{display:flex;align-items:center;gap:10px;margin:10px 0 4px;font-size:14px;color:#8aa0b0;}
  #micRow input{width:22px;height:22px;}
  #micWarn{display:none;font-size:12px;color:#ffb74d;line-height:1.45;margin:0 0 6px;}
  body.micon #micWarn{display:block;}
  #micBtn small{display:block;font-size:12px;font-weight:normal;opacity:.8;margin-top:4px;}
  #heard{width:100%;background:#151b21;color:#E8F0F5;border:1px solid #2a3540;border-radius:12px;
         padding:12px;font-size:18px;min-height:64px;line-height:1.45;font-family:inherit;direction:auto;}
  .row{display:flex;gap:8px;margin-top:8px;}
  button.act{flex:1;height:56px;font-size:17px;border-radius:10px;border:none;color:#fff;}
  #sendBtn{background:#0d47a1;flex:2;}
  #sendBtn:disabled{background:#2a3540;color:#66757f;}
  #clearBtn{background:#2a3540;}
  #status{font-size:12px;color:#8aa0b0;min-height:16px;margin-top:6px;}
</style>
</head>
<body>
<h1>&#127908; הקודר הענק בקול</h1>
<div class="sub">Qwen3-Coder-480B · eran2+3+4 · ברירת מחדל: הקלדה. מיקרופון רק אם תפעיל למטה.</div>
<div id="thread"><div class="msg assistant">מחכה. כתוב בתיבה ושלח — או הפעל מיקרופון למטה.</div></div>
<div id="micRow"><input type="checkbox" id="micToggle"><label for="micToggle">מיקרופון (כבוי) — הזיהוי שלנו, לא של גוגל</label></div>
<div id="micWarn">&#9888; בזמן הקלטה אנדרואיד מעביר אוזניות בלוטות׳ לאיכות טלפון והמוזיקה תישבר. המיקרופון משוחרר מיד אחרי כל הקלטה.</div>
<button id="micBtn">החזק ודבר<small>hold · speak · release</small></button>
<textarea id="heard" rows="2" placeholder="מה ששמעתי יופיע כאן — אפשר לתקן לפני שליחה"></textarea>
<div class="row">
  <button id="sendBtn" class="act" disabled>שלח לקודר &#9166;</button>
  <button id="clearBtn" class="act">נקה</button>
</div>
<div id="status"></div>

<script>
(function(){
  var micBtn = document.getElementById('micBtn');
  var heardEl = document.getElementById('heard');
  var sendBtn = document.getElementById('sendBtn');
  var clearBtn = document.getElementById('clearBtn');
  var statusEl = document.getElementById('status');
  var thread = document.getElementById('thread');
  var stream = null, recorder = null, chunks = [], busy = false;
  var recT0 = 0, recTimer = null, holdPointerId = null;
  var micToggle = document.getElementById('micToggle');

  // The mic is OPT-IN. Nothing on this page touches audio until the box is ticked,
  // and the capture stream is released after every clip so a Bluetooth headset
  // flips back from HFP (phone quality) to A2DP (music) immediately.
  function releaseMic(){
    if (stream){ try { stream.getTracks().forEach(function(t){ t.stop(); }); } catch(_){} stream = null; }
  }
  micToggle.addEventListener('change', function(){
    if (micToggle.checked){ document.body.classList.add('micon'); micToggle.nextElementSibling.textContent='מיקרופון (פעיל) — הזיהוי שלנו, לא של גוגל'; }
    else { document.body.classList.remove('micon'); stopRec(); releaseMic(); micToggle.nextElementSibling.textContent='מיקרופון (כבוי) — הזיהוי שלנו, לא של גוגל'; }
  });

  function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function setStatus(t){ statusEl.textContent = t || ''; }
  function tickRec(){
    var s = ((Date.now()-recT0)/1000).toFixed(1);
    micBtn.innerHTML = '&#9679; מקליט ' + s + ' ש׳<small>שחרר כשסיימת</small>';
  }
  function resetMicLabel(){ micBtn.innerHTML = 'החזק ודבר<small>hold · speak · release</small>'; }
  function scrollDown(){ thread.scrollTop = thread.scrollHeight; }

  function renderBody(text){
    var parts=[], last=0, re=/```(\w*)\n?([\s\S]*?)```/g, m;
    while((m=re.exec(text))){
      if(m.index>last) parts.push({code:false,text:text.slice(last,m.index)});
      parts.push({code:true,text:m[2]});
      last=re.lastIndex;
    }
    if(last<text.length) parts.push({code:false,text:text.slice(last)});
    return parts.map(function(p){ return p.code
      ? '<pre class="code">'+esc(p.text)+'</pre>'
      : '<div class="ptext" dir="auto">'+esc(p.text)+'</div>'; }).join('');
  }
  function bubble(role, content, meta){
    var d=document.createElement('div');
    d.className='msg '+role;
    d.innerHTML=renderBody(content)+(meta?'<div class="meta">'+esc(meta)+'</div>':'');
    thread.appendChild(d); scrollDown(); return d;
  }
  function updateSend(){ sendBtn.disabled = busy || !heardEl.value.trim(); }
  heardEl.addEventListener('input', updateSend);

  function startRec(){
    if (busy) return;
    var go=function(){
      chunks=[];
      var opts={};
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) opts.mimeType='audio/webm;codecs=opus';
      recorder=new MediaRecorder(stream, opts);
      recorder.ondataavailable=function(e){ if(e.data && e.data.size) chunks.push(e.data); };
      recorder.onstop=onRecStop;
      recorder.start();
      micBtn.classList.add('rec');
      recT0 = Date.now(); tickRec();
      recTimer = setInterval(tickRec, 100);
      setStatus('מקליט… תמשיך להחזיק');
    };
    if (!micToggle.checked){ setStatus('המיקרופון כבוי — הפעל אותו למעלה אם אתה רוצה לדבר'); return; }
    if (stream){ go(); return; }
    // plain {audio:true}: the echoCancellation/noiseSuppression constraints push Android
    // onto the VOICE_COMMUNICATION path, the one that forces the Bluetooth HFP switch.
    navigator.mediaDevices.getUserMedia({audio:true})
      .then(function(s){ stream=s; go(); })
      .catch(function(e){ setStatus('אין גישה למיקרופון: '+e); });
  }
  function stopRec(){
    if (recTimer){ clearInterval(recTimer); recTimer=null; }
    if (recorder && recorder.state!=='inactive') recorder.stop();
    micBtn.classList.remove('rec');
    resetMicLabel();
    holdPointerId = null;
  }
  function onRecStop(){
    releaseMic();  // give the headset its music back before we even wait for the decoder
    setStatus('שולח לזיהוי…');
    var blob=new Blob(chunks,{type:(recorder.mimeType||'audio/webm')});
    fetch('/api/stt',{method:'POST',headers:{'Content-Type':blob.type},body:blob})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if (j.text){
          heardEl.value = (heardEl.value.trim() ? heardEl.value.trim()+' ' : '') + j.text;
          setStatus('זוהה ב-'+(j.latency_ms||'?')+' ms — תקן אם צריך, ואז שלח');
        } else if (j.reason === 'too_short'){
          setStatus('זו הייתה לחיצה ('+(j.duration_ms||0)+' ms) — צריך להחזיק את הכפתור בזמן שמדברים. תראה את המונה רץ.');
        } else {
          setStatus('לא זוהה דיבור — נסה שוב '+(j.reason||''));
        }
        updateSend();
      })
      .catch(function(e){ setStatus('שגיאת זיהוי: '+e); });
  }
  // hold semantics that survive a phone: capture the pointer so a finger that
  // drifts off the button keeps the hold alive; kill the long-press menu.
  micBtn.addEventListener('contextmenu', function(e){ e.preventDefault(); });
  micBtn.addEventListener('pointerdown', function(e){
    e.preventDefault();
    holdPointerId = e.pointerId;
    try { micBtn.setPointerCapture(e.pointerId); } catch(_){}
    startRec();
  });
  micBtn.addEventListener('pointerup', function(e){ if (holdPointerId===null || e.pointerId===holdPointerId) stopRec(); });
  micBtn.addEventListener('pointercancel', function(e){ if (holdPointerId===null || e.pointerId===holdPointerId) stopRec(); });
  micBtn.addEventListener('lostpointercapture', function(e){ if (holdPointerId!==null && e.pointerId===holdPointerId) stopRec(); });

  clearBtn.onclick=function(){ heardEl.value=''; updateSend(); setStatus(''); };

  sendBtn.onclick=function(){
    var text=heardEl.value.trim();
    if(!text || busy) return;
    busy=true; updateSend();
    bubble('user', text);
    heardEl.value='';
    var pending=bubble('assistant pending', 'חושב… (480B — יכול לקחת דקה)');
    setStatus('הקודר עובד…');
    fetch('/api/coder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})})
      .then(function(r){ return r.json(); })
      .then(function(j){
        pending.remove();
        if (j.error){ bubble('assistant', 'שגיאה: '+j.error); }
        else { bubble('assistant', j.reply||'(תשובה ריקה)', (j.completion_tokens||'?')+' tokens · '+(j.dt||'?')+'s'); }
        setStatus('');
      })
      .catch(function(e){ pending.remove(); bubble('assistant','שגיאת רשת: '+e); setStatus(''); })
      .then(function(){ busy=false; updateSend(); });
  };

  // last few turns of the shared conversation, so the phone shows where the PC left off
  fetch('/api/history').then(function(r){return r.json();}).then(function(j){
    var msgs=(j.messages||[]).slice(-6);
    if(!msgs.length) return;
    thread.innerHTML='';
    msgs.forEach(function(m){ bubble(m.role==='user'?'user':'assistant', m.content||''); });
  }).catch(function(){});
})();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "VoiceCoderWeb/1.0"

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
                st, taste = taste_call("GET", "http://127.0.0.1:8875/health", timeout=5)
                self._send_json(200, {"ok": True, "service": "voice-coder-web", "pid": os.getpid(),
                                       "ffmpeg": bool(FFMPEG), "taste480": taste if st == 200 else {"unreachable": st}})
                return
            if self.path == "/api/history":
                st, resp = taste_call("GET", TASTE_HISTORY, timeout=10)
                self._send_json(st, resp)
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            log(f"GET {self.path} error: {e}\n{traceback.format_exc()}")
            self._send_json(500, {"error": str(e)})

    def do_POST(self):
        try:
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
                    log(f"STT too_short duration_ms={duration_ms} in_bytes={len(raw)} (a tap, not a hold)")
                    self._send_json(200, {"ok": True, "text": "", "reason": "too_short", "duration_ms": duration_ms})
                    return
                ok, text, lang, avg_logprob = keshev_decoder.transcribe_hebrew_pcm(pcm)
                latency_ms = round((time.time() - t0) * 1000, 1)
                log(f"STT ok={ok} text={text!r} lang={lang} avg_logprob={avg_logprob} duration_ms={duration_ms} latency_ms={latency_ms}")
                self._send_json(200 if ok else 502, {"ok": ok, "text": text, "lang": lang,
                                                       "avg_logprob": avg_logprob, "duration_ms": duration_ms,
                                                       "latency_ms": latency_ms})
                return
            if self.path == "/api/coder":
                try:
                    body = json.loads(self._read_body() or b"{}")
                except Exception:
                    body = {}
                msg = str(body.get("message", "")).strip()[:6000]
                if not msg:
                    self._send_json(400, {"error": "empty message"})
                    return
                log(f"coder <- {msg[:80]!r}")
                t0 = time.time()
                st, resp = taste_call("POST", TASTE_CHAT, {"message": msg})
                log(f"coder -> status={st} dt={round(time.time()-t0,1)}s reply={str(resp.get('reply',''))[:60]!r}")
                self._send_json(st if st < 500 else 502, resp)
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            log(f"POST {self.path} error: {e}\n{traceback.format_exc()}")
            self._send_json(500, {"error": str(e)})


def main():
    set_priority_below_normal()
    log(f"voice-coder-web starting, pid={os.getpid()}, ffmpeg={FFMPEG!r}, "
        f"KESHEV_STT_URL={os.environ.get('KESHEV_STT_URL')!r}, taste={TASTE_CHAT}")
    httpd = ThreadingHTTPServer((BIND_LOOPBACK, PORT), Handler)
    log(f"bound {BIND_LOOPBACK}:{PORT} (reach it via `tailscale serve --https={PORT}`)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
