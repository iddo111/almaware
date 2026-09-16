# -*- coding: utf-8 -*-
"""wiki_server.py -- the window Iddo opens into the second brain.

Iddo, 2026-08-24: "carpathy run search on second brain and implement." Karpathy's LLM-wiki
pattern says the LLM maintains an interlinked markdown wiki (Obsidian is his viewer). Obsidian
isn't installed here, so this is the viewer: a stdlib HTTP server that renders the memory vault
(~365 markdown files) in a browser -- search, clickable [[wikilinks]], the MEMORY.md index as
home. Read-only: it never edits the wiki (Claude maintains that). "ביני ובינך" -- the shared brain
he can finally see.

Pure stdlib (http.server + a tiny markdown renderer). No framework, no CDN -- ALMAWARE purity.
"""
import html
import http.server
import os
import re
import socketserver
import urllib.parse
from pathlib import Path

PORT = 8811
VAULT = Path(os.environ.get(
    "SECOND_BRAIN_VAULT",
    r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory"))


def slug_to_file(slug):
    """Resolve a [[slug]] to a file, tolerant of hyphen/underscore and missing prefix."""
    slug = slug.strip()
    cands = [slug, slug.replace("-", "_"), slug.replace(" ", "_")]
    for pre in ("", "project_", "feedback_", "reference_", "user_", "index_"):
        for c in list(cands):
            cands.append(pre + c)
    for c in cands:
        p = VAULT / (c + ".md")
        if p.exists():
            return c + ".md"
    # fall back: match by frontmatter name
    for f in VAULT.glob("*.md"):
        try:
            head = f.read_text(encoding="utf-8", errors="ignore")[:400]
            m = re.search(r"^name:\s*(.+)$", head, re.M)
            if m and m.group(1).strip().strip('"').replace("-", "_") == slug.replace("-", "_"):
                return f.name
        except Exception:
            pass
    return None


def md_to_html(text):
    out = []
    in_code = False
    for raw in text.split("\n"):
        if raw.strip().startswith("```"):
            in_code = not in_code
            out.append("<pre>" if in_code else "</pre>")
            continue
        if in_code:
            out.append(html.escape(raw))
            continue
        line = html.escape(raw)
        # wikilinks [[slug]] -> anchor
        def wl(m):
            s = m.group(1)
            f = slug_to_file(s)
            cls = "" if f else ' class="dead"'
            href = f"/page/{urllib.parse.quote(f)}" if f else "#"
            return f'<a href="{href}"{cls}>{html.escape(s)}</a>'
        line = re.sub(r"\[\[([^\]]+)\]\]", wl, line)
        # markdown links [txt](href)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                      lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', line)
        # bold / inline code
        line = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
        if re.match(r"^#{1,6}\s", raw):
            lvl = len(raw) - len(raw.lstrip("#"))
            out.append(f"<h{lvl}>{line.lstrip('#').strip()}</h{lvl}>")
        elif re.match(r"^\s*[-*]\s", raw):
            out.append(f"<li>{re.sub(r'^\s*[-*]\s', '', line)}</li>")
        elif raw.strip().startswith("|"):
            out.append(f'<div class="tr">{line}</div>')
        elif not raw.strip():
            out.append("<br>")
        else:
            out.append(f"<p>{line}</p>")
    return "\n".join(out)


PAGE = """<!doctype html><html lang=he dir=auto><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{title}</title><style>
:root{{--ink:#1a1f2b;--bg:#fbfbf6;--gold:#e6a400;--dim:#8a94a6;--line:#e6e9ef;--link:#1565c0}}
body{{margin:0;font-family:system-ui,'Segoe UI',Arial;background:var(--bg);color:var(--ink);line-height:1.5}}
.top{{position:sticky;top:0;background:var(--ink);padding:10px 16px;display:flex;gap:12px;align-items:center}}
.top a{{color:#fff;text-decoration:none;font-weight:700}} .top form{{flex:1}}
.top input{{width:100%;padding:8px 12px;border:0;border-radius:8px;font-size:15px}}
.wrap{{max-width:820px;margin:0 auto;padding:18px}}
a{{color:var(--link);text-decoration:none}} a:hover{{text-decoration:underline}}
a.dead{{color:#c0392b;border-bottom:1px dotted #c0392b}}
h1,h2,h3{{line-height:1.25}} h1{{border-bottom:2px solid var(--gold);padding-bottom:4px}}
pre{{background:#0f1420;color:#cfe;padding:10px;border-radius:8px;overflow-x:auto;white-space:pre-wrap}}
code{{background:#eef;padding:1px 4px;border-radius:4px}}
li{{margin-right:1em}} .tr{{font-family:Consolas,monospace;font-size:13px;color:#333}}
.card{{display:block;padding:8px 10px;border:1px solid var(--line);border-radius:8px;margin:6px 0;background:#fff}}
.meta{{color:var(--dim);font-size:13px}}
</style></head><body>
<div class=top><a href="/">🧠 מוח שני</a><form action="/search"><input name=q placeholder="חיפוש / search…" value="{q}"></form><a href="/page/MEMORY.md">index</a><a href="/page/log.md">log</a></div>
<div class=wrap>{body}</div></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, title, body, q=""):
        out = PAGE.format(title=html.escape(title), body=body, q=html.escape(q)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/" or u.path == "/page/MEMORY.md":
            self._home()
        elif u.path.startswith("/page/"):
            self._page(urllib.parse.unquote(u.path[len("/page/"):]))
        elif u.path == "/search":
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0]
            self._search(q)
        else:
            self.send_error(404)

    def _home(self):
        idx = VAULT / "MEMORY.md"
        body = md_to_html(idx.read_text(encoding="utf-8", errors="ignore")) if idx.exists() else "no index"
        n = len(list(VAULT.glob("*.md")))
        self._send("מוח שני — index", f'<p class=meta>{n} pages · Karpathy LLM-wiki</p>' + body)

    def _page(self, name):
        if "/" in name or "\\" in name or not name.endswith(".md"):
            self.send_error(400); return
        p = VAULT / name
        if not p.exists():
            self._send("missing", f"<h1>{html.escape(name)}</h1><p class=dead>אין דף כזה.</p>"); return
        self._send(name, md_to_html(p.read_text(encoding="utf-8", errors="ignore")))

    def _search(self, q):
        q = q.strip()
        hits = []
        if q:
            ql = q.lower()
            for f in sorted(VAULT.glob("*.md")):
                try:
                    t = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if ql in t.lower() or ql in f.name.lower():
                    desc = ""
                    m = re.search(r"^description:\s*(.+)$", t[:600], re.M)
                    if m:
                        desc = m.group(1).strip().strip('"')[:160]
                    hits.append((f.name, desc))
        body = f"<h1>חיפוש: {html.escape(q)}</h1><p class=meta>{len(hits)} תוצאות</p>"
        for name, desc in hits[:200]:
            body += (f'<a class=card href="/page/{urllib.parse.quote(name)}">'
                     f'<b>{html.escape(name[:-3])}</b><br><span class=meta>{html.escape(desc)}</span></a>')
        self._send(f"search {q}", body, q=q)


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"second brain: http://127.0.0.1:{PORT}/   vault={VAULT}")
    S(("0.0.0.0", PORT), H).serve_forever()
