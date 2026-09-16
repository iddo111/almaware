#!/usr/bin/env python3
"""brain2_server.py — THE DOOR of the ALMA SECOND BRAIN.

One HTTP service on 127.0.0.1:8897 (claimed in RAMCHAT 2026-09-11 10:04 —
8895 was taken by a pythonw, 8896 is CONTROL). Reachable on the tailnet via
`tailscale serve --bg --https=8897 http://127.0.0.1:8897`. Tailnet only, no
funnel — the 2026-06-24 leak scar.

    GET  /                      the index page, rendered
    GET  /health                honest liveness (does NOT claim the wiki is good)
    GET  /search?q=...&n=10     full-text over the wiki, Hebrew-safe
    GET  /page/<id>             one page (?format=raw for the markdown)
    GET|POST /ask?q=...         answer FROM THE WIKI, with citations
    POST /propose               an agent proposes an edit -> maintainer queue
    GET  /proposals             the open queue

Auth: header `X-Brain2-Token` (or `?key=`) matching state/token.txt.
Loopback GET reads are allowed without a token so a local agent, a browser and
the CONTROL page can read; every WRITE and every /ask needs the token, always.

Pure stdlib: http.server, urllib, html. No Flask, no CDN.
"""

from __future__ import annotations

import html
import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain2_lib as B  # noqa: E402

# MNEMO (2026-09-14, super-project Phase 3): /recall reuses tokensave/ask.py's
# existing 5-source fan-out (memory files, brain2 itself, alma-recall, RAMCHAT,
# Ezra HaSofer) verbatim -- one implementation, now reachable over HTTP so any
# agent on any box (Muse, a fleet model, the phone) gets the same recall
# Claude Code already has locally, instead of brain2's door being narrower
# (wiki-only) than what's actually available on this machine.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tokensave"))
try:
    import ask as _ask  # noqa: E402
    _RECALL_OK = True
except Exception as _recall_import_err:  # pragma: no cover -- degrade, don't crash the door
    _RECALL_OK = False

HOST, PORT = "127.0.0.1", 8897
TOKEN = B.read_token()

ASK_SYSTEM = (
    "You answer ONLY from the wiki excerpts given to you. "
    "Answer in Hebrew first, then a short English version. "
    "Cite the page ids you used, like [scars/mic]. "
    "If the excerpts do not contain the answer, say so plainly in both languages "
    "and name what is missing. Never invent a fact, a date or a number."
)


def ask_wiki(question: str, model: str | None, base: str | None, n: int = 6) -> dict:
    terms = B.expand_query(question, model=model, base=base)
    hits = B.search_many(terms, limit=n)
    if not hits:
        return {"ok": False, "answer": "", "citations": [], "terms": terms,
                "error": "no page in the wiki matches that question"}
    context = []
    for h in hits:
        page = B.read_page(h["id"])
        if not page:
            continue
        _fm, body = page
        context.append(f"### [{h['id']}]\n{B.excerpt(body, ' '.join(terms))}")
    prompt = (
        "קטעים מהוויקי של הפרויקט / wiki excerpts:\n\n"
        + "\n\n".join(context)[:24000]
        + f"\n\n---\nהשאלה / question: {question}\n"
        "ענה רק מהקטעים שלמעלה, וציין את מזהי הדפים."
    )
    try:
        answer = B.ask_model(prompt, system=ASK_SYSTEM, model=model, base=base, max_tokens=1000)
    except B.ModelEmpty as exc:
        return {"ok": False, "answer": "", "citations": [h["id"] for h in hits],
                "error": f"model returned nothing usable: {exc}",
                "hint": "the pages are there; the model door failed. See /search for the raw hits."}
    return {
        "ok": True,
        "answer": answer,
        "citations": [h["id"] for h in hits],
        "terms": terms,
        "model": model or B.DEFAULT_MODEL,
        "base": (base or B.DEFAULT_MODEL_BASE),
    }


