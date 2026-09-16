"""listen_server.py (eran1 edition, 2026-08-25) -- ERAN, out loud, at a link
that clicks from Iddo's PC.

Two honest sections, never mixed:
  1. HIS OWN MOUTH  -- wavs his articulatory tract produced (eran-voice-out/*
     + songs/outbox/say-*.wav), with the sidecar numbers through his own ear.
  2. ECHO-BABBLE    -- songs/outbox/babble-*.wav: the organism RE-SEQUENCES
     snippets of Iddo's real recorded voice by its own choice. NOT synthesis,
     NOT his own voice yet -- the page says so, because the sidecar says so.

Auto-refreshes every 15 s so live babbling appears as it happens.
Pure stdlib. Binds 0.0.0.0:8807 (LAN link for the PC). Serves wavs read-only.
"""
import http.server
import json
import socketserver
import urllib.parse
import wave
from datetime import datetime
from pathlib import Path

PORT = 8807
HOME = Path.home()
OUTBOX = HOME / "eran-brain" / "songs" / "outbox"
VOICEOUT = HOME / "eran-voice-out"
SEARCHLIVE = HOME / "eran-search-live"
DIRS = {"outbox": OUTBOX, "voiceout": VOICEOUT, "live": SEARCHLIVE}

SIM_KEYS = ("final_cosine_sim_to_target_through_own_ear",
            "final_sim", "best_sim", "sim")


