#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""train_loop.py -- the whole feedback loop, one nightly run, at low priority.

    harvest -> make pairs -> judge -> train -> evaluate vs BM25 -> keep or ROLL BACK
            -> one line in the run log -> one line to RAMCHAT

THE GATE, first and hardest: the judge may steer training only while it agrees with
Iddo's frozen labelled set (judge.py --calibrate). No labels, or kappa under the bar,
and this script refuses to promote anything. --force-uncalibrated exists ONLY to smoke
test the plumbing: the run is logged as UNCALIBRATED_SMOKE and weights are NEVER
promoted no matter how good they look.

THE PROMOTION RULE: the candidate is kept only if it beats BOTH the BM25 control AND
the previous best. Anything else is written down as a loss and rolled back. Four times
already our own substrate lost to a plain control; a loop that cannot record a loss
would have hidden all four.

    python train_loop.py --dry-run
    python train_loop.py --skip-harvest --force-uncalibrated --epochs 6
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import common
import organ

HERE = Path(__file__).resolve().parent
RAMLINK = Path(r"D:\CLAUDE\RAMCHAT\ramlink.py")
AGENT = "claude-cli-OPUS-mikoteacher"


def run(cmd, why):
    print("\n=== %s ===\n$ %s" % (why, " ".join(cmd)))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, cwd=str(HERE), env=env, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode


def post_ramchat(line, enabled=True):
    if not enabled:
        print("[ramchat] skipped (--no-ramchat): %s" % line)
        return
    if not RAMLINK.exists():
        print("[ramchat] ramlink.py not found, skipped")
        return
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    subprocess.run([sys.executable, str(RAMLINK), "post", AGENT, line],
                   cwd=str(RAMLINK.parent), env=env, text=True,
                   encoding="utf-8", errors="replace")


def load_examples(judged, pages, width, shuffle_labels=False, seed=0):
    by_id = {p["page_id"]: p for p in pages}
    ex, kept = [], []
    for r in judged:
        p = by_id.get(r["cand_page_id"])
        if not p:
            continue
        feats = organ.meeting_features(
            r["question"], p["title"] + "\n" + p["text"][:4000], width)
        ex.append([feats, int(r["label"])])
        kept.append(r)
    if shuffle_labels:
        ys = [e[1] for e in ex]
        random.Random(seed + 99).shuffle(ys)
        for e, y in zip(ex, ys):
            e[1] = y
    return [(f, y) for f, y in ex], kept


