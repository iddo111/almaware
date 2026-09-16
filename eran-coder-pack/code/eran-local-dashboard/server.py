# ERAN private dashboard — runs on THIS PC, served tailnet-only via `tailscale serve`.
# Gathers live data by SSHing the nodes directly. NOT public.
import http.server, socketserver, subprocess, threading, time, json, socket

# Suppress the console/terminal window Windows pops for each child ssh.exe.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PORT = 8790
STATE = {"json": '{"ts":0,"nodes":[]}'}

GATHER = (
    "nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null | head -1\n"
    "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | head -1\n"
    "awk '{print int($1)}' /proc/uptime 2>/dev/null\n"
    "awk '{print $1}' /proc/loadavg 2>/dev/null\n"
    "pgrep -f 'train.py|eran-live|dgx4_launch|gist|robot_civ' >/dev/null 2>&1 && echo 1 || echo 0\n"
    "cat ~/eran/fleet/eran_live_status.json 2>/dev/null\n"
)

def ssh(host):
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, GATHER],
                           capture_output=True, text=True, timeout=14,
                           creationflags=NO_WINDOW)
        return r.stdout
    except Exception:
        return ""

def num(x, d=0):
    try: return float(str(x).strip())
    except: return d

def node(name, label, host):
    out = ssh(host)
    lines = out.split("\n")
    if not out.strip() or not lines[0].strip():
        return {"name": name, "host": label, "online": False}
    smi = [p.strip() for p in lines[0].split(",")]
    gtemp = int(num(smi[0])); gutil = int(num(smi[1] if len(smi) > 1 else 0))
    gpow = num(smi[2] if len(smi) > 2 else 0)
    soc = num(lines[1] if len(lines) > 1 else 0); soc = int(soc/1000) if soc > 1000 else gtemp
    up = int(num(lines[2] if len(lines) > 2 else 0))
    load = (lines[3].strip() if len(lines) > 3 else "0") or "0"
    train = (lines[4].strip() == "1") if len(lines) > 4 else False
    return {"name": name, "host": label, "online": True, "train": train,
            "gtemp": gtemp, "gutil": gutil, "soc": soc, "gpow": gpow, "load": load, "up": up}

def eran_vitals():
    out = ssh("eran4")
    for ln in out.split("\n"):
        ln = ln.strip()
        if ln.startswith("{") and "step" in ln:
            try: return json.loads(ln)
            except: pass
    return {}

def jetson():
    # Orin Nano over USB gadget (may be down while flashing)
    try:
        s = socket.create_connection(("<lan-ip>", 22), timeout=2); s.close()
        return {"name": "Jetson Orin", "host": "<lan-ip> · USB-C", "online": True, "note": "reachable (SSH)"}
    except Exception:
        return {"name": "Jetson Orin", "host": "<lan-ip> · USB-C", "online": False, "note": "flashing / offline"}

def refresh():
    while True:
        try:
            nodes = [
                node("eran1", "GB10 · 128GB", "eran1"),
                node("eran4", "edgexpert-3636", "eran4"),
                {"name": "eran2", "host": "200G mesh", "online": False},
                {"name": "eran3", "host": "200G mesh", "online": False},
                jetson(),
            ]
            STATE["json"] = json.dumps({"ts": int(time.time()), "eran": eran_vitals(), "nodes": nodes})
        except Exception:
            pass
        time.sleep(5)

