#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLEET MODE server - stdlib only. No Flask, no CDN, no Claude, no API key, no MCP.

Bind:   127.0.0.1:8872  AND  <tailscale-ip>:8872
Never   0.0.0.0. The LAN cannot see this.

Two-step by construction: POST /api/plan returns the exact list of units that will
start and stop plus a single-use token; POST /api/apply will not do anything without
that token. There is no one-click mode switch and no free-text command field.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_mode as fm  # noqa: E402
import ollama_switch as ox  # noqa: E402 - the model-switch panel, added 2026-09-07
import train_vs_coder as tc  # noqa: E402 - TRAIN<->ONBOARD CODER flip, added 2026-09-07 22:40

PORT = int(os.environ.get("FLEET_MODE_PORT", "8872"))
PROBE_TTL_S = 20.0
TOKEN_TTL_S = 120.0
OLLAMA_TTL_S = 12.0  # 4 boxes x (free + ollama list + ollama ps) over ssh isn't free
TRAINCODER_TTL_S = 10.0  # one box, several ssh round-trips (systemctl + 2 cat + ollama + free + df)

_lock = threading.Lock()
_probe_cache: dict = {"at": 0.0, "data": {}}
_ollama_cache: dict = {"at": 0.0, "data": {}}
_traincoder_cache: dict = {"at": 0.0, "data": {}}
_tokens: dict[str, dict] = {}


# ---------------------------------------------------------------- helpers

def tailscale_ip() -> str | None:
    """Our own <tailnet-ip>/10 address, if tailscaled has given us one."""
    for exe in (r"C:\Program Files\Tailscale\tailscale.exe", "tailscale"):
        try:
            import subprocess
            p = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=10)
            if p.returncode == 0:
                for line in (p.stdout or "").split():
                    try:
                        a = ipaddress.ip_address(line.strip())
                    except ValueError:
                        continue
                    if a.version == 4 and a in ipaddress.ip_network("<tailnet-ip>/10"):
                        return str(a)
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def authorized(client_ip: str) -> bool:
    """Loopback or tailnet only. Belt and braces - we do not bind the LAN either."""
    try:
        a = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    if a.is_loopback:
        return True
    return a.version == 4 and a in ipaddress.ip_network("<tailnet-ip>/10")


def get_probe(force: bool = False) -> dict:
    with _lock:
        fresh = (time.time() - _probe_cache["at"]) < PROBE_TTL_S
        if fresh and not force and _probe_cache["data"]:
            return _probe_cache["data"]
    modes = fm.load_modes()
    mu = fm.managed_units(modes)
    hosts = sorted({h for h, _ in mu})
    data = fm.probe_fleet(hosts, of_interest=mu)
    with _lock:
        _probe_cache["at"] = time.time()
        _probe_cache["data"] = data
    return data


def get_ollama_status(force: bool = False) -> dict:
    with _lock:
        fresh = (time.time() - _ollama_cache["at"]) < OLLAMA_TTL_S
        if fresh and not force and _ollama_cache["data"]:
            return _ollama_cache["data"]
    data = ox.fleet_status()
    with _lock:
        _ollama_cache["at"] = time.time()
        _ollama_cache["data"] = data
    return data


def get_traincoder_status(force: bool = False) -> dict:
    with _lock:
        fresh = (time.time() - _traincoder_cache["at"]) < TRAINCODER_TTL_S
        if fresh and not force and _traincoder_cache["data"]:
            return _traincoder_cache["data"]
    data = tc.read_state()
    with _lock:
        _traincoder_cache["at"] = time.time()
        _traincoder_cache["data"] = data
    return data


def mint_token(kind: str, mode: str | None, plan) -> str:
    tok = secrets.token_urlsafe(18)
    with _lock:
        _tokens[tok] = {"kind": kind, "mode": mode, "plan": plan, "at": time.time()}
        for k, v in list(_tokens.items()):
            if time.time() - v["at"] > TOKEN_TTL_S:
                _tokens.pop(k, None)
    return tok


def take_token(tok: str) -> dict | None:
    """Single use. Taking it removes it."""
    with _lock:
        rec = _tokens.pop(tok, None)
    if rec and (time.time() - rec["at"]) <= TOKEN_TTL_S:
        return rec
    return None


