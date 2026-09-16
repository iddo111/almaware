#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alma_web.py - the ALMA-OS T-Deck simulator, in the browser.

Runs sim/alma_sim.exe (Iddo's real firmware compiled against a virtual T-Deck)
and puts its 320x240 panel on http://127.0.0.1:8864/ , with the Q10 keyboard,
the trackball and the LoRa air wired to the page.

Pure stdlib: http.server only. No Flask, no framework, no CDN - the same
purity rule the firmware itself follows.

לזכרה של עלמה ז"ל · ALMAWARE
"""
import http.server
import json
import socketserver
import subprocess
import threading
import os
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(ROOT, "alma_sim.exe")
PORT = int(os.environ.get("ALMA_SIM_PORT", "8864"))

_proc = None
_lock = threading.Lock()


def start_sim():
    """Launch the firmware simulator at below-normal priority."""
    global _proc
    env = dict(os.environ)
    env["PATH"] = r"C:\msys64\usr\bin;" + env.get("PATH", "")
    flags = 0
    if hasattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS"):
        flags |= subprocess.BELOW_NORMAL_PRIORITY_CLASS
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    _proc = subprocess.Popen(
        [EXE, ROOT], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=env, cwd=ROOT, creationflags=flags)
    return _proc


def send_cmd(line):
    with _lock:
        if _proc and _proc.poll() is None:
            try:
                _proc.stdin.write((line + "\n").encode("utf-8"))
                _proc.stdin.flush()
                return True
            except Exception:
                return False
    return False


PAGE = """<!doctype html>
<html lang="he"><head><meta charset="utf-8">
<title>ALMA-OS · T-Deck Simulator</title>
<style>
 body{background:#0e1116;color:#e8eef7;font-family:Segoe UI,system-ui,sans-serif;
      margin:0;padding:18px;display:flex;gap:22px;flex-wrap:wrap}
 h1{font-size:19px;margin:0 0 2px 0;font-weight:600}
 .sub{font-size:12px;color:#8b98ab;margin-bottom:14px}
 .deck{background:#1b2029;border:1px solid #2c3444;border-radius:14px;padding:14px}
 #screen{image-rendering:pixelated;width:960px;height:720px;max-width:100%;display:block;
         border-radius:4px;background:#000}
 .wrap{position:relative;display:inline-block}
 #sleep{position:absolute;inset:0;display:none;align-items:center;justify-content:center;
        border-radius:4px;cursor:pointer;background:rgba(6,9,14,.55)}
 #sleep div{background:#0a58c8;color:#fff;padding:12px 20px;border-radius:9px;
        font-size:14px;text-align:center;line-height:1.6;box-shadow:0 6px 24px #000a}
 .col{min-width:330px;max-width:420px}
 .card{background:#161b23;border:1px solid #262e3b;border-radius:10px;
       padding:12px 14px;margin-bottom:12px}
 .card h2{font-size:13px;margin:0 0 8px 0;color:#7fb0ff;font-weight:600;
          text-transform:uppercase;letter-spacing:.5px}
 button{background:#222b38;color:#dce6f5;border:1px solid #36435a;border-radius:7px;
        padding:7px 12px;font-size:13px;cursor:pointer;margin:2px}
 button:hover{background:#2d3a4d}
 button.on{background:#0a58c8;border-color:#0a58c8;color:#fff}
 input[type=text]{background:#0e1319;color:#e8eef7;border:1px solid #36435a;
        border-radius:7px;padding:7px 10px;font-size:13px;width:100%;box-sizing:border-box}
 pre{background:#0b0f14;border:1px solid #222a36;border-radius:7px;padding:9px;
     font-size:11.5px;line-height:1.45;max-height:170px;overflow:auto;margin:0;
     white-space:pre-wrap;word-break:break-all}
 table{font-size:12px;border-collapse:collapse;width:100%}
 td{padding:2px 4px} td:first-child{color:#8b98ab}
 .kbmap{font-size:11px;color:#9fb0c6;line-height:1.7;direction:ltr}
 .kbmap b{color:#e8eef7;font-weight:600}
 .hint{font-size:11.5px;color:#8b98ab;margin-top:6px;line-height:1.5}
 .warn{color:#ffb648}
 .focus{outline:2px solid #0a58c8}
</style></head><body>

<div>
 <h1>ALMA-OS · T-Deck &mdash; סימולטור / Simulator</h1>
 <div class="sub">
   הקושחה האמיתית שלך רצה מול חומרה וירטואלית &middot; לחץ על המסך וכתוב<br>
   Your real firmware running against virtual hardware &middot; click the screen and type
 </div>
 <div class="deck"><div class="wrap"><img id="screen" src="/frame.bmp" tabindex="0">
   <div id="sleep"><div>המסך נרדם אחרי 60 שניות &mdash; לחץ להעיר<br>
     <span style="font-size:12px;opacity:.85">his own power-save: backlight off after 60 s idle &mdash; click to wake</span></div></div>
 </div></div>
 <div class="hint">
   המקלדת: לחץ על המסך ואז הקלד. הפריסה העברית היא <b>של ALMA-OS</b>, לא של ווינדוס.<br>
   Keyboard: click the screen, then type. The Hebrew layout is <b>ALMA-OS's own</b>, not Windows'.
 </div>
</div>

<div class="col">
 <div class="card">
  <h2>כדור-מסלול / Trackball</h2>
  <button onclick="cmd('TB L')">&#9664; שמאלה</button>
  <button onclick="cmd('TB R')">ימינה &#9654;</button>
  <button onclick="cmd('TB U')">&#9650;</button>
  <button onclick="cmd('TB D')">&#9660;</button>
  <button onclick="cmd('TB C')">&#9679; לחיצה / click</button>
  <div class="hint">שמאלה/ימינה מחליף כרטיס (צ'אט &harr; מערכת).<br>Left/right switches card.</div>
 </div>

 <div class="card">
  <h2>מקשים / Keys</h2>
  <button onclick="cmd('K 13')">&#9166; Enter</button>
  <button onclick="cmd('K 8')">&#9003; Backspace</button>
  <button onclick="cmd('K 36')">$ &mdash; עברית/English</button>
 </div>

 <div class="card">
  <h2>האוויר / The LoRa air</h2>
  <input type="text" id="rx" placeholder="הודעה מצומת אחר / message from another node">
  <div style="margin-top:6px">
   <button onclick="sendRx()">שדר אליו / Send to him</button>
   <button id="radiobtn" onclick="toggleRadio()">SX1262: מחובר</button>
  </div>
  <div class="hint">
   ה-SX1262 הוא <b>ציוד היקפי מדומה</b> - הוא מוכיח את הפרוטוקול, לא רדיו.<br>
   The SX1262 is a <b>simulated peripheral</b>: it proves the protocol, not RF.
  </div>
 </div>

 <div class="card">
  <h2>מצב / State</h2>
  <table>
   <tr><td>uptime</td><td id="up">-</td></tr>
   <tr><td>תאורה / backlight</td><td id="bl">-</td></tr>
   <tr><td>שודר / frames sent</td><td id="tx">-</td></tr>
   <tr><td>מסגרת ALMA-MESH</td><td id="txhex" style="font-family:Consolas,monospace;font-size:11px">-</td></tr>
   <tr><td>מטען / payload</td><td id="txtxt">-</td></tr>
  </table>
 </div>

 <div class="card">
  <h2>Serial (115200)</h2>
  <pre id="ser">...</pre>
 </div>

 <div class="card">
  <h2>פריסת המקלדת / Hebrew layout</h2>
  <div class="kbmap">
   <b>q</b>/ <b>w</b>&#1523; <b>e</b>&#1511; <b>r</b>&#1512; <b>t</b>&#1488; <b>y</b>&#1496; <b>u</b>&#1493; <b>i</b>&#1503; <b>o</b>&#1501; <b>p</b>&#1508;<br>
   <b>a</b>&#1513; <b>s</b>&#1491; <b>d</b>&#1490; <b>f</b>&#1499; <b>g</b>&#1506; <b>h</b>&#1497; <b>j</b>&#1495; <b>k</b>&#1500; <b>l</b>&#1498; <b>;</b>&#1507;<br>
   <b>z</b>&#1494; <b>x</b>&#1505; <b>c</b>&#1489; <b>v</b>&#1492; <b>b</b>&#1504; <b>n</b>&#1502; <b>m</b>&#1510; <b>,</b>&#1514; <b>.</b>&#1509;
  </div>
  <div class="hint">נסה: <b>akuo</b> = &#1513;&#1500;&#1493;&#1501; &middot; ואז Enter.<br>
   שאל את עלמא: <b>?gzrv</b> = ?&#1506;&#1494;&#1512;&#1492;</div>
 </div>
</div>

<script>
var radioOn = true;
function cmd(c){ fetch('/cmd?c=' + encodeURIComponent(c)); }
function sendRx(){
  var v = document.getElementById('rx').value;
  if(v){ cmd('RX ' + v); document.getElementById('rx').value=''; }
}
function toggleRadio(){
  radioOn = !radioOn;
  cmd('RADIO ' + (radioOn ? 1 : 0));
  var b = document.getElementById('radiobtn');
  b.textContent = 'SX1262: ' + (radioOn ? 'מחובר' : 'נותק');
  b.className = radioOn ? '' : 'on';
}

// Physical-key capture. We deliberately use e.code (the PHYSICAL key), so that
// Iddo's Windows Hebrew layout does not pre-translate anything: the ALMA-OS
// layout table in keyboard.h is what turns 'a' into ש.
var PUNCT = {Semicolon:59, Comma:44, Period:46, Slash:47, Quote:39,
             Minus:45, Equal:61, Backquote:96};
var scr = document.getElementById('screen');
var sleepBox = document.getElementById('sleep');
scr.addEventListener('click', function(){ scr.classList.add('focus'); scr.focus(); });
// The trackball centre-click is what wakes a sleeping T-Deck, so that is what
// the overlay sends - the same path the real hardware takes.
sleepBox.addEventListener('click', function(){ cmd('TB C'); scr.classList.add('focus'); scr.focus(); });
document.addEventListener('keydown', function(e){
  if(document.activeElement && document.activeElement.id === 'rx') return;
  var c = e.code, n = 0;
  if(/^Key[A-Z]$/.test(c))        n = c.charCodeAt(3) + 32;      // KeyA -> 'a'
  else if(/^Digit[0-9]$/.test(c)) n = c.charCodeAt(5);
  else if(c === 'Enter')          n = 13;
  else if(c === 'Backspace')      n = 8;
  else if(c === 'Space')          n = 32;
  else if(PUNCT[c] !== undefined) n = PUNCT[c];
  else if(e.key === '$')          n = 36;
  if(n){ e.preventDefault(); cmd('K ' + n); }
});

// panel refresh
setInterval(function(){
  var img = new Image();
  img.onload = function(){ scr.src = img.src; };
  img.src = '/frame.bmp?t=' + Date.now();
}, 140);

setInterval(function(){
  fetch('/status?t=' + Date.now()).then(function(r){return r.json();}).then(function(s){
    document.getElementById('up').textContent  = (s.uptime_ms/1000).toFixed(0) + ' s';
    document.getElementById('bl').textContent  = s.backlight ? 'דולקת / on'
                                                             : 'כבתה (60 שנ׳) / asleep';
    sleepBox.style.display = s.backlight ? 'none' : 'flex';
    document.getElementById('tx').textContent  = s.tx_count;
    document.getElementById('txhex').textContent = s.last_tx_hex || '-';
    document.getElementById('txtxt').textContent = s.last_tx_text || '-';
    document.getElementById('ser').textContent = s.serial || '';
  }).catch(function(){});
}, 600);
</script>
</body></html>
"""


_cache = {}


BMP_BYTES = 14 + 40 + 320 * 240 * 3      # exactly what sim_hw.cpp writes


def _valid(name, data):
    if not data:
        return False
    if name.endswith(".bmp"):
        return len(data) == BMP_BYTES and data[:2] == b"BM"
    try:
        json.loads(data.decode("utf-8"))
        return True
    except Exception:
        return False


def read_retry(name, tries=6):
    """The sim rewrites these files constantly. Serve only a complete file;
    otherwise hand back the last good one rather than a torn frame."""
    path = os.path.join(ROOT, name)
    for _ in range(tries):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if _valid(name, data):
                _cache[name] = data
                return data
        except Exception:
            pass
        time.sleep(0.004)
    return _cache.get(name)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _nocache(self, ctype, body):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)

        if u.path in ("/", "/index.html"):
            self._nocache("text/html; charset=utf-8", PAGE.encode("utf-8"))

        elif u.path == "/frame.bmp":
            data = read_retry("frame.bmp")
            if data:
                self._nocache("image/bmp", data)
            else:
                self.send_error(404)

        elif u.path == "/status":
            data = read_retry("status.json")
            self._nocache("application/json; charset=utf-8", data or b"{}")

        elif u.path == "/cmd":
            c = q.get("c", [""])[0]
            ok = send_cmd(c) if c else False
            self._nocache("text/plain", b"ok" if ok else b"no")

        else:
            self.send_error(404)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def already_running():
    """Double-clicking the shortcut twice should not start a second machine."""
    import socket
    s = socket.socket()
    s.settimeout(0.6)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except Exception:
        return False
    finally:
        s.close()


def main():
    if not os.path.exists(EXE):
        print("alma_sim.exe missing - run build_sim.cmd first")
        sys.exit(1)
    if already_running():
        print("ALMA-OS simulator is already up  ->  http://127.0.0.1:%d/" % PORT)
        print("כבר רץ. הדפדפן נפתח.")
        sys.exit(0)
    # Clear last run's artifacts so the page cannot show a stale machine while
    # this one is still in setup().
    for f in ("status.json", "frame.bmp"):
        try:
            os.remove(os.path.join(ROOT, f))
        except Exception:
            pass
    start_sim()
    time.sleep(0.3)
    with Server(("127.0.0.1", PORT), Handler) as srv:
        print("ALMA-OS simulator  ->  http://127.0.0.1:%d/" % PORT)
        print("Ctrl-C to stop.")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            send_cmd("QUIT")
            time.sleep(0.2)
            try:
                _proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    main()
