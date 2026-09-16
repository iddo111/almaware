#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""loop.py -- THE WIRING. What happens every time training writes a sample.

Iddo, 2026-09-12: "give the training a JUDGE, with him as a judge too, so the
training loop closes." judge.py is the judge; gate.py is him-as-a-judge-too;
this file is the loop itself -- the one thing that has to happen, in order,
every time poly_train.py (owned by claude-cli-SONNET-darwishtrain, NOT
touched by this file) checkpoints and draws a sample with poly_sample.py.

This file does NOT start, stop, or read the training process. It is a small
CLI the training loop (or a human, or a scheduled task) calls once per
sample, with whatever it already knows:

    python loop.py --sample OUT.mid --step 4000 --held-out-loss 2.137 --scale freygish
    python loop.py --sample OUT.wav --step 4000 --held-out-loss 2.137 --scale freygish

WHAT ONE CALL DOES, IN ORDER
------------------------------
 1. judge.score_sample() on --sample (routed by extension: .mid/.midi -> symbolic,
    else audio).
 2. gate.current_status() -- the standing verdict from the last --calibrate
    run (STEERING or BENCHED). This file never re-runs calibration itself;
    that is gate.py's job, called separately whenever new ratings exist (see
    --reconcile below), so a training loop calling this every few minutes
    does not hammer the gate.
 3. Queues the sample for Iddo to rate, WITHOUT telling him which checkpoint
    made it: a MIDI sample is rendered to a short audible preview with this
    file's own tiny sine synth (NOT psy_synth.py, NOT modes.py's preview synth
    -- a third, independent renderer, so this slice never touches the files
    the voices/mode slices own); a .wav/.mp3 sample is queued as-is. Either
    way, one PENDING row is appended to darwish_ratings.csv (the same ledger
    taste_server.py already serves) with a neutral, rotating Hebrew label
    ("קטע לאימון #N") -- the real step number and file only ever live in
    queue_mapping.jsonl, which taste_server.py's allow-listed do_GET never
    serves.
 4. Appends ONE line to runs/run_log.jsonl: step, held-out loss, judge score
    (+ components), gate status, and his verdict IF he has already rated this
    exact sample (normally null -- it was just queued this second).

--reconcile walks run_log.jsonl for rows still missing his verdict, checks
whether darwish_ratings.csv has since gained a rating for that queued file
(matched through queue_mapping.jsonl), and fills it in. Run this after he has
tapped some ratings -- e.g. after Sukkot -- and run_log.jsonl becomes a
complete answer to "did it get better": step, loss, judge, him, side by side.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import struct
import sys
import time
import wave
from pathlib import Path

import common
import gate
import judge

QUEUE_LABEL_PREFIX = "קטע לאימון"   # neutral: no step number, no checkpoint name


# --------------------------------------------------------------------- tiny preview synth

def render_midi_preview(midi_path, out_wav, max_s=45.0, sr=22050):
    """A THIRD, independent renderer -- not psy_synth.py (owned by the voices
    slice), not body/modes.py's preview synth (owned by the mode slice). Pure
    stdlib + the notes judge.py already parsed via mido: additive sine tones
    for pitched notes, a short noise burst for drums. Exists only so a
    symbolic (MIDI) training sample can be PLAYED in taste_server.py's
    <audio> tag, which cannot play raw MIDI."""
    import random
    notes, drums, bpm = judge.parse_midi(midi_path)
    end = max_s
    if notes or drums:
        end = min(max_s, max((n["onset"] + n["dur"] for n in notes), default=0.0) or max_s,
                  max((d["onset"] for d in drums), default=0.0) + 0.3 or max_s)
        end = max(end, 1.0)
    n_samples = int(end * sr) + sr
    buf = [0.0] * n_samples
    rng = random.Random(17)
    for n in notes:
        if n["onset"] > max_s:
            continue
        f = 440.0 * 2 ** ((n["pitch"] - 69) / 12.0)
        dur = min(n["dur"], 1.0)
        start = int(n["onset"] * sr)
        n_i = int(dur * sr)
        for i in range(min(n_i, n_samples - start)):
            env = math.exp(-i / (0.3 * sr)) if dur > 0.05 else math.exp(-i / (0.03 * sr))
            buf[start + i] += 0.25 * env * math.sin(2 * math.pi * f * i / sr)
    for d in drums:
        if d["onset"] > max_s:
            continue
        start = int(d["onset"] * sr)
        is_kick = d["note"] in (35, 36)
        n_i = int((0.15 if is_kick else 0.05) * sr)
        for i in range(min(n_i, n_samples - start)):
            if is_kick:
                f = 150.0 * math.exp(-i / (0.03 * sr)) + 45.0
                env = math.exp(-i / (0.05 * sr))
                buf[start + i] += 0.5 * env * math.sin(2 * math.pi * f * i / sr)
            else:
                env = math.exp(-i / (0.01 * sr))
                buf[start + i] += 0.15 * env * (rng.random() * 2 - 1)
    peak = max(1e-6, max(abs(x) for x in buf))
    scale = 0.9 / peak
    frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x * scale)) * 32767)) for x in buf)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return end


# --------------------------------------------------------------------- queueing

