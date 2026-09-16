# -*- coding: utf-8 -*-
"""make_substreams.py - tokens-poly/ -> tokens-rhythm/ + tokens-pitch/.

לזכרו של לָאוֹר ז״ל.

Writes the two sub-streams in EXACTLY the JSON shape midi_data.py already
consumes, so the same loader, the same split.json and the same cache machinery
work unchanged and the ONLY thing that differs between control and treatment is
which tokens a model has to predict.

Every file is round-tripped before it is written: merge(split(x)) must equal x
token for token, and the decoded Score must be identical. A single failure
aborts the run rather than writing a corpus that is quietly wrong.

Also emits substream_stats.json: token counts per stream per lane, the
duplicated-clock overhead, and tokens per second of music for each alphabet -
the numbers the CE comparison needs in order to be admissible.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import poly_tok as PT                                              # noqa: E402
import split_tok as ST                                             # noqa: E402


def convert(rec: dict):
    joint = [int(t) for t in rec["tokens"]]
    r, p = ST.split_stream(joint)
    back = ST.merge_streams(r, p)
    if back != joint:
        k = next((i for i, (a, b) in enumerate(zip(joint, back)) if a != b), None)
        raise ValueError("round trip broke at index %s (len %d vs %d)"
                         % (k, len(joint), len(back)))
    s1 = PT.decode(joint, key_pc=rec["key_pc"]).normalised()
    s2 = PT.decode(back, key_pc=rec["key_pc"]).normalised()
    if s1.notes != s2.notes or s1.drums != s2.drums:
        raise ValueError("decoded music differs after round trip")
    return r, p


def lane_counts(toks, lane_fn):
    out = {}
    for t in toks:
        k = lane_fn(t)
        out[k] = out.get(k, 0) + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE.parent / "tokens-poly"))
    ap.add_argument("--out-rhythm", default=str(HERE.parent / "tokens-rhythm"))
    ap.add_argument("--out-pitch", default=str(HERE.parent / "tokens-pitch"))
    ap.add_argument("--stats", default=str(HERE / "substream_stats.json"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass

    os.makedirs(a.out_rhythm, exist_ok=True)
    os.makedirs(a.out_pitch, exist_ok=True)
    files = sorted(Path(a.src).glob("*.json"))
    if not files:
        print("no token files in " + a.src)
        return 1

    tot = {"joint": 0, "rhythm": 0, "pitch": 0}
    lanes = {"joint": {}, "rhythm": {}, "pitch": {}}
    seconds = 0.0
    n_ok = 0
    for f in files:
        rec = json.loads(f.read_text(encoding="utf-8"))
        r, p = convert(rec)
        for name, toks, fn in (("joint", rec["tokens"], ST.lane_of_joint),
                               ("rhythm", r, ST.lane_of_rhythm),
                               ("pitch", p, ST.lane_of_pitch)):
            tot[name] += len(toks)
            for k, v in lane_counts(toks, fn).items():
                lanes[name][k] = lanes[name].get(k, 0) + v
        seconds += rec["seconds"]

        for toks, outdir, vocab, rung in (
                (r, a.out_rhythm, ST.R_VOCAB,
                 "split-rhythm - drums + the shared STEP clock only"),
                (p, a.out_pitch, ST.P_VOCAB,
                 "split-pitch - PITCH+DUR (melody AND harmony) + the shared STEP clock")):
            sub = dict(rec)
            sub["tokens"] = toks
            sub["n_tokens"] = len(toks)
            sub["vocab"] = vocab
            sub["tokens_per_second"] = round(len(toks) / max(rec["seconds"], 1e-6), 3)
            sub["rung"] = rung
            sub["joint_n_tokens"] = rec["n_tokens"]
            (Path(outdir) / f.name).write_text(
                json.dumps(sub, ensure_ascii=False), encoding="utf-8")
        n_ok += 1
        if not a.quiet and n_ok % 50 == 0:
            print("[%d/%d] ok" % (n_ok, len(files)), flush=True)

    stats = {
        "n_files": n_ok,
        "seconds_of_music": round(seconds, 1),
        "tokens": tot,
        "lane_tokens": lanes,
        "tokens_per_second": {k: round(v / max(seconds, 1e-9), 3)
                              for k, v in tot.items()},
        "split_total_over_joint": round((tot["rhythm"] + tot["pitch"])
                                        / max(tot["joint"], 1), 4),
        "duplicated_clock_tokens": lanes["pitch"].get("struct", 0),
        "note": ("split_total_over_joint > 1 because BOS/STEP/BAR/PHRASE/EOS are "
                 "carried by BOTH streams. That duplicated clock is the price of "
                 "the factorisation and is counted in full by the total-nats "
                 "measurement in split_eval.py - never netted out."),
    }
    Path(a.stats).write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(stats, indent=1))
    print("ROUND TRIP EXACT on %d/%d files" % (n_ok, len(files)))
    return 0 if n_ok == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
