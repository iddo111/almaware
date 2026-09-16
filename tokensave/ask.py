#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ask.py -- SEARCH BEFORE YOU THINK.

Answers a question from what is already known on this machine, instead of
burning a model turn (or a full-file read) to re-derive it.

Queries, in order of priority: Claude's own memory files, BRAIN2, alma-recall,
RAMCHAT. Prints the 3 best short answers with their source. One line if
nothing is found.

Usage:
    python ask.py "is BRAIN2 alive"
    python ask.py "what is the fabric topology"

Options:
    -n N        how many answers to show (default 3)
    --json      machine-readable output
    --help      this text
"""
import sys
import os
import re
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import lower_priority, http_get_json, approx_tokens, eprint

MEMORY_DIR = r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory"
BRAIN2_URL = "http://127.0.0.1:8897/search"
RECALL_URL = "http://127.0.0.1:8794/api/search"
RAMCHAT_SESSION = r"D:\CLAUDE\RAMCHAT\ramchat_session.json"

STOPWORDS = set("""
the a an is are was were be been being of to in on at for with and or not
do does did how what when where why who which this that these those i you
he she it we they my your his her its our their am can could would should
will shall have has had
""".split())

# HEBREW-RECALL scar (measured 2026-09-15, claude-cli-SONNET-hebrecall): the
# STOPWORDS set above was English-only. Hebrew question words rode along as
# "content" keywords and matched by accident inside unrelated words -- e.g.
# the un-filtered stopword "\u05DC\u05DE\u05D4" (why) is literally a substring of "\u05E2\u05DC\u05DE\u05D4"
# (Alma, Iddo's late sister), so a Hebrew question about Maverick pulled in
# memorial pages. English questions never had this problem because their
# stopwords WERE filtered. Proven live: curl .../recall?q=<he> before this
# fix returned Alma-memorial hits for a Maverick question; after, it doesn't.
HEBREW_STOPWORDS = set("""
\u05DE\u05D4 \u05DC\u05DE\u05D4 \u05DE\u05D9 \u05D0\u05D9\u05DA \u05D4\u05D0\u05DD \u05DB\u05DF \u05DC\u05D0 \u05D6\u05D4 \u05D6\u05D5 \u05D6\u05D0\u05EA \u05D0\u05DC\u05D4 \u05D0\u05DC\u05D5 \u05D4\u05D5\u05D0 \u05D4\u05D9\u05D0 \u05D4\u05DD \u05D4\u05DF \u05D0\u05E0\u05D9 \u05D0\u05EA\u05D4 \u05D0\u05EA\u05DF
\u05D0\u05E0\u05D7\u05E0\u05D5 \u05D0\u05EA\u05DD \u05E9\u05DC \u05E2\u05DD \u05E2\u05DC \u05D0\u05DC \u05DE\u05DF \u05D2\u05DD \u05E8\u05E7 \u05DB\u05D9 \u05D0\u05D1\u05DC \u05D0\u05D5 \u05D0\u05DD \u05DB\u05DE\u05D5 \u05D9\u05E9 \u05D0\u05D9\u05DF \u05D4\u05D9\u05D4 \u05D4\u05D9\u05EA\u05D4 \u05D4\u05D9\u05D5 \u05D9\u05D4\u05D9\u05D4
\u05DB\u05DC \u05DB\u05DA \u05E9\u05DD \u05E4\u05D4 \u05DB\u05D0\u05DF \u05E2\u05D5\u05D3 \u05DB\u05D1\u05E8 \u05EA\u05D5\u05DA \u05D1\u05D9\u05DF \u05D0\u05D7\u05E8\u05D9 \u05DC\u05E4\u05E0\u05D9 \u05E0\u05D2\u05D3 \u05D1\u05DC\u05D9 \u05DC\u05D2\u05D1\u05D9 \u05D0\u05E6\u05DC \u05D3\u05E8\u05DA \u05D1\u05D2\u05DC\u05DC \u05DB\u05D3\u05D9
\u05D0\u05D6 \u05E2\u05DB\u05E9\u05D9\u05D5 \u05D5\u05D2\u05DD \u05E9\u05D5\u05D1 \u05D0\u05D9\u05E4\u05D4 \u05DE\u05EA\u05D9 \u05DB\u05DE\u05D4 \u05D0\u05D5\u05DC\u05D9 \u05D1\u05DB\u05DC\u05DC \u05DE\u05DE\u05E9 \u05D4\u05D6\u05D4 \u05D4\u05D6\u05D0\u05EA \u05D4\u05D0\u05DC\u05D4
""".split())
STOPWORDS |= HEBREW_STOPWORDS

TAG_RE = re.compile(r"<[^>]+>")

# Niqqud/cantillation block -- stripped so a vowel-pointed query still matches
# unpointed corpus text (and vice versa). Cheap, deterministic, no model call.
_NIQQUD_RE = re.compile(r"[\u0591-\u05C7]")
# Final letter-forms (\u05DA \u05DD \u05DF \u05E3 \u05E5) folded to their regular form (\u05DB \u05DE \u05E0 \u05E4 \u05E6) so a
# word ending a query doesn't miss corpus text where it sits mid-word (or a
# differently-inflected form) purely over which glyph Hebrew uses at a
# word-boundary.
_SOFIT_MAP = str.maketrans("\u05DA\u05DD\u05DF\u05E3\u05E5", "\u05DB\u05DE\u05E0\u05E4\u05E6")
# Classical single-letter Hebrew prefixes (\u05D5-\u05D1-\u05D4-\u05DC-\u05DE-\u05E9-\u05DB, "\u05D4\u05D0\u05D5\u05EA\u05D9\u05D5\u05EA \u05D4\u05E9\u05D9\u05DE\u05D5\u05E9")
# fuse onto the next word with no space: "\u05DC\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7" = \u05DC ("to") + "\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7"
# (Maverick). A query written the natural Hebrew way keeps the prefix; stored
# text usually doesn't. Substring matching already covers the OTHER direction
# (corpus token carries the prefix, query doesn't: "\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7" IS a substring of
# "\u05D4\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7") -- only this direction was broken. Proven live 2026-09-15: the
# query "\u05DE\u05D4 \u05E7\u05E8\u05D4 \u05DC\u05D4\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7" only matched once "\u05DC\u05D4\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7" was expanded to also
# try "\u05D4\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7" and "\u05DE\u05D0\u05D1\u05E8\u05D9\u05E7".
_HEB_PREFIX_LETTERS = "\u05D5\u05D1\u05D4\u05DC\u05DE\u05E9\u05DB"


def _normalize_he(s):
    return _NIQQUD_RE.sub("", s).translate(_SOFIT_MAP)


def _prefix_variants(word):
    """Extra candidate forms with 1 then 2 leading Hebrew prefix letters
    stripped, kept only while >=3 chars remain (real Hebrew roots run 3+
    letters, so this avoids manufacturing near-meaningless 1-2 letter
    fragments). Returned IN ADDITION to the original word, never replacing
    it -- the original still matches corpus text that also carries a prefix."""
    out = []
    w = word
    for _ in range(2):
        if len(w) >= 4 and w[0] in _HEB_PREFIX_LETTERS and len(w) - 1 >= 3:
            w = w[1:]
            out.append(w)
        else:
            break
    return out


def keywords(q):
    q = _normalize_he(q)
    words = re.findall(r"[\w\u0590-\u05FF]+", q.lower())
    kws = []
    for w in words:
        if len(w) < 2 or w in STOPWORDS:
            continue
        if w not in kws:
            kws.append(w)
        if re.search(r"[\u0590-\u05FF]", w):
            for variant in _prefix_variants(w):
                if variant not in STOPWORDS and variant not in kws:
                    kws.append(variant)
    return kws


def score_text(text, kws):
    t = _normalize_he(text).lower()
    return sum(1 for k in kws if k in t)


def clean(s, width=140):
    s = TAG_RE.sub("", s or "")
    s = " ".join(s.split())
    return (s[:width] + "...") if len(s) > width else s


def scan_memory(kws, raw_chars):
    cands = []
    if not os.path.isdir(MEMORY_DIR):
        return cands, raw_chars
    try:
        names = [f for f in os.listdir(MEMORY_DIR) if f.endswith(".md")]
    except Exception:
        return cands, raw_chars
    for fn in names:
        path = os.path.join(MEMORY_DIR, fn)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception:
            continue
        raw_chars += len(content)
        low = content.lower()
        if not any(k in low for k in kws):
            continue
        for i, line in enumerate(content.splitlines(), 1):
            sc = score_text(line, kws)
            if sc > 0 and line.strip():
                cands.append({
                    "source": "memory:%s#L%d" % (fn, i),
                    "text": clean(line),
                    "score": sc,
                    "pri": 0,
                })
    return cands, raw_chars


def scan_brain2(kws, q, raw_chars):
    cands = []
    try:
        import urllib.parse as up
        url = BRAIN2_URL + "?q=" + up.quote(q)
        data = http_get_json(url, timeout=2.5)
    except Exception as e:
        eprint("[ask.py] BRAIN2 unreachable: %s" % e)
        return cands, raw_chars
    raw_chars += len(json.dumps(data))
    for hit in (data.get("hits") or [])[:10]:
        snip = hit.get("snippet") or hit.get("name") or ""
        sc = score_text(snip, kws) + score_text(hit.get("name", ""), kws)
        if sc > 0:
            cands.append({
                "source": "BRAIN2:%s" % hit.get("name", hit.get("id", "?")),
                "text": clean(snip),
                "score": sc,
                "pri": 1,
            })
    return cands, raw_chars


def scan_recall(kws, q, raw_chars):
    cands = []
    try:
        import urllib.parse as up
        url = RECALL_URL + "?q=" + up.quote(q) + "&limit=10"
        data = http_get_json(url, timeout=2.5)
    except Exception as e:
        eprint("[ask.py] alma-recall unreachable: %s" % e)
        return cands, raw_chars
    raw_chars += len(json.dumps(data))
    for hit in (data.get("hits") or [])[:10]:
        snip = hit.get("snip") or ""
        sc = score_text(snip, kws)
        if sc > 0:
            src = hit.get("title") or hit.get("project") or hit.get("source") or "?"
            cands.append({
                "source": "recall:%s" % src,
                "text": clean(snip),
                "score": sc,
                "pri": 2,
            })
    return cands, raw_chars


def scan_ramchat(kws, raw_chars):
    cands = []
    if not os.path.isfile(RAMCHAT_SESSION):
        return cands, raw_chars
    try:
        with open(RAMCHAT_SESSION, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        data = json.loads(content)
    except Exception:
        return cands, raw_chars
    raw_chars += len(content)
    for entry in data[-500:]:
        text = entry.get("text", "")
        sc = score_text(text, kws)
        if sc > 0:
            cands.append({
                "source": "ramchat:%s@%s" % (entry.get("who", "?"), entry.get("at", "?")),
                "text": clean(text),
                "score": sc,
                "pri": 3,
            })
    return cands, raw_chars


EZRA_LOG = r"D:\CLAUDE\ezra-hasofer\log.jsonl"


def scan_ezra(kws, raw_chars):
    """עזרא הסופר / Ezra HaSofer -- the resident transcript scribe (2026-09-12).
    Logs every user/assistant turn from this workspace's Claude Code sessions
    with a real RTC timestamp, text-only (no thinking/tool payloads). Scan
    only the tail: it is an append-only log that can grow to tens of
    thousands of lines, and recent turns are what a live question needs."""
    cands = []
    if not os.path.isfile(EZRA_LOG):
        return cands, raw_chars
    try:
        with open(EZRA_LOG, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-4000:]
    except Exception:
        return cands, raw_chars
    for line in lines:
        raw_chars += len(line)
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        text = entry.get("text", "")
        sc = score_text(text, kws)
        if sc > 0:
            cands.append({
                "source": "ezra:%s@%s" % (entry.get("role", "?"), entry.get("ts", "?")),
                "text": clean(text),
                "score": sc,
                "pri": 3,
            })
    return cands, raw_chars


def main():
    ap = argparse.ArgumentParser(
        prog="ask.py",
        description="Search memory/BRAIN2/alma-recall/RAMCHAT before asking a model.",
    )
    ap.add_argument("question", nargs="+", help="the question, quoted or not")
    ap.add_argument("-n", type=int, default=3, help="number of answers (default 3)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    lower_priority()
    q = " ".join(args.question)
    kws = keywords(q)
    if not kws:
        print("no usable keywords in question.")
        return

    raw_chars = 0
    all_cands = []
    for fn in (scan_memory, lambda k, r: scan_brain2(k, q, r),
               lambda k, r: scan_recall(k, q, r), scan_ramchat, scan_ezra):
        cands, raw_chars = fn(kws, raw_chars)
        all_cands.extend(cands)

    all_cands.sort(key=lambda c: (-c["score"], c["pri"], len(c["text"])))
    top = all_cands[:args.n]

    out_chars = 0
    if not top:
        line = "NOTHING FOUND in memory/BRAIN2/alma-recall/RAMCHAT for: %s" % q
        print(line)
        out_chars = len(line)
    else:
        if args.json:
            payload = json.dumps(top, ensure_ascii=False)
            print(payload)
            out_chars = len(payload)
        else:
            for i, c in enumerate(top, 1):
                line = "%d. [%s] %s" % (i, c["source"], c["text"])
                print(line)
                out_chars += len(line)

    saved = max(0, approx_tokens("x" * raw_chars) - approx_tokens("x" * out_chars))
    print("[ask.py] scanned ~%d chars across 5 sources -> ~%d tokens saved vs reading them raw"
          % (raw_chars, saved))


if __name__ == "__main__":
    main()
