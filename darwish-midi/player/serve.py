"""serve.py -- a GUI for the Darwish renders. Iddo, 2026-08-23 09:10: "load darwish with a gui".

Serves D:\\CLAUDE\\darwish-midi\\songs\\outbox as a bright player page on 127.0.0.1:8810.
A local http:// URL is the one link shape that IS clickable for Iddo (CLICKABLE-ACCESS LAW),
which is why this is a server and not an .html file dropped on the Desktop.

Range requests are implemented by hand: SimpleHTTPRequestHandler has no Range support and the
renders are ~73 MB, so without it the seek bar is dead and the browser has to buffer the whole
file before the first sound.

SACRED AUDIO LAW: nothing autoplays. He presses play.
"""
import contextlib
import html
import http.server
import json
import os
import re
import socketserver
import urllib.parse
import wave

OUTBOX = r"D:\CLAUDE\darwish-midi\songs\outbox"
PORT = 8810

CSS = """
*{box-sizing:border-box}
body{margin:0;font:16px/1.55 "Segoe UI",system-ui,sans-serif;background:#fbf7ef;color:#1d1a15}
.wrap{max-width:860px;margin:0 auto;padding:34px 22px 70px}
h1{margin:0 0 4px;font-size:30px;letter-spacing:-.02em}
.sub{color:#6b6255;margin:0 0 26px;font-size:15px}
.card{background:#fff;border:1px solid #e6dece;border-radius:14px;padding:20px 22px;margin:0 0 18px;
      box-shadow:0 1px 3px rgba(60,45,20,.06)}
.card h2{margin:0 0 3px;font-size:18px;word-break:break-all}
.meta{color:#7a7061;font-size:13.5px;margin:0 0 12px}
audio{width:100%;height:42px;margin:6px 0 10px}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0}
.f{background:#f4efe4;border:1px solid #e6dece;border-radius:999px;padding:4px 12px;font-size:13px;color:#4a4238}
.f b{color:#1d1a15;font-weight:600}
a.dl{display:inline-block;margin:12px 10px 0 0;padding:8px 15px;border-radius:9px;text-decoration:none;
     background:#1d1a15;color:#fbf7ef;font-size:14px}
a.dl.alt{background:#fff;color:#1d1a15;border:1px solid #cfc4ae}
.note{font-size:13.5px;color:#7a7061;border-left:3px solid #e0d5bd;padding:2px 0 2px 13px;margin:22px 0 0}
.empty{color:#8a8072}
code{background:#f4efe4;padding:1px 5px;border-radius:4px;font-size:13px}
"""

PAGE = """<!doctype html><meta charset="utf-8"><title>DARWISH - from the model</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{css}</style>
<div class="wrap">
<h1>&#1491;&#1512;&#1493;&#1493;&#1497;&#1513; &#8212; &#1502;&#1492;&#1502;&#1493;&#1491;&#1500; / DARWISH &#8212; from the model</h1>
<p class="sub">The 1.36M-parameter transformer on eran4 that learned 271 Darwish tracks,
rendered through psy_synth. Nothing autoplays &#8212; press play.</p>
{cards}
<p class="note">&#1500;&#1494;&#1499;&#1512;&#1493; &#1513;&#1500; &#1500;&#1488;&#1493;&#1512; &#1494;"&#1500;. This is a memorial, not a training run.<br>
Served locally from <code>{outbox}</code> &#183; port {port}</p>
</div>"""


def wav_seconds(path):
    try:
        with contextlib.closing(wave.open(path, "rb")) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def build_page():
    try:
        names = sorted(os.listdir(OUTBOX), reverse=True)
    except OSError:
        names = []

    # the sidecar json belongs to the run, not to one filename stem -- take the newest
    sidecar = {}
    for n in names:
        if n.endswith(".json"):
            try:
                sidecar = json.load(open(os.path.join(OUTBOX, n), encoding="utf-8"))
            except Exception:
                sidecar = {}
            break

    q = urllib.parse.quote
    cards = []
    for wav in [n for n in names if n.lower().endswith(".wav")]:
        stem = wav[:-4]
        full = os.path.join(OUTBOX, wav)
        mb = os.path.getsize(full) / 1e6
        secs = wav_seconds(full)
        dur = "%d:%02d" % (int(secs) // 60, int(secs) % 60) if secs else "?"
        mid = stem + ".mid"
        has_mid = os.path.exists(os.path.join(OUTBOX, mid))

        facts = ['<span class="f">length <b>%s</b></span>' % dur]
        for k in ("bpm", "key", "step", "temp", "top_k", "n_tokens"):
            if k in sidecar:
                v = sidecar[k]
                v = ("%.1f" % v) if isinstance(v, float) else v
                facts.append('<span class="f">%s <b>%s</b></span>' % (k, html.escape(str(v))))
        facts.append('<span class="f">size <b>%.0f MB</b></span>' % mb)

        seed = sidecar.get("seed_from")
        meta = ("seeded from " + html.escape(os.path.basename(seed))) if seed else "model sample"

        card = ('<div class="card"><h2>%s</h2><p class="meta">%s</p>'
                '<audio controls preload="metadata" src="/f/%s"></audio>'
                '<div class="facts">%s</div>'
                '<a class="dl" href="/f/%s" download>WAV</a>'
                % (html.escape(stem), meta, q(wav), "".join(facts), q(wav)))
        if has_mid:
            card += '<a class="dl alt" href="/f/%s" download>MIDI</a>' % q(mid)
        cards.append(card + "</div>")

    if not cards:
        cards = ['<div class="card empty">No renders in the outbox yet.</div>']
    return PAGE.format(css=CSS, cards="\n".join(cards),
                       outbox=html.escape(OUTBOX), port=PORT)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = build_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/f/"):
            return self.send_media(urllib.parse.unquote(self.path[3:]))
        self.send_error(404)

    def send_media(self, name):
        name = os.path.basename(name)          # no traversal: basename only
        path = os.path.join(OUTBOX, name)
        if not os.path.isfile(path):
            return self.send_error(404)
        size = os.path.getsize(path)
        ctype = {".wav": "audio/wav", ".mid": "audio/midi",
                 ".json": "application/json"}.get(
            os.path.splitext(name)[1].lower(), "application/octet-stream")

        start, end, partial = 0, size - 1, False
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                s, e = m.group(1), m.group(2)
                if s:
                    start = int(s)
                    if e:
                        end = min(int(e), size - 1)
                elif e:                        # suffix range: the last N bytes
                    start = max(0, size - int(e))
                if start <= end < size:
                    partial = True

        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()

        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(262144, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    return                     # browser seeked away -- normal, not an error
                left -= len(chunk)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    with Server(("127.0.0.1", PORT), Handler) as httpd:
        print("darwish player -> http://127.0.0.1:%d/" % PORT, flush=True)
        httpd.serve_forever()
