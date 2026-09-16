#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""breslev_corpus.py -- harvest the Breslov treasure + everything it cites.

Roots: Likutei Moharan, Likutei Halakhot, Sippurei Maasiyot (Rebbe
Nachman + Rebbe Natan, Sefaria EN+HE), then ONE hop along Sefaria
links into cited Tanakh/Talmud/Midrash/Zohar/Chasidut (capped).
Output: nachman/data/corpus_parts.json + nachman/corpus_full.txt.

Run: python D:\\CLAUDE\\nachman\\breslev_corpus.py   (long! hours)
Progress: prints every book + counts; resumable via parts file.
"""
import json
import os
import time
import urllib.parse
import urllib.request

API = "https://www.sefaria.org/api"
BASE = r"D:\CLAUDE\nachman"
DATA = os.path.join(BASE, "data")
PARTS = os.path.join(DATA, "corpus_parts.json")
FULL = os.path.join(BASE, "corpus_full.txt")
SLEEP = 0.25
LINK_CAP = 400

ROOTS = ["Likutei Moharan", "Likutei Halakhot", "Sippurei Maasiyot",
         "Sippurei Maasiot", "Likutei Tefilot"]


def get(path):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.load(r)


def flat_text(v):
    if isinstance(v, list):
        out = []
        for x in v:
            out.append(flat_text(x))
        return " ".join(t for t in out if t)
    return v if isinstance(v, str) else ""


def text_of(ref):
    try:
        d = get("/texts/%s?context=0&commentary=0"
                % urllib.parse.quote(ref))
    except Exception as e:
        return "", "", "err:%s" % str(e)[:60]
    return flat_text(d.get("he", "")), flat_text(d.get("text", "")), ""


def walk_nodes(node, prefix, out):
    """Collect leaf refs from an index schema."""
    if not isinstance(node, dict):
        return
    if node.get("type") in ("Talmud",) or "nodes" in node:
        for ch in node.get("nodes", []):
            key = ch.get("key", "")
            walk_nodes(ch, prefix + ", " + key if prefix else key, out)
        return
    title = node.get("title") or prefix
    if title and node.get("type") != "Schema":
        out.append(title)
    for ch in node.get("nodes", []):
        walk_nodes(ch, title, out)


def refs_for(title):
    try:
        idx = get("/index/%s" % urllib.parse.quote(title))
    except Exception as e:
        return [], "index-err:%s" % str(e)[:80]
    refs = []
    walk_nodes(idx.get("schema", {}), title, refs)
    if not refs and idx.get("title"):
        refs = [title]
    return sorted(set(refs)), ""

def load_parts():
    if os.path.isfile(PARTS):
        try:
            return json.load(open(PARTS, encoding="utf-8"))
        except ValueError:
            pass
    return {}


def save_parts(parts):
    tmp = PARTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(parts, f, ensure_ascii=False)
    os.replace(tmp, PARTS)


def pull_ref(ref, parts, hop=0):
    if ref in parts:
        return parts[ref].get("en_len", 0)
    he, en, err = text_of(ref)
    parts[ref] = {"he_len": len(he), "en_len": len(en),
                  "err": err, "hop": hop,
                  "he": he[:200000], "en": en[:200000]}
    return len(en)


def main():
    parts = load_parts()
    print("roots: %s (have %d)" % (ROOTS, len(parts)), flush=True)
    root_refs = []
    for title in ROOTS:
        refs, err = refs_for(title)
        print("%s: %d refs %s" % (title, len(refs), err), flush=True)
        root_refs += [(r, 0) for r in refs]
        time.sleep(SLEEP)
    # pull roots first
    for i, (ref, hop) in enumerate(root_refs):
        n = pull_ref(ref, parts, hop)
        if i % 20 == 0:
            save_parts(parts)
            print("roots %d/%d ..." % (i, len(root_refs)), flush=True)
        time.sleep(SLEEP)
    save_parts(parts)
    # one hop along links into cited sources
    linked = {}
    for ref in list(parts):
        if parts[ref].get("hop", 0) != 0:
            continue
        slug = ref.replace(" ", "_")
        try:
            links = get("/links/%s?with_text=0"
                        % urllib.parse.quote(slug))
        except Exception:
            continue
        for l in links:
            r = l.get("ref")
            if r and r not in parts and r not in linked:
                linked[r] = l.get("category", "?")
        time.sleep(SLEEP)
    print("linked refs found: %d (cap %d)" % (len(linked), LINK_CAP),
          flush=True)
    for i, ref in enumerate(list(linked)[:LINK_CAP]):
        pull_ref(ref, parts, 1)
        if i % 25 == 0:
            save_parts(parts)
            print("links %d ..." % i, flush=True)
        time.sleep(SLEEP)
    save_parts(parts)
    # assemble: EN roots + EN links, then HE
    en = "\n\n".join(p["en"] for p in parts.values() if p.get("en"))
    he = "\n\n".join(p["he"] for p in parts.values() if p.get("he"))
    open(FULL, "w", encoding="utf-8").write(
        en + "\n\n===== HEBREW =====\n\n" + he)
    print("DONE refs=%d en=%d he=%d -> %s"
          % (len(parts), len(en), len(he), FULL), flush=True)


if __name__ == "__main__":
    main()
