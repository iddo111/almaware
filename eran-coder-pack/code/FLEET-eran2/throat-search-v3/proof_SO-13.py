# -*- coding: utf-8 -*-
"""PROOF SO-13 -- unpruned: every improvement of a flagged arm copied wav+json into
review/ under a timestamped name and nothing ever pruned. review/ is the folder whose whole
purpose is to hold winners until IDDO'S EAR reaches them; on 2026-09-06 it held 1,536 files
(25 MB) in v3 and 416 (6.5 MB) in v4, and not one had a verdict.

    python3 proof_SO-13.py ~/throat-search-v3/run_worker.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-13.py ~/throat-search-v3/run_worker.py                    -> PASS

The functions under test are lifted OUT of the file by ast and run on a throwaway tree in
/tmp -- the real review/ folders are not touched, and run_worker itself (numpy, ear3,
mouth2, CMA) is never imported, so this costs eran2 nothing.
"""
import ast
import glob
import json
import os
import shutil
import sys
import tempfile
import time

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1
                          else "~/throat-search-v3/run_worker.py")
print("PROOF SO-13 against %s" % PATH)
src = open(PATH, encoding="utf-8").read()
tree = ast.parse(src)
want = {"prune_review", "verdicted_tags"}
picked = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
checks = []

ns = {"os": os, "glob": glob, "json": json, "shutil": shutil,
      "utcnow": lambda: time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())}
if picked:
    exec(compile(ast.Module(body=picked, type_ignores=[]), PATH, "exec"), ns)

checks.append(("the worker HAS a review pruner",
               "prune_review" in ns,
               "found %s" % sorted(n.name for n in picked)))
checks.append(("the pruner is actually called at the copy site",
               "prune_review(review_dir" in src,
               "call site present=%s" % ("prune_review(review_dir" in src)))

if "prune_review" in ns:
    tmp = tempfile.mkdtemp(prefix="proof-so13-")
    rev = os.path.join(tmp, "review")
    os.makedirs(rev)
    made = []
    for i in range(6):
        tag = "ba-cv-9-3-2026-08-30T0%d0000Z" % i
        open(os.path.join(rev, tag + ".wav"), "wb").write(b"RIFF" + bytes([i]))
        json.dump({"arm": "ba-cv-9"}, open(os.path.join(rev, tag + ".json"), "w"))
        t = time.time() - (10 - i) * 3600
        for e in (".wav", ".json"):
            os.utime(os.path.join(rev, tag + e), (t, t))
        made.append(tag)
    for i in range(2):
        tag = "ma-nasal-0-1-2026-08-27T0%d0000Z" % i
        open(os.path.join(rev, tag + ".wav"), "wb").write(b"RIFF")
        json.dump({}, open(os.path.join(rev, tag + ".json"), "w"))
    open(os.path.join(rev, "LISTENED-ba-cv-9.txt"), "w").write("murphy sat here")
    # Iddo has ruled on the OLDEST one -- it must survive
    with open(os.path.join(tmp, "verdicts.jsonl"), "w") as f:
        f.write(json.dumps({"tag": made[0], "verdict": "not ba"}) + "\n")

    before = len(os.listdir(rev))
    moved = ns["prune_review"](rev, "ba-cv-9", keep=3)
    left = sorted(os.listdir(rev))
    arch_dir = os.path.join(tmp, "review-archive")
    arch = sorted(os.listdir(arch_dir)) if os.path.isdir(arch_dir) else []

    kept_ba = [f for f in left if f.startswith("ba-cv-9-") and f.endswith(".wav")]
    # the newest 3, PLUS the one Iddo already ruled on -- a verdict outranks an mtime
    checks.append(("only the newest 3 of that arm stay in review/ (plus the ruled one)",
                   sorted(kept_ba) == sorted(x + ".wav" for x in [made[0]] + made[3:]),
                   "kept=%s" % kept_ba))
    checks.append(("Iddo's already-ruled candidate is spared",
                   made[0] + ".wav" in left, "verdicted tag still in review/=%s"
                   % (made[0] + ".wav" in left)))
    checks.append(("the rest MOVED to review-archive/, nothing deleted",
                   moved == 2 and len([a for a in arch if a.endswith(".wav")]) == 2
                   and before == len(left) + len([a for a in arch if a != "MANIFEST.jsonl"]),
                   "moved=%d archive=%s" % (moved, arch)))
    man = os.path.join(arch_dir, "MANIFEST.jsonl")
    lines = [json.loads(x) for x in open(man)] if os.path.exists(man) else []
    checks.append(("every move is written down", len(lines) == 2 and
                   all(l.get("tag") and l.get("why") for l in lines),
                   "manifest=%s" % [l.get("tag") for l in lines]))
    checks.append(("another arm is untouched",
                   len([f for f in left if f.startswith("ma-nasal-0-")]) == 4,
                   "ma files left=%d" % len([f for f in left if f.startswith("ma-nasal-0-")])))
    checks.append(("LISTENED-*.txt is never touched",
                   "LISTENED-ba-cv-9.txt" in left, "present=%s"
                   % ("LISTENED-ba-cv-9.txt" in left)))
    shutil.rmtree(tmp, ignore_errors=True)
else:
    real = os.path.join(os.path.dirname(os.path.abspath(PATH)), "review")
    n = len(os.listdir(real)) if os.path.isdir(real) else 0
    checks.append(("nothing prunes review/ (%d files sitting there right now)" % n,
                   False, "no prune_review in this file"))

ok = all(c[1] for c in checks)
for label, good, detail in checks:
    print("  [%s] %s -- %s" % ("PASS" if good else "FAIL", label, detail))
print("PROOF %s" % ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
