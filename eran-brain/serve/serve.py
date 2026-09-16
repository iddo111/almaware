"""serve.py — the READ-ONLY observation window on :8820.

A parent watches through the glass; the window changes nothing. Renders the
chemistry curves (inline SVG from metrics.jsonl), curriculum state, energy,
the latest dream journal, the newest exam, and the babble outbox with
players that start PAUSED (Sacred Audio law: nothing ever autoplays, nothing
ever notifies anyone).

stdlib http.server only. GET only. No writes, ever.
"""
import glob
import html
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))

import genome                                     # noqa: E402

CURVES = [("da", "#e4572e"), ("ne", "#f3a712"), ("sht", "#29335c"),
          ("oxt", "#a8577e"), ("E", "#4c9f70")]
TAIL = 400


def _metrics_tail(n=TAIL):
    if not os.path.exists(genome.METRICS_FILE):
        return []
    with open(genome.METRICS_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()[-n:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _svg(points_by_key, width=640, height=160):
    if not points_by_key or not any(points_by_key.values()):
        return "<p>(no metrics yet)</p>"
    parts = [f'<svg width="{width}" height="{height}" '
             f'style="background:#fff;border:1px solid #ccc">']
    for (key, color) in CURVES:
        pts = points_by_key.get(key, [])
        if not pts:
            continue
        top = max(max(pts), 1.0)
        step = width / max(len(pts) - 1, 1)
        path = " ".join(f"{i * step:.1f},{height - (v / top) * (height - 10) - 5:.1f}"
                        for i, v in enumerate(pts))
        parts.append(f'<polyline fill="none" stroke="{color}" '
                     f'stroke-width="1.5" points="{path}"/>')
    parts.append("</svg>")
    legend = " · ".join(f'<span style="color:{c}">{k}</span>'
                        for k, c in CURVES)
    return "".join(parts) + f"<div>{legend}</div>"


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def _page():
    tail = _metrics_tail()
    curves = {k: [float(m.get(k, 0) or 0) for m in tail if k in m]
              for k, _ in CURVES}
    last = tail[-1] if tail else {}
    cur = _read_json(genome.CURRICULUM_FILE) or {}
    exam = _read_json(os.path.join(genome.RESULTS_DIR, "ERANB-001.json"))
    journal_path = _latest(os.path.join(genome.STATE_DIR, "journal-*.md"))
    journal = ""
    if journal_path:
        with open(journal_path, "r", encoding="utf-8") as f:
            journal = f.read()[-4000:]
    wavs = sorted(glob.glob(os.path.join(genome.OUTBOX_DIR, "*.wav")),
                  reverse=True)[:10]
    audio = "".join(
        f'<div><code>{html.escape(os.path.basename(w))}</code><br>'
        f'<audio controls preload="metadata" '
        f'src="/songs/{html.escape(os.path.basename(w))}"></audio></div>'
        for w in wavs) or "<p>(no babble yet)</p>"
    exam_html = (f"<pre>{html.escape(json.dumps(exam, indent=1)[:3000])}</pre>"
                 if exam else "<p>(no exam yet)</p>")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>ERAN — Perceptron Mark II</title>
<style>body{{font-family:sans-serif;background:#fdfdf8;color:#222;
max-width:760px;margin:1em auto;padding:0 1em}}
h2{{border-bottom:2px solid #e4572e}}pre{{background:#f4f4ee;padding:.5em;
overflow-x:auto}}</style></head><body>
<h1>Perceptron Mark II · the organism of ERAN 🧠</h1>
<p>read-only window · beat {last.get('beat', 0)} ·
prototypes {last.get('protos', 0)} · mass {last.get('mass', 0)} ·
energy {last.get('E', '?')} · unit <b>{html.escape(str(last.get('unit')))}</b></p>
<h2>chemistry</h2>{_svg(curves)}
<h2>curriculum</h2><pre>{html.escape(json.dumps(cur, indent=1)[:2000])}</pre>
<h2>newest exam (results/ERANB-001.json)</h2>{exam_html}
<h2>dream journal (latest)</h2>
<pre>{html.escape(journal) if journal else '(no journal yet)'}</pre>
<h2>babble outbox (players start PAUSED — Sacred Audio)</h2>{audio}
</body></html>"""


class Window(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/songs/"):
            name = os.path.basename(self.path[len("/songs/"):])
            path = os.path.join(genome.OUTBOX_DIR, name)
            if name.endswith(".wav") and os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_response(404)
            self.end_headers()
            return
        body = _page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):                    # quiet window
        pass


def main():
    server = ThreadingHTTPServer(("0.0.0.0", genome.PORT), Window)
    print(f"[serve] observation window on http://0.0.0.0:{genome.PORT}/ "
          f"(read-only, never notifies)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
