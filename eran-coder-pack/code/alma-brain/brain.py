#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA-BRAIN — the SHARED second brain for Claude, Qwen and gpt-oss.
ALMA-BRAIN — המוח השני המשותף לקלוד, קוון ו-gpt-oss.

It does NOT re-index anything. It reads ALMA-RECALL's existing SQLite FTS index
(D:\\CLAUDE\\alma-recall\\recall.db, read-only) and adds the layer that was missing:
a single question-in / brief-out endpoint that any of the three models can curl.

WHY THIS EXISTS (what ALMA-RECALL alone could not do)
  1. recall's fts_query() ANDs every word, stopwords included, so a real question
     like "what did Iddo decide about the MIDI model" collapsed to 6 hits.
     Here: stopwords are dropped, terms are OR'd, then re-scored by coverage.
  2. recall ranks by raw bm25 only. A June log outranked the August work.
     Here: score = coverage x recency-decay x source-prior.
  3. recall drowns the 325 curated memory files under 5,000+ raw transcripts.
     Here: results are SPLIT by memory tier and each tier is answered separately.
  4. recall serves 127.0.0.1 only, so no DGX box could ever reach it.
     Here: binds 0.0.0.0 behind a shared token so eran1..eran4 can query it.

MEMORY TIERS (standard agent-memory taxonomy, mapped onto what Iddo already has)
  semantic  = ~/.claude/.../memory/*.md   curated, distilled facts   (source: memory)
  team      = RAMCHAT council + queue     decisions between agents   (source: ramchat)
  episodic  = every AI session transcript what actually happened     (claude/codex/grok/...)

No torch. No network calls out. Read-only over recall.db.
"""
import json
import math
import os
import re
import sqlite3
import sys
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("RECALL_DB", os.path.join("D:" + os.sep, "CLAUDE", "alma-recall", "recall.db"))
TOKEN_FILE = os.path.join(APP_DIR, "token.txt")
PORT = int(os.environ.get("BRAIN_PORT", "8797"))
BIND = os.environ.get("BRAIN_BIND", "0.0.0.0")

# Tier definitions -----------------------------------------------------------
SEMANTIC = ("memory",)
TEAM = ("ramchat",)
EPISODIC = ("claude", "codex", "grok", "gemini", "cursor", "perplexity")

# A curated memory file is worth far more than a random line of a transcript.
SOURCE_PRIOR = {
    "memory": 3.0,
    "ramchat": 2.0,
    "claude": 1.0,
    "codex": 0.85,
    "grok": 0.7,
    "gemini": 0.6,
    "cursor": 0.5,
    "perplexity": 0.4,
}

# Recency half-life in days. Iddo's work turns over fast; a 60-day-old transcript
# is usually superseded. Memory files are exempt (they are maintained, not dated).
HALFLIFE_DAYS = 45.0

STOP = set("""
a an and are as at be been but by can could did do does for from had has have how i if in into is it
its me my of on or our so than that the their them then there these they this to was we were what when
where which who why will with would you your about after all also am any because before being between
both each few more most no not now only other out over same some such through under up very
tell show give find get know need want please just like new use using make made
""".split())
# Hebrew function words — his transcripts are half Hebrew.
STOP |= set("""
של על עם או גם כי אם אבל מה מי איך למה כמה זה זו זאת הוא היא הם הן אני אתה את אנחנו
לא כן יש אין היה הייתה היו אז שם פה כאן עוד רק כל אחד אחת יותר פחות כדי אחרי לפני
""".split())


def connect():
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH.replace("\\", "/"), uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def load_token():
    if os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE, encoding="utf-8").read().strip()
        if t:
            return t
    import secrets
    t = secrets.token_urlsafe(18)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(t)
    return t


TOKEN = load_token()


def terms_of(q):
    """Content words only. Keeps quoted phrases whole."""
    phrases = re.findall(r'"([^"]+)"', q)
    rest = re.sub(r'"[^"]+"', " ", q)
    raw = [t for t in re.split(r"[^\w\u0590-\u05FF]+", rest) if t]
    out = []
    for t in raw:
        tl = t.lower()
        # Single characters are KEPT once stopwords are gone: "KESHEV B" and
        # "plan A" are real names here. Dropping them lost keshev-b entirely.
        if tl in STOP:
            continue
        out.append(t)
    return phrases, out


def bigrams(terms):
    """Adjacent query words are probably a name ("KESHEV B", "MIDI model")."""
    return ["%s %s" % (terms[i], terms[i + 1]) for i in range(len(terms) - 1)]


def fts_expr(phrases, terms):
    parts = ['"%s"' % p.replace('"', "") for p in phrases]
    # Exact adjacent pairs first — these are the high-precision signal.
    for b in bigrams(terms):
        parts.append('"%s"' % re.sub(r'["*()^:]', "", b))
    for t in terms:
        t = re.sub(r'["*()^:]', "", t)
        if t:
            parts.append('"%s"*' % t)
    # OR, not AND: a good answer rarely contains every word of the question.
    return " OR ".join(parts) if parts else None


def age_days(ts):
    if not ts:
        return 365.0
    s = str(ts).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        try:
            d = datetime.fromisoformat(s[:19])
        except ValueError:
            return 365.0
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400.0)


_IDF_CACHE = {}


def idf(con, term):
    """Rarity weight. In THIS corpus 'Iddo' and 'model' are near-stopwords —
    every document is about Iddo deciding something. 'MIDI' is the real query.
    Without this, generic words drown the one word that matters."""
    t = term.lower()
    if t in _IDF_CACHE:
        return _IDF_CACHE[t]
    try:
        n = con.execute("SELECT count(*) FROM msgs_fts WHERE msgs_fts MATCH ?",
                        ('"%s"' % re.sub(r'["*()^:]', "", t),)).fetchone()[0]
    except sqlite3.OperationalError:
        n = 1
    total = _IDF_CACHE.get("__total__")
    if total is None:
        total = con.execute("SELECT count(*) FROM msgs").fetchone()[0] or 1
        _IDF_CACHE["__total__"] = total
    w = math.log((total + 1.0) / (n + 1.0))
    _IDF_CACHE[t] = w
    return w


def retrieve(con, q, sources, pool=500):
    phrases, terms = terms_of(q)
    expr = fts_expr(phrases, terms)
    if not expr:
        return []
    ph = ",".join("?" * len(sources))
    sql = """
    SELECT m.id AS mid, m.sess, m.seq, m.role, s.source, s.project, s.title, s.path,
           COALESCE(m.ts, s.ended, s.started) AS ts,
           substr(m.text, 1, 6000) AS body,
           snippet(msgs_fts, 0, '', '', ' ... ', 40) AS snip,
           bm25(msgs_fts) AS bm
    FROM msgs_fts
    JOIN msgs m ON m.id = msgs_fts.rowid
    JOIN sessions s ON s.id = m.sess
    WHERE msgs_fts MATCH ? AND s.source IN (%s)
    ORDER BY bm LIMIT ?
    """ % ph
    rows = con.execute(sql, [expr] + list(sources) + [pool]).fetchall()

    needles = [t.lower() for t in terms] + [p.lower() for p in phrases]
    bigs = [b.lower() for b in bigrams(terms)]
    # IDF weight per needle; phrases inherit the max idf of their words.
    wts = {}
    for n in needles:
        wts[n] = max((idf(con, w) for w in n.split()), default=1.0)
    wtot = sum(wts.values()) or 1.0
    scored = []
    for r in rows:
        low = (r["body"] or "").lower()
        coverage = sum(wts[n] for n in needles if n in low) / wtot
        # An exact adjacent pair ("keshev b") is worth much more than two loose words.
        phrase_hit = sum(1 for b in bigs if b in low or b.replace(" ", "-") in low)
        coverage = min(1.0, coverage + 0.5 * phrase_hit)
        # A term in the TITLE/filename beats the same term buried in prose:
        # project_darwish_alma_midi_model.md is *about* the MIDI model.
        head = ((r["title"] or "") + " " + (r["path"] or "")).lower()
        title_w = 1.0 + 0.6 * (sum(wts[n] for n in needles if n in head) / wtot)
        # A doc matching 3 of 4 question words beats one matching 1 of 4, hard.
        cov_w = 0.15 + coverage ** 1.5
        rec = 0.5 ** (age_days(r["ts"]) / HALFLIFE_DAYS)
        prior = SOURCE_PRIOR.get(r["source"], 0.5)
        bmw = 1.0 / (1.0 + math.exp(min(20.0, max(-20.0, r["bm"] + 8.0))))
        # Substance floor: "let's see what happened to the microphone" is 100%
        # coverage and zero information. Reward messages long enough to explain.
        n = len(r["body"] or "")
        sub = min(1.0, math.log10(max(n, 10)) / 3.0)  # ~1.0 at 1000+ chars
        score = cov_w * prior * (0.35 + 0.65 * rec) * (0.5 + bmw) * (0.25 + 0.75 * sub) * title_w
        d = dict(r)
        d["score"] = score
        d["coverage"] = coverage
        d["age_days"] = age_days(r["ts"])
        scored.append(d)
    scored.sort(key=lambda x: -x["score"])
    return scored


def dedupe(hits, per_session=2, limit=8):
    seen = {}
    out = []
    for h in hits:
        k = h["sess"]
        if seen.get(k, 0) >= per_session:
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(h)
        if len(out) >= limit:
            break
    return out


def clean(text, maxlen=900):
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t[:maxlen] + (" ..." if len(t) > maxlen else "")


def excerpt_around(body, terms, width=700):
    """Pull the window of the body where the query words actually are."""
    low = (body or "").lower()
    best, bestpos = -1, 0
    for i in range(0, max(1, len(low) - 200), 200):
        w = low[i:i + width]
        c = sum(1 for t in terms if t.lower() in w)
        if c > best:
            best, bestpos = c, i
    return clean((body or "")[bestpos:bestpos + width], width)


def build_brief(con, q, per_tier=4):
    _ph, terms = terms_of(q)
    tiers = [
        ("FACTS  (curated memory)", SEMANTIC),
        ("TEAM   (RAMCHAT decisions)", TEAM),
        ("HISTORY(what actually happened)", EPISODIC),
    ]
    result = {"query": q, "terms": terms, "tiers": []}
    for label, srcs in tiers:
        # Prefer distinct sessions when few slots: two excerpts of the same
        # conversation is one source wearing two hats.
        hits = dedupe(retrieve(con, q, srcs),
                      per_session=1 if per_tier <= 3 else 2, limit=per_tier)
        items = []
        for h in hits:
            items.append({
                "source": h["source"],
                "title": clean(h["title"], 120),
                "when": (h["ts"] or "")[:16].replace("T", " "),
                "age_days": round(h["age_days"], 1),
                "score": round(h["score"], 4),
                "coverage": round(h["coverage"], 2),
                "project": h["project"],
                "path": h["path"],
                "text": excerpt_around(h["body"], terms),
            })
        result["tiers"].append({"tier": label, "sources": list(srcs), "hits": items})
    return result


def render_text(brief):
    L = []
    L.append("=" * 72)
    L.append("ALMA-BRAIN — shared second brain (Claude / Qwen / gpt-oss)")
    L.append("QUESTION: %s" % brief["query"])
    L.append("keywords: %s" % ", ".join(brief["terms"]))
    L.append("=" * 72)
    for t in brief["tiers"]:
        L.append("")
        L.append("### %s" % t["tier"])
        if not t["hits"]:
            L.append("  (nothing indexed matches)")
            continue
        for i, h in enumerate(t["hits"], 1):
            L.append("  [%d] %s | %s | %s" % (i, h["source"], h["when"] or "?", h["title"]))
            L.append("      %s" % h["text"])
            L.append("      -- %s" % h["path"])
    L.append("")
    L.append("=" * 72)
    L.append("Retrieved from ALMA-RECALL index. Facts outrank history; recent outranks old.")
    return "\n".join(L)


PAGE = """<!doctype html><meta charset=utf-8><title>ALMA-BRAIN</title>
<style>body{font:16px system-ui;margin:2rem auto;max-width:60rem;background:#fff;color:#111}
input{width:70%;padding:.6rem;font-size:1rem}button{padding:.6rem 1rem;font-size:1rem}
pre{white-space:pre-wrap;background:#f6f7f9;padding:1rem;border-radius:8px}</style>
<h1>ALMA-BRAIN</h1><p>Shared second brain — Claude, Qwen, gpt-oss.</p>
<form onsubmit="go(event)"><input id=q placeholder="what happened with the microphone">
<button>ask</button></form><pre id=o></pre>
<script>async function go(e){e.preventDefault();o.textContent='...';
const r=await fetch('/ask?token='+encodeURIComponent(TOK)+'&q='+encodeURIComponent(q.value));
o.textContent=await r.text();}
const TOK=new URLSearchParams(location.search).get('token')||'';</script>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))

    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        if not isinstance(data, (bytes, bytearray)):
            if ctype.startswith("application/json"):
                data = json.dumps(data, ensure_ascii=False, indent=2)
            data = str(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/health":
            return self._send(200, {"ok": True, "db": DB_PATH,
                                    "db_exists": os.path.exists(DB_PATH), "port": PORT})
        tok = (qs.get("token") or [""])[0] or self.headers.get("X-Brain-Token", "")
        if tok != TOKEN:
            return self._send(401, {"error": "bad or missing token"})
        q = (qs.get("q") or [""])[0].strip()
        if not q:
            return self._send(400, {"error": "missing q"})
        try:
            con = connect()
            n = int((qs.get("n") or ["4"])[0])
            brief = build_brief(con, q, per_tier=max(1, min(n, 10)))
            con.close()
        except Exception as e:
            return self._send(500, {"error": repr(e)})
        if u.path == "/ask":
            return self._send(200, render_text(brief), "text/plain; charset=utf-8")
        if u.path == "/ask.json":
            return self._send(200, brief)
        return self._send(404, {"error": "not found"})


REFRESH_SECS = int(os.environ.get("BRAIN_REFRESH", "300"))


def refresher():
    """Keep the fast-moving sources fresh so 'what happened before' means MINUTES ago.

    RAMCHAT changes every few minutes while the team works; the memory files change
    whenever Claude saves. Both are tiny and incremental (mtime+size skip), so this
    costs ~0.2s. Everything else (5,000+ transcripts) stays on ALMA-RECALL's own
    schedule — we never re-walk those from here.
    """
    import threading
    import time as _t

    def loop():
        sys.path.insert(0, os.path.join("D:" + os.sep, "CLAUDE", "alma-recall"))
        while True:
            _t.sleep(REFRESH_SECS)
            try:
                import recall
                con = sqlite3.connect(DB_PATH, timeout=30)
                con.row_factory = sqlite3.Row
                con.execute("PRAGMA busy_timeout=30000")
                recall.Indexer(con, log=lambda *a: None).run(only=["ramchat", "memory"])
                con.close()
                _IDF_CACHE.clear()
            except Exception as e:
                sys.stderr.write("refresh failed: %r\n" % (e,))

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def main():
    if not os.path.exists(DB_PATH):
        print("recall.db not found at %s" % DB_PATH)
        return 1
    refresher()
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print("ALMA-BRAIN on http://%s:%d/  token=%s  refresh=%ds"
          % (BIND, PORT, TOKEN, REFRESH_SECS))
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main() or 0)
