"""tap_server.py — Chai's listen/tap page. Always-on on eran4, port 8806.

stdlib http.server only, no external assets. Sacred Audio law: nothing ever
autoplays — every <audio> is preload="metadata" and starts paused; the human
presses play.

GET  /            song cards, newest first: .wav player (paused), .mid
                   download link, a one-line trace summary if the song's
                   trace.json exists, and four tap buttons.
GET  /songs/<f>    serves one file straight out of songs/outbox/ (path
                   traversal blocked: basename only, must already exist).
POST /tap          form body {song_id, tap in up|down|fire|skip}; appends one
                   JSON line to feedback/inbox/taps-<UTC date>.jsonl in
                   EXACTLY the schema body/parent.py reads: {"song_id",
                   "tap": +2|+1|0|-1, "ts"}. Silence is neutral: "skip" is
                   logged as tap:0 and parent.py's own reader ignores it.

Archive guard: every write path is checked against ~/darwish-ai before any
file touches disk — this service never writes into the archived pipeline.
"""
import datetime
import glob
import html
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _stream in (sys.stdout, sys.stderr):           # Hebrew/emoji-safe console
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "body"))

import genome                                     # noqa: E402

PORT = getattr(genome, "PORT", 8806)
OUTBOX_DIR = os.path.join(ROOT, "songs", "outbox")
INBOX_DIR = os.path.join(ROOT, "feedback", "inbox")

# name -> (numeric tap value paid through parent.py, the label shown on the button)
TAP_BUTTONS = [
    ("up", 1.0, "\U0001F44D"),                    # 👍
    ("down", -1.0, "\U0001F44E"),                  # 👎
    ("fire", 2.0, "\U0001F525 עוד כזה"),   # 🔥 עוד כזה
    ("skip", 0.0, "⏭"),                       # ⏭
]
TAP_VALUE = {name: v for name, v, _ in TAP_BUTTONS}


def _archive_guard(path):
    bad = os.path.normpath(os.path.abspath(os.path.expanduser(os.path.join("~", "darwish-ai"))))
    rp = os.path.normpath(os.path.abspath(path))
    if rp == bad or rp.startswith(bad + os.sep):
        raise RuntimeError(f"archive path-guard: refusing to touch {rp}")