def build_status() -> dict:
    modes = fm.load_modes()
    probe = get_probe()
    hud = fm.read_hud()
    derived = fm.derive_current(modes, probe)
    paused = fm.read_pause()

    boxes = []
    for host in sorted({h for h, _ in fm.managed_units(modes)}):
        f = (hud.get("fleet") or {}).get(host) or {}
        gpu = (f.get("gpu") or [{}])[0]
        mem = f.get("mem") or {}
        p = probe.get(host, {})
        managed_here = [
            {"unit": u, "state": p.get("units", {}).get(u, "absent")}
            for h, u in fm.managed_units(modes) if h == host
        ]
        boxes.append({
            "host": host,
            "reachable": bool(p.get("ok")),
            "probe_error": p.get("error"),
            "hud_reachable": f.get("reachable"),
            "gpu_util": gpu.get("util_pct"),
            "gpu_temp": gpu.get("temp_c"),
            "gpu_watt": gpu.get("power_w"),
            "mem_pct": mem.get("pct"),
            "mem_used_gb": mem.get("used_gb"),
            "load": f.get("load"),
            "units": managed_here,
        })

    return {
        "now_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hud": {"stale": hud["stale"], "age_s": hud["age_s"], "ok": hud["ok"],
                "error": hud["error"], "source": hud.get("source")},
        "derived": derived,
        "boxes": boxes,
        "paused": ({"at": paused["paused_at_iso"], "units": paused["was_running"]}
                   if paused else None),
        "protected": [{"host": h, "unit": u} for h, u in fm.PROTECTED_UNITS],
        "protected_patterns": list(fm.PROTECTED_PATTERNS),
    }


# ---------------------------------------------------------------- the page

