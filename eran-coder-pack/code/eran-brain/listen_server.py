"""listen_server.py -- ERAN, out loud, at a link that actually clicks.

Iddo has asked for clickable links more than a hundred times. Windows paths
(C:\\..., D:\\...) do not click in his app; a local http:// URL does. Handing him
a path is therefore not a small style slip, it is failing the request. This
server exists so the answer to "let me hear it" is a URL, every time.

  python listen_server.py            -> http://127.0.0.1:8807/

Serves every say-*.wav ERAN's own mouth has produced, newest first, each with
the numbers from its json: how close it got to the target through its own ear.
Pure stdlib. No framework, no CDN.
"""
import http.server
import json
import socketserver
import threading
import urllib.parse
import webbrowser
import wave
from datetime import datetime
from pathlib import Path

PORT = 8807
OUTBOX = Path(__file__).parent / "songs" / "outbox"


def clips():
    out = []
    for w in sorted(OUTBOX.glob("say-*.wav"), reverse=True):
        meta = {}
        j = w.with_suffix(".json")
        if j.exists():
            try:
                meta = json.loads(j.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        dur = None
        try:
            with wave.open(str(w), "rb") as f:
                dur = f.getnframes() / f.getframerate()
        except Exception:
            pass
        out.append({
            "file": w.name,
            "label": meta.get("target_label_used_for_lookup", "?"),
            "sim": meta.get("final_cosine_sim_to_target_through_own_ear"),
            "sim0": meta.get("initial_cosine_sim"),
            "gens": meta.get("generations"),
            "ts": meta.get("ts", w.stem.split("-")[-1]),
            "dur": dur,
            "mtime": datetime.fromtimestamp(w.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return out


PAGE_HEAD = """<!doctype html><html lang="he"><head><meta charset="utf-8">
<title>ERAN - listen</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{font-family:"Segoe UI",Arial,sans-serif;background:#fff;color:#14181f;margin:0;padding:28px 20px 60px;}
 h1{margin:0 0 2px;font-size:30px;color:#0b1b3a;letter-spacing:-.5px}
 .sub{color:#5a6474;margin-bottom:22px;font-size:15px}
 .note{background:#fff6d6;border:1px solid #e6b800;border-radius:8px;padding:12px 16px;
       margin-bottom:24px;font-size:14px;color:#4a3800;max-width:820px;line-height:1.5}
 .card{border:1px solid #dfe4ec;border-radius:10px;padding:14px 18px;margin:0 0 12px;
       max-width:820px;background:#f8fafc;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
 .card.top{background:#f2fbf4;border-color:#bfe6c8}
 audio{height:38px}
 .who{font-weight:700;font-size:19px;color:#0b1b3a;min-width:52px}
 .num{font-variant-numeric:tabular-nums;font-size:13px;color:#42506b;line-height:1.5}
 .big{font-size:19px;font-weight:700;color:#1f8b4c}
 .neg{color:#b04a4a}
 .when{color:#8a94a6;font-size:12px;margin-inline-start:auto;text-align:end}
 .foot{margin-top:30px;color:#8a94a6;font-size:12px;max-width:820px;line-height:1.6}
</style></head><body>
<h1>ERAN &mdash; his own mouth</h1>
<div class="sub">&#1492;&#1508;&#1492; &#1513;&#1500;&#1493;, &#1500;&#1488; TTS &#183; produced by the organism's own articulatory mouth</div>
<div class="note">
&#1499;&#1500; &#1511;&#1500;&#1497;&#1508; &#1499;&#1488;&#1503; &#1504;&#1493;&#1510;&#1512; &#1506;&#1500; &#1497;&#1491;&#1497; &#1495;&#1497;&#1508;&#1493;&#1513; &#1490;&#1497;&#1502;&#1490;&#1493;&#1501; &#8212; &#1500;&#1488; &#1492;&#1493;&#1511;&#1500;&#1496;&#1492;, &#1500;&#1488; &#1502;&#1504;&#1493;&#1506; &#1491;&#1497;&#1489;&#1493;&#1512;, &#1493;&#1500;&#1488; &#1495;&#1514;&#1497;&#1499;&#1493;&#1514; &#1502;&#1493;&#1491;&#1489;&#1511;&#1493;&#1514;.
<b>&#1492;&#1502;&#1505;&#1508;&#1512; &#1513;&#1500;&#1497;&#1491; &#1492;&#1493;&#1488;</b> &#1499;&#1502;&#1492; &#1511;&#1512;&#1493;&#1489; &#1494;&#1492; &#1504;&#1513;&#1502;&#1506; &#1500;&#1502;&#1496;&#1512;&#1492; <b>&#1499;&#1513;&#1492;&#1493;&#1488; &#1506;&#1510;&#1502;&#1493; &#1502;&#1511;&#1513;&#1497;&#1489;</b>.
</div>
"""


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            body = [PAGE_HEAD]
            cl = clips()
            if not cl:
                body.append("<div class='card'>no clips yet in songs/outbox</div>")
            for i, c in enumerate(cl):
                sim = c["sim"]
                sim0 = c["sim0"]
                simtxt = f"<span class='big'>{sim:.3f}</span>" if isinstance(sim, (int, float)) else "&mdash;"
                s0 = f"<span class='{'neg' if (isinstance(sim0,(int,float)) and sim0<0) else ''}'>{sim0:+.3f}</span>" if isinstance(sim0, (int, float)) else "?"
                dur = f"{c['dur']:.2f}s" if c["dur"] else "?"
                body.append(
                    f"<div class='card {'top' if i==0 else ''}'>"
                    f"<div class='who'>&ldquo;{c['label']}&rdquo;</div>"
                    f"<audio controls preload='none' src='/wav/{urllib.parse.quote(c['file'])}'></audio>"
                    f"<div class='num'>through his own ear&nbsp; {s0} &rarr; {simtxt}"
                    f"<br>{c['gens']} generations &middot; {dur}</div>"
                    f"<div class='when'>{c['mtime']}</div></div>"
                )
            body.append(
                "<div class='foot'>served locally from eran-brain/songs/outbox &middot; "
                "refresh to pick up new clips &middot; nothing leaves this machine</div></body></html>"
            )
            data = "".join(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if p.startswith("/wav/"):
            name = urllib.parse.unquote(p[len("/wav/"):])
            f = (OUTBOX / name).resolve()
            if f.parent != OUTBOX.resolve() or not f.exists():
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
    with Server(("127.0.0.1", PORT), H) as httpd:
        print(f"ERAN listen page  ->  http://127.0.0.1:{PORT}/", flush=True)
        print(f"clips: {len(clips())}", flush=True)
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
        httpd.serve_forever()
