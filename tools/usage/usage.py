"""SHAVITI — what Claude has actually consumed on this machine. 127.0.0.1:8849

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תעשה לי אפליקציית... קלוד usage שתמיד נותנת לי את היוסאג'"* and, plainly,
*"כמה נשאר"*.

## The one thing this page will never do

**It cannot tell you how much of your plan is left.** Anthropic does not write your
subscription quota to this disk, so no local program can honestly report it — and a
meter that showed a made-up "remaining" would be worse than no meter, because you would
plan around it. What IS on disk, in every one of the 1,600-odd session transcripts under
`~/.claude/projects`, is the exact token usage of every single message. So this measures
**consumption**, precisely, and says so at the top of the page.

## Why a local server and not a file

Iddo's own law: a `C:\\...` path is not clickable in his app and never has been, but
`http://127.0.0.1:PORT/` is. So the meter lives at a link he can actually press.

    python usage.py            # then open http://127.0.0.1:8849
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.expanduser(r"~\.claude\projects")
PORT = 8849
# USD per million tokens: (fresh input, output, cache WRITE, cache READ).
# The cache columns are the whole reason this is split out. All-time input here is 22.9
# BILLION tokens and almost all of it is cache reads, which bill at a tenth of input --
# pricing it flat would have shown Iddo a number several times too big, on a page whose
# entire point is not misleading him about money.
PRICE = {
    "opus":   (15.0, 75.0, 18.75, 1.50),
    "sonnet": (3.0, 15.0, 3.75, 0.30),
    "haiku":  (0.80, 4.0, 1.00, 0.08),
    "fable":  (3.0, 15.0, 3.75, 0.30),
}

_lock = threading.Lock()
_state = {"days": {}, "models": {}, "projects": {}, "sessions": {},
          "scanned": 0, "files": 0, "when": "", "seconds": 0.0, "grew": 0}
# path -> (bytes already read, its accumulated counters). THIS IS THE WHOLE FIX.
# The first version re-read all 940 MB every 60 s and the scan takes 84 s, so it never
# stopped: measured at 99.7% of a core, continuously, on Iddo's machine while he was
# trying to work. A meter that costs a core to tell you what things cost is a bad joke,
# and it broke his own standing law -- do not overload the PC. Now a file is re-opened
# only from the byte where it was last left off, and a finished session is never read
# twice.
_seen: dict[str, tuple[int, dict]] = {}
_totals = {"days": collections.defaultdict(lambda: collections.Counter()),
           "models": collections.defaultdict(lambda: collections.Counter()),
           "projects": collections.defaultdict(lambda: collections.Counter()),
           "sessions": collections.defaultdict(lambda: collections.Counter()),
           "lines": 0}


def _tier(model: str) -> str:
    m = (model or "").lower()
    for k in PRICE:
        if k in m:
            return k
    return "other"


def scan(full: bool = False) -> None:
    """Walk the transcripts and add up what is there.

    Incremental on purpose: 940 MB of jsonl is too much to re-read every refresh, so a
    file is only re-opened when it has GROWN, and only the new bytes are parsed. That is
    also what makes the live session's number move while you watch it.
    """
    t0 = time.time()
    files = new_lines = grew = 0
    days, models = _totals["days"], _totals["models"]
    projects, sessions = _totals["projects"], _totals["sessions"]

    for dirpath, _, names in os.walk(ROOT):
        proj = os.path.basename(dirpath)
        for n in names:
            if not n.endswith(".jsonl"):
                continue
            p = os.path.join(dirpath, n)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            files += 1
            start = _seen.get(p, (0, None))[0]
            if size <= start and not full:
                continue                       # nothing new in this session, skip it
            grew += 1
            try:
                f = io.open(p, encoding="utf-8", errors="replace")
            except OSError:
                continue
            with f:
                if start and not full:
                    f.seek(start)
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    msg = o.get("message") or {}
                    u = msg.get("usage") or {}
                    if not u:
                        continue
                    new_lines += 1
                    fresh = int(u.get("input_tokens", 0) or 0)
                    cw = int(u.get("cache_creation_input_tokens", 0) or 0)
                    cr = int(u.get("cache_read_input_tokens", 0) or 0)
                    out = int(u.get("output_tokens", 0) or 0)
                    ts = (o.get("timestamp") or "")[:10] or "unknown"
                    tier = _tier(msg.get("model", ""))
                    for bucket, key in ((days, ts), (models, tier),
                                        (projects, proj), (sessions, n[:8])):
                        c = bucket[key]
                        c["in"] += fresh + cw + cr
                        c["out"] += out
                        c["fresh"] += fresh
                        c["cw"] += cw
                        c["cr"] += cr
                        c["msgs"] += 1
                _seen[p] = (f.tell() if not full else size, None)
    _totals["lines"] += new_lines

    with _lock:
        _state.update(days=dict(days), models=dict(models), projects=dict(projects),
                      sessions=dict(sessions), scanned=_totals["lines"], files=files,
                      grew=grew,
                      when=dt.datetime.now().strftime("%H:%M:%S"),
                      seconds=round(time.time() - t0, 1))


def cost(tier: str, c: collections.Counter) -> float:
    """Priced per column. Cache reads are a tenth of input and dominate the volume."""
    if tier not in PRICE:
        return 0.0
    i, o, cw, cr = PRICE[tier]
    return (c["fresh"] / 1e6 * i + c["out"] / 1e6 * o
            + c["cw"] / 1e6 * cw + c["cr"] / 1e6 * cr)


def num(n) -> str:
    return "{:,}".format(int(n))


def page() -> str:
    with _lock:
        s = dict(_state)
    days = s["days"]
    today = dt.date.today().isoformat()
    week = [(dt.date.today() - dt.timedelta(days=i)).isoformat() for i in range(7)]
    t = days.get(today, collections.Counter())
    w = collections.Counter()
    for d in week:
        w.update(days.get(d, {}))
    allc = collections.Counter()
    for c in days.values():
        allc.update(c)
    spend = sum(cost(k, v) for k, v in s["models"].items())

    def bars(title, rows, keyfmt=str, top=12):
        rows = sorted(rows.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"]))[:top]
        big = max([r[1]["in"] + r[1]["out"] for r in rows] or [1])
        out = ['<h2>%s</h2><table>' % html.escape(title)]
        for k, c in rows:
            tot = c["in"] + c["out"]
            out.append(
                '<tr><td class=k>%s</td><td class=b>'
                '<span style="width:%.1f%%"></span></td>'
                '<td class=n>%s</td><td class=s>%s msgs</td></tr>'
                % (html.escape(keyfmt(k))[:44], 100.0 * tot / big, num(tot),
                   num(c["msgs"])))
        return "".join(out) + "</table>"

    return """<!doctype html><meta charset=utf-8>
