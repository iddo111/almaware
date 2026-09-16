#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
find_one_language.py — hunt "פרויקט שפה אחת" / the ONE-LANGUAGE project across
every archive on this machine, using ALMA-RECALL first and the disk second.

Iddo, 2026-09-01 12:35: "תעלה סוכן וסקריפט ותשתמש בתוכנת חיפוש שלנו גם = פרויקט
שפה אחת". The phrase is his; the record is what decides what it means. This
script does not guess — it reports every hit with its date and source, and says
plainly when a phrasing returns nothing.

Usage:  PYTHONIOENCODING=utf-8 python tools/find_one_language.py
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request

RECALL = "http://127.0.0.1:8794/api/search"
OUT = r"D:\CLAUDE\tools\one-language-findings.md"

# Every plausible phrasing, including how KESHEV would garble it.
QUERIES = [
    "פרויקט שפה אחת",
    "שפה אחת",
    "שפה אחת לכולם",
    "one language",
    "one language project",
    "ONE LANGUAGE",
    "שפת עלמה אחת",
    "לשון אחת",
    "unified language",
    "one codex",
    "one weave",
    "שפה אוניברסלית",
    "אספרנטו",
    "מגדל בבל",
    "Babel",
]

# Memory + disk fallback: substrings worth grepping for.
DISK_TOKENS = ["שפה אחת", "לשון אחת", "one language", "ONE LANGUAGE",
               "one_language", "one-language"]
DISK_ROOTS = [
    r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory",
    r"D:\CLAUDE\alma-language",
    r"D:\CLAUDE\RAMCHAT",
]
DISK_EXT = {".md", ".txt", ".json", ".py"}


def recall(q, limit=12):
    """Ask ALMA-RECALL. Returns hits or [] with the reason recorded."""
    url = "%s?q=%s&limit=%d" % (RECALL, urllib.parse.quote(q), limit)
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return json.loads(r.read().decode("utf-8")).get("hits", []), None
    except Exception as exc:
        return [], str(exc)


def scan_disk():
    hits = []
    for root in DISK_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if any(s in dirpath for s in (".git", "__pycache__", "node_modules")):
                dirnames[:] = []
                continue
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() not in DISK_EXT:
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    if os.path.getsize(p) > 4_000_000:
                        continue
                    with io.open(p, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                for tok in DISK_TOKENS:
                    i = text.find(tok)
                    if i >= 0:
                        hits.append({
                            "path": p, "token": tok,
                            "context": text[max(0, i - 200):i + 300].replace("\n", " "),
                        })
                        break
    return hits


def main():
    lines = ["> \U0001fa9f **BROKEN WINDOWS LAW** \u2014 if it's not working, fix it IMMEDIATELY.\n",
             "# \u05e4\u05e8\u05d5\u05d9\u05e7\u05d8 \u05e9\u05e4\u05d4 \u05d0\u05d7\u05ea \u2014 what the record actually holds\n"]
    total = 0
    for q in QUERIES:
        hits, err = recall(q)
        if err:
            lines.append("\n## `%s`\n\nRECALL ERROR: %s\n" % (q, err))
            print("  %-24s ERROR %s" % (q, err))
            continue
        print("  %-24s %d hits" % (q, len(hits)))
        if not hits:
            lines.append("\n## `%s`\n\nnothing \u2014 a real negative result.\n" % q)
            continue
        total += len(hits)
        lines.append("\n## `%s` \u2014 %d hits\n" % (q, len(hits)))
        for h in hits[:8]:
            lines.append("- **%s** \u00b7 %s \u00b7 `%s`\n  > %s\n" % (
                (h.get("ts") or "?")[:16], h.get("source") or "?",
                (h.get("title") or "")[:70],
                (h.get("snip") or "").replace("\n", " ")[:300]))

    dh = scan_disk()
    print("  disk scan: %d hits" % len(dh))
    lines.append("\n# Disk (memory + alma-language + RAMCHAT) \u2014 %d hits\n" % len(dh))
    for h in dh[:30]:
        lines.append("- `%s` (%s)\n  > %s\n" % (h["path"], h["token"], h["context"][:300]))

    io.open(OUT, "w", encoding="utf-8").write("".join(lines))
    print("\nrecall hits: %d | disk hits: %d\nwrote %s" % (total, len(dh), OUT))


if __name__ == "__main__":
    main()
