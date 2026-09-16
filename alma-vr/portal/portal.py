#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALMAWARE PORTAL — everything Iddo built, on one wall inside the Quest.

Built 2026-09-07 23:14 while he was wearing the headset: "תבנה אפליקציה שנכניס
אותו והיא תיתן לנו פורטל תמידי לתוך המשקפיים עם האפליקציות שלנו, עם ה-ALMAWARE
וכל העניינים."

Served from the PC on :8899 and reached from the headset over Tailscale, so the
Quest needs nothing installed. Every tile is probed when the page is drawn -- a
door that does not answer is drawn DOWN, never hidden and never assumed. That
rule is here because a page on this fleet spent five days claiming "חי" over a
search that had stopped.

Touch targets are sized for a headset ray, not a mouse.
"""
import concurrent.futures as cf
import html
import http.server
import socketserver
import ssl
import time
import urllib.request

PORT = 8899

# --------------------------------------------------------------------------
# ADDRESSES (2026-09-11, WAVE A2 address sweep)
#
# This file used to say PC = "<lan-ip>". The PC is <lan-ip> and has been
# for a while, so 9 of the 11 tiles pointed at an address that belongs to nobody
# and the wall showed 2/11 alive. Worse: the SERVER was probing that same dead
# address, so every render paid a ~2 s connect timeout per tile.
#
# Two different questions, two different answers:
#   PROBE  -- am I, the server, able to reach this service?  -> 127.0.0.1, always.
#   HREF   -- can the VISITOR (Quest headset / phone) reach it? -> tailnet https
#             where a `tailscale serve` mapping exists, LAN address where the
#             service binds 0.0.0.0, and NOTHING at all when it binds loopback.
#
# A loopback-only service is not "down" -- it is alive and unreachable, and the
# wall now says exactly that instead of pretending. Addresses come from
# D:\CLAUDE\fleet_inventory.json (`python fleet_inventory.py --refresh`).
# --------------------------------------------------------------------------
import sys as _sys
_sys.path.insert(0, r"D:\CLAUDE")
try:
    import fleet_inventory as _fi
    PC = _fi.ip("pc", "lan") or "127.0.0.1"
    TAILNET = _fi.load()["tailnet"]["root"].replace("https://", "")
except Exception:                                             # noqa: BLE001
    _fi = None
    PC = "<lan-ip>"
    TAILNET = "<tailnet-host>"

# Some PC services bind their tailnet address directly instead of sitting behind
# `tailscale serve` (FLEET MODE does). Those need the 100.x address, not the name.
PC_TAILNET = (_fi.ip("pc", "tailnet") if _fi else None) or "<tailnet-ip>"

PROBE_HOST = "127.0.0.1"      # never probe ourselves over the LAN -- see above

def _scan_url():
    """The room-scan page (quest-drop :8871). Its save needs a token; the Desktop
    shortcut already carries it, so read the URL from there instead of writing
    the token into this file. Falls back to the token-less page (scan works,
    save would 403) if the shortcut is missing."""
    import os, re
    # 2026-09-09 18:52: the Desktop .url had moved, this fell back to the token-less
    # page, and Iddo's FIRST real headset scan hit /api/save-room four times -> 403.
    # The source of truth is quest-drop/token.txt (what serve.py checks); read it
    # first, the shortcut second, and only then the token-less page.
    tok_file = os.path.join("D:" + os.sep, "CLAUDE", "quest-drop", "token.txt")
    try:
        with open(tok_file, encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return f"https://{PC}:8871/quest-mesh.html?t={tok}"
    except OSError:
        pass
    for lnk in (os.path.join(os.path.expanduser("~"), "Desktop", "QUEST - לשאוב את החדר.url"),
                os.path.join(os.path.expanduser("~"), "Desktop", "תוצרי קלוד", "QUEST - לשאוב את החדר.url")):
        try:
            with open(lnk, encoding="utf-8", errors="replace") as f:
                m = re.search(r"^URL=(\S+)", f.read(), re.M)
            if m:
                return m.group(1)
        except OSError:
            pass
    return f"https://{PC}:8871/quest-mesh.html"


# (icon, name, href-for-the-visitor, probe-url-for-the-server, description, reach)
# reach: "tailnet" = any device signed into Tailscale · "lan" = same Wi-Fi ·
#        "local"   = binds 127.0.0.1 only, so NO other device can open it.
TILES = [
    ("🛋️", "לשאוב את החדר", _scan_url(), f"https://{PC}:8871/",
     "Quest → המש של החדר למחשב (WebXR)", "lan"),
    ("🏠", "CONTROL", f"https://{TAILNET}:8896/control", "http://127.0.0.1:8896/",
     "לוח הבקרה · הצי, הדלתות, הפעולות", "tailnet"),
    ("⚖️", "QUORUM", f"https://{TAILNET}:8099/", "http://127.0.0.1:8099/",
     "שקלא וטריא · כל המודלים מתווכחים", "tailnet"),
    # RETIRED 2026-09-11 (holy harness law): ALMIDO IDE eran3 :8443 -> F:/ALMAWARE-ARCHIVE/HARNESSES-20260911/eran3-almido-ide-8443
    ("🎙️", "המיק בטלפון", f"https://{TAILNET}:8893/", "http://127.0.0.1:8893/",
     "הטלפון כמיקרופון", "tailnet"),
    # RETIRED 2026-09-11 (holy harness law): VOICE CODER :8894 -> F:/ALMAWARE-ARCHIVE/HARNESSES-20260911/voice-coder-8894
    ("👁️", "ERAN", "https://<tailnet-host>:8820/",
     "https://<tailnet-host>:8820/", "החלון של ערן", "tailnet"),
    # RETIRED 2026-09-11 (Iddo 18:21 "תוריד את הוויס אנט פרם"): VOICE ANT FARM :8765 taken down on the PC;
    # voice-ant-farm units disabled on eran2/3/4 (RAMCHAT 09-15 06:48). Tile removed 2026-09-15 by bw-W4-PC-PAGES.
    ("🎨", "GALERIA", f"http://{PC}:8861/", "http://127.0.0.1:8861/",
     "כל מה שהמודלים יצרו", "local"),
    ("🖥️", "ALMAWARE", f"http://{PC}:8790/", "http://127.0.0.1:8790/",
     "הקוקפיט", "local"),
    ("🔎", "ALMA-RECALL", f"http://{PC}:8794/", "http://127.0.0.1:8794/",
     "חיפוש בכל הזיכרון", "local"),
    ("🏠", "MAKOM", f"http://{PC}:8858/", "http://127.0.0.1:8858/",
     "מקום", "local"),
    # FLEET MODE binds 127.0.0.1 AND the PC's tailnet address directly (no
    # `tailscale serve` in front), so the headset reaches it at the 100.x URL.
    # 2026-09-11: it had no launcher and was simply not running — restored to
    # autostart as the scheduled task ALMA-FleetMode-8872.
    ("🎛️", "FLEET MODE", f"http://{PC_TAILNET}:8872/", "http://127.0.0.1:8872/",
     "מצב הצי · ארבע הקופסאות, החלפת מודלים", "tailnet"),
    # RETIRED 2026-09-11 (holy harness law): ALMIDO window :8877 (almido_window.py) -> F:/ALMAWARE-ARCHIVE/HARNESSES-20260911/almido-window-8877
]


def probe(url, timeout=4):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


_probe_memo = {"t": 0.0, "codes": None}


def page():
    # One probe round costs 6-9 s (seven tiles point at <lan-ip> ports that
    # only listen on 127.0.0.1, so each is a ~2 s drop-wait; ERAN's tailnet TLS
    # is ~3 s). Measured 2026-09-09: concurrent requests multiplied that to
    # 40-60 s. Reuse the last round for 15 s so a headset reload is instant.
    now = time.time()
    if _probe_memo["codes"] is not None and now - _probe_memo["t"] < 15:
        codes = _probe_memo["codes"]
    else:
        with cf.ThreadPoolExecutor(max_workers=len(TILES)) as ex:
            codes = list(ex.map(lambda t: probe(t[3]), TILES))
        _probe_memo["t"], _probe_memo["codes"] = now, codes

    cards = []
    for (icon, name, url, _probe_url, what, reach), code in zip(TILES, codes):
        up = bool(code) and code < 500
        cls = "up" if up else "down"
        badge = ("חי" if code == 200 else
                 f"מוגן {code}" if code in (401, 403) else
                 str(code) if code else "כבוי")
        # Honesty: a loopback-only service is alive but NOT openable from this
        # headset/phone. Say so on the tile instead of handing over a dead link.
        reach_note = {"tailnet": "", "lan": " · באותו וויפי",
                      "local": " · מהמחשב בלבד"}[reach]
        if reach == "local" and up:
            badge = "מקומי"
            cls = "up local"
        cards.append(f"""
      <a class="tile {cls}" href="{html.escape(url)}">
        <div class="ico">{icon}</div>
        <div class="body"><div class="name">{html.escape(name)}</div>
          <div class="what">{html.escape(what + reach_note)}</div></div>
        <div class="badge">{html.escape(badge)}</div>
      </a>""")

    live = sum(1 for c in codes if c and c < 500)
    now = time.strftime("%H:%M:%S")

    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>ALMAWARE PORTAL</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;padding:40px 32px;background:#fff;color:#111;
      font:20px/1.5 -apple-system,Segoe UI,Arial,sans-serif}}
 h1{{font-size:44px;margin:0 0 4px;letter-spacing:-.5px}}
 .sub{{color:#666;font-size:19px;margin:0 0 30px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:20px}}
 .tile{{display:flex;align-items:center;gap:20px;padding:26px 24px;border-radius:16px;
        text-decoration:none;color:inherit;border:2px solid #e6e6e6;background:#fafafa;
        transition:transform .1s,box-shadow .1s;min-height:112px}}
 .tile:hover{{transform:translateY(-3px);box-shadow:0 8px 26px rgba(0,0,0,.13)}}
 .tile.up{{border-color:#0a7d2e;background:#f4fbf6}}
 .tile.down{{border-color:#ddd;background:#f7f7f7;opacity:.62}}
 .ico{{font-size:44px;line-height:1}}
 .body{{flex:1;min-width:0}}
 .name{{font-size:27px;font-weight:700;margin-bottom:3px}}
 .what{{font-size:17px;color:#666}}
 .badge{{font-size:16px;font-weight:700;padding:7px 15px;border-radius:999px;
         background:#eee;color:#555;white-space:nowrap}}
 .up .badge{{background:#0a7d2e;color:#fff}}
 .tile.local{{border-color:#b8860b;background:#fffdf4}}
 .local .badge{{background:#b8860b;color:#fff}}
 .foot{{margin-top:34px;color:#888;font-size:16px;border-top:1px solid #eee;padding-top:16px}}
</style></head><body>
<h1>ALMAWARE</h1>
<p class="sub">כל מה שבנית, על קיר אחד · {live} מתוך {len(TILES)} חיים · נבדק {now}</p>
<div class="grid">{"".join(cards)}</div>
<p class="foot">כל אריח נבדק ברגע שהדף נטען. אפור = לא עונה עכשיו, לא מוסתר.
צהוב "מקומי" = חי על המחשב אבל מאזין רק ל-127.0.0.1, כלומר לא ייפתח מהקסדה או מהטלפון.
הכתובות מגיעות מ-fleet_inventory.json · רענן כדי למדוד שוב.</p>
</body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with S(("0.0.0.0", PORT), H) as srv:
        print(f"ALMAWARE PORTAL on http://{PC}:{PORT}/", flush=True)
        srv.serve_forever()
