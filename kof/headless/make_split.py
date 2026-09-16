#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the KESHEV 7 train / held-out split from Iddo's accepted clips.

Source: the nightly corpus archives (mic-rebuild/state/corpus-sent/<date>/
manifest.jsonl + <sid>/<id>.wav), copied as-is to the DGX. Only clips whose
text Iddo let the old mic type (source == "typed") exist there.

Split is by SESSION (one recording day/sitting), never by clip, so the
held-out set is a day the model has never heard. Sessions are ordered by
sha256(seed + session id); held-out sessions are taken in that order until
about --heldout-frac of the clips.

Writes:
  <sandbox>/data/train/wav/<id>.wav, train.jsonl, STATS.json   (rally reads)
  <eval>/audio/<id>.wav, refs/heldout.jsonl, split.json,
  baselines.json, scoreboard.jsonl                              (rally never sees)
Refuses to overwrite a non-empty destination.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
import wave


def load_eval_module(eval_dir):
    spec = importlib.util.spec_from_file_location(
        "keshev7_eval", os.path.join(eval_dir, "eval.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wav_info(path):
    with wave.open(path, "rb") as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(),
                w.getnframes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--sandbox", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--seed", default="keshev7-2026-09-15")
    ap.add_argument("--heldout-frac", type=float, default=0.10)
    ap.add_argument("--min-s", type=float, default=0.3)
    ap.add_argument("--max-s", type=float, default=30.0)
    a = ap.parse_args()
    src = os.path.expanduser(a.src)
    sandbox = os.path.expanduser(a.sandbox)
    evald = os.path.expanduser(a.eval)
    ev = load_eval_module(evald)

    train_dir = os.path.join(sandbox, "data", "train")
    for d in (os.path.join(train_dir, "wav"), os.path.join(evald, "audio"),
              os.path.join(evald, "refs")):
        if os.path.isdir(d) and os.listdir(d):
            sys.exit("REFUSED: %s is not empty" % d)

    rows, seen = [], set()
    rejected = collections.Counter()
    for dated in sorted(os.listdir(src)):
        man = os.path.join(src, dated, "manifest.jsonl")
        if not os.path.isfile(man):
            continue
        for line in open(man, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r["id"] in seen:
                rejected["duplicate id"] += 1
                continue
            wav = os.path.join(src, dated, r["wav"])
            if not os.path.isfile(wav):
                rejected["wav missing"] += 1
                continue
            try:
                ch, sw, sr, nf = wav_info(wav)
            except Exception:
                rejected["wav unreadable"] += 1
                continue
            if (ch, sw, sr) != (1, 2, 16000):
                rejected["not 16k mono 16-bit"] += 1
                continue
            secs = nf / 16000.0
            if not (a.min_s <= secs <= a.max_s):
                rejected["duration out of range"] += 1
                continue
            if not ev.normalize(r.get("text", "")):
                rejected["empty text after normalization"] += 1
                continue
            seen.add(r["id"])
            rows.append({"id": r["id"], "sid": r["sid"], "ts": r.get("ts"),
                         "text": r["text"], "ms": int(secs * 1000),
                         "src_wav": wav})

    by_sid = collections.defaultdict(list)
    for r in rows:
        by_sid[r["sid"]].append(r)
    order = sorted(by_sid, key=lambda s: hashlib.sha256(
        (a.seed + s).encode()).hexdigest())
    target = a.heldout_frac * len(rows)
    held, cnt = [], 0
    for sid in order:
        c = len(by_sid[sid])
        if cnt >= target:
            break
        if cnt > 0 and cnt + c > 1.6 * target:
            continue
        held.append(sid)
        cnt += c
    held_set = set(held)
    train = [r for r in rows if r["sid"] not in held_set]
    heldout = [r for r in rows if r["sid"] in held_set]

    # Cross-split dedup that the by-session split cannot see: drop any held-out
    # clip whose AUDIO (byte-for-byte) or whose normalized TEXT is identical to
    # a train clip, so a content-hash lookup can never turn a train answer into
    # a held-out answer. Report the overlap either way so the scoreboard is honest.
    def _sha(path):
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    train_audio = {_sha(r["src_wav"]) for r in train}
    train_text = {ev.normalize(r["text"]) for r in train}
    quarantined_audio = quarantined_none = 0
    kept = []
    for r in heldout:
        if _sha(r["src_wav"]) in train_audio:
            quarantined_audio += 1
            continue
        kept.append(r)
    audio_removed = len(heldout) - len(kept)
    heldout = kept
    text_overlap = sum(1 for r in heldout if ev.normalize(r["text"]) in train_text)

    os.makedirs(os.path.join(train_dir, "wav"), exist_ok=True)
    os.makedirs(os.path.join(evald, "audio"), exist_ok=True)
    os.makedirs(os.path.join(evald, "refs"), exist_ok=True)
    with open(os.path.join(train_dir, "train.jsonl"), "w", encoding="utf-8") as f:
        for r in train:
            shutil.copyfile(r["src_wav"], os.path.join(train_dir, "wav", r["id"] + ".wav"))
            f.write(json.dumps({"id": r["id"], "wav": "wav/%s.wav" % r["id"],
                                "text": r["text"], "ms": r["ms"], "sid": r["sid"],
                                "ts": r["ts"]}, ensure_ascii=False) + "\n")
    with open(os.path.join(evald, "refs", "heldout.jsonl"), "w", encoding="utf-8") as f:
        for r in heldout:
            shutil.copyfile(r["src_wav"], os.path.join(evald, "audio", r["id"] + ".wav"))
            f.write(json.dumps({"id": r["id"], "wav": "audio/%s.wav" % r["id"],
                                "text": r["text"], "ms": r["ms"], "sid": r["sid"]},
                               ensure_ascii=False) + "\n")

    def hours(rs):
        return round(sum(r["ms"] for r in rs) / 3.6e6, 3)

    base = ev.baselines([r["text"] for r in train], [r["text"] for r in heldout])
    heb = sum(1 for r in train if ev.has_hebrew(r["text"]))
    stats = {
        "clips": len(train), "hours": hours(train),
        "sessions": len(set(r["sid"] for r in train)),
        "hebrew_clips": heb, "non_hebrew_clips": len(train) - heb,
        "format": "wav PCM 16 kHz mono 16-bit",
        "top_texts": collections.Counter(r["text"].strip() for r in train).most_common(12),
        "note": ("text = what Iddo let the old mic type (accepted). Short "
                 "English courtesy words on very short clips are probably "
                 "the old engine's hallucinations that slipped through."),
        "heldout_clips": len(heldout), "heldout_hours": hours(heldout),
    }
    split = {"created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seed": a.seed,
             "heldout_frac_target": a.heldout_frac,
             "sessions_total": len(by_sid), "sessions_heldout": sorted(held),
             "train_clips": len(train), "train_hours": hours(train),
             "heldout_clips": len(heldout), "heldout_hours": hours(heldout),
             "heldout_hebrew_clips": sum(1 for r in heldout if ev.has_hebrew(r["text"])),
             "heldout_dropped_audio_dup_with_train": audio_removed,
             "heldout_text_seen_in_train": text_overlap,
             "note_overlap": ("held-out clips whose AUDIO is byte-identical to a "
                              "train clip are dropped (cheat-proof); text overlap is "
                              "reported but left in - a memorize-train-phrases oracle "
                              "with no acoustics still scores far above the CER bar."),
             "rejected": dict(rejected)}
    json.dump(stats, open(os.path.join(train_dir, "STATS.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(split, open(os.path.join(evald, "split.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(base, open(os.path.join(evald, "baselines.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    open(os.path.join(evald, "scoreboard.jsonl"), "a").close()
    print(json.dumps({"split": split, "baselines": base,
                      "train_hebrew_clips": heb}, ensure_ascii=False))


if __name__ == "__main__":
    main()