<meta http-equiv=refresh content=30>
<title>Claude usage</title><style>
body{font:15px/1.5 "Segoe UI",system-ui,sans-serif;background:#fbfcfe;color:#141828;
     margin:0;padding:26px 32px;max-width:1180px}
h1{margin:0 0 2px;font-size:27px;letter-spacing:-.3px}
h2{margin:26px 0 8px;font-size:15px;text-transform:uppercase;letter-spacing:1.1px;
   color:#5a6684}
.note{background:#fff6e6;border-left:5px solid #e8a33d;padding:11px 15px;margin:14px 0 4px;
      border-radius:0 7px 7px 0;font-size:14px}
.cards{display:flex;gap:16px;flex-wrap:wrap;margin-top:18px}
.card{background:#fff;border:1px solid #e3e8f2;border-radius:12px;padding:16px 20px;
      min-width:186px;box-shadow:0 1px 3px rgba(20,30,60,.05)}
.card .v{font-size:29px;font-weight:650;letter-spacing:-.5px}
.card .l{color:#6b7590;font-size:12.5px;text-transform:uppercase;letter-spacing:.8px}
table{border-collapse:collapse;width:100%%}
td{padding:3px 8px 3px 0;vertical-align:middle}
.k{color:#2a3350;white-space:nowrap;font-size:14px}
.b{width:56%%}.b span{display:block;height:11px;border-radius:6px;
   background:linear-gradient(90deg,#4d7fe0,#7aa2f0)}
.n{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
.s{color:#8b93a8;font-size:12px;white-space:nowrap;padding-left:12px}
footer{margin-top:30px;color:#8b93a8;font-size:12.5px}
</style>
<h1>Claude usage on this machine</h1>
<div class=note><b>This is what has been CONSUMED, not what is left.</b>
Your plan's remaining quota is not written to this disk by anything, so no local page can
honestly show it. Everything below is counted from the %s session transcripts themselves.</div>
<div class=cards>
  <div class=card><div class=l>today</div><div class=v>%s</div><div class=l>tokens</div></div>
  <div class=card><div class=l>last 7 days</div><div class=v>%s</div><div class=l>tokens</div></div>
  <div class=card><div class=l>all time</div><div class=v>%s</div><div class=l>tokens</div></div>
  <div class=card><div class=l>output all time</div><div class=v>%s</div><div class=l>tokens written</div></div>
  <div class=card><div class=l>list price</div><div class=v>$%s</div><div class=l>cache priced correctly</div></div>
</div>
%s%s%s%s
<footer>%s usage records from %s transcripts &middot; %d file(s) had new lines this pass, %.1f s &middot; refreshed %s
&middot; page refreshes every 30 s, data every 10 min &middot; port 8849, claimed in RAMCHAT</footer>
""" % (num(s["files"]), num(t["in"] + t["out"]), num(w["in"] + w["out"]),
       num(allc["in"] + allc["out"]), num(allc["out"]), "{:,.0f}".format(spend),
       bars("by day", {k: v for k, v in days.items() if k in week},
            lambda d: d, 7),
       bars("by model", s["models"]),
       bars("by project", s["projects"]),
       bars("busiest sessions", s["sessions"], top=8),
       num(s["scanned"]), num(s["files"]), s.get("grew", 0), s["seconds"], s["when"])


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/rescan"):
            scan()
        body = page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Claude usage meter.")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--once", action="store_true", help="print the totals and exit")
    a = ap.parse_args(argv)

    print("reading transcripts under %s ..." % ROOT)
    scan()
    with _lock:
        s = dict(_state)
    allc = collections.Counter()
    for c in s["days"].values():
        allc.update(c)
    print("%s usage records from %s transcripts in %.1f s"
          % (num(s["scanned"]), num(s["files"]), s["seconds"]))
    print("all time: %s in, %s out" % (num(allc["in"]), num(allc["out"])))
    if a.once:
        return 0

    def refresher():
        while True:
            time.sleep(600)          # ten minutes. It reads only what grew, so this is plenty.
            try:
                scan()
            except Exception:                                       # noqa: BLE001
                pass

    threading.Thread(target=refresher, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print("\n  http://127.0.0.1:%d\n" % a.port)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