PAGE = ("""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ערן · פרטי · Tailscale</title>
<link rel="manifest" href="/manifest.json"><meta name="theme-color" content="#0038b8">
<link rel="apple-touch-icon" href="/icon.svg"><link rel="icon" href="/icon.svg">
<style>
 :root{--blue:#0038b8;--ink:#0b1320;--line:#dbe3f4;--bg:#f5f8ff;--green:#1aa251;--amber:#e8a317;--red:#d6293e;}
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:"Segoe UI","Heebo",Arial,sans-serif;background:var(--bg);color:var(--ink);padding:22px;max-width:1100px;margin:0 auto}
 header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
 h1{font-size:27px;color:var(--blue)} h1 small{font-size:14px;opacity:.6;font-weight:400}
 .lock{font-size:11px;background:#eef3ff;border:1px solid var(--blue);color:var(--blue);border-radius:999px;padding:3px 10px;font-weight:700}
 .stamp{font-size:13px;opacity:.75} .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#c9d3e6;margin-inline-start:6px;animation:p 2s infinite}
 .dot.live{background:var(--green)} @keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
 .lbl{font-size:11px;letter-spacing:.14em;color:var(--blue);opacity:.85;font-weight:700;text-transform:uppercase;margin:24px 0 10px}
 .hero{background:#fff;border:1px solid var(--line);border-top:4px solid var(--blue);border-radius:16px;padding:20px;box-shadow:0 4px 18px rgba(0,56,184,.08)}
 .hero .who{font-size:20px;font-weight:900;color:var(--blue)} .hero .who span{font-size:12px;font-weight:400;opacity:.6}
 .step{font-size:clamp(36px,8vw,58px);font-weight:900;line-height:1.05;margin:8px 0} .step small{font-size:15px;opacity:.5;font-weight:400}
 .hs{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-top:12px}
 .hs div{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
 .hs .k{font-size:11px;opacity:.6} .hs .v{font-size:20px;font-weight:900;color:var(--blue)}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
 .card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 2px 10px rgba(0,56,184,.06)}
 .card.off{opacity:.6;border-style:dashed}
 .ct{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}
 .nm{font-size:18px;font-weight:900;color:var(--blue)} .ho{font-size:11px;opacity:.55}
 .bd{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px} .tr{background:#e7f6ee;color:var(--green)} .id{background:#eef1f7;color:#69748a} .of{background:#fdecee;color:var(--red)}
 .tmp{display:flex;align-items:baseline;gap:6px;margin:2px 0 10px} .tmp .v{font-size:40px;font-weight:900} .tmp .u{font-size:16px;opacity:.6} .tmp .l{font-size:11px;opacity:.6;margin-inline-start:auto}
 .rw{display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px} .bar{height:7px;border-radius:5px;background:#eef1f7;overflow:hidden;margin-bottom:8px} .bar i{display:block;height:100%}
 .meta{display:flex;justify-content:space-between;font-size:11px;opacity:.65;border-top:1px solid var(--line);padding-top:8px;margin-top:8px}
 footer{margin-top:26px;font-size:12px;opacity:.7;text-align:center;line-height:1.8}
</style></head><body>
<header><h1>ערן — לוח פרטי <small>DGX ×4 + Jetson</small></h1>
 <div><span class="lock">🔒 Tailscale בלבד · לא פומבי</span> <span class="stamp"><span id="dot" class="dot"></span> <span id="ago">מתחבר…</span></span></div></header>
<div class="lbl">ערן — סימנים חיוניים</div>
<div class="hero"><div class="ct"><div class="who">ERAN v1 <span>· eran4 · byte-LM 3.23M</span></div><span class="bd tr" id="el">● חי</span></div>
 <div class="step"><span id="step">—</span> <small>צעדים</small></div>
 <div class="hs"><div><div class="k">loss / ema</div><div class="v" id="loss">—</div></div>
  <div><div class="k">tok/s</div><div class="v" id="tok">—</div></div>
  <div><div class="k">steps/s</div><div class="v" id="sps">—</div></div>
  <div><div class="k">VRAM</div><div class="v" id="vram">—</div></div></div></div>
<div class="lbl">צי + Jetson</div><div class="grid" id="grid"></div>
<footer>נמשך חי דרך SSH מהמחשב הזה · Tailscale serve · רענון 5ש׳ · <b>לזכרה של עלמה ז״ל</b></footer>
<script>
const $=i=>document.getElementById(i), tc=t=>t>=80?'var(--red)':t>=70?'var(--amber)':'var(--green)';
const up=s=>{const d=(s/86400|0),h=(s%86400/3600|0),m=(s%3600/60|0);return(d?d+'d ':'')+h+'h '+m+'m';};
function card(n){
 if(!n.online) return `<div class="card off"><div class="ct"><span class="nm">${n.name}</span><span class="bd of">לא נגיש</span></div><div style="font-size:12px;opacity:.6">${n.host}${n.note?' · '+n.note:''}</div></div>`;
 if(n.gtemp==null) return `<div class="card"><div class="ct"><span class="nm">${n.name}</span><span class="bd tr">● online</span></div><div style="font-size:12px;opacity:.6">${n.host}${n.note?' · '+n.note:''}</div></div>`;
 const c=tc(n.gtemp),s=tc(n.soc);
 return `<div class="card"><div class="ct"><div><span class="nm">${n.name}</span> <span class="ho">${n.host}</span></div><span class="bd ${n.train?'tr':'id'}">${n.train?'● מאמן':'idle'}</span></div>
  <div class="tmp"><span class="v" style="color:${c}">${n.gtemp}</span><span class="u">°C</span><span class="l">GPU</span></div>
  <div class="rw"><span>GPU</span><b>${n.gutil}%</b></div><div class="bar"><i style="width:${n.gutil}%;background:var(--blue)"></i></div>
  <div class="rw"><span>SoC</span><b style="color:${s}">${n.soc}°C</b></div><div class="bar"><i style="width:${Math.min(n.soc,100)}%;background:${s}"></i></div>
  <div class="meta"><span>⚡${Math.round(n.gpow)}W</span><span>load ${n.load}</span><span>⏱${up(n.up)}</span></div></div>`;
}
async function tick(){try{const d=await(await fetch('/status.json',{cache:'no-store'})).json();const e=d.eran||{};
 if(e.step!=null)$('step').textContent=Number(e.step).toLocaleString();
 if(e.loss!=null)$('loss').textContent=e.loss.toFixed(4)+' / '+(e.ema_loss??e.loss).toFixed(4);
 if(e.tokens_per_s!=null)$('tok').textContent=Math.round(e.tokens_per_s/1000)+'k';
 if(e.steps_per_s!=null)$('sps').textContent=e.steps_per_s.toFixed(1);
 if(e.vram_mb!=null)$('vram').textContent=Math.round(e.vram_mb)+'MB';
 $('grid').innerHTML=(d.nodes||[]).map(card).join('');
 $('ago').textContent='לפני '+Math.max(0,(Date.now()/1000-(d.ts||0))|0)+'ש׳';$('dot').className='dot live';
}catch(e){$('ago').textContent='ממתין…';$('dot').className='dot';}}
tick();setInterval(tick,5000);
</script></body></html>""").encode("utf-8")

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/manifest.json"):
            m = ('{"name":"\\u05e2\\u05e8\\u05df \\u2014 \\u05dc\\u05d5\\u05d7 \\u05e4\\u05e8\\u05d8\\u05d9",'
                 '"short_name":"\\u05e2\\u05e8\\u05df","start_url":"/","display":"standalone",'
                 '"background_color":"#f5f8ff","theme_color":"#0038b8",'
                 '"icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}').encode()
            self.send_response(200); self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Content-Length", str(len(m))); self.end_headers(); self.wfile.write(m); return
        if self.path.startswith("/icon.svg"):
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">'
                   '<rect width="192" height="192" rx="40" fill="#0038b8"/>'
                   '<text x="96" y="142" font-size="118" font-family="Arial" font-weight="bold" '
                   'fill="#fff" text-anchor="middle">ע</text></svg>').encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(svg))); self.end_headers(); self.wfile.write(svg); return
        if self.path.startswith("/status.json"):
            b = STATE["json"].encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE))); self.end_headers(); self.wfile.write(PAGE)
    def log_message(self, *a): pass

if __name__ == "__main__":
    threading.Thread(target=refresh, daemon=True).start()
    time.sleep(2)
    socketserver.TCPServer.allow_reuse_address = True
    print(f"ERAN private dashboard on http://127.0.0.1:{PORT}")
    socketserver.TCPServer(("127.0.0.1", PORT), H).serve_forever()
