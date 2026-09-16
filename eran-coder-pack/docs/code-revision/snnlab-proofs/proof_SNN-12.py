"""proof_SNN-12 — run files must be pruned by code, not by hand or never.

runs/ held 45 MB in 21 files, one of them 14,946,513 bytes, and nothing ever
rotated them. This box carries Iddo's phone mic; nothing on it may grow without
a ceiling. The reports in results/ (SWEEP.json, the ERAN-vs-SNN verdicts) must
be structurally untouchable by the pruner.

Runs entirely in /tmp; the real runs/ and results/ are never touched.

  FAILS on server.py.bak-rev-20260906   PASSES on the fixed server.py
"""
import argparse
import os
import shutil
import sys
import tempfile
import time

from _proofcommon import HERE, load, verdict

REPORTS = ["SWEEP.json", "HELDOUT-TEMPORAL.json",
           "ERAN-vs-SNN-2026-08-21.json", "ERAN-WIDTH-2026-08-21.json",
           "ERAN-vs-SNN-VERDICT-2026-08-21.md", "mnist-real.json"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "server.py"))
    a = ap.parse_args()
    mod = load(a.src, "server_under_test")

    prune = getattr(mod, "prune_runs", None)
    if prune is None:
        print("server.py has no pruning at all: 21 files / 45 MB today, and "
              "the only limit is the disk")
        return verdict(False, "unbounded growth on the box that carries the mic")

    tmp = tempfile.mkdtemp(prefix="proof_snn12_")
    try:
        runs, results = os.path.join(tmp, "runs"), os.path.join(tmp, "results")
        os.makedirs(runs)
        os.makedirs(results)
        now = time.time()
        for i in range(30):
            rid = f"syllables-20260821-{200000 + i:06d}"
            for d, ext in ((runs, ".jsonl"), (results, ".json")):
                p = os.path.join(d, rid + ext)
                with open(p, "w", encoding="utf-8") as f:
                    f.write('{"ev":"log","msg":"x"}\n' * 500)
                os.utime(p, (now - (30 - i) * 60, now - (30 - i) * 60))
        for r in REPORTS:
            with open(os.path.join(results, r), "w", encoding="utf-8") as f:
                f.write("{}")
        newest = "syllables-20260821-200029"
        before = len(os.listdir(runs)), len(os.listdir(results))

        done = prune(runs, results, keep_events=15, keep_results=20,
                     gzip_after=3, protect=(newest,))

        left_runs = sorted(os.listdir(runs))
        left_res = sorted(os.listdir(results))
        gz = [f for f in left_runs if f.endswith(".gz")]
        reports_left = [r for r in REPORTS if r in left_res]
        print(f"before: {before[0]} run files, {before[1]} results "
              f"(incl {len(REPORTS)} reports)")
        print(f"after:  {len(left_runs)} run files ({len(gz)} gzipped), "
              f"{len(left_res)} results")
        print(f"reports still present: {len(reports_left)}/{len(REPORTS)}")
        print(f"newest run protected: {newest + '.jsonl' in left_runs}")

        # 30 run files, one protected (the run about to start) -> 29 candidates:
        # the newest 15 survive (3 of them uncompressed, 12 gzipped), 14 go.
        # results/: 29 candidates -> 20 survive, 9 go, all 6 reports untouched.
        ok = (len(left_runs) == 16 and len(gz) == 12
              and len(reports_left) == len(REPORTS)
              and newest + ".jsonl" in left_runs
              and len(left_res) == 21 + len(REPORTS)
              and len(done["deleted"]) == 23)
        return verdict(ok, "old runs are pruned by count; reports and the live "
                           "run are never touched")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
