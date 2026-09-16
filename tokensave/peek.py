#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
peek.py -- show only what matters from a big file. Never the whole file.

No pattern: head + tail + structure (def/class/function lines for code) + stats.
With pattern: grep-like matching lines with 2 lines of context, capped.

Usage:
    python peek.py big_log.txt
    python peek.py server.py "class .*Handler"
    python peek.py huge.json --head 5 --tail 5

Options:
    --head N     head lines to show (default 12)
    --tail N     tail lines to show (default 8)
    --max N      max matches to show for a pattern (default 20)
    --context N  context lines around a pattern match (default 2)
    --help       this text
"""
import sys
import os
import re
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import lower_priority, approx_tokens, eprint

MAX_READ_BYTES = 30_000_000  # safety cap so a giant file can't stall the PC

STRUCT_RE = re.compile(
    r'^\s*(def |class |async def |function |const .*=.*(=>|\bfunction\b)'
    r'|export (default )?(function|class|const)|interface |struct |impl |'
    r'public |private |protected |fn |type \w+ ?=)'
)


def read_lines(path):
    size = os.path.getsize(path)
    truncated = False
    with open(path, "rb") as fh:
        data = fh.read(MAX_READ_BYTES)
        if len(data) < size:
            truncated = True
    text = data.decode("utf-8", "replace")
    lines = text.splitlines()
    return lines, size, truncated


def main():
    ap = argparse.ArgumentParser(prog="peek.py", description=__doc__)
    ap.add_argument("file")
    ap.add_argument("pattern", nargs="?", default=None)
    ap.add_argument("--head", type=int, default=12)
    ap.add_argument("--tail", type=int, default=8)
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--context", type=int, default=2)
    args = ap.parse_args()

    lower_priority()
    if not os.path.isfile(args.file):
        print("peek.py: no such file: %s" % args.file)
        return

    lines, size, truncated = read_lines(args.file)
    n = len(lines)
    out_lines = []
    header = "FILE: %s (%d lines, %d bytes%s)" % (
        args.file, n, size, ", truncated read" if truncated else ""
    )
    out_lines.append(header)

    if args.pattern:
        try:
            rx = re.compile(args.pattern, re.I)
        except re.error as e:
            print("peek.py: bad pattern: %s" % e)
            return
        matches = [i for i, l in enumerate(lines) if rx.search(l)]
        out_lines.append("-- matches for /%s/ (%d found, showing %d) --" % (
            args.pattern, len(matches), min(len(matches), args.max)))
        shown = set()
        for i in matches[:args.max]:
            lo = max(0, i - args.context)
            hi = min(n, i + args.context + 1)
            for j in range(lo, hi):
                if j in shown:
                    continue
                shown.add(j)
                mark = ">>" if j == i else "  "
                out_lines.append("%s%6d: %s" % (mark, j + 1, lines[j]))
            out_lines.append("--")
    else:
        out_lines.append("-- head --")
        for i in range(min(args.head, n)):
            out_lines.append("%6d: %s" % (i + 1, lines[i]))
        if n > args.head + args.tail:
            out_lines.append("... (%d lines omitted) ..." % (n - args.head - args.tail))
        out_lines.append("-- tail --")
        for i in range(max(n - args.tail, args.head), n):
            out_lines.append("%6d: %s" % (i + 1, lines[i]))
        struct = [(i, l) for i, l in enumerate(lines) if STRUCT_RE.match(l)]
        if struct:
            out_lines.append("-- structure (%d def/class/function lines) --" % len(struct))
            for i, l in struct[:60]:
                out_lines.append("%6d: %s" % (i + 1, l.strip()))

    text_out = "\n".join(out_lines)
    print(text_out)

    saved = max(0, approx_tokens("x" * size) - approx_tokens(text_out))
    print("[peek.py] file is ~%d tokens raw -> shown ~%d tokens (saved ~%d)"
          % (approx_tokens("x" * size), approx_tokens(text_out), saved))


if __name__ == "__main__":
    main()