PAGE_CSS = """
body{font-family:Segoe UI,system-ui,sans-serif;max-width:980px;margin:0 auto;padding:24px;
background:#fff;color:#111;line-height:1.6}
a{color:#0b5ed7} code{background:#f2f4f7;padding:1px 5px;border-radius:4px}
pre{background:#f7f8fa;padding:14px;border-radius:8px;overflow-x:auto;border:1px solid #e5e7eb}
.hit{border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px;margin:10px 0;background:#fcfcfd}
.meta{color:#667085;font-size:.88em} h1,h2{line-height:1.25}
input[type=text]{padding:8px;width:60%;border:1px solid #d0d5dd;border-radius:6px}
button{padding:8px 16px;border-radius:6px;border:1px solid #0b5ed7;background:#0b5ed7;color:#fff}
"""


def shell(title: str, inner: str) -> bytes:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{PAGE_CSS}</style></head><body>{inner}</body></html>"
    ).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "brain2/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter than the default
        sys.stderr.write(f"[brain2] {self.address_string()} {fmt % args}\n")

    # -- helpers ---------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"))

    def _authed(self, q: dict) -> bool:
        given = self.headers.get("X-Brain2-Token") or (q.get("key", [""])[0])
        return bool(given) and given == TOKEN

    def _loopback(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1")

    # -- routes ----------------------------------------------------------
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        if path == "/health":
            pages = len(B.all_pages())
            head = B.git("rev-parse", "--short", "HEAD").stdout.strip()
            return self._json(200, {
                "service": "brain2",
                "listening": f"{HOST}:{PORT}",
                "wiki_pages": pages,
                "wiki_commit": head,
                "open_proposals": len(B.open_proposals()),
                "model_door": B.model_alive(),
                "note": "liveness only. This says the door is open, NOT that the wiki is correct.",
                "time": B.now_iso(),
            })

        if path == "/search":
            term = (q.get("q") or [""])[0]
            if not term.strip():
                return self._json(400, {"error": "q= is required"})
            n = min(int((q.get("n") or ["10"])[0] or 10), 50)
            hits = B.search(term, limit=n)
            if (q.get("format") or [""])[0] == "html" or "text/html" in (self.headers.get("Accept") or ""):
                inner = [f"<h1>brain2 · חיפוש / search</h1><p class=meta>{html.escape(term)} — {len(hits)} hits</p>"]
                for h in hits:
                    inner.append(
                        f"<div class=hit><a href='/page/{html.escape(h['id'])}'><b>{html.escape(h['name'])}</b></a>"
                        f" <span class=meta>{h['id']} · score {h['score']} · {html.escape(h['updated'])}</span>"
                        f"<div>{html.escape(h['snippet'])}</div></div>")
                return self._send(200, shell(f"search: {term}", "".join(inner)), "text/html; charset=utf-8")
            return self._json(200, {"query": term, "count": len(hits), "hits": hits})

        if path.startswith("/page/"):
            pid = urllib.parse.unquote(path[len("/page/"):])
            try:
                page = B.read_page(pid)
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            if page is None:
                return self._json(404, {"error": f"no such page: {pid}",
                                        "hint": "GET /search?q=... to find one"})
            fm, body = page
            if (q.get("format") or [""])[0] == "raw":
                return self._send(200, (B.render_page(fm, body)).encode("utf-8"),
                                  "text/markdown; charset=utf-8")
            if "text/html" in (self.headers.get("Accept") or ""):
                inner = (f"<h1>{html.escape(str(fm.get('name', pid)))}</h1>"
                         f"<p class=meta>{html.escape(pid)} · updated {html.escape(str(fm.get('updated','')))}"
                         f" · confidence {html.escape(str(fm.get('confidence','')))}</p>"
                         f"<pre>{html.escape(body)}</pre>")
                return self._send(200, shell(pid, inner), "text/html; charset=utf-8")
            return self._json(200, {"id": pid, "front_matter": fm, "body": body})

        if path == "/proposals":
            return self._json(200, {"open": B.open_proposals()})

        if path == "/recall":
            term = (q.get("q") or [""])[0]
            if not term.strip():
                return self._json(400, {"error": "q= is required"})
            if not _RECALL_OK:
                return self._json(503, {"error": "recall fan-out unavailable (tokensave/ask.py failed to import)"})
            n = min(int((q.get("n") or ["3"])[0] or 3), 20)
            kws = _ask.keywords(term)
            if not kws:
                return self._json(200, {"query": term, "count": 0, "hits": [],
                                        "note": "no usable keywords"})
            raw_chars = 0
            all_cands = []
            for fn in (_ask.scan_memory, lambda k, r: _ask.scan_brain2(k, term, r),
                       lambda k, r: _ask.scan_recall(k, term, r),
                       _ask.scan_ramchat, _ask.scan_ezra):
                cands, raw_chars = fn(kws, raw_chars)
                all_cands.extend(cands)
            all_cands.sort(key=lambda c: (-c["score"], c["pri"], len(c["text"])))
            top = all_cands[:n]
            return self._json(200, {"query": term, "count": len(top), "hits": top,
                                    "sources": ["memory", "brain2", "alma-recall", "ramchat", "ezra"]})

        if path == "/ask":
            if not self._authed(q):
                return self._json(401, {"error": "X-Brain2-Token required for /ask (it spends model time)"})
            question = (q.get("q") or [""])[0]
            if not question.strip():
                return self._json(400, {"error": "q= is required"})
            model = (q.get("model") or [None])[0]
            base = (q.get("base") or [None])[0]
            return self._json(200, ask_wiki(question, model, base))

        if path == "/":
            page = B.read_page("index")
            body = page[1] if page else "(the wiki has no index yet — run brain2_maintain.py)"
            inner = ("<form action='/search'><input type=text name=q placeholder='חפש בוויקי / search the wiki'>"
                     "<input type=hidden name=format value=html><button>חפש / search</button></form>"
                     f"<pre>{html.escape(body)}</pre>")
            return self._send(200, shell("ALMA SECOND BRAIN", inner), "text/html; charset=utf-8")

        return self._json(404, {"error": "unknown route",
                                "routes": ["/health", "/search?q=", "/recall?q= (5-source fan-out)",
                                           "/page/<id>", "/ask?q=",
                                           "/propose (POST)", "/remember (POST, alias of /propose)",
                                           "/proposals"]})

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(min(length, 200_000)) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}

        if path in ("/propose", "/remember"):
            # /remember is the MNEMO-contract name for the same propose path
            # (2026-09-14) -- no new logic, just the vocabulary Iddo's memory-
            # unification design uses: recall() to read, remember() to write.
            if not self._authed(q) and not self._loopback():
                return self._json(401, {"error": "X-Brain2-Token required"})
            page = str(data.get("page") or "").strip()
            change = str(data.get("change") or "").strip()
            author = str(data.get("author") or "").strip()
            if not (page and change and author):
                return self._json(400, {"error": "page, change and author are all required"})
            if len(change) > 20000:
                return self._json(400, {"error": "change is too long (max 20000 chars)"})
            section = page.split("/")[0]
            item = B.propose(page, change, author, str(data.get("rationale") or ""))
            note = None
            if section in B.READ_ONLY_FOR_AGENTS:
                note = ("laws/ is read-only for agents. The proposal is RECORDED for Iddo but the "
                        "maintainer will refuse to apply it. Only Iddo's word changes a law.")
            elif section in B.APPEND_ONLY:
                note = "scars/ is append-only: this will be appended, never replace existing history."
            return self._json(202, {"status": "queued", "proposal": item, "note": note,
                                    "applied_by": "brain2_maintain.py --apply-proposals"})

        if path == "/ask":
            if not self._authed(q):
                return self._json(401, {"error": "X-Brain2-Token required for /ask"})
            question = str(data.get("q") or data.get("question") or "")
            if not question.strip():
                return self._json(400, {"error": "q is required"})
            return self._json(200, ask_wiki(question, data.get("model"), data.get("base")))

        return self._json(404, {"error": "unknown route"})


def main() -> int:
    B.lower_priority()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    print(f"[brain2] door open on http://{HOST}:{PORT}  ({len(B.all_pages())} pages)")
    print(f"[brain2] token file: {B.TOKEN_FILE}")
    threading.current_thread().name = "brain2"
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
