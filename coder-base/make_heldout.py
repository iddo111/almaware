#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a DETERMINISTIC held-out set of D:\\CLAUDE code.

Hold-out rule: sha1(relpath) % 20 == 7  -> held out, NEVER trained on.
The rule is the contract. Any future training run must apply the same
filter and exclude these files, or the baseline number below is worthless.
"""
import hashlib, json, os, subprocess, sys

ROOT = r"D:\CLAUDE"
# .json/.yaml/.yml deliberately EXCLUDED: they are config and data, highly
# predictable, and 282 of the first 400 hits were .json - they would have
# dominated the token count and flattered the score. This is a CODE baseline.
EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".ps1", ".c", ".cpp", ".h",
        ".rs", ".go", ".java", ".html", ".css", ".sql"}
MIN, MAX = 400, 40000          # bytes; skip trivia and giant generated blobs

out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                     text=True, encoding="utf-8", errors="replace")
files = [f for f in out.stdout.splitlines() if os.path.splitext(f)[1].lower() in EXTS]
print(f"git-tracked code files: {len(files)}", file=sys.stderr)

held = []
for rel in files:
    h = hashlib.sha1(rel.encode("utf-8")).hexdigest()
    if int(h[:8], 16) % 20 != 7:
        continue
    p = os.path.join(ROOT, rel)
    try:
        sz = os.path.getsize(p)
        if not (MIN <= sz <= MAX):
            continue
        with open(p, "r", encoding="utf-8", errors="strict") as fh:
            txt = fh.read()
    except Exception:
        continue
    if not txt.strip():
        continue
    held.append({"path": rel.replace("\\", "/"), "ext": os.path.splitext(rel)[1].lower(),
                 "bytes": sz, "text": txt})

held.sort(key=lambda r: r["path"])
held = held[:400]
print(f"held-out files: {len(held)}  total bytes: {sum(r['bytes'] for r in held):,}",
      file=sys.stderr)
from collections import Counter
print(Counter(r["ext"] for r in held).most_common(), file=sys.stderr)

dest = sys.argv[1]
with open(dest, "w", encoding="utf-8") as f:
    for r in held:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"wrote {dest}", file=sys.stderr)