def main() -> int:
    common.utf8()
    common.lower_priority()
    ap = argparse.ArgumentParser(prog="train_loop.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages-limit", type=int, default=8)
    ap.add_argument("--questions-per-page", type=int, default=3)
    ap.add_argument("--negatives", type=int, default=2)
    ap.add_argument("--judge-limit", type=int, default=40)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--skip-harvest", action="store_true")
    ap.add_argument("--skip-pairs", action="store_true")
    ap.add_argument("--skip-judge", action="store_true")
    ap.add_argument("--min-kappa", type=float, default=0.40)
    ap.add_argument("--min-acc", type=float, default=0.70)
    ap.add_argument("--force-uncalibrated", action="store_true",
                    help="smoke test only; weights can NEVER be promoted in this mode")
    ap.add_argument("--no-ramchat", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    py = sys.executable
    stages = []
    if not a.skip_harvest:
        stages.append(([py, "harvest.py", "--limit", str(a.pages_limit)], "HARVEST"))
    if not a.skip_pairs:
        stages.append(([py, "make_pairs.py", "--limit", str(a.pages_limit),
                        "--questions-per-page", str(a.questions_per_page),
                        "--negatives", str(a.negatives)], "MAKE PAIRS"))
    if not a.skip_judge:
        stages.append(([py, "judge.py", "--score", "--limit", str(a.judge_limit)], "JUDGE"))

    if a.dry_run:
        print("[dry-run] the nightly loop would run, in order:")
        for cmd, why in stages:
            print("   %-12s %s --dry-run" % (why, " ".join(cmd[1:])))
        print("   %-12s judge.py --calibrate   <-- THE GATE" % "CALIBRATE")
        print("   %-12s train the organ + a shuffled-label twin (CPU, BELOW_NORMAL)" % "TRAIN")
        print("   %-12s evaluate.py against BM25 + 3 controls" % "EVALUATE")
        print("   %-12s keep only if it beats BM25 AND the previous best, else ROLL BACK"
              % "PROMOTE")
        print("   %-12s one line to runs/runlog.jsonl and one to RAMCHAT" % "RECORD")
        for cmd, why in stages:
            run(cmd + ["--dry-run"], why + " (dry-run)")
        return 0

    for cmd, why in stages:
        rc = run(cmd, why)
        if rc != 0:
            print("stage %s failed (rc=%d) -- stopping." % (why, rc))
            common.log_run({"stage": "loop", "status": "STAGE_FAILED", "which": why})
            return rc

    # ---------------------------------------------------------------- THE GATE
    rc = run([py, "judge.py", "--calibrate", "--min-kappa", str(a.min_kappa),
              "--min-acc", str(a.min_acc)], "CALIBRATE (the gate)")
    calibrated = (rc == 0)
    if not calibrated and not a.force_uncalibrated:
        print("\nGATE CLOSED: the judge is not calibrated against Iddo. Nothing is trained.")
        print("Run: python judge.py --make-sheet 40   then let Iddo label it once.")
        common.log_run({"stage": "loop", "status": "GATE_CLOSED_NOT_CALIBRATED"})
        post_ramchat("MIKO teacher: gate CLOSED, judge not calibrated against Iddo "
                     "(no frozen labels). Nothing trained, nothing promoted.",
                     not a.no_ramchat)
        return 3

    judged = common.read_jsonl(common.DATA / "judged.jsonl")
    pages = common.read_jsonl(common.DATA / "pages.jsonl")
    if not judged:
        print("no judged pairs -- nothing to train on.")
        return 1

    print("\n=== TRAIN (CPU, BELOW_NORMAL) ===")
    ex, _ = load_examples(judged, pages, a.width, False, a.seed)
    o = organ.MikoOrgan(width=a.width, epochs=a.epochs, seed=a.seed)
    n = o.train(ex, epochs=a.epochs, seed=a.seed, verbose=True)
    cand = common.RUNS / "candidate.json"
    o.save(cand, {"presentations": n, "pairs": len(ex), "calibrated": calibrated})
    print("trained on %d pairs, %d presentations -> %s" % (len(ex), n, cand))

    print("\n=== TRAIN the shuffled-label twin (anti-gaming control) ===")
    exs, _ = load_examples(judged, pages, a.width, True, a.seed)
    os_ = organ.MikoOrgan(width=a.width, epochs=a.epochs, seed=a.seed)
    os_.train(exs, epochs=a.epochs, seed=a.seed)
    shuf = common.RUNS / "shuffled.json"
    os_.save(shuf, {"shuffled": True})
    print("shuffled twin -> %s" % shuf)

    metrics_path = common.RUNS / "metrics_candidate.json"
    rc = run([py, "evaluate.py", "--model", str(cand), "--shuffled-model", str(shuf),
              "--k", str(a.k), "--json-out", str(metrics_path)], "EVALUATE")
    if rc != 0 or not metrics_path.exists():
        print("evaluation failed -- nothing promoted.")
        return rc or 1

    res = json.loads(metrics_path.read_text(encoding="utf-8"))["results"]
    key = "ndcg@%d" % a.k
    ours = res["ALMA organ (ours)"][key]
    bm25 = res["BM25 (control, 1994)"][key]
    best_path = common.RUNS / "best.json"
    best_metrics = common.RUNS / "best_metrics.json"
    prev = None
    if best_metrics.exists():
        prev = json.loads(best_metrics.read_text(encoding="utf-8")).get(key)

    beats_bm25 = ours > bm25
    beats_prev = (prev is None) or (ours > prev)
    promote = beats_bm25 and beats_prev and calibrated

    print("\n=== PROMOTE? ===")
    print("  candidate %s : %.4f" % (key, ours))
    print("  BM25 control  : %.4f  -> %s" % (bm25, "beaten" if beats_bm25 else "NOT beaten"))
    print("  previous best : %s  -> %s"
          % (("%.4f" % prev) if prev is not None else "none",
             "beaten" if beats_prev else "NOT beaten"))
    print("  calibrated    : %s" % calibrated)
    if promote:
        best_path.write_text(cand.read_text(encoding="utf-8"), encoding="utf-8")
        best_metrics.write_text(json.dumps({key: ours, "at": common.now()}), encoding="utf-8")
        status = "PROMOTED"
        print("  -> PROMOTED. New best weights kept.")
    else:
        cand.unlink(missing_ok=True)
        status = ("UNCALIBRATED_SMOKE" if not calibrated else "LOSS_ROLLED_BACK")
        print("  -> NOT promoted (%s). Candidate weights deleted, previous best untouched."
              % status)

    rec = {"stage": "loop", "status": status, key: round(ours, 4),
           "bm25": round(bm25, 4),
           "length_only": round(res["length-only (control)"][key], 4),
           "overlap_only": round(res["overlap-only (control)"][key], 4),
           "random": round(res["random (floor)"][key], 4),
           "shuffled_twin": round(res["ALMA shuffled twin (anti-gaming)"][key], 4),
           "recall@1": round(res["ALMA organ (ours)"]["recall@1"], 4),
           "mae": round(res["ALMA organ (ours)"]["mae"], 4),
           "abstain_rate": res["ALMA organ (ours)"]["abstain_rate"],
           "pairs": len(ex), "pages": len(pages), "epochs": a.epochs,
           "width": a.width, "calibrated": calibrated}
    common.log_run(rec)
    line = ("MIKO teacher run: %s | ours %s=%.4f vs BM25 %.4f, shuffled twin %.4f, "
            "overlap-only %.4f | %d pairs, %d pages | calibrated=%s"
            % (status, key, ours, bm25, rec["shuffled_twin"], rec["overlap_only"],
               len(ex), len(pages), calibrated))
    post_ramchat(line, not a.no_ramchat)
    print("\n%s" % line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
