#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE FOOTBALL — Iddo's private fleet console.

Iddo, 2026-08-15: "write the best code you can to manage the DGX — to be my
private dashboard, GUI and Tailscale, both, to control DGX, the ant farm, the
ComfyUI, the LTX, the Qwen, the OSS. Like President Trump's football."

One case he opens from anywhere and commands the whole fleet from. Four GB10
boxes, every service on them, and the local ones on this PC — status and
control in one page.

DESIGN LAWS THIS OBEYS
----------------------
* **Pure stdlib.** http.server, subprocess, json, urllib. No Flask, no CDN,
  no npm. Same as RAMCHAT and QUORUM ([[project_quorum]]) — 100% ours.
* **A CLOSED ACTION LIST.** The one genuinely dangerous thing a control panel
  can do is run what it is told. This one cannot: every action is a
  (node, unit, verb) triple looked up in TARGETS below, and the verb is one
  of start/stop/restart. There is no field anywhere that reaches a shell.
  subprocess is called with an argv LIST and shell=False, always.
* **Nothing destructive, ever.** No rm, no delete, no reset, no kill -9, no
  config writes. The worst this panel can do is stop a service that can be
  started again on the next click. That is deliberate and matches the
  standing red lines: irreversible actions are never automated.
* **Token-gated.** His eyes only. The token lives in state/token, is created
  on first run, and every request must carry it. A wrong token gets 401 and
  a journal line.
* **Read-only by default.** Control requires POST + token. A GET can never
  change anything.
* **Bright.** White ground, big type, colour only where it means something.

REACH
-----
Binds to 127.0.0.1 AND the machine's Tailscale IP if one exists, so the same
page serves the desk and the phone. It never binds 0.0.0.0 — the open
internet is not invited.

    python football.py            serve
    python football.py --token    print the token (to paste on the phone)
"""
from __future__ import annotations

import html
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
TOKEN_FILE = STATE / "token"
LOG_FILE = STATE / "football.log"
PORT = 8899                      # claimed in RAMCHAT before first bind
SSH_TIMEOUT = 12
POLL_SECONDS = 20                # background refresh cadence

# --------------------------------------------------------------- the fleet
# Reach paths VERIFIED 2026-08-15. CLAUDE.md's are stale: eran3 is <fabric-ip>
# (not <fabric-ip>) and eran4 answers directly on the LAN.
NODES: dict[str, dict] = {
    "eran1": {
        "label": "eran1 · ראש קוון",
        "ssh": ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={SSH_TIMEOUT}", "eran1"],
        "note": "Qwen3-Coder-480B head + KESHEV STT",
    },
    "eran2": {
        "label": "eran2 · רכזת הסיב",
        "ssh": ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={SSH_TIMEOUT}", "eran2"],
        "note": "RPC worker · fabric hub · gateway for eran3",
    },
    "eran3": {
        "label": "eran3 · דרך הסיב",
        "ssh": ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={SSH_TIMEOUT}",
                "-J", "eran2", "eran3@<fabric-ip>"],
        "note": "RPC worker · no LAN of its own, NATs through eran2",
    },
    "eran4": {
        "label": "eran4 · הקופסה של ערן",
        "ssh": ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={SSH_TIMEOUT}",
                "eran4@<lan-ip>"],
        "note": "Eran · Darwish · nightly LoRA · ant farm · alma-stt",
    },
}

# The CLOSED action list. A unit not in here cannot be touched by this panel,
# whatever any request says. `user` marks a systemd --user unit.
TARGETS: list[dict] = [
    {"node": "eran1", "unit": "qwen-head",        "user": True,  "label": "Qwen 480B (ראש)"},
    {"node": "eran1", "unit": "keshev-stt",       "user": True,  "label": "KESHEV STT (המיק)"},
    {"node": "eran1", "unit": "comfyui",          "user": True,  "label": "ComfyUI · LTX"},
    {"node": "eran2", "unit": "qwen-rpc",         "user": True,  "label": "Qwen RPC worker"},
    {"node": "eran3", "unit": "qwen-rpc",         "user": True,  "label": "Qwen RPC worker"},
    {"node": "eran3", "unit": "voice-ant-farm",   "user": True,  "label": "חוות הנמלים"},
    {"node": "eran4", "unit": "darwish-train",    "user": True,  "label": "דרוויש · אימון 24/7"},
    {"node": "eran4", "unit": "keshev-lora",      "user": True,  "label": "LoRA לילי (טיימר)",
     "timer": True},
    {"node": "eran4", "unit": "voice-ant-farm",   "user": True,  "label": "חוות הנמלים"},
    {"node": "eran4", "unit": "alma-stt",         "user": True,  "label": "ALMA STT"},
    {"node": "eran4", "unit": "comfyui",          "user": True,  "label": "ComfyUI · LTX"},
]

# Local http services on this PC — link only, never controlled from here.
LOCAL_LINKS: list[dict] = [
    {"port": 8790, "label": "ALMAWARE Cockpit"},
    {"port": 8803, "label": "חוות הנמלים · Voice Ant Farm"},
    {"port": 8794, "label": "ALMA-RECALL"},
    {"port": 8895, "label": "Eran Federation"},
    {"port": 8099, "label": "QUORUM"},
    {"port": 8804, "label": "דגימות קול של הנמלים"},
    {"port": 8806, "label": "דוח 48 שעות"},
]

# Remote http endpoints worth a click.
REMOTE_LINKS: list[dict] = [
    {"url": "http://<lan-ip>:8080/", "label": "Qwen head · eran1"},
    {"url": "http://<lan-ip>:4408/", "label": "K2 printer · fluidd"},
]


# ------------------------------------------------------------------ plumbing

def log(msg: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(line)
    print(line.rstrip(), flush=True)


def get_token() -> str:
    STATE.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(tok, encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError as exc:                       # never silent
        log(f"could not chmod token file: {exc}")
    log("new token generated")
    return tok


def run(argv: list[str], timeout: int = SSH_TIMEOUT + 8) -> tuple[int, str]:
    """The ONLY place this program executes anything. argv list, shell=False —
    so no value from any request can ever become shell syntax."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, shell=False)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as exc:                     # never silent (gate G1)
        return 1, f"{type(exc).__name__}: {exc}"


