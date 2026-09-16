#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sum.py -- summarise big files/folders WITHOUT sending them through Claude.

Ships the content to Iddo's own resident fleet models (dgx4 coder / eran2
gpt-oss-120b, OpenAI-compatible endpoints) instead. Free: his hardware.
Chunks large input, summarises each chunk, returns under 30 lines.

Usage:
    python sum.py big_module.py
    python sum.py D:\\CLAUDE\\some_project\\

Options:
    --max-files N    cap files scanned in a folder (default 10)
    --max-chunks N   cap chunks summarised per file (default 3)
    --chunk-chars N  chunk size in characters (default 5000)
    --help           this text
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import lower_priority, approx_tokens, call_fleet, eprint

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             ".worktrees", ".superpowers", "dist", "build"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".exe", ".dll", ".db",
              ".pyc", ".zip", ".7z", ".ico", ".mp3", ".mp4", ".wav", ".bin",
              ".stl", ".onnx", ".pt", ".bak"}

SYS_PROMPT = ("Summarize the given text in 1-2 terse bullet points. "
              "No preamble, no restating the request, just the bullets.")


def looks_binary(chunk_bytes):
    return b"\x00" in chunk_bytes[:2000]


def gather_files(path, max_files):
    if os.path.isfile(path):
        return [path]
    files = []
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            ext = os.path.splitext(n)[1].lower()
            if ext in BINARY_EXT:
                continue
            files.append(os.path.join(root, n))
            if len(files) >= max_files:
                return files
    return files


def read_capped(path, cap):
    try:
        with open(path, "rb") as fh:
            data = fh.read(cap)
        if looks_binary(data):
            return None, os.path.getsize(path)
        return data.decode("utf-8", "replace"), os.path.getsize(path)
    except Exception:
        return None, 0


def main():
    ap = argparse.ArgumentParser(prog="sum.py", description=__doc__)
    ap.add_argument("path")
    ap.add_argument("--max-files", type=int, default=10)
    ap.add_argument("--max-chunks", type=int, default=3)
    ap.add_argument("--chunk-chars", type=int, default=5000)
    args = ap.parse_args()

    lower_priority()
    if not os.path.exists(args.path):
        print("sum.py: no such path: %s" % args.path)
        return

    files = gather_files(args.path, args.max_files)
    if not files:
        print("sum.py: nothing summarisable found under %s" % args.path)
        return

    is_single = os.path.isfile(args.path)
    raw_chars_total = 0
    bullets = []
    fleet_used = None

    for fp in files:
        text, size = read_capped(fp, args.chunk_chars * args.max_chunks)
        raw_chars_total += size
        if text is None:
            continue
        chunks = [text[i:i + args.chunk_chars]
                  for i in range(0, len(text), args.chunk_chars)][:args.max_chunks]
        rel = fp if is_single else os.path.relpath(fp, args.path)
        for ci, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            try:
                name, model, content = call_fleet(
                    [{"role": "system", "content": SYS_PROMPT},
                     {"role": "user", "content": chunk}],
                    max_tokens=110, temperature=0.1, timeout=90)
                fleet_used = (name, model)
            except RuntimeError as e:
                bullets.append("%s: [fleet unreachable: %s]" % (rel, e))
                continue
            tag = rel if len(chunks) == 1 else "%s [chunk %d/%d]" % (rel, ci + 1, len(chunks))
            for line in content.strip().splitlines():
                line = line.strip(" -*\t")
                if line:
                    bullets.append("%s: %s" % (tag, line))

    if not bullets:
        print("sum.py: no text content could be summarised (binary/unreadable/fleet down)")
        return

    MAX_LINES = 29
    shown = bullets[:MAX_LINES]
    header = "SUMMARY of %s (%d file(s), ~%d chars read%s)" % (
        args.path, len(files), raw_chars_total,
        "" if fleet_used is None else ", via %s/%s" % fleet_used)
    print(header)
    for b in shown:
        print("- " + b)
    if len(bullets) > MAX_LINES:
        print("... (%d more chunk-summaries omitted)" % (len(bullets) - MAX_LINES))

    out_chars = len(header) + sum(len(b) for b in shown)
    saved = max(0, approx_tokens("x" * raw_chars_total) - approx_tokens("x" * out_chars))
    print("[sum.py] ~%d raw tokens summarised on the free fleet -> ~%d shown (saved ~%d paid tokens)"
          % (approx_tokens("x" * raw_chars_total), approx_tokens("x" * out_chars), saved))


if __name__ == "__main__":
    main()
