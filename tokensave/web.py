#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web.py -- a cheap web search from the command line.

Uses the DuckDuckGo HTML endpoint (no API key, no JS). Returns up to 5
titles + URLs + one-line snippets, so an agent never has to spend a full
model turn just to search the web.

Usage:
    python web.py "tailscale serve address already in use"

Options:
    -n N        number of results (default 5)
    --json      machine-readable output
    --help      this text
"""
import sys
import os
import re
import time
import json
import html as htmlmod
import argparse
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import lower_priority, approx_tokens, eprint

DDG_URL = "https://html.duckduckgo.com/html/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# DuckDuckGo throws a JS "anomaly" / bot-check page instead of results when it
# decides a client looks automated -- it can trigger after a single burst of
# a few requests, independent of client (seen from both urllib and curl.exe
# in testing). Detect it explicitly instead of silently reporting "0 results".
BLOCK_MARKERS = ("anomaly.js", "cc=botnet", "challenge-form")


class RateLimited(Exception):
    pass

TAG_RE = re.compile(r"<[^>]+>")
RESULT_RE = re.compile(
    r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', re.S
)
SNIPPET_RE = re.compile(
    r'<a class="result__snippet"[^>]*>(.*?)</a>', re.S
)


def strip_tags(s):
    return htmlmod.unescape(TAG_RE.sub("", s)).strip()


def real_url(href):
    # DDG html wraps real links as //duckduckgo.com/l/?uddg=<url>&rut=...
    if href.startswith("//"):
        href = "https:" + href
    p = urllib.parse.urlparse(href)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        qs = urllib.parse.parse_qs(p.query)
        if "uddg" in qs:
            return urllib.parse.unquote(qs["uddg"][0])
    return href


def _fetch(query, timeout):
    url = DDG_URL + "?" + urllib.parse.urlencode({"q": query})
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def search(query, n=5, timeout=8.0, retries=1, backoff=3.0):
    last_raw = ""
    for attempt in range(retries + 1):
        raw = _fetch(query, timeout)
        last_raw = raw
        if any(m in raw for m in BLOCK_MARKERS):
            if attempt < retries:
                time.sleep(backoff)
                continue
            raise RateLimited(
                "DuckDuckGo is bot-challenging this IP right now "
                "(triggers fast under repeated calls) -- wait a bit and retry")
        titles = RESULT_RE.findall(raw)
        snippets = SNIPPET_RE.findall(raw)
        results = []
        for i, (href, title_html) in enumerate(titles[:n]):
            snip = strip_tags(snippets[i]) if i < len(snippets) else ""
            results.append({
                "title": strip_tags(title_html),
                "url": real_url(href),
                "snippet": snip,
            })
        return raw, results
    return last_raw, []


def main():
    ap = argparse.ArgumentParser(
        prog="web.py", description="Cheap CLI web search via DuckDuckGo HTML."
    )
    ap.add_argument("query", nargs="+")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    lower_priority()
    q = " ".join(args.query)
    try:
        raw, results = search(q, n=args.n)
    except RateLimited as e:
        print("web.py: %s" % e)
        return
    except Exception as e:
        print("web.py: search failed (%s)" % e)
        return

    out_chars = 0
    if not results:
        line = "no results for: %s" % q
        print(line)
        out_chars = len(line)
    elif args.json:
        payload = json.dumps(results, ensure_ascii=False)
        print(payload)
        out_chars = len(payload)
    else:
        for i, r in enumerate(results, 1):
            line = "%d. %s | %s | %s" % (i, r["title"], r["url"], r["snippet"])
            print(line)
            out_chars += len(line)

    saved = max(0, approx_tokens("x" * len(raw)) - approx_tokens("x" * out_chars))
    print("[web.py] fetched ~%d chars of search HTML -> ~%d tokens saved vs a model browsing it raw"
          % (len(raw), saved))


if __name__ == "__main__":
    main()
