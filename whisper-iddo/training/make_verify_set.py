"""Export a human-verification pack.

THE LIMITATION THIS EXISTS TO FIX: not one transcript on this fleet was typed by
a human. Every WER in this project is measured against a machine label, so it
reports agreement with a previous model, not accuracy. Nothing in the training
pipeline can remove that -- only a human can.

This writes N held-out clips as playable WAVs plus a CSV pre-filled with the
best model's transcription, so correcting is editing rather than typing. Roughly
250 corrected rows is enough to turn every number in the report from "agrees
with the old labeller" into "is right", and it is a job measured in an hour or
two, not days.

Clips are sampled stratified by language and duration so the resulting set can
report he/en separately.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as ev  # noqa: E402

ROOT = os.path.expanduser("~/whisper-iddo")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="iddo_tierA")
    ap.add_argument("--n", type=int, default=250)
    ap.add_argument("--hyps", required=True, help="hyps/<tag>.<set>.jsonl from the best model")
    ap.add_argument("--out", default=os.path.join(ROOT, "verify_pack"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rows, blob = ev.load_set(args.set)
    hyps = [json.loads(l) for l in open(args.hyps, encoding="utf-8")]
    assert len(hyps) == len(rows), "hyp file does not match the eval set"

    buckets = {}
    for i, r in enumerate(rows):
        buckets.setdefault((r["lang"], r["dur"] > 4.0), []).append(i)
    rng = random.Random(args.seed)
    picked = []
    per = max(1, args.n // max(1, len(buckets)))
    for k, v in buckets.items():
        rng.shuffle(v)
        picked += v[:per]
    picked = picked[:args.n]
    rng.shuffle(picked)

    os.makedirs(os.path.join(args.out, "audio"), exist_ok=True)
    with open(os.path.join(args.out, "verify.csv"), "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "seconds", "lang_guess", "machine_transcript",
                    "CORRECTED_TRANSCRIPT_EDIT_THIS", "unusable?"])
        for rank, i in enumerate(picked):
            r = rows[i]
            name = f"{rank:04d}_{r['lang']}.wav"
            pcm = np.asarray(blob[r["off"] // 2: r["off"] // 2 + r["n"]], dtype=np.int16)
            with wave.open(os.path.join(args.out, "audio", name), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm.tobytes())
            w.writerow([name, f"{r['dur']:.2f}", r["lang"], hyps[i]["hyp"],
                        hyps[i]["hyp"], ""])

    print(f"wrote {len(picked)} clips to {args.out}")
    print("Correct column E where it is wrong; mark column F if the clip is not "
          "speech. Anything left untouched counts as 'the machine got it right'.")


if __name__ == "__main__":
    main()