def tailscale_ip() -> str | None:
    for exe in (r"C:\Program Files\Tailscale\tailscale.exe", "tailscale"):
        rc, out = run([exe, "ip", "-4"], timeout=8)
        if rc == 0:
            ip = out.strip().splitlines()[0].strip() if out.strip() else ""
            if ip and ip.count(".") == 3:
                return ip
    return None


# -------------------------------------------------------------- fleet probe

PROBE = (
    'echo "UP=$(uptime -p 2>/dev/null)"; '
    'free -g | awk \'/^Mem:/{print "MEM="$3"/"$2" AVAIL="$7}\'; '
    'echo "LOAD=$(cut -d" " -f1-3 /proc/loadavg)"; '
    'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null '
    '| head -1 | sed "s/^/GPU=/"'
)


def probe_node(name: str) -> dict:
    cfg = NODES[name]
    rc, out = run(cfg["ssh"] + [PROBE])
    d = {"name": name, "label": cfg["label"], "note": cfg["note"],
         "online": rc == 0, "raw": out.strip()[:400]}
    for line in out.splitlines():
        line = line.strip()
        for key in ("UP", "MEM", "AVAIL", "LOAD", "GPU"):
            if line.startswith(key + "="):
                d[key.lower()] = line[len(key) + 1:].strip()
        if line.startswith("MEM=") and "AVAIL=" in line:
            mem, _, avail = line.partition(" AVAIL=")
            d["mem"] = mem[4:]
            d["avail"] = avail.strip()
    return d


def probe_units(node: str) -> dict[str, str]:
    """One SSH per node for ALL its units — not one per unit."""
    units = [t for t in TARGETS if t["node"] == node]
    if not units:
        return {}
    names = []
    for t in units:
        names.append(t["unit"] + (".timer" if t.get("timer") else ".service"))
    cmd = "; ".join(
        f'printf "%s=%s\\n" {n} "$(systemctl --user is-active {n} 2>/dev/null)"'
        for n in names)
    rc, out = run(NODES[node]["ssh"] + [cmd])
    state = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.strip().partition("=")
            state[k] = v.strip() or "unknown"
    return state