PAGE = r"""<!doctype html>
<html lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FLEET MODE</title><style>
*{box-sizing:border-box}
body{margin:0;background:#f6f8fb;color:#16202c;
 font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:16px}
h1{font-size:21px;margin:0 0 2px}
.sub{color:#5b6b7d;font-size:13px;margin-bottom:14px}
.card{background:#fff;border:1px solid #dfe6ee;border-radius:12px;padding:14px;margin-bottom:12px}
.now{font-size:19px;font-weight:700}
.bad{color:#b3261e}.good{color:#1a7f37}.warn{color:#9a6700}
.stale{background:#fff4f3;border-color:#f3b3ae}
.modes{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
button{font:inherit;cursor:pointer;border-radius:10px;border:1px solid #c8d3e0;
 background:#fff;padding:12px 14px;width:100%;text-align:left}
button:hover{background:#eef4ff}
button.on{border-color:#1a7f37;background:#eefaf0}
button:disabled{opacity:.5;cursor:not-allowed}
.pausebar{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.pausebar button{text-align:center;font-weight:700;padding:16px}
#pause{border-color:#c98a00;background:#fffaf0}
#resume{border-color:#1a5fb4;background:#f0f6ff}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:5px 6px;border-bottom:1px solid #eef2f6;text-align:left}
th{color:#5b6b7d;font-weight:600}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11.5px;font-weight:600}
.p-active{background:#e6f6ec;color:#1a7f37}
.p-inactive{background:#eef2f6;color:#5b6b7d}
.p-failed{background:#fde8e6;color:#b3261e}
.p-absent{background:#fff4e0;color:#9a6700}
.prot{background:#fff;border:1px dashed #b3261e;border-radius:12px;padding:12px;
 margin-bottom:12px;font-size:13px}
.prot b{color:#b3261e}
#dlg{position:fixed;inset:0;background:rgba(12,20,30,.55);display:none;
 align-items:center;justify-content:center;padding:14px;z-index:9}
#dlg.on{display:flex}
.box{background:#fff;border-radius:14px;max-width:520px;width:100%;
 max-height:86vh;overflow:auto;padding:18px}
.box h2{margin:0 0 8px;font-size:18px}
.row{display:flex;gap:8px;margin-top:14px}
.row button{flex:1;text-align:center;font-weight:700}
#go{background:#1a5fb4;color:#fff;border-color:#1a5fb4}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.log{white-space:pre-wrap;background:#f6f8fb;border-radius:8px;padding:10px;
 margin-top:12px;font-family:ui-monospace,Consolas,monospace;font-size:12px}
</style></head><body><div class="wrap">

<h1>FLEET MODE · מצב הצי</h1>
<div class="sub">4 × DGX Spark · no Claude in any path · <span id="bind"></span></div>

<div class="prot">
  <b>PROTECTED / מוגן —</b> nothing here can ever stop these:
  <span id="protlist" class="mono"></span>.
  A mode that names one <b>fails to load</b>.
</div>

<div class="card" id="hudcard">
  <div class="now" id="cur">…</div>
  <div class="sub" id="hudline"></div>
</div>

<div class="card">
  <div class="sub"><b>PAUSE / פאוזה</b> — stop the workloads, remember exactly what was running.</div>
  <div class="pausebar">
    <button id="pause">⏸ PAUSE</button>
    <button id="resume">▶ RESUME</button>
  </div>
  <div class="sub" id="pausenote" style="margin-top:8px"></div>
</div>

<div class="card">
  <div class="sub"><b>SWITCH / החלף מצב</b> — every switch shows what it will do first.</div>
  <div class="modes" id="modes"></div>
</div>

<div class="card"><table id="boxes"></table></div>

<div class="card">
  <div class="sub"><b>MODELS ACROSS THE FLEET · מודלים בצי</b> — which ollama model is
  loaded on each box, its size, and free RAM. eran1 is ERAN — shown, never switchable.</div>
  <div id="ollama_boxes">…</div>
</div>

<div class="card" id="tc_card">
  <div class="sub"><b>TRAIN ↔ ONBOARD CODER · אימון מול קודר</b> — eran3 only. Flipping
  it TO the coder <b class="bad">stops coder-train.service</b>, the run Iddo declared
  PERMANENT on 2026-09-05 ("every training run never stops"). That direction needs the
  typed phrase <span class="mono">STOP TRAINING</span>, not just a click. eran1 is not
  in this control at all.</div>
  <div id="tc_body">…</div>
</div>
<div id="out"></div>

</div>

<div id="dlg"><div class="box">
  <h2 id="dtitle"></h2>
  <div id="dbody"></div>
  <div id="confirmwrap" style="display:none;margin-top:12px">
    <label class="sub" for="confirmphrase">Type <b class="mono">STOP TRAINING</b> to enable Confirm:</label>
    <input id="confirmphrase" type="text" autocomplete="off"
      style="width:100%;padding:10px;border-radius:8px;border:1px solid #c8d3e0;margin-top:4px;font:inherit">
  </div>
  <div class="row">
    <button onclick="closeDlg()">Cancel · בטל</button>
    <button id="go">Confirm · אשר</button>
  </div>
</div></div>

<script>
let TOKEN=null, BUSY=false;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function api(path,body){
  const o={headers:{'Content-Type':'application/json'}};
  if(body){o.method='POST';o.body=JSON.stringify(body);}
  const r=await fetch(path,o); return r.json();
}

function pill(s){return '<span class="pill p-'+esc(s)+'">'+esc(s)+'</span>';}

async function refresh(){
  const s=await api('/api/status');
  $('bind').textContent=s.bind||'';
  $('protlist').textContent=s.protected.map(p=>p.host+'/'+p.unit).join('  ');

  const d=s.derived;
  $('cur').innerHTML = d.current
     ? '<span class="good">'+esc(d.current_summary)+'</span>'
     : '<span class="warn">'+esc(d.current_summary)+'</span>';

  const h=s.hud;
  $('hudcard').className = 'card' + (h.stale?' stale':'');
  $('hudline').innerHTML = h.stale
     ? '<b class="bad">⚠ HUD STALE'+(h.age_s!=null?' ('+h.age_s+'s old)':'')+
       ' — GPU/mem numbers below are NOT current.</b>'
     : 'health from almaware-hud, '+h.age_s+'s old · '+esc(s.now_iso);

  $('pausenote').innerHTML = s.paused
     ? '<b class="warn">PAUSED '+esc(s.paused.at)+'</b> — '+s.paused.units.length+
       ' unit(s) held: <span class="mono">'+
       s.paused.units.map(u=>esc(u.host+'/'+u.unit)).join(', ')+'</span>'
     : 'not paused.';
  $('resume').disabled = !s.paused;

  $('modes').innerHTML = d.modes.map(m=>
    '<button class="'+(m.in_force?'on':'')+'" onclick="pickMode(\''+esc(m.name)+'\')">'+
    '<b>'+esc(m.label||m.name)+'</b><br><span class="sub">'+esc(m.summary)+'</span></button>'
  ).join('');

  let t='<tr><th>box</th><th>GPU</th><th>mem</th><th>managed units</th></tr>';
  for(const b of s.boxes){
    const gpu = h.stale ? '<span class="bad">stale</span>'
        : (b.gpu_util!=null? b.gpu_util+'% · '+b.gpu_temp+'°C · '+b.gpu_watt+'W' : '—');
    const mem = h.stale ? '<span class="bad">stale</span>'
        : (b.mem_pct!=null? b.mem_pct+'%' : '—');
    const us = b.reachable
        ? b.units.map(u=>esc(u.unit.replace('.service',''))+' '+pill(u.state)).join('<br>')
        : '<span class="bad">UNREACHABLE: '+esc(b.probe_error||'?')+'</span>';
    t+='<tr><td><b>'+esc(b.host)+'</b></td><td>'+gpu+'</td><td>'+mem+'</td><td>'+us+'</td></tr>';
  }
  $('boxes').innerHTML=t;
}

async function planAndConfirm(kind,mode){
  if(BUSY) return;
  OLLAMA_MODE=false;
  const r=await api('/api/plan',{kind:kind,mode:mode});
  if(r.error){alert('REFUSED: '+r.error);return;}
  TOKEN=r.token;
  $('dtitle').textContent=r.title;
  if(!r.plan.length){
    $('dbody').innerHTML='<p>Nothing to do — every unit is already in the wanted state.<br>'+
      'אין מה לעשות, הכול כבר במצב הנכון.</p>';
    $('go').disabled=true;
  }else{
    $('go').disabled=false;
    $('dbody').innerHTML='<p>This will do exactly this, and nothing else:</p><table>'+
      r.plan.map(p=>'<tr><td>'+(p.want==='start'?'▶ <b class="good">START</b>':'⏹ <b class="bad">STOP</b>')+
      '</td><td class="mono">'+esc(p.host)+'/'+esc(p.unit)+'</td><td>'+pill(p.from_state)+'</td></tr>').join('')+
      '</table><p class="sub">Protected units are not in this list and cannot be.</p>';
  }
  $('dlg').classList.add('on');
}
function closeDlg(){
  $('dlg').classList.remove('on');TOKEN=null;OLLAMA_MODE=false;TRAINCODER_MODE=null;
  $('confirmwrap').style.display='none';$('confirmphrase').value='';
  $('confirmphrase').oninput=null;
}

$('go').onclick=async()=>{
  if(!TOKEN||BUSY)return;
  if(TRAINCODER_MODE==='to_coder' && $('confirmphrase').value.trim()!=='STOP TRAINING')return;
  BUSY=true;$('go').disabled=true;$('go').textContent='working…';
  let path='/api/apply', extra={};
  if(OLLAMA_MODE){path='/api/ollama/apply';}
  else if(TRAINCODER_MODE){
    path='/api/traincoder/apply';
    extra={confirm_text:$('confirmphrase').value.trim()};
  }
  const r=await api(path,Object.assign({token:TOKEN},extra));
  BUSY=false;$('go').textContent='Confirm · אשר';
  const wasOllama = OLLAMA_MODE, wasTC = TRAINCODER_MODE;
  closeDlg();
  if(r.error){$('out').innerHTML='<div class="card"><b class="bad">REFUSED: '+esc(r.error)+'</b></div>';}
  else if(wasOllama){
    const before=(r.before_ps&&r.before_ps.loaded)||[];
    const after=(r.after_ps&&r.after_ps.loaded)||[];
    $('out').innerHTML='<div class="card"><b class="'+(r.result==='OK'?'good':'bad')+'">'+
      r.result+'</b> — '+esc(r.host)+' → '+esc(r.model)+' · '+r.elapsed_s+'s'+
      '<div class="log">BEFORE ollama ps: '+esc(before.map(m=>m.name+' ('+m.size_str+')').join(', ')||'(nothing loaded)')+
      '\nAFTER  ollama ps: '+esc(after.map(m=>m.name+' ('+m.size_str+')').join(', ')||'(nothing loaded)')+
      '\nverified_loaded: '+r.verified_loaded+
      '\ngeneration: '+esc(r.generation||'(none)')+'</div>'+
      '<div class="sub">verified by re-reading ollama ps after the switch, not by the return code.</div></div>';
    refreshOllama();
  }else if(wasTC){
    $('out').innerHTML='<div class="card"><b class="'+(r.result==='OK'?'good':(r.result==='NOOP'?'warn':'bad'))+'">'+
      r.result+'</b> — eran3 '+esc(wasTC)+' · '+(r.elapsed_s!=null?r.elapsed_s+'s':'')+
      '<div class="log">'+esc(JSON.stringify(r,null,2))+'</div></div>';
    refreshTrainCoder();
  }
  refresh();
};
$('pause').onclick=()=>planAndConfirm('pause');
$('resume').onclick=()=>planAndConfirm('resume');
// Deliberately TWO names. The first version exported the handler under the same
// name the handler itself calls, so it overwrote itself and every mode button
// recursed until the stack blew - the buttons were completely dead. Measured
// 2026-09-05 with a real click. These two names cannot collide.
window.pickMode=(m)=>planAndConfirm('mode',m);

// ---------------------------------------------------------- models panel
let OLLAMA_MODE=false;

async function refreshOllama(){
  const s=await api('/api/ollama/status');
  const hosts=['eran1','eran2','eran3','eran4'];
  let html='';
  for(const h of hosts){
    const b=(s.boxes||{})[h]||{};
    if(!b.reachable){
      html+='<div class="card" style="border-color:#b3261e;margin-bottom:8px">'+
        '<b>'+h+'</b> — <b class="bad">UNREACHABLE: '+esc(b.error||'?')+'</b></div>';
      continue;
    }
    const mem=b.mem||{};
    const loaded=(b.loaded||[]).map(m=>esc(m.name)+' ('+esc(m.size_str)+
      (m.processor?', '+esc(m.processor):'')+')').join(', ')||'<i>nothing loaded</i>';
    let action;
    if(b.switchable){
      const opts=(b.catalog||[]).map(m=>
        '<option value="'+esc(m.name)+'">'+esc(m.name)+' — '+esc(m.size_str)+'</option>').join('');
      action='<div style="margin-top:8px;display:flex;gap:8px">'+
        '<select id="sel_'+h+'" style="flex:1;padding:8px;border-radius:8px;border:1px solid #c8d3e0">'+
        opts+'</select>'+
        '<button onclick="ollamaSwitch(\''+h+'\')">SWITCH · החלף</button></div>';
    }else{
      action='<div class="sub" style="margin-top:8px"><b class="bad">'+
        'ERAN — LOAD BLOCKED, READ ONLY · חסום לטעינה, קריאה בלבד</b></div>';
    }
    let doorsLine='';
    if(b.doors){
      doorsLine='<div class="sub" style="margin-top:4px">doors: '+
        Object.keys(b.doors).map(p=>p+' '+pill(b.doors[p]?'active':'failed')).join('  ')+'</div>';
    }
    html+='<div class="card" style="margin-bottom:8px">'+
      '<div><b>'+h+'</b> · RAM '+mem.used_gb+' / '+mem.total_gb+' GB used · '+
      '<b class="good">free '+mem.available_gb+' GB</b>'+
      (b.disk?' · disk free '+b.disk.free_gb+' GB':'')+'</div>'+
      '<div class="sub" style="margin-top:4px">loaded: '+loaded+'</div>'+
      doorsLine+
      action+'</div>';
  }
  $('ollama_boxes').innerHTML=html;
}

async function ollamaSwitch(host){
  if(BUSY)return;
  const model=$('sel_'+host).value;
  const r=await api('/api/ollama/plan',{host:host,model:model});
  const p=r.plan||{};
  OLLAMA_MODE=true;
  $('dtitle').textContent='Switch '+host+' → '+model;
  let body='<p class="mono">'+esc(p.arithmetic||'')+'</p>';
  if(!r.token){
    body+='<p><b class="bad">REFUSED · נדחה</b> — '+esc((p.reasons||[]).join('; ')||'cannot switch')+'</p>';
    $('go').disabled=true;
  }else{
    body+='<p>Will stop: <span class="mono">'+esc((p.will_stop||[]).join(', ')||'(nothing)')+
      '</span><br>Then run a real prompt on <b>'+esc(model)+'</b> and verify with '+
      '<span class="mono">ollama ps</span> before and after.</p>';
    $('go').disabled=false;
  }
  $('dbody').innerHTML=body;
  TOKEN=r.token;
  $('dlg').classList.add('on');
}

// ------------------------------------------------------ train<->coder panel
let TRAINCODER_MODE=null;  // null | 'to_coder' | 'to_training'

function tcPill(mode){
  const cls = mode==='TRAINING' ? 'p-active' : (mode==='ONBOARD CODER' ? 'p-inactive' : 'p-failed');
  return '<span class="pill '+cls+'">'+esc(mode)+'</span>';
}

async function refreshTrainCoder(){
  const s=await api('/api/traincoder/status');
  if(!s.reachable){
    $('tc_body').innerHTML='<b class="bad">UNREACHABLE / REFUSED: '+esc(s.error||'?')+'</b>';
    return;
  }
  const step = s.training_step!=null ? s.training_step+' / '+s.training_max_steps : '—';
  let html = '<div>' +
    '<b>eran3</b> '+tcPill(s.mode)+
    ' · RAM '+(s.mem?s.mem.used_gb+' / '+s.mem.total_gb+' GB used, free '+s.mem.available_gb+' GB':'—')+
    '</div>' +
    '<div class="sub" style="margin-top:6px">' +
      'training: step <b>'+esc(String(step))+'</b>'+
      (s.training_loss!=null?' · loss '+s.training_loss:'')+
      (s.training_reserved_gb!=null?' · '+s.training_reserved_gb+' GB reserved':'')+
      (s.training_eta_h!=null?(' · ETA '+(s.training_eta_h.toFixed?s.training_eta_h.toFixed(1):s.training_eta_h)+'h'):'')+
      '<br>newest checkpoint: <span class="mono">'+esc(s.newest_checkpoint||'none')+'</span>'+
      ' ('+esc(s.newest_checkpoint_age||'?')+' old)'+
      '<br>watchdog: '+esc(s.watchdog_verdict||'—')+
      '<br>resume command: <span class="mono">'+esc(s.resume_command)+'</span>'+
      '<br>onboard coder present on eran3: '+
      (s.onboard_coder_present&&s.onboard_coder_present.length?esc(s.onboard_coder_present.join(', ')):'<b class="bad">none — not pulled</b>')+
    '</div>' +
    '<div class="row" style="margin-top:10px">' +
      '<button style="border-color:#b3261e" onclick="trainCoderAction(\'to_coder\')">→ ONBOARD CODER · לקודר (stops training)</button>' +
      '<button style="border-color:#1a5fb4" onclick="trainCoderAction(\'to_training\')">→ TRAINING · לאימון (resume)</button>' +
    '</div>';
  $('tc_body').innerHTML = html;
}

async function trainCoderAction(direction){
  if(BUSY)return;
  const r=await api('/api/traincoder/plan',{direction:direction});
  const p=r.plan||{};
  OLLAMA_MODE=false; TRAINCODER_MODE=direction;
  $('dtitle').textContent = direction==='to_coder'
     ? 'eran3: TRAINING → ONBOARD CODER'
     : 'eran3: ONBOARD CODER → TRAINING (resume)';
  let body='';
  if(p.warning) body += '<p><b class="warn">'+esc(p.warning)+'</b></p>';
  if(p.arithmetic) body += '<p class="mono">'+esc(p.arithmetic)+'</p>';
  if(!r.token){
    body += '<p><b class="bad">REFUSED · נדחה</b> — '+esc((p.reasons||[]).join('; ')||'cannot flip')+'</p>';
    $('go').disabled=true;
    $('confirmwrap').style.display='none';
  }else{
    $('go').disabled=false;
    if(direction==='to_coder'){
      body += '<p>Will stop: <span class="mono">coder-train.service'+
        ((p.will_stop_ollama&&p.will_stop_ollama.length)?', '+esc(p.will_stop_ollama.join(', ')):'')+
        '</span>, then run a real prompt on <b>'+esc(p.model)+'</b> and verify with '+
        '<span class="mono">systemctl show</span> + <span class="mono">ollama ps</span> before and after.</p>';
      $('confirmwrap').style.display='block';
      $('go').disabled=true;  // stays disabled until the phrase matches, checked live
      $('confirmphrase').oninput=()=>{ $('go').disabled = ($('confirmphrase').value.trim()!=='STOP TRAINING'); };
    }else{
      body += '<p>Will stop: <span class="mono">'+esc((p.will_stop_ollama||[]).join(', ')||'(nothing)')+
        '</span>, then <span class="mono">systemctl --user start coder-train.service</span> '+
        '(resumes automatically from '+esc(p.newest_checkpoint||'the newest checkpoint')+').</p>';
      $('confirmwrap').style.display='none';
    }
  }
  $('dbody').innerHTML=body;
  TOKEN=r.token;
  $('dlg').classList.add('on');
}

refresh(); setInterval(refresh,15000);
refreshOllama(); setInterval(refreshOllama,15000);
refreshTrainCoder(); setInterval(refreshTrainCoder,15000);
</script></body></html>
"""


