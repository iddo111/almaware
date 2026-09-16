# -*- coding: utf-8 -*-
"""KESHEV AUTOTRAIN / stage.py -- gather a training set into one shippable folder.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

Takes gold_pairs.jsonl (whose `wav` is a bare filename in keshev-next/segments)
and produces a self-contained directory:

    <stage>/manifest.jsonl      wav (relative), text, truth, source
    <stage>/wav/<name>.wav      the audio itself

so the whole thing can be copied to a fleet box and trained on with no path
surgery on the far side. Only HIS OWN recordings move, and only to HIS OWN
machines.
"""
from __future__ import annotations
import argparse, io, json, os, shutil, sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SEGDIR = r"D:\CLAUDE\keshev-next\segments"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=r"D:\CLAUDE\keshev-autotrain\data\gold_pairs.jsonl")
    ap.add_argument("--stage", default=r"D:\CLAUDE\keshev-autotrain\stage\gold")
    ap.add_argument("--sources", default="correction,confirmed",
                    help="which label kinds to include")
    ap.add_argument("--segdir", default=SEGDIR)
    a = ap.parse_args()

    want = set(s.strip() for s in a.sources.split(",") if s.strip())
    wavdir = os.path.join(a.stage, "wav")
    os.makedirs(wavdir, exist_ok=True)

    n, miss, by_src = 0, 0, {}
    with io.open(a.pairs, encoding="utf-8") as fh, \
         io.open(os.path.join(a.stage, "manifest.jsonl"), "w", encoding="utf-8") as out:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            src = d.get("source", "asr")
            if src not in want:
                continue
            name = os.path.basename(d["wav"])
            src_path = os.path.join(a.segdir, name)
            if not os.path.exists(src_path):
                miss += 1
                continue
            dst = os.path.join(wavdir, name)
            if not os.path.exists(dst):
                shutil.copy2(src_path, dst)
            out.write(json.dumps({"wav": "wav/" + name,
                                  "text": d.get("text", ""),
                                  "truth": d.get("truth") or d.get("text", ""),
                                  "source": src,
                                  "sim": d.get("sim")}, ensure_ascii=False) + "\n")
            by_src[src] = by_src.get(src, 0) + 1
            n += 1

    print("[stage] staged %d utterances -> %s" % (n, a.stage))
    for k, v in sorted(by_src.items()):
        print("[stage]   %-12s %d" % (k, v))
    if miss:
        print("[stage]   %d wav files no longer on disk (skipped, not invented)" % miss)
    return 0


if __name__ == "__main__":
    sys.exit(main())