class Fleet:
    """Background poller so a page load never waits on four SSH round-trips."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.nodes: dict[str, dict] = {}
        self.units: dict[str, dict[str, str]] = {}
        self.stamp = "never"
        self.polling = False

    def snapshot(self) -> dict:
        with self.lock:
            return {"nodes": dict(self.nodes), "units": dict(self.units),
                    "stamp": self.stamp}

    def poll_once(self) -> None:
        nodes, units = {}, {}
        threads = []

        def work(n: str) -> None:
            nodes[n] = probe_node(n)
            if nodes[n]["online"]:
                units[n] = probe_units(n)

        for n in NODES:
            th = threading.Thread(target=work, args=(n,), daemon=True)
            th.start()
            threads.append(th)
        for th in threads:
            th.join(timeout=SSH_TIMEOUT + 20)
        with self.lock:
            self.nodes, self.units = nodes, units
            self.stamp = datetime.now().strftime("%H:%M:%S")

    def loop(self) -> None:
        self.polling = True
        while True:
            try:
                self.poll_once()
            except Exception as exc:             # a poller that dies is no poller
                log(f"poll failed: {type(exc).__name__}: {exc}")
            time.sleep(POLL_SECONDS)


FLEET = Fleet()


def do_action(node: str, unit: str, verb: str) -> tuple[bool, str]:
    """Execute ONE whitelisted action. Everything is validated against
    TARGETS first — the request cannot name a unit that is not in the list,
    and cannot name a verb that is not one of these three."""
    if verb not in ("start", "stop", "restart"):
        return False, f"verb {verb!r} is not allowed"
    match = next((t for t in TARGETS
                  if t["node"] == node and t["unit"] == unit), None)
    if match is None:
        return False, f"{node}/{unit} is not in the action list"
    full = unit + (".timer" if match.get("timer") else ".service")
    rc, out = run(NODES[node]["ssh"] + [f"systemctl --user {verb} {full}"],
                  timeout=60)
    log(f"ACTION {verb} {node}/{full} rc={rc} {out.strip()[:120]}")
    return rc == 0, out.strip()[:300] or f"rc={rc}"


# ------------------------------------------------------------------- page

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#fff;color:#111827;font-family:"Segoe UI",Arial,sans-serif;font-size:16px}
.wrap{max-width:1150px;margin:0 auto;padding:22px 20px 70px}
h1{font-size:34px;margin:0 0 2px}
.sub{color:#6b7280;font-size:14px;margin-bottom:20px}
h2{font-size:20px;margin:30px 0 10px;padding-top:16px;border-top:3px solid #e5e7eb}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:13px}
.node{border:1px solid #e5e7eb;border-radius:13px;padding:15px 17px}
.node.off{background:#fef2f2;border-color:#fecaca}
.node h3{margin:0 0 3px;font-size:19px}
.node .note{color:#6b7280;font-size:12px;margin-bottom:9px}
.kv{font-family:Consolas,monospace;font-size:13px;color:#374151;line-height:1.75}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-inline-end:7px}
.on{background:#059669}.offd{background:#dc2626}
table{width:100%;border-collapse:collapse;margin-top:8px}
td,th{padding:8px 9px;border-bottom:1px solid #f3f4f6;text-align:start;font-size:15px}
th{background:#f9fafb;font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:.5px}
.st{font-family:Consolas,monospace;font-size:13px;padding:2px 8px;border-radius:6px}
.act{background:#ecfdf5;color:#059669}.ina{background:#f3f4f6;color:#6b7280}
.unk{background:#fffbeb;color:#d97706}
button{font-family:inherit;font-size:13px;padding:5px 12px;border-radius:7px;
  border:1px solid #d1d5db;background:#fff;cursor:pointer;margin-inline-end:4px}
button:hover{background:#f9fafb}
button.go{border-color:#059669;color:#059669}
button.no{border-color:#dc2626;color:#dc2626}
a.link{display:inline-block;padding:9px 13px;border:1px solid #e5e7eb;border-radius:10px;
  margin:0 7px 7px 0;text-decoration:none;color:#1d4ed8;background:#fff}
a.link:hover{background:#f9fafb}
.foot{margin-top:40px;color:#6b7280;font-size:13px;border-top:3px solid #e5e7eb;padding-top:14px}
#msg{position:fixed;inset-inline-end:18px;bottom:18px;background:#111827;color:#fff;
  padding:11px 16px;border-radius:10px;display:none;max-width:440px;font-size:14px}
"""