# ---------------------------------------------------------------- handler

class H(BaseHTTPRequestHandler):
    server_version = "FleetMode/1.0"
    bind_label = ""

    def log_message(self, fmt, *a):  # quieter
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _guard(self) -> bool:
        ip = self.client_address[0]
        if not authorized(ip):
            self._json(403, {"error": f"not authorized from {ip} - loopback and tailnet only"})
            return False
        return True

    def do_GET(self):  # noqa: N802
        if not self._guard():
            return
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            try:
                s = build_status()
                s["bind"] = self.bind_label
                self._json(200, s)
            except fm.ProtectedUnitError as exc:
                self._json(500, {"error": str(exc)})
        elif self.path == "/api/ollama/status":
            try:
                self._json(200, {"boxes": get_ollama_status(),
                                 "switchable_hosts": list(ox.SWITCHABLE_HOSTS),
                                 "safety_margin_gb": ox.SAFETY_MARGIN_GB,
                                 "now_iso": time.strftime("%Y-%m-%d %H:%M:%S")})
            except Exception as exc:  # noqa: BLE001 - never 500 into a blank page
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
        elif self.path == "/api/traincoder/status":
            try:
                self._json(200, get_traincoder_status())
            except Exception as exc:  # noqa: BLE001 - never 500 into a blank page
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
        elif self.path == "/healthz":
            self._json(200, {"up": True, "port": PORT})
        else:
            self._json(404, {"error": "no such path"})

    def do_POST(self):  # noqa: N802
        if not self._guard():
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "bad json"})
            return

        if self.path == "/api/plan":
            self._plan(body)
        elif self.path == "/api/ollama/plan":
            self._ollama_plan(body)
        elif self.path == "/api/ollama/apply":
            self._ollama_apply(body)
        elif self.path == "/api/traincoder/plan":
            self._traincoder_plan(body)
        elif self.path == "/api/traincoder/apply":
            self._traincoder_apply(body)
        elif self.path == "/api/apply":
            self._apply(body)
        else:
            self._json(404, {"error": "no such path"})

    # -- step 1: show exactly what will happen, hand out a single-use token --
    def _plan(self, body):
        kind = str(body.get("kind") or "")
        try:
            modes = fm.load_modes()
        except fm.ProtectedUnitError as exc:
            self._json(500, {"error": str(exc)})
            return

        if kind == "mode":
            name = str(body.get("mode") or "")
            if name not in modes:
                self._json(400, {"error": f"no such mode: {name}"})
                return
            plan = fm.plan_mode(modes[name], get_probe(force=True))
            title = f"Switch to {modes[name].label}"
        elif kind == "pause":
            plan = fm.plan_pause(modes, get_probe(force=True))
            title = "PAUSE · פאוזה"
        elif kind == "resume":
            plan = fm.plan_resume()
            title = "RESUME · המשך"
        else:
            self._json(400, {"error": f"unknown kind: {kind}"})
            return

        # Gate the plan now too, so a protected unit can never even be OFFERED.
        try:
            for s in plan:
                fm.assert_actionable(s["host"], s["unit"], s["want"])
        except fm.ProtectedUnitError as exc:
            self._json(400, {"error": str(exc)})
            return

        self._json(200, {"title": title, "plan": plan,
                         "token": mint_token(kind, body.get("mode"), plan)})

    # -- step 2: the second click. no token, no action. --
    def _apply(self, body):
        rec = take_token(str(body.get("token") or ""))
        if not rec:
            self._json(400, {"error": "no valid confirmation token - "
                                      "plan first, then confirm within 2 minutes"})
            return
        actor = f"web:{self.client_address[0]}"
        try:
            if rec["kind"] == "pause":
                out = fm.do_pause(fm.load_modes(), actor=actor)
            elif rec["kind"] == "resume":
                out = fm.do_resume(actor=actor)
            else:
                out = fm.execute_plan(rec["plan"], actor=actor,
                                      reason=f"mode:{rec.get('mode')}")
        except fm.ProtectedUnitError as exc:
            fm.log_action({"actor": actor, "reason": rec["kind"], "result": "FAIL",
                           "error": str(exc), "planned": len(rec["plan"]),
                           "verified_ok": 0, "verified_fail": len(rec["plan"])})
            self._json(400, {"error": str(exc)})
            return
        with _lock:
            _probe_cache["at"] = 0.0  # force a fresh probe on the next render
        self._json(200, out)

    # -- ollama model switch: step 1, show the RAM arithmetic + a token --
    def _ollama_plan(self, body):
        host = str(body.get("host") or "")
        model = str(body.get("model") or "")
        plan = ox.plan_switch(host, model)
        token = None
        if plan.get("fits"):
            token = mint_token("ollama", None, plan)
        self._json(200, {
            "title": f"Switch {host} to {model}",
            "plan": plan,
            "token": token,
        })

    # -- ollama model switch: step 2, the second click. re-derives, doesn't trust --
    def _ollama_apply(self, body):
        rec = take_token(str(body.get("token") or ""))
        if not rec or rec.get("kind") != "ollama":
            self._json(400, {"error": "no valid confirmation token - "
                                      "plan first, then confirm within 2 minutes"})
            return
        host = rec["plan"]["host"]
        model = rec["plan"]["model"]
        actor = f"web:{self.client_address[0]}"
        try:
            out = ox.apply_switch(host, model, actor=actor)
        except ox.SwitchRefused as exc:
            self._json(400, {"error": str(exc)})
            return
        with _lock:
            _ollama_cache["at"] = 0.0  # force a fresh read on the next render
        self._json(200 if out.get("result") == "OK" else 500, out)

    # -- train<->coder flip: step 1, show the warning + arithmetic + a token --
    # A token is minted ONLY when plan.fits - same rule as ollama plan/apply.
    # For direction=to_coder that means: while the onboard coder model is not
    # yet present on eran3, NO token is ever issued, so there is nothing the
    # UI can even attempt to confirm. The typed phrase in _traincoder_apply is
    # a second, independent gate on top of that, not a replacement for it.
    def _traincoder_plan(self, body):
        direction = str(body.get("direction") or "")
        model = body.get("model")
        if direction == "to_coder":
            plan = tc.plan_to_coder(model=model)
        elif direction == "to_training":
            plan = tc.plan_to_training()
        else:
            self._json(400, {"error": f"unknown direction: {direction!r}"})
            return
        token = None
        if plan.get("fits"):
            token = mint_token("traincoder", direction, plan)
        self._json(200, {"title": f"eran3 {direction}", "plan": plan, "token": token})

    # -- train<->coder flip: step 2. to_coder additionally requires the exact
    # typed phrase - checked here, server-side, never trusted from the client. --
    def _traincoder_apply(self, body):
        rec = take_token(str(body.get("token") or ""))
        if not rec or rec.get("kind") != "traincoder":
            self._json(400, {"error": "no valid confirmation token - "
                                      "plan first, then confirm within 2 minutes"})
            return
        direction = rec["mode"]
        actor = f"web:{self.client_address[0]}"
        try:
            if direction == "to_coder":
                confirm_text = str(body.get("confirm_text") or "")
                out = tc.apply_to_coder(actor, model=rec["plan"].get("model"),
                                        confirm_text=confirm_text)
            else:
                out = tc.apply_to_training(actor)
        except tc.TrainCoderRefused as exc:
            self._json(400, {"error": str(exc)})
            return
        with _lock:
            _traincoder_cache["at"] = 0.0  # force a fresh read on the next render
        code = 200 if out.get("result") in ("OK", "NOOP") else 500
        self._json(code, out)