def _next_neutral_id():
    n = len(common.read_jsonl(common.QUEUE_MAP)) + 1
    return "%s #%d" % (QUEUE_LABEL_PREFIX, n)


def queue_for_rating(sample_path, step, extra):
    """Append one PENDING row to the SAME ledger taste_server.py reads
    (darwish_ratings.csv), with a neutral label. Never overwrites; only ever
    appends, matching taste_server.py's own append-only contract."""
    sample_path = Path(sample_path)
    playable = sample_path
    rendered_preview = None
    if sample_path.suffix.lower() in (".mid", ".midi"):
        preview_dir = common.DATA / "previews"
        preview_dir.mkdir(exist_ok=True)
        playable = preview_dir / (sample_path.stem + "-judgeloop-preview.wav")
        render_midi_preview(sample_path, playable)
        rendered_preview = str(playable)

    neutral = _next_neutral_id()
    common.RATINGS_CSV.parent.mkdir(parents=True, exist_ok=True)
    is_new = not common.RATINGS_CSV.exists()
    with open(common.RATINGS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["date", "step", "file", "iddo_pct", "note", "label"])
        w.writerow([time.strftime("%Y-%m-%d"), step, str(playable), "", "PENDING", neutral])

    common.append_jsonl(common.QUEUE_MAP, {
        "ts": common.now(), "neutral_id": neutral, "queued_file": str(playable),
        "true_sample": str(sample_path), "rendered_preview": rendered_preview,
        "step": step, **extra,
    })
    return neutral, str(playable)


# --------------------------------------------------------------------- his verdict lookup

def _his_verdict_for(playable_path):
    target = os.path.basename(playable_path).lower()
    if not common.RATINGS_CSV.exists():
        return None
    with open(common.RATINGS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pct = (row.get("iddo_pct") or "").strip()
            fname = (row.get("file") or "").strip()
            if pct in ("0", "100") and os.path.basename(fname).lower() == target:
                return "good" if pct == "100" else "bad"
    return None


# --------------------------------------------------------------------- main flow

def run_once(sample, step, held_out_loss, scale, no_queue=False) -> dict:
    sample = Path(sample)
    is_midi = sample.suffix.lower() in (".mid", ".midi")
    result = judge.score_sample(midi_path=str(sample) if is_midi else None,
                                audio_path=None if is_midi else str(sample),
                                scale=scale)
    common.append_jsonl(common.JUDGED_LOG, {
        "ts": common.now(), "label": sample.name, "file": str(sample),
        "scale": scale, "overall_score_0to100": result.get("overall_score_0to100"),
    })
    gate_status = gate.current_status()

    queued_id = queued_path = None
    if not no_queue:
        queued_id, queued_path = queue_for_rating(sample, step, {"scale": scale})

    his_verdict = _his_verdict_for(queued_path) if queued_path else None
    line = {
        "step": step, "held_out_loss": held_out_loss,
        "judge_score": result.get("overall_score_0to100"),
        "judge_components": {k: v.get("score") if isinstance(v, dict) else v
                             for k, v in result.get("components", {}).items()},
        "gate_status": gate_status.get("status"), "gate_steer_allowed": gate_status.get("steer_allowed"),
        "queued_as": queued_id, "sample": str(sample), "his_verdict": his_verdict,
    }
    common.log_run(line)
    return {"judge_result": result, "gate_status": gate_status, "run_log_line": line}


def reconcile() -> dict:
    """Walk run_log.jsonl for rows still missing his_verdict; fill in any that
    darwish_ratings.csv has since gained. Run after he rates queued samples."""
    rows = common.read_jsonl(common.RUN_LOG)
    if not rows:
        return {"updated": 0, "note": "run_log.jsonl is empty"}
    updated = 0
    out = []
    for r in rows:
        if r.get("his_verdict") is None and r.get("queued_as"):
            qmap = {m["neutral_id"]: m for m in common.read_jsonl(common.QUEUE_MAP)}
            m = qmap.get(r["queued_as"])
            if m:
                v = _his_verdict_for(m["queued_file"])
                if v is not None:
                    r = dict(r, his_verdict=v)
                    updated += 1
        out.append(r)
    if updated:
        with open(common.RUN_LOG, "w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"updated": updated, "n_rows": len(out)}


def main() -> int:
    common.utf8()
    common.lower_priority()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", default=None, help=".mid/.midi or .wav/.mp3 -- one written training sample")
    ap.add_argument("--step", type=int, default=0)
    ap.add_argument("--held-out-loss", type=float, default=None)
    ap.add_argument("--scale", default="freygish", choices=["chromatic", "minor", "freygish", "hijaz"])
    ap.add_argument("--no-queue", action="store_true", help="score only, do not add to his taste queue")
    ap.add_argument("--reconcile", action="store_true", help="fill in his verdict for already-queued samples")
    a = ap.parse_args()
    if a.reconcile:
        print(json.dumps(reconcile(), ensure_ascii=False, indent=1))
        return 0
    if not a.sample:
        ap.error("give --sample (or --reconcile)")
    out = run_once(a.sample, a.step, a.held_out_loss, a.scale, a.no_queue)
    print(json.dumps(out["run_log_line"], ensure_ascii=False, indent=1))
    print()
    print("gate: %s" % out["gate_status"].get("verdict", out["gate_status"].get("status")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
