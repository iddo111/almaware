"""alma-mic / training / relabel_teacher.py — a STRONGER model rewrites the answer key.

THE POINT (why this is the whole game)
  The first fine-tune failed the gate for one honest reason: every training label was
  written by whisper-large-v3-TURBO - the same model we were teaching. Training a model
  on its own transcripts is studying from an answer key you wrote yourself: you practise
  your own habits, mistakes included, and cannot learn anything new.

  This fixes that at the source. A STRONGER teacher - whisper-large-v3 (the FULL model,
  not the distilled turbo; more decoder layers, measurably better on hard/accented audio)
  - re-transcribes every clip. Where the teacher is confident and disagrees with the old
  label, the teacher's transcript becomes the new training target. Now the student learns
  from a better teacher, not from itself. THAT can actually beat the gate.

HONEST LIMITS (no overselling)
  - large-v3 is better than turbo but is still a Whisper - it is not ground truth. Some of
    its "corrections" will be wrong. We keep the old label when the teacher's own
    confidence is low, so a shaky teacher guess never overwrites a decent label.
  - The real gold standard is still Iddo hand-correcting a few hundred clips. This is the
    best we can do WITHOUT his time - a strong step, not a magic one.

  python relabel_teacher.py                    # relabel train.jsonl -> train_teacher.jsonl
  python relabel_teacher.py --teacher Systran/faster-whisper-large-v3

Runs CTranslate2 (not torch) - allowed on the PC. Uses the GPU.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
CORPUS = os.path.join(APP, "voice_corpus")
DATASET = os.path.join(HERE, "dataset")

sys.path.insert(0, HERE)
from evaluate import normalise, edits        # reuse the same scoring


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default="Systran/faster-whisper-large-v3",
                    help="the STRONGER model; full large-v3, not turbo")
    ap.add_argument("--split", default="train.jsonl")
    ap.add_argument("--out", default="train_teacher.jsonl")
    ap.add_argument("--min-teacher-conf", type=float, default=-0.55,
                    help="avg-logprob floor; below this the teacher is too unsure to trust")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    sys.path.insert(0, APP)
    try:
        from stt import _enable_cuda_dlls
        _enable_cuda_dlls()
    except Exception:
        pass
    from faster_whisper import WhisperModel

    rows = [json.loads(l) for l in open(os.path.join(DATASET, a.split), encoding="utf-8") if l.strip()]
    if a.limit:
        rows = rows[:a.limit]
    print("ALMA-MIC  TEACHER RELABEL")
    print("=" * 64)
    print("teacher : %s" % a.teacher)
    print("clips   : %d" % len(rows))
    print("-" * 64)

    m = WhisperModel(a.teacher, device="cuda", compute_type="float16")

    kept_old = replaced = skipped_lowconf = 0
    out_rows = []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        wav = os.path.join(CORPUS, r["wav"])
        if not os.path.exists(wav):
            continue
        segs, _info = m.transcribe(wav, beam_size=5, temperature=0.0,
                                   language=r.get("lang") or None,
                                   condition_on_previous_text=False)
        segs = list(segs)
        teacher_text = " ".join(s.text for s in segs).strip()
        dur = sum((s.end - s.start) for s in segs) or 1.0
        conf = sum(getattr(s, "avg_logprob", -9.9) * (s.end - s.start) for s in segs) / dur

        old = (r.get("text") or "").strip()
        row = dict(r)
        if not teacher_text or conf < a.min_teacher_conf:
            row["text"] = old                      # teacher unsure -> keep the old label
            row["label_src"] = "student"
            skipped_lowconf += 1 if teacher_text else 0
            kept_old += 1
        else:
            # measure how much the teacher changed it (for the report)
            wr = edits(normalise(old).split(), normalise(teacher_text).split())
            if wr == 0:
                row["text"] = old
                row["label_src"] = "agree"
                kept_old += 1
            else:
                row["text"] = teacher_text
                row["label_src"] = "teacher"
                row["teacher_conf"] = round(conf, 3)
                replaced += 1
        out_rows.append(row)
        if i % 200 == 0:
            print("  %4d/%d  replaced=%d kept=%d  (%.0fs)"
                  % (i, len(rows), replaced, kept_old, time.time() - t0), flush=True)

    outp = os.path.join(DATASET, a.out)
    with open(outp, "w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("-" * 64)
    print("DONE  %d clips in %.0f min" % (len(out_rows), (time.time() - t0) / 60))
    print("  teacher REPLACED the label : %d  (%.0f%%)"
          % (replaced, 100 * replaced / max(len(out_rows), 1)))
    print("  teacher AGREED / kept old  : %d" % kept_old)
    print("  teacher too unsure, skipped: %d" % skipped_lowconf)
    print("  wrote %s" % os.path.relpath(outp, APP))
    print()
    print("NEXT: train on this file instead of train.jsonl:")
    print("  (on the DGX)  python train_full.py --data dataset --out runs/teacher-run \\")
    print("                (point the trainer at train_teacher.jsonl)")
    print("Then convert -> evaluate -> promote.py. The gate still decides. This just gives")
    print("it a challenger that learned from a better teacher instead of from itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