# ---------------------------------------------------------------- main

def serve_on(host: str, label: str) -> ThreadingHTTPServer | None:
    try:
        cls = type("H_" + label.replace(".", "_"), (H,), {"bind_label": label})
        srv = ThreadingHTTPServer((host, PORT), cls)
        srv.daemon_threads = True
        return srv
    except OSError as exc:
        print(f"[fleet-mode] cannot bind {host}:{PORT} - {exc}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    globals()["PORT"] = args.port

    # Fail fast and loudly if the mode file itself is refused.
    try:
        modes = fm.load_modes()
    except fm.ProtectedUnitError as exc:
        print("\n" + "!" * 70)
        print(str(exc))
        print("!" * 70 + "\nServer NOT started.\n")
        return 3
    print(f"[fleet-mode] modes: {', '.join(modes)}")

    ts = tailscale_ip()
    label = f"{ts}:{args.port}" if ts else f"127.0.0.1:{args.port} (no tailscale)"

    servers = []
    lo = serve_on("127.0.0.1", label)
    if lo:
        servers.append(("127.0.0.1", lo))
    if ts:
        t = serve_on(ts, label)
        if t:
            servers.append((ts, t))
    else:
        print("[fleet-mode] WARNING: no tailscale IPv4 found - loopback only.")

    if not servers:
        print("[fleet-mode] nothing bound. exiting.", file=sys.stderr)
        return 1

    for ip, _ in servers:
        print(f"[fleet-mode] listening http://{ip}:{args.port}/")
    print("[fleet-mode] NOT bound on 0.0.0.0 - the LAN cannot reach this.")
    print(f"[fleet-mode] protected: "
          f"{', '.join(f'{h}/{u}' for h, u in fm.PROTECTED_UNITS)} + patterns "
          f"{fm.PROTECTED_PATTERNS}")

    for _, s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        servers[0][1].serve_forever()
    except KeyboardInterrupt:
        print("\n[fleet-mode] stopped.")
    return 0


BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


def go_below_normal() -> str:
    """Drop to BELOW_NORMAL. Normal-priority work on this PC starves Iddo's live mic.

    The argtypes/restype are NOT optional: without them GetCurrentProcess's pseudo-
    handle is truncated to c_int and the call silently does nothing. Measured
    2026-09-05 - the first version of this reported success and left the process at
    NORMAL (Win32_Process.Priority = 8). So we read the class back and say what it is.
    """
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k.GetPriorityClass.argtypes = [ctypes.c_void_p]
        h = k.GetCurrentProcess()
        k.SetPriorityClass(h, BELOW_NORMAL_PRIORITY_CLASS)
        got = k.GetPriorityClass(h)
        if got == BELOW_NORMAL_PRIORITY_CLASS:
            return "BELOW_NORMAL (verified)"
        return f"WARNING: priority class is {hex(got)}, NOT below-normal"
    except (AttributeError, OSError) as exc:
        return f"WARNING: could not set priority ({type(exc).__name__})"


if __name__ == "__main__":
    print(f"[fleet-mode] priority: {go_below_normal()}")
    sys.exit(main())