JS = """
async function act(node, unit, verb, label){
  if(verb === 'stop' && !confirm('לעצור ' + label + ' על ' + node + '?')) return;
  say('...' + verb + ' ' + label);
  const r = await fetch('/act?token=' + TOKEN, {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({node:node, unit:unit, verb:verb})});
  const j = await r.json();
  say((j.ok ? '\\u2705 ' : '\\u274c ') + label + ' \\u2014 ' + (j.detail || verb));
  setTimeout(()=>location.reload(), 2500);
}
function say(t){ const m=document.getElementById('msg'); m.textContent=t; m.style.display='block';
  clearTimeout(window._t); window._t=setTimeout(()=>m.style.display='none', 6000); }
setTimeout(()=>location.reload(), 30000);
"""


def render(token: str) -> str:
    snap = FLEET.snapshot()
    o = []
    o.append("<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'>")
    o.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    o.append("<title>🏈 THE FOOTBALL</title>")
    o.append(f"<style>{CSS}</style></head><body><div class='wrap'>")
    o.append("<h1>🏈 THE FOOTBALL</h1>")
    o.append(f"<div class='sub'>לוח הבקרה הפרטי של עידו · נמדד {html.escape(snap['stamp'])} · "
             f"מתרענן לבד כל 30 שניות</div>")

    o.append("<h2>🖧 הצי</h2><div class='grid'>")
    for name in NODES:
        n = snap["nodes"].get(name, {"label": NODES[name]["label"],
                                     "note": NODES[name]["note"], "online": False})
        cls = "node" if n.get("online") else "node off"
        dot = "on" if n.get("online") else "offd"
        o.append(f"<div class='{cls}'><h3><span class='dot {dot}'></span>"
                 f"{html.escape(n.get('label',name))}</h3>")
        o.append(f"<div class='note'>{html.escape(n.get('note',''))}</div>")
        if n.get("online"):
            o.append("<div class='kv'>")
            for k, lbl in (("up", "uptime"), ("mem", "זיכרון"),
                           ("avail", "פנוי"), ("load", "עומס"), ("gpu", "GPU")):
                if n.get(k):
                    o.append(f"{lbl}: {html.escape(str(n[k]))}<br>")
            o.append("</div>")
        else:
            o.append("<div class='kv'>לא נגיש</div>")
        o.append("</div>")
    o.append("</div>")

    o.append("<h2>⚙️ שירותים — הפעלה ועצירה</h2>")
    o.append("<table><tr><th>שירות</th><th>מכונה</th><th>מצב</th><th>פעולות</th></tr>")
    for t in TARGETS:
        full = t["unit"] + (".timer" if t.get("timer") else ".service")
        st = snap["units"].get(t["node"], {}).get(full, "—")
        cls = "act" if st == "active" else ("ina" if st in ("inactive", "failed") else "unk")
        o.append("<tr>")
        o.append(f"<td><b>{html.escape(t['label'])}</b><br>"
                 f"<span class='kv'>{html.escape(full)}</span></td>")
        o.append(f"<td>{html.escape(t['node'])}</td>")
        o.append(f"<td><span class='st {cls}'>{html.escape(st)}</span></td>")
        j = json.dumps
        o.append("<td>"
                 f"<button class='go' onclick='act({j(t[chr(110)+chr(111)+chr(100)+chr(101)])},"
                 f"{j(t[chr(117)+chr(110)+chr(105)+chr(116)])},\"start\",{j(t[chr(108)+chr(97)+chr(98)+chr(101)+chr(108)])})'>הפעל</button>"
                 f"<button onclick='act({j(t[chr(110)+chr(111)+chr(100)+chr(101)])},"
                 f"{j(t[chr(117)+chr(110)+chr(105)+chr(116)])},\"restart\",{j(t[chr(108)+chr(97)+chr(98)+chr(101)+chr(108)])})'>אתחל</button>"
                 f"<button class='no' onclick='act({j(t[chr(110)+chr(111)+chr(100)+chr(101)])},"
                 f"{j(t[chr(117)+chr(110)+chr(105)+chr(116)])},\"stop\",{j(t[chr(108)+chr(97)+chr(98)+chr(101)+chr(108)])})'>עצור</button>"
                 "</td></tr>")
    o.append("</table>")

    o.append("<h2>🔗 מסכים</h2>")
    for l in LOCAL_LINKS:
        o.append(f"<a class='link' href='http://127.0.0.1:{l['port']}/' target='_blank'>"
                 f"{html.escape(l['label'])} <span class='kv'>:{l['port']}</span></a>")
    for l in REMOTE_LINKS:
        o.append(f"<a class='link' href='{html.escape(l['url'])}' target='_blank'>"
                 f"{html.escape(l['label'])}</a>")

    o.append("<div class='foot'>"
             "פעולות מוגבלות לרשימה סגורה של שירותים מוכרים — הפעלה, אתחול ועצירה בלבד. "
             "<b>אין כאן שום פעולה שמוחקת משהו.</b><br>"
             "<span dir='ltr'>Closed action list; start/stop/restart only. "
             "Nothing here deletes anything.</span></div>")
    o.append("<div id='msg'></div>")
    o.append(f"<script>const TOKEN={json.dumps(token)};{JS}</script>")
    o.append("</div></body></html>")
    return "".join(o)


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    server_version = "Football/1.0"
    token = ""

    def log_message(self, fmt, *args):           # quiet; we journal ourselves
        return

    def _auth(self) -> bool:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        supplied = (q.get("token", [""])[0]
                    or self.headers.get("X-Token", ""))
        if secrets.compare_digest(supplied, self.token):
            return True
        log(f"401 from {self.client_address[0]} for {self.path.split('?')[0]}")
        self._send(HTTPStatus.UNAUTHORIZED, "text/plain; charset=utf-8",
                   "401 — token required. Open the link the console printed.")
        return False

    def _send(self, status, ctype, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            if not self._auth():
                return
            self._send(HTTPStatus.OK, "text/html; charset=utf-8",
                       render(self.token))
            return
        if path == "/api/status":
            if not self._auth():
                return
            self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                       json.dumps(FLEET.snapshot(), ensure_ascii=False))
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "not found")

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path != "/act":
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "not found")
            return
        if not self._auth():
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8",
                       json.dumps({"ok": False, "detail": f"bad json: {exc}"}))
            return
        ok, detail = do_action(str(payload.get("node", "")),
                               str(payload.get("unit", "")),
                               str(payload.get("verb", "")))
        self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                   json.dumps({"ok": ok, "detail": detail}, ensure_ascii=False))


def main() -> int:
    token = get_token()
    if "--token" in sys.argv:
        print(token)
        return 0

    Handler.token = token
    threading.Thread(target=FLEET.loop, daemon=True).start()

    binds = ["127.0.0.1"]
    ts = tailscale_ip()
    if ts:
        binds.append(ts)

    servers = []
    for host in binds:
        try:
            srv = ThreadingHTTPServer((host, PORT), Handler)
        except OSError as exc:
            log(f"cannot bind {host}:{PORT} — {exc}")
            continue
        servers.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log(f"listening on http://{host}:{PORT}/?token={token}")

    if not servers:
        log("nothing bound — refusing to pretend the console is up")
        return 1

    print("\n" + "=" * 72)
    print("  THE FOOTBALL is up. Open with the token:")
    for host in binds:
        print(f"    http://{host}:{PORT}/?token={token}")
    print("=" * 72 + "\n")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log("shutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