def write_tap(song_id, tap_value, inbox_dir=None):
    """Append one tap line, in EXACTLY the schema body/parent.py's pay_taps() reads."""
    inbox_dir = inbox_dir or INBOX_DIR
    _archive_guard(inbox_dir)
    os.makedirs(inbox_dir, exist_ok=True)
    date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path = os.path.join(inbox_dir, f"taps-{date}.jsonl")
    rec = {"song_id": song_id, "tap": tap_value,
           "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def _trace_line(song_id):
    trace_path = os.path.join(OUTBOX_DIR, song_id + ".trace.json")
    if not os.path.exists(trace_path):
        return None
    try:
        with open(trace_path, "r", encoding="utf-8") as f:
            trace = json.load(f).get("trace", {})
        n_cells = len(trace)
        n_syn = sum(len(v) for v in trace.values())
        return f"trace saved: {n_cells} cells, {n_syn} tagged pathways"
    except (OSError, ValueError):
        return "trace: (unreadable)"


def list_songs():
    """[{id, wav, mid, trace_line}], newest song_id first."""
    wavs = {os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob(os.path.join(OUTBOX_DIR, "*.wav"))}
    mids = {os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob(os.path.join(OUTBOX_DIR, "*.mid"))}
    ids = sorted(wavs | mids, reverse=True)
    return [{"id": sid, "wav": sid in wavs, "mid": sid in mids,
            "trace_line": _trace_line(sid)} for sid in ids]


def _song_card(song):
    sid = html.escape(song["id"])
    parts = [f'<div class="card"><div class="sid">{sid}</div>']
    if song["wav"]:
        parts.append(f'<audio controls preload="metadata" src="/songs/{sid}.wav"></audio>')
    else:
        parts.append('<p class="muted">(no .wav yet)</p>')
    if song["mid"]:
        parts.append(f'<a class="dl" href="/songs/{sid}.mid" download>&#11015; {sid}.mid</a>')
    if song["trace_line"]:
        parts.append(f'<div class="trace">{html.escape(song["trace_line"])}</div>')
    buttons = "".join(
        f'<form method="POST" action="/tap" class="tapform">'
        f'<input type="hidden" name="song_id" value="{sid}">'
        f'<input type="hidden" name="tap" value="{name}">'
        f'<button type="submit" class="btn">{label}</button></form>'
        for name, _v, label in TAP_BUTTONS)
    parts.append(f'<div class="taps">{buttons}</div></div>')
    return "".join(parts)


def render_page(flash=None):
    songs = list_songs()
    cards = "".join(_song_card(s) for s in songs) or (
        '<p class="muted">Chai has not sung yet. Check back soon '
        '— no notifications, no nagging.</p>')
    flash_html = f'<div class="flash">{html.escape(flash)}</div>' if flash else ""
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>חַי הזמיר</title>
<style>
:root{{color-scheme:light}}
body{{font-family:"Segoe UI",Tahoma,Arial,sans-serif;background:#fffdf7;color:#1a1a1a;
     max-width:720px;margin:0 auto;padding:24px}}
h1{{font-size:26px;margin:0 0 4px}}
.sub{{color:#666;font-size:14px;margin:0 0 20px;line-height:1.5}}
.flash{{background:#eaffea;border:1px solid #8bc98b;border-radius:8px;
       padding:8px 12px;margin-bottom:16px;font-size:13px}}
.card{{border:1px solid #e7e0cf;border-radius:14px;padding:16px 18px;margin:0 0 16px;
      box-shadow:0 1px 3px rgba(0,0,0,.05);background:#fff}}
.sid{{font-weight:700;font-size:14px;margin-bottom:8px;direction:ltr;text-align:left;
     color:#a15c00}}
audio{{width:100%;margin-bottom:8px}}
.dl{{display:inline-block;margin:0 0 8px;color:#a15c00;text-decoration:none;font-size:13px}}
.trace{{color:#888;font-size:12px;margin-bottom:8px;direction:ltr;text-align:left}}
.taps{{display:flex;gap:8px;flex-wrap:wrap;direction:ltr}}
.tapform{{display:inline}}
.btn{{font-size:20px;border:1px solid #ddd;border-radius:10px;background:#faf7ee;
     padding:6px 14px;cursor:pointer}}
.btn:hover{{background:#f0ead9}}
.muted{{color:#999}}
footer{{margin-top:28px;padding-top:12px;border-top:1px solid #eee;color:#888;
       font-size:12px;line-height:1.5}}
</style></head><body>
<h1>חַי הזמיר — לזכר לאור ז"ל</h1>
<p class="sub">A small synaptic-memory bird learning drum+bass structure from Darwish's
psytrance corpus &mdash; pure Python, no torch. Press play; nothing plays on its own.
&#128077; / &#128078; / &#128293; עוד כזה / &#9197; דלג.</p>
{flash_html}
{cards}
<footer>Chai is an experimental context-mixing pattern memory (PPM-family), not a
finished composer &mdash; a rhythm-section skeleton, no melody, no mix. Every tap is
read through the song's saved synaptic trace, sometimes hours or days later;
silence is neutral, never a verdict.</footer>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype, extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/":
            flash = urllib.parse.parse_qs(parsed.query).get("flash", [None])[0]
            self._send(200, render_page(flash), "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/songs/"):
            name = os.path.basename(parsed.path[len("/songs/"):])
            path = os.path.join(OUTBOX_DIR, name)
            if not name or not os.path.isfile(path):
                self._send(404, "not found", "text/plain; charset=utf-8")
                return
            if name.endswith(".wav"):
                ctype, extra = "audio/wav", None
            elif name.endswith(".mid"):
                ctype = "audio/midi"
                extra = {"Content-Disposition": f'attachment; filename="{name}"'}
            else:
                ctype, extra = "application/octet-stream", None
            with open(path, "rb") as f:
                data = f.read()
            self._send(200, data, ctype, extra)
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/tap":
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = urllib.parse.parse_qs(raw)
        song_id = (form.get("song_id") or [""])[0].strip()
        tap_name = (form.get("tap") or ["skip"])[0].strip()
        value = TAP_VALUE.get(tap_name, 0.0)
        if song_id and tap_name in TAP_VALUE:
            write_tap(song_id, value)
            flash = f"tap recorded: {tap_name} on {song_id}"
        else:
            flash = "ignored: missing song_id or unknown tap"
        location = "/?flash=" + urllib.parse.quote(flash)
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):                       # quiet
        pass


def main():
    os.makedirs(OUTBOX_DIR, exist_ok=True)
    os.makedirs(INBOX_DIR, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[tap] חַי הזמיר listening on "
          f"http://0.0.0.0:{PORT}/ (never autoplays, never notifies)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
