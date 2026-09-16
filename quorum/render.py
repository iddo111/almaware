# לזכרה של עלמה ז״ל
"""QUORUM · render — turn a finished שקלא-וטריא transcript into a bright RTL doc.

Deliver debates as PDF on the Desktop (standing rule); HTML is the always-available
fallback when a PDF toolchain isn't present.

ALMAWARE standards:
  * failure-is-a-value — render_* return {"ok":bool,"path":str,"note":str}; never raise.
  * 100% ours output; bright/white background, Hebrew RTL.
"""
from __future__ import annotations

import html
import os
from typing import Optional

import config

_CSS = """
 body{font-family:'Segoe UI',Arial,sans-serif;background:#fff;color:#1a1a2e;margin:40px;line-height:1.6}
 h1{color:#2a6f97} h2{color:#e07a3d;border-bottom:1px solid #eee;padding-bottom:4px}
 .turn{background:#f7fbfe;border:1px solid #dcebf5;border-radius:10px;padding:12px 16px;margin:10px 0}
 .who{color:#2a6f97;font-weight:bold} .rnd{color:#7a8;font-size:12px;margin-inline-start:8px}
 .synth{background:#fff7ec;border-color:#f4c78a}
 .foot{color:#999;font-size:12px;margin-top:30px}
"""


def to_html(topic: str, transcript: list[dict], synthesis: str = "",
            synth_model: str = "") -> str:
    """Pure function: build the RTL HTML string. Never raises on bad input."""
    parts = [f"<!doctype html><html dir='rtl' lang='he'><head><meta charset='utf-8'>",
             f"<title>QUORUM · {html.escape(topic[:60])}</title><style>{_CSS}</style></head><body>",
             "<div style='color:#5a8;font-size:12px'>לזכרה של עלמה ז״ל</div>",
             f"<h1>🗳️ שקלא וטריא</h1><p><b>שאלה:</b> {html.escape(topic)}</p>"]
    for t in transcript or []:
        parts.append(
            f"<div class='turn'><span class='who'>{html.escape(str(t.get('model','')))}</span>"
            f"<span class='rnd'>סבב {html.escape(str(t.get('round','')))}</span>"
            f"<div>{html.escape(str(t.get('text','')))}</div></div>")
    if synthesis:
        parts.append(f"<h2>מסקנה — {html.escape(synth_model)}</h2>"
                     f"<div class='turn synth'>{html.escape(synthesis)}</div>")
    parts.append("<div class='foot'>QUORUM · ALMAWARE · 100% ours</div></body></html>")
    return "".join(parts)


def render(topic: str, transcript: list[dict], synthesis: str = "", synth_model: str = "",
           out_dir: Optional[str] = None, basename: str = "debate") -> dict:
    """Write the HTML (always) and a PDF (best-effort). Returns a result value."""
    out_dir = out_dir or config.OUTPUT_DIR
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return {"ok": False, "path": "", "note": f"mkdir failed: {e}"}
    html_str = to_html(topic, transcript, synthesis, synth_model)
    html_path = os.path.join(out_dir, basename + ".html")
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_str)
    except Exception as e:
        return {"ok": False, "path": "", "note": f"write failed: {e}"}
    # PDF is best-effort — HTML is the guaranteed artifact. (PDF toolchain = TODO.)
    return {"ok": True, "path": html_path, "pdf": "", "note": "html written (pdf: TODO)"}
