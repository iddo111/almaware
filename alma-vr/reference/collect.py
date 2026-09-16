"""REFERENCE — collect real photographs of the city we are building.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תפעיל סריפט לאסוף ולהוריד תמונות וסרטים היסטוריים ולהשתמש בהם."*

**First attempt went to the Library of Congress and it 403s every automated request** —
tested three endpoints, with and without browser headers, all refused. So this goes to
**Wikimedia Commons**, which is a better source for this job anyway: every file carries an
explicit licence template in its own metadata, so the licence travels *with the picture*
instead of being asserted by me.

**Nothing is kept unless Commons itself says it is free.** The check reads
`extmetadata.LicenseShortName` / `Copyrighted` and keeps only public-domain and CC files;
everything else is counted and skipped. Each file's exact licence, author, date and source
page go into `CREDITS.json` next to it — because the failure that put the film in a
commission of inquiry two days ago was exactly a credit that drifted away from its media.

    python collect.py               # the 1930s Tel Aviv sweep
    python collect.py --q "Jaffa port 1930s" --n 25
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "photos")
API = "https://commons.wikimedia.org/w/api.php"
UA = "ALMA-VR-reference/1.0 (historical reference for a 1930s Tel Aviv scene; research use)"

QUERIES = [
    "Tel Aviv 1930s",
    "Tel Aviv 1920s",
    "Tel Aviv street 1930s",
    "Allenby Street Tel Aviv",
    "Rothschild Boulevard Tel Aviv historical",
    "Bauhaus Tel Aviv White City historical",
    "Jaffa 1930s",
    "Tel Aviv beach 1930s",
    "Mandatory Palestine street scene",
    "Tel Aviv building 1934",
]

FREE = ("public domain", "pd-", "cc0", "cc by", "cc-by", "cc by-sa", "cc-by-sa",
        "attribution", "no restrictions")


def api(params: dict, tries: int = 3):
    params = dict(params, format="json", action="query")
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as e:
            if i == tries - 1:
                print("  ! %s" % e)
                return None
            time.sleep(2 + 2 * i)
    return None


def is_free(em: dict) -> tuple[bool, str]:
    """Only what Commons itself declares free. Never inferred."""
    lic = ((em.get("LicenseShortName") or {}).get("value") or "").strip()
    cop = ((em.get("Copyrighted") or {}).get("value") or "").strip().lower()
    low = lic.lower()
    if cop == "false":
        return True, lic or "public domain (Copyrighted=False)"
    return any(t in low for t in FREE), lic or "(no licence field)"


def txt(em: dict, key: str) -> str:
    v = (em.get(key) or {}).get("value") or ""
    return re.sub(r"<[^>]+>", "", str(v)).strip()


def slug(s: str, n: int = 70) -> str:
    s = re.sub(r"^File:", "", s)
    s = re.sub(r"\.(jpe?g|png|tiff?)$", "", s, flags=re.I)
    s = re.sub(r"[^A-Za-z0-9֐-׿]+", "-", s).strip("-")
    return (s[:n] or "item").lower()


def sweep(queries, per_query: int, credits: list, seen: set, width: int):
    kept = skipped = 0
    for q in queries:
        print("\n[q] %s" % q)
        d = api({"list": "search", "srsearch": q, "srnamespace": 6,
                 "srlimit": per_query * 3})
        hits = ((d or {}).get("query") or {}).get("search") or []
        titles = [h["title"] for h in hits if h["title"] not in seen]
        if not titles:
            print("  (nothing new)")
            continue
        got = 0
        for i in range(0, len(titles), 20):
            if got >= per_query:
                break
            batch = titles[i:i + 20]
            info = api({"titles": "|".join(batch), "prop": "imageinfo",
                        "iiprop": "url|extmetadata", "iiurlwidth": width})
            pages = ((info or {}).get("query") or {}).get("pages") or {}
            for _, pg in pages.items():
                if got >= per_query:
                    break
                title = pg.get("title", "")
                ii = (pg.get("imageinfo") or [{}])[0]
                em = ii.get("extmetadata") or {}
                ok, lic = is_free(em)
                if not ok:
                    skipped += 1
                    seen.add(title)
                    continue
                url = ii.get("thumburl") or ii.get("url")
                if not url:
                    skipped += 1
                    seen.add(title)
                    continue
                name = slug(title) + ".jpg"
                path = os.path.join(OUT, name)
                seen.add(title)
                if os.path.exists(path):
                    continue
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=90) as r:
                        blob = r.read()
                except Exception as e:                                # noqa: BLE001
                    print("  ! %s" % e)
                    skipped += 1
                    continue
                if len(blob) < 6000:
                    skipped += 1
                    continue
                io.open(path, "wb").write(blob)
                kept += 1
                got += 1
                credits.append({
                    "file": name, "commons_title": title,
                    "licence": lic,
                    "author": txt(em, "Artist"),
                    "credit": txt(em, "Credit"),
                    "date": txt(em, "DateTimeOriginal") or txt(em, "DateTime"),
                    "description": txt(em, "ImageDescription")[:300],
                    "page": "https://commons.wikimedia.org/wiki/" +
                            urllib.parse.quote(title.replace(" ", "_")),
                    "query": q, "source": "Wikimedia Commons"})
                print("  + %-56s %5.0f KB  [%s]" % (name[:56], len(blob) / 1024, lic[:22]))
                time.sleep(0.25)
    return kept, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect free historical reference photos.")
    ap.add_argument("--q", action="append")
    ap.add_argument("--n", type=int, default=12, help="max kept per query")
    ap.add_argument("--width", type=int, default=1600)
    a = ap.parse_args(argv)

    os.makedirs(OUT, exist_ok=True)
    cpath = os.path.join(OUT, "CREDITS.json")
    credits, seen = [], set()
    if os.path.exists(cpath):
        try:
            credits = json.load(io.open(cpath, encoding="utf-8"))
            seen = {c.get("commons_title") for c in credits}
        except Exception:                                            # noqa: BLE001
            credits = []

    kept, skipped = sweep(list(QUERIES) + list(a.q or []), a.n, credits, seen, a.width)

    io.open(cpath, "w", encoding="utf-8").write(
        json.dumps(credits, ensure_ascii=False, indent=1))
    io.open(os.path.join(OUT, "SOURCE.txt"), "w", encoding="utf-8").write(
        "Historical reference photographs for ALMA VR (1930s Tel Aviv).\n"
        "Source: Wikimedia Commons. Every file was kept ONLY because Commons' own\n"
        "licence metadata says it is public domain or freely licensed; the exact\n"
        "wording, author and source page per file are in CREDITS.json.\n"
        "These are REFERENCE for building geometry. If any ever appears in a\n"
        "deliverable, its credit line must travel with it.\n")
    print("\nkept %d, skipped %d (licence not free / no image)" % (kept, skipped))
    print("total on disk: %d  ->  %s" % (len(credits), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