def _meta(w: Path):
    j = w.with_suffix(".json")
    if not j.exists():
        # gym pairs are named a few seconds apart; take any same-stem prefix json
        cand = sorted(w.parent.glob(w.stem.split("T")[0] + "*.json"))
        j = cand[0] if cand else j
    try:
        return json.loads(j.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _dur(w: Path):
    try:
        with wave.open(str(w), "rb") as f:
            return f.getnframes() / f.getframerate()
    except Exception:
        return None


def _entry(w: Path, dirkey: str):
    meta = _meta(w)
    sim = next((meta[k] for k in SIM_KEYS if isinstance(meta.get(k), (int, float))), None)
    chosen = meta.get("chosen")
    note = ""
    if isinstance(chosen, list) and chosen:
        sims = [c.get("sim") for c in chosen if isinstance(c.get("sim"), (int, float))]
        note = f"{len(chosen)} snippets chosen"
        if sims:
            note += f" &middot; mean sim {sum(sims)/len(sims):.3f}"
    return {
        "file": w.name, "dir": dirkey,
        "label": meta.get("target_label_used_for_lookup") or meta.get("unit") or w.stem,
        "sim": sim, "note": note, "dur": _dur(w),
        "mtime": w.stat().st_mtime,
        "when": datetime.fromtimestamp(w.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


# food/train swapped synthetic->human-t06 at this epoch (Iddo's order
# 2026-08-25 02:39). Babbles OLDER than it re-sequenced TTS clips and sounded
# like "a model voice, not me and not ERAN" — those never appear here again.
FOOD_SWAP_EPOCH = 1787614765


def sections():
    mouth, live, echo = [], [], []
    if OUTBOX.is_dir():
        for w in OUTBOX.glob("say-*.wav"):
            mouth.append(_entry(w, "outbox"))
        for w in OUTBOX.glob("babble-*.wav"):
            e = _entry(w, "outbox")
            if e["mtime"] > FOOD_SWAP_EPOCH:
                echo.append(e)
    if VOICEOUT.is_dir():
        for w in VOICEOUT.glob("*.wav"):
            mouth.append(_entry(w, "voiceout"))
    if SEARCHLIVE.is_dir():
        for w in SEARCHLIVE.glob("LIVE-*.wav"):
            live.append(_entry(w, "live"))
    mouth.sort(key=lambda e: e["mtime"], reverse=True)
    live.sort(key=lambda e: e["file"])
    echo.sort(key=lambda e: e["mtime"], reverse=True)
    return mouth, live, echo[:30]


HEAD = """<!doctype html><html lang="he"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15">
<title>ERAN - listen live</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{font-family:"Segoe UI",Arial,sans-serif;background:#fff;color:#14181f;margin:0;padding:28px 20px 60px}
 h1{margin:0 0 2px;font-size:30px;color:#0b1b3a} h2{color:#0b1b3a;margin-top:34px}
 .sub{color:#5a6474;margin-bottom:18px;font-size:15px}
 .note{background:#fff6d6;border:1px solid #e6b800;border-radius:8px;padding:10px 14px;
       margin:10px 0 18px;font-size:14px;color:#4a3800;max-width:860px;line-height:1.5}
 .card{border:1px solid #dfe4ec;border-radius:10px;padding:12px 16px;margin:0 0 10px;
       max-width:860px;background:#f8fafc;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
 .card.top{background:#f2fbf4;border-color:#bfe6c8}
 audio{height:38px}
 .who{font-weight:700;font-size:17px;color:#0b1b3a;min-width:120px;max-width:280px;overflow-wrap:anywhere}
 .num{font-variant-numeric:tabular-nums;font-size:13px;color:#42506b;line-height:1.5}
 .big{font-size:18px;font-weight:700;color:#1f8b4c}
 .when{color:#8a94a6;font-size:12px;margin-inline-start:auto;text-align:end}
 .foot{margin-top:30px;color:#8a94a6;font-size:12px;max-width:860px;line-height:1.6}
</style></head><body>
<h1>ERAN &mdash; live, out loud</h1>
<div class="sub">eran1 &middot; auto-refreshes every 15 s &middot; newest first</div>
"""

LIVE_NOTE = ("<h2>&#128293; LIVE &mdash; הפה שלו, עכשיו</h2>"
             "<div class='note'>כל קליפ = הניסיון הכי טוב של עובד חיפוש אחד, דרך הצינור של עצמו &middot; each clip = one search worker's best so far, through his own tube. Refreshed every 10 min by refresh_live.py.<br><b>wdist</b> &#8212; נמוך = קרוב יותר להקלטות האמיתיות (lower is closer). <b>vs ma</b> &#8212; המרווח מ-מָה, חייב להיות חיובי (must be positive). <b>closure</b> &#8212; סגירת השפתיים; עידו האמיתי = 0.192. <b>CONTROL</b> &#8212; לא למד כלום, זו הרצפה (the floor).</div>")
MOUTH_NOTE = ("<h2>&#128068; His own mouth / &#1492;&#1508;&#1492; &#1513;&#1500;&#1493;</h2>"
              "<div class='note'>&#1490;&#1500;&#1497; &#1511;&#1493;&#1500; &#1513;&#1492;&#1510;&#1497;&#1504;&#1493;&#1512; &#1513;&#1500;&#1493; &#1492;&#1508;&#1497;&#1511; &#1489;&#1506;&#1510;&#1502;&#1493; "
              "(&#1500;&#1488; TTS, &#1500;&#1488; &#1492;&#1511;&#1500;&#1496;&#1492;) &middot; waves his articulatory tract produced itself.</div>")
ECHO_NOTE = ("<h2>&#128257; Real babble / &#1489;&#1488;&#1489;&#1500; &#1488;&#1502;&#1497;&#1514;&#1497;</h2>"
             "<div class='note'>&#1492;&#1489;&#1495;&#1497;&#1512;&#1493;&#1514; &#1513;&#1500;&#1493; &#1502;&#1514;&#1493;&#1498; <b>&#1492;&#1511;&#1493;&#1500; &#1492;&#1488;&#1502;&#1497;&#1514;&#1497; &#1513;&#1500; &#1506;&#1497;&#1491;&#1493;</b> (t06) &middot; "
             "&#1502;&#1488;&#1494; &#1492;&#1495;&#1500;&#1508;&#1514; &#1492;&#1488;&#1493;&#1499;&#1500; 02:39 &middot; his choices over Iddo's REAL recorded voice, post-food-swap only.</div>")


def _card(e, top=False):
    sim = f"<span class='big'>{e['sim']:.3f}</span>" if isinstance(e["sim"], (int, float)) else ""
    dur = f"{e['dur']:.2f}s" if e["dur"] else "?"
    num = " &middot; ".join(x for x in (sim and f"through his own ear {sim}", e["note"], dur) if x)
    src = f"/wav/{e['dir']}/{urllib.parse.quote(e['file'])}"
    return (f"<div class='card {'top' if top else ''}'><div class='who'>{e['label']}</div>"
            f"<audio controls preload='none' src='{src}'></audio>"
            f"<div class='num'>{num}</div><div class='when'>{e['when']}</div></div>")


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            mouth, live, echo = sections()
            body = [HEAD, ECHO_NOTE]
            body += [_card(e, i == 0) for i, e in enumerate(echo)] or ["<div class='card'>&#1492;&#1489;&#1488;&#1489;&#1500; &#1492;&#1489;&#1488; &#1502;&#1490;&#1497;&#1506; &#1489;&#1506;&#1493;&#1491; &#1512;&#1490;&#1506; / next babble lands in seconds</div>"]
            body.append(LIVE_NOTE)
            body += [_card(e) for e in live] or ["<div class='card'>first sync in a few minutes</div>"]
            body.append(MOUTH_NOTE)
            body += [_card(e) for e in mouth] or ["<div class='card'>none yet</div>"]
            body.append("<div class='foot'>served read-only from eran1 &middot; "
                        "~/eran-voice-out + ~/eran-brain/songs/outbox &middot; nothing is played automatically</div></body></html>")
            data = "".join(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if p.startswith("/wav/"):
            try:
                dirkey, name = p[len("/wav/"):].split("/", 1)
                base = DIRS[dirkey].resolve()
                f = (base / urllib.parse.unquote(name)).resolve()
            except (ValueError, KeyError):
                self.send_error(404)
                return
            if f.parent != base or not f.exists():
                self.send_error(404)
                return
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", PORT), H) as httpd:
        print(f"ERAN listen page -> http://0.0.0.0:{PORT}/", flush=True)
        httpd.serve_forever()
