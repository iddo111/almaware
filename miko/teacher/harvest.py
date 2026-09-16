#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""harvest.py -- take PUBLIC web pages, decently, and write them down with their source.

WHAT THIS WILL NOT CRAWL, and the refusal is in the code, not in a promise:
  * any host not listed in allowlist.txt (measured allow-list, not a wish-list)
  * anything its own robots.txt refuses for OUR User-Agent (en.wikipedia.org says no,
    so Wikipedia is NOT harvested -- measured 2026-09-12)
  * anything behind a login: no cookies are ever sent, no auth header, no form post,
    and a URL carrying userinfo (user:pass@host) is refused outright
  * anything paywalled, any private machine, any personal account, any page about a
    private individual. The seed list is documentation and public-domain text.
Every page is stored with its URL, the time it was fetched and a sha256 of its text,
so any training pair made from it can be walked back to its source.

    python harvest.py --dry-run
    python harvest.py --limit 6 --delay 2.0
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

import common

UA = "MikoTeacherBot/0.1 (+research; respects robots.txt; contact iddo111@gmail.com)"
HERE = Path(__file__).resolve().parent

_SCRIPT = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def load_allowlist(path=None) -> set[str]:
    p = Path(path or (HERE / "allowlist.txt"))
    hosts = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            hosts.add(line.lower())
    return hosts


def strip_html(raw: str) -> tuple[str, str]:
    title = ""
    m = _TITLE.search(raw)
    if m:
        title = html.unescape(_TAG.sub(" ", m.group(1))).strip()
    body = _SCRIPT.sub(" ", raw)
    body = _TAG.sub("\n", body)
    body = html.unescape(body)
    body = _WS.sub(" ", body)
    body = "\n".join(ln.strip() for ln in body.split("\n"))
    body = _NL.sub("\n\n", body).strip()
    return title, body


def refuse(url: str, allow: set[str]) -> str | None:
    """Return a reason to refuse, or None if the URL may be considered."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        return "scheme %r is not http(s)" % p.scheme
    if "@" in p.netloc:
        return "URL carries userinfo (a login) -- refused"
    host = p.hostname or ""
    if host.lower() not in allow:
        return "host %r is not in allowlist.txt" % host
    return None


class Robots:
    """One robots.txt per host, read once, obeyed. Unreadable robots.txt = refuse."""

    def __init__(self):
        self._cache: dict[str, object] = {}

    def check(self, url: str) -> tuple[bool, float | None, str]:
        p = urllib.parse.urlparse(url)
        host = "%s://%s" % (p.scheme, p.netloc)
        rp = self._cache.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(host + "/robots.txt")
            try:
                rp.read()
            except Exception as e:
                self._cache[host] = False
                return False, None, "robots.txt unreadable (%s) -- refusing" % type(e).__name__
            self._cache[host] = rp
        if rp is False:
            return False, None, "robots.txt unreadable earlier -- refusing"
        ok = rp.can_fetch(UA, url)
        delay = None
        try:
            delay = rp.crawl_delay(UA)
        except Exception:
            pass
        return ok, delay, ("allowed" if ok else "robots.txt refuses this URL for our UA")


def main() -> int:
    common.utf8()
    common.lower_priority()
    ap = argparse.ArgumentParser(prog="harvest.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default=str(HERE / "seeds.txt"))
    ap.add_argument("--allowlist", default=str(HERE / "allowlist.txt"))
    ap.add_argument("--out", default=str(common.DATA / "pages.jsonl"))
    ap.add_argument("--limit", type=int, default=0, help="stop after N pages (0 = all seeds)")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="minimum seconds between two fetches of the same host")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--min-chars", type=int, default=800,
                    help="skip pages with less text than this")
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and print, fetch NOTHING")
    a = ap.parse_args()

    allow = load_allowlist(a.allowlist)
    seeds = [ln.strip() for ln in Path(a.seeds).read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    print("allowlist: %d hosts | seeds: %d URLs | UA: %s" % (len(allow), len(seeds), UA))

    robots = Robots()
    existing = {r["url"] for r in common.read_jsonl(a.out)}
    last_hit: dict[str, float] = {}
    rows, kept, skipped = [], 0, 0

    for url in seeds:
        if a.limit and kept >= a.limit:
            break
        why = refuse(url, allow)
        if why:
            print("  REFUSE %s -- %s" % (url, why)); skipped += 1; continue
        if url in existing:
            print("  have   %s" % url); continue
        ok, cdelay, note = robots.check(url) if not a.dry_run else (True, None, "not checked (dry-run)")
        if not ok:
            print("  ROBOTS %s -- %s" % (url, note)); skipped += 1; continue
        if a.dry_run:
            print("  WOULD FETCH %s" % url); kept += 1; continue

        host = urllib.parse.urlparse(url).hostname or ""
        wait = max(a.delay, float(cdelay or 0.0))
        gap = time.time() - last_hit.get(host, 0.0)
        if gap < wait:
            time.sleep(wait - gap)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "text/html,text/plain;q=0.9"})
            with urllib.request.urlopen(req, timeout=a.timeout) as r:
                raw = r.read().decode("utf-8", "replace")
        except Exception as e:
            print("  FAIL   %s -- %s: %s" % (url, type(e).__name__, str(e)[:70]))
            skipped += 1; last_hit[host] = time.time(); continue
        last_hit[host] = time.time()
        title, text = strip_html(raw)
        if len(text) < a.min_chars:
            print("  THIN   %s -- %d chars" % (url, len(text))); skipped += 1; continue
        rows.append({
            "page_id": "p_" + common.sha256_text(url)[:12],
            "url": url, "host": host, "title": title[:200],
            "fetched_at": common.now(), "bytes": len(raw), "chars": len(text),
            "sha256": common.sha256_text(text), "robots": "allowed for " + UA.split("/")[0],
            "text": text,
        })
        kept += 1
        print("  OK     %-70s %6d chars  %s" % (url[:70], len(text), title[:40]))

    if a.dry_run:
        print("\n[dry-run] would fetch %d, refuse/skip %d. Nothing was fetched." % (kept, skipped))
        return 0
    old = common.read_jsonl(a.out)
    allrows = old + rows
    common.write_jsonl(a.out, allrows)
    print("\nwrote %d new page(s), %d total -> %s" % (len(rows), len(allrows), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
