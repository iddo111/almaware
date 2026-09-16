#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
miko/research/_common.py -- shared crawling + fleet-prompt helpers for
dig.py and watch.py. Stdlib only (same ethos as D:\\CLAUDE\\tokensave).

Reuse map (so it is obvious what is NOT reinvented here):
  - web search (DuckDuckGo)      -> tokensave/web.py, called as a subprocess
  - own notes / memory / RAMCHAT -> tokensave/ask.py, called as a subprocess
  - talking to the free fleet    -> tokensave/_common.call_fleet (imported
                                     directly -- this is the exact engine
                                     sum.py and fleet.py are built on).
  - bulk text compression        -> tokensave/sum.py, called as a subprocess
                                     by watch.py for big deltas.

What IS new here (no existing helper covered these): politely fetching an
arbitrary public page (robots.txt + pacing + charset), extracting text/links
from its HTML, and the three research-specific fleet prompts (which links
are worth following, what does this page claim, and the final sourced
synthesis). sum.py's own prompt is fixed to generic "1-2 terse bullets" and
is not question-aware, so those three prompts call the shared call_fleet()
primitive directly instead of shelling out to sum.py's fixed prompt.
"""
import sys
import os
import re
import io
import json
import time
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import urllib.robotparser as robotparser
from html.parser import HTMLParser
from collections import Counter

TOKENSAVE_DIR = r"D:\CLAUDE\tokensave"
sys.path.insert(0, TOKENSAVE_DIR)
from _common import lower_priority, call_fleet, approx_tokens, eprint  # noqa: E402

RESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(RESEARCH_DIR, "runs")

# Honest, descriptive user agent. No personal contact info in it on purpose
# -- that would leak Iddo's identity to every public site this touches.
UA = ("Mozilla/5.0 (compatible; PersonalResearchBot/1.0; "
      "+local single-user non-commercial research reader; text only)")

MIN_GAP_SEC = 2.0          # politeness floor: seconds between 2 reqs to same domain
ROBOTS_TIMEOUT = 6.0
FETCH_TIMEOUT = 10.0
MAX_PAGE_BYTES = 1_500_000  # 1.5 MB cap per page -- text only, never media

BAD_EXT = (".pdf", ".zip", ".7z", ".rar", ".png", ".jpg", ".jpeg", ".gif",
           ".svg", ".webp", ".ico", ".mp3", ".mp4", ".wav", ".mov", ".avi",
           ".exe", ".dmg", ".msi", ".css", ".js", ".woff", ".woff2", ".ttf",
           ".eot", ".xml", ".rss", ".json", ".csv", ".xlsx", ".docx", ".pptx")

JUNK_LINK_RE = re.compile(
    r"(login|signin|sign-in|signup|sign-up|register|logout|/cart|/checkout|"
    r"/subscribe|newsletter|cookie[-_]?polic|privacy[-_]?polic|terms[-_]?of|"
    r"advertis|doubleclick|googletagmanager|facebook\.com|twitter\.com|x\.com/|"
    r"instagram\.com|linkedin\.com/(shareArticle|share)|pinterest\.|"
    r"reddit\.com/submit|/feed/?$|feed\.xml)", re.I)

_robots_cache = {}   # domain -> RobotFileParser instance, or None = fail-closed
_last_request = {}   # domain -> monotonic time of last request


def utf8_stdio():
    """Make stdout/stderr tolerant of Hebrew regardless of the Windows
    console code page. PYTHONIOENCODING=utf-8 should also be set in the
    environment before launch; this is the in-process belt-and-suspenders."""
    for name in ("stdout", "stderr"):
        s = getattr(sys, name, None)
        if s is None:
            continue
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def slugify(text, maxlen=40):
    keep = re.findall(r"[\w\u0590-\u05FF]+", text.lower())
    s = "-".join(keep)[:maxlen].strip("-")
    return s or "topic"


def domain_of(url):
    return urllib.parse.urlparse(url).netloc.lower()


def normalize_url(url):
    """Dedup key: drop fragment + common tracking params, lower-case host."""
    p = urllib.parse.urlparse(url)
    qs = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
          if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref"))]
    query = urllib.parse.urlencode(sorted(qs))
    return urllib.parse.urlunparse((p.scheme.lower(), p.netloc.lower(),
                                     p.path.rstrip("/") or "/", "", query, ""))


def looks_fetchable(url):
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    path = p.path.lower()
    return not any(path.endswith(ext) for ext in BAD_EXT)


def iri_to_uri(url):
    """Hebrew (and any other non-ASCII) URLs are legal IRIs but urllib's
    http.client chokes building the raw request line unless the path/query
    are percent-encoded first ('ascii' codec can't encode ...). Encode only
    the non-ASCII pieces so already-percent-encoded URLs are left alone."""
    p = urllib.parse.urlsplit(url)
    netloc = p.netloc
    try:
        netloc.encode("ascii")
    except UnicodeEncodeError:
        host = p.hostname or ""
        try:
            enc_host = host.encode("idna").decode("ascii")
        except Exception:
            enc_host = host
        userinfo = ""
        if p.username:
            userinfo = p.username + (":" + p.password if p.password else "") + "@"
        port = ":" + str(p.port) if p.port else ""
        netloc = userinfo + enc_host + port
    path = urllib.parse.quote(p.path, safe="/%")
    query = urllib.parse.quote(p.query, safe="=&%")
    fragment = urllib.parse.quote(p.fragment, safe="%")
    return urllib.parse.urlunsplit((p.scheme, netloc, path, query, fragment))


# ---------------------------------------------------------------- robots.txt
def _fetch_robots_text(robots_url):
    """robotparser.read() uses a bare urllib UA that some sites (Wikipedia
    included) 403 outright, which silently makes it deny-all. Fetch with our
    own honest headers instead and feed the text in via .parse()."""
    req = urllib.request.Request(iri_to_uri(robots_url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=ROBOTS_TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def get_robots(url):
    dom = domain_of(url)
    if dom in _robots_cache:
        return _robots_cache[dom]
    scheme = urllib.parse.urlparse(url).scheme
    robots_url = "%s://%s/robots.txt" % (scheme, dom)
    rp = robotparser.RobotFileParser()
    try:
        text = _fetch_robots_text(robots_url)
        rp.parse(text.splitlines())
        _robots_cache[dom] = rp
    except urllib.error.HTTPError as e:
        if e.code == 404:
            rp.parse([])  # no robots.txt published -> no restrictions declared
            _robots_cache[dom] = rp
        else:
            _robots_cache[dom] = None  # fail closed: can't confirm the policy
    except Exception:
        _robots_cache[dom] = None  # timeout / DNS / TLS -- fail closed
    return _robots_cache[dom]


def allowed_to_fetch(url):
    rp = get_robots(url)
    if rp is None:
        return False, "robots.txt unreachable -- skipped (fail closed)"
    ok = rp.can_fetch(UA, url)
    return ok, (None if ok else "disallowed by robots.txt")


def polite_wait(url):
    """One request at a time per site, with a pause -- and honour a
    Crawl-delay from robots.txt if the site published one."""
    dom = domain_of(url)
    delay = MIN_GAP_SEC
    rp = _robots_cache.get(dom)
    try:
        if rp is not None:
            cd = rp.crawl_delay(UA)
            if cd:
                delay = max(delay, float(cd))
    except Exception:
        pass
    last = _last_request.get(dom, 0.0)
    now = time.monotonic()
    wait = delay - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_request[dom] = time.monotonic()


# ------------------------------------------------------------- HTML parsing
class _Extractor(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self.text_parts = []
        self.links = []          # (abs_url, anchor_text)
        self._cur_href = None
        self._cur_anchor = []

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag in ("script", "style", "noscript", "template"):
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and ad.get("href"):
            href = ad["href"].strip()
            if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
                self._cur_href = urllib.parse.urljoin(self.base_url, href)
                self._cur_anchor = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._cur_href is not None:
            anchor = " ".join("".join(self._cur_anchor).split())
            self.links.append((self._cur_href, anchor[:140]))
            self._cur_href = None
            self._cur_anchor = []

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        if self._cur_href is not None:
            self._cur_anchor.append(data)
        stripped = data.strip()
        if stripped:
            self.text_parts.append(stripped)


def extract(html_text, base_url):
    p = _Extractor(base_url)
    try:
        p.feed(html_text)
    except Exception:
        pass
    text = "\n".join(p.text_parts)
    text = re.sub(r"\n{2,}", "\n", text)
    return (p.title.strip() or base_url), text, p.links


def _decode(raw, content_type):
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    tried = []
    if m:
        tried.append(m.group(1))
    m2 = re.search(rb'charset=["\']?([\w-]+)', raw[:2048], re.I)
    if m2:
        try:
            tried.append(m2.group(1).decode("ascii", "ignore"))
        except Exception:
            pass
    tried += ["utf-8", "windows-1255", "windows-1256", "iso-8859-8"]
    for enc in tried:
        try:
            return raw.decode(enc, "strict")
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def fetch_page(url, timeout=FETCH_TIMEOUT):
    """GET a public page, text/html only, with robots.txt + pacing. Returns
    a dict; never raises."""
    if not looks_fetchable(url):
        return {"ok": False, "url": url, "error": "non-text extension, skipped"}
    ok, why = allowed_to_fetch(url)
    if not ok:
        return {"ok": False, "url": url, "error": "robots: %s" % why}
    polite_wait(url)
    safe_url = iri_to_uri(url)
    req = urllib.request.Request(safe_url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        "Accept-Language": "he,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "") or ""
            final_url = r.geturl()
            if ctype and not any(t in ctype for t in ("text/html", "xhtml", "text/plain")):
                return {"ok": False, "url": url, "error": "non-html content-type: %s" % ctype}
            raw = r.read(MAX_PAGE_BYTES)
    except urllib.error.HTTPError as e:
        return {"ok": False, "url": url, "error": "HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e)}

    text0 = _decode(raw, ctype)
    title, text, links = extract(text0, final_url)
    return {"ok": True, "url": final_url, "orig_url": url, "title": title,
            "text": text, "links": links}


def filter_candidate_links(links, own_domain):
    """Filter junk, then put off-domain links first. A hub page like a
    Wikipedia article can carry 1000+ internal nav/interlanguage links
    before its actual references/external-links section appears in the
    HTML; since the fleet ranker only ever sees a capped sample, sampling
    in raw DOM order means it never sees a single reference. Off-domain
    links are far more often the "paper, lab page, datasheet, follow-up
    thread" this tool exists to find, so they go first (order preserved
    within each group)."""
    seen = set()
    external, internal = [], []
    for href, anchor in links:
        if href in seen:
            continue
        seen.add(href)
        if JUNK_LINK_RE.search(href):
            continue
        if not looks_fetchable(href):
            continue
        (external if domain_of(href) != own_domain else internal).append((href, anchor))
    return external + internal


# --------------------------------------------------------- subprocess reuse
def _run_tool(script, args, timeout):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(TOKENSAVE_DIR, script)] + args,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=env)
        return p.stdout or "", p.stderr or ""
    except Exception as e:
        return "", str(e)


def _first_json_line(stdout):
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("[") or line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def get_own_notes(question, n=6, timeout=25):
    """Reuse tokensave/ask.py exactly as shipped -- his own memory / BRAIN2 /
    alma-recall / RAMCHAT, searched before anything goes to the web."""
    out, err = _run_tool("ask.py", [question, "-n", str(n), "--json"], timeout)
    data = _first_json_line(out)
    if data is None:
        return [], (out.strip() or err.strip() or "ask.py: no output")
    return data, None


def ddg_seeds(question, n=8, timeout=25):
    """Reuse tokensave/web.py exactly as shipped for the general web search
    leg of the seed list."""
    out, err = _run_tool("web.py", [question, "-n", str(n), "--json"], timeout)
    data = _first_json_line(out)
    if data is None:
        return [], (out.strip() or err.strip() or "web.py: no output")
    return data, None


def sum_via_toolkit(path, timeout=90):
    """Reuse tokensave/sum.py exactly as shipped to compress a big text file
    on the free fleet (used by watch.py for large deltas)."""
    out, err = _run_tool("sum.py", [path], timeout)
    return out.strip() or err.strip()


def semanticscholar_search(query, n=5, timeout=8):
    """Public paper-search API, not scraped HTML -- own robots-equivalent is
    its published rate limit, which we simply back off from on 429."""
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search?" + \
            urllib.parse.urlencode({"query": query, "limit": n,
                                     "fields": "title,url,year"})
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return data.get("data", []) or [], None
    except urllib.error.HTTPError as e:
        return [], "HTTP %s" % e.code
    except Exception as e:
        return [], str(e)


# --------------------------------------------------------------- fleet work
ENTITY_SYS = (
    "A researcher asked the question below, in whatever language it is "
    "written in. Reply with a short seed list for a web crawl, ENGLISH, "
    "one phrase per line, most important first, no numbering, no "
    "explanation, no extra text:\n"
    "- Line 1-2: the core technical concept(s) themselves, worded exactly "
    "as their most likely English Wikipedia article title (e.g. "
    "'Memristor', 'Neuromorphic computing', 'In-memory computing').\n"
    "- Line 3-6: specific real companies, research labs, named research "
    "groups, or universities actually known for THIS topic -- never a "
    "generic body, a journal name, or the word Wikipedia/Google/IEEE on "
    "its own.")

_ENTITY_BLOCKLIST = {"wikipedia", "google", "google scholar", "ieee", "nature",
                      "arxiv", "youtube", "reddit", "twitter", "facebook"}


def suggest_entities_with_fleet(question, timeout=60):
    try:
        _, _, content = call_fleet(
            [{"role": "system", "content": ENTITY_SYS},
             {"role": "user", "content": question}],
            max_tokens=150, temperature=0.1, timeout=timeout)
    except Exception as e:
        return [], str(e)
    ents = [l.strip(" -*\t0123456789.") for l in content.splitlines()]
    ents = [e for e in ents if 2 <= len(e) <= 60
            and e.lower() not in _ENTITY_BLOCKLIST][:6]
    return ents, None


RANK_SYS = (
    "You help a hardware/AI researcher decide which links on a web page are "
    "worth opening next. Given the research question, the current page, and "
    "a numbered list of candidate links (index. anchor text | url), pick up "
    "to K links most likely to be a primary source, a paper, a lab/company "
    "page, a datasheet, or a substantive follow-up -- not navigation, ads, "
    "or social share. Reply with ONLY a JSON array, nothing else: "
    '[{"i": <index>, "reason": "<short phrase>"}]')


def _extract_json_array(content):
    m = re.search(r"\[.*\]", content, re.S)
    if not m:
        raise ValueError("no JSON array in fleet reply")
    return json.loads(m.group(0))


def rank_links_with_fleet(question, page_title, page_url, links, k=4, timeout=90):
    if not links:
        return []
    cand = links[:40]
    listing = "\n".join("%d. %s | %s" % (i, (a or "(no anchor text)"), u)
                         for i, (u, a) in enumerate(cand))
    user = ("QUESTION: %s\nCURRENT PAGE: %s (%s)\nCANDIDATE LINKS:\n%s\n"
            "Pick up to %d." % (question, page_title, page_url, listing, k))
    try:
        _, _, content = call_fleet(
            [{"role": "system", "content": RANK_SYS},
             {"role": "user", "content": user}],
            max_tokens=400, temperature=0.1, timeout=timeout)
        data = _extract_json_array(content)
        picks = []
        for item in data[:k]:
            i = int(item.get("i"))
            if 0 <= i < len(cand):
                picks.append({"url": cand[i][0], "anchor": cand[i][1],
                              "reason": str(item.get("reason", ""))[:120]})
        if picks:
            return picks
    except Exception as e:
        eprint("[dig] link ranking via fleet failed (%s) -- falling back to keyword overlap" % e)
    kws = set(re.findall(r"[\w\u0590-\u05FF]{3,}", question.lower()))
    scored = []
    for u, a in cand:
        s = sum(1 for kw in kws if kw in (a or "").lower() or kw in u.lower())
        if s:
            scored.append((s, u, a))
    scored.sort(key=lambda t: -t[0])
    return [{"url": u, "anchor": a, "reason": "keyword overlap (fleet unavailable)"}
            for _, u, a in scored[:k]]


CLAIM_SYS = (
    "You extract factual claims from a web page's text for a research "
    "assistant. Use ONLY facts stated in the given text -- never add outside "
    "knowledge, never guess. Write in the SAME LANGUAGE as the question. "
    "Return 2-5 short bullet claims relevant to the question, plain text, "
    "one per line, no numbering, no preamble. If nothing on this page is "
    "relevant to the question, return exactly: NOTHING_RELEVANT")


def extract_claims_with_fleet(question, url, title, text, max_chars=6000, timeout=100):
    chunk = text[:max_chars]
    if not chunk.strip():
        return []
    user = ("QUESTION: %s\nPAGE TITLE: %s\nPAGE URL: %s\nPAGE TEXT:\n%s"
            % (question, title, url, chunk))
    try:
        _, _, content = call_fleet(
            [{"role": "system", "content": CLAIM_SYS},
             {"role": "user", "content": user}],
            max_tokens=320, temperature=0.15, timeout=timeout)
    except Exception as e:
        eprint("[dig] claim extraction failed for %s: %s" % (url, e))
        return []
    content = (content or "").strip()
    if not content or content.upper().startswith("NOTHING_RELEVANT"):
        return []
    bullets = []
    for line in content.splitlines():
        line = line.strip(" -*\t\u2022")
        if line:
            bullets.append(line)
    return bullets[:5]


SYNTH_SYS = (
    "You are a research assistant writing a final answer for a hardware/AI "
    "researcher, in the SAME LANGUAGE as the question. You are given (A) "
    "relevant material already known from the user's own notes, and (B) "
    "claims gathered from public web pages during this run, each already "
    "tagged with its source URL. Write exactly these three sections:\n"
    "1) 'From your own notes:' -- using ONLY the (A) material, or say "
    "plainly that nothing relevant was found there if (A) is empty.\n"
    "2) 'From the web:' -- a short sourced answer. Every factual claim ends "
    "with its source URL in square brackets, e.g. [https://...]. Use ONLY "
    "the (B) material -- never invent a claim or a URL not given to you.\n"
    "3) 'What I could not find:' -- an honest, short list of sub-questions "
    "the material did not answer.\n"
    "Be concise. No filler, no repeating the question back.")


def synthesize(question, notes_hits, claims_by_url, timeout=150):
    notes_block = "\n".join(
        "- [%s] %s" % (h.get("source", "?"), h.get("text", "")) for h in notes_hits
    ) or "(none)"
    parts = []
    for url, info in claims_by_url.items():
        for c in info["claims"]:
            parts.append("- %s [%s]" % (c, url))
    web_block = "\n".join(parts) or "(none)"
    user = ("QUESTION: %s\n\n(A) OWN NOTES:\n%s\n\n(B) WEB CLAIMS:\n%s"
            % (question, notes_block, web_block))
    try:
        _, _, content = call_fleet(
            [{"role": "system", "content": SYNTH_SYS},
             {"role": "user", "content": user}],
            max_tokens=900, temperature=0.2, timeout=timeout)
        return content.strip()
    except Exception as e:
        return ("[synthesis failed -- fleet unreachable: %s]\n\n"
                 "Raw web claims:\n%s\n\nOwn notes:\n%s" % (e, web_block, notes_block))


# -------------------------------------------------------------------- misc
def log_event(run_dir, kind, **fields):
    rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind}
    rec.update(fields)
    with open(os.path.join(run_dir, "journal.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
