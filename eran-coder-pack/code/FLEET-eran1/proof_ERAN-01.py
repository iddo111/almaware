#!/usr/bin/env python3
"""proof_ERAN-01.py -- the boot scan of metrics.jsonl must be BOUNDED.

Defect: eran_life._last_metrics_beat (and proof/measure._latest_metrics) walked
and json-parsed EVERY line of state/metrics.jsonl. That file is one line per
beat and had reached 54.97 GB (~296M lines), growing 3.47 GB/day -- 8.3 minutes
of parsing at wake, and deploy/nanny.sh restarted eranb-life whenever the
metrics file was older than 900 s. Once the scan outgrew 15 minutes, every
restart would be killed mid-boot and restarted forever.

This tests the CODE, not the living process: the two functions are lifted out
of their files by source segment and run against a synthetic metrics file.
Nothing from the organism is imported (no numpy, no ears, no brain), nothing on
eran1 is restarted, and the real state/ is never touched.

    python3 proof_ERAN-01.py                 # the files as they are now
    python3 proof_ERAN-01.py --bak           # the .bak-rev-20260906 backups
"""
import ast
import io
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LINES = 215000                 # ~40 MB at 186 B/line -- the real line width
BYTE_BUDGET = 2 * 1024 * 1024  # a bounded reader may not read more than this
TIME_BUDGET = 0.10             # seconds


# ------------------------------------------------------------ source surgery
def _seg(path, dotted):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    def find(body, want):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == want:
                return n
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == want:
                        return n
        return None

    node, body = None, tree.body
    for part in dotted.split("."):
        node = find(body, part)
        if node is None:
            return None
        body = getattr(node, "body", [])
    return textwrap.dedent(ast.get_source_segment(src, node) or "")


def grab(path, dotted, glb):
    seg = _seg(path, dotted)
    if seg is None:
        return None, dict(glb)
    g = dict(glb)
    exec(compile(seg, "%s::%s" % (os.path.basename(path), dotted), "exec"), g)
    return g[dotted.split(".")[-1]], g


# ------------------------------------------------------- a counting open()
class _Counting(object):
    def __init__(self, f, ctr):
        self._f, self._ctr = f, ctr

    def read(self, *a):
        d = self._f.read(*a)
        self._ctr[0] += len(d)
        return d

    def readline(self, *a):
        d = self._f.readline(*a)
        self._ctr[0] += len(d)
        return d

    def __iter__(self):
        for line in self._f:
            self._ctr[0] += len(line)
            yield line

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return self._f.__exit__(*a)

    def __getattr__(self, n):
        return getattr(self._f, n)


def counting_open(ctr):
    def _open(path, mode="r", *a, **kw):
        return _Counting(io.open(path, mode, *a, **kw), ctr)
    return _open


# --------------------------------------------------------------- the fixture
def build(dirpath):
    p = os.path.join(dirpath, "metrics.jsonl")
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        for i in range(1, LINES + 1):
            f.write(json.dumps({
                "ts": "2026-09-06T17:00:00", "beat": i, "protos": 60,
                "mass": 93000.0, "layers": 1, "layer_protos": [60],
                "E": 0.0, "unit": "la", "da": 0.0, "ne": 0.0, "ach": 1.0,
                "sht": 0.5, "oxt": 0.2, "surprise": 0.0661}) + "\n")
    return p, LINES


def run_one(name, fn, path, expect, results):
    ctr = [0]
    g = fn.__globals__
    g["open"] = counting_open(ctr)
    t0 = time.time()
    got = fn(path) if name == "beat" else fn()
    dt = time.time() - t0
    got_beat = got if name == "beat" else got.get("beat")
    ok_val = (got_beat == expect)
    ok_bytes = ctr[0] <= BYTE_BUDGET
    ok_time = dt <= TIME_BUDGET
    print("  %-18s beat=%s (want %s) %-4s | read %8.2f MB %-4s | %6.3f s %s"
          % (name, got_beat, expect, "OK" if ok_val else "BAD",
             ctr[0] / 1048576.0, "OK" if ok_bytes else "BAD",
             dt, "OK" if ok_time else "BAD"))
    results.append(ok_val and ok_bytes and ok_time)


def main():
    bak = "--bak" in sys.argv
    suf = ".bak-rev-20260906" if bak else ""
    life = os.path.join(HERE, "eran_life.py") + suf
    meas = os.path.join(HERE, "proof", "measure.py") + suf
    print("proof ERAN-01 -- bounded boot scan of metrics.jsonl")
    print("  eran_life : %s" % life)
    print("  measure   : %s" % meas)
    for p in (life, meas):
        if not os.path.exists(p):
            print("FAIL: missing %s" % p)
            return 1

    tmp = tempfile.mkdtemp(prefix="proof-eran01-")
    try:
        path, n = build(tmp)
        print("  fixture   : %s (%d lines, %.1f MB)"
              % (path, n, os.path.getsize(path) / 1048576.0))
        results = []

        f_beat, _ = grab(life, "_last_metrics_beat",
                         {"os": os, "json": json})
        if f_beat is None:
            print("  _last_metrics_beat: NOT FOUND")
            results.append(False)
        else:
            run_one("beat", f_beat, path, n, results)

        genome_stub = type("G", (), {"METRICS_FILE": path})
        f_lat, _ = grab(meas, "_latest_metrics",
                        {"os": os, "json": json, "genome": genome_stub})
        if f_lat is None:
            print("  _latest_metrics   : NOT FOUND")
            results.append(False)
        else:
            run_one("latest_metrics", f_lat, path, n, results)

        ok = all(results) and len(results) == 2
        print("RESULT: %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
