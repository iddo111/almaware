"""
Build D:\\CLAUDE\\voice-ant-farm\\corpus-big\\open\\  from open, multi-speaker Hebrew speech.

Sources
  fleurs_he_il : google/fleurs config he_il          CC-BY-4.0
  cv17_he      : Common Voice 17 Hebrew (fsicoli mirror)  CC0-1.0

Output: 16 kHz mono PCM16 wav, train/ and heldout/, speaker-disjoint.

Speaker-disjointness
  cv17_he      : real client_id speaker labels -> our own greedy speaker-level split.
  fleurs_he_il : NO speaker ids published. We use the dataset's native split, which
                 the FLEURS authors document as speaker-disjoint (train speakers are
                 different from dev/test speakers). fleurs train -> train,
                 fleurs dev+test -> heldout. This is an inherited guarantee, not one
                 we can verify from the metadata.
"""
import csv, io, json, os, hashlib, subprocess, sys, wave
from concurrent.futures import ThreadPoolExecutor

STAGE = r"D:\CLAUDE\voice-ant-farm\corpus-big\_staging"
OUT   = r"D:\CLAUDE\voice-ant-farm\corpus-big\open"
EXT   = os.path.join(STAGE, "ext")

TRAIN_SHARE = 0.80


def ffmpeg_to_pcm16(src, dst):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", src,
         "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
         "-c:a", "pcm_s16le", dst],
        check=True, stdin=subprocess.DEVNULL,
    )


def wav_stats(path):
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1, path
        assert w.getframerate() == 16000, path
        assert w.getsampwidth() == 2, path
        n = w.getnframes()
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return n / 16000.0, h.hexdigest()


# ---------------------------------------------------------------- collect items
# item: dict(dataset, licence, speaker_id, gender, src, split_hint, source_id)
items = []

# ---- FLEURS ------------------------------------------------------------------
FL_TSV = os.path.join(STAGE, "fleurs_he_il", "data", "he_il")
for tsv, subdir, hint in [("train.tsv", "train", "train"),
                          ("dev.tsv", "dev", "heldout"),
                          ("test.tsv", "test", "heldout")]:
    claimed = set()
    with io.open(os.path.join(FL_TSV, tsv), encoding="utf-8") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            # Rows are 7 cols normally, 6 when char_transcription is absent.
            # Read positionally from both ends so both shapes parse.
            if len(row) < 6:
                continue
            r = {"filename": row[1], "gender": row[-1]}
            src = os.path.join(EXT, "fleurs", subdir, r["filename"])
            if not os.path.exists(src) or r["filename"] in claimed:
                continue
            claimed.add(r["filename"])
            items.append(dict(
                dataset="fleurs_he_il", licence="CC-BY-4.0",
                # No speaker ids in FLEURS. Encode the disjoint pool it came from
                # so the manifest never implies we know the individual talker.
                speaker_id=f"fleurs_pool_{ 'train' if hint=='train' else 'devtest' }",
                speaker_id_known=False,
                gender=(r["gender"] or "").lower() or None,
                src=src, split_hint=hint,
                source_id=f"fleurs/{subdir}/{r['filename']}",
            ))
    # Safety net: any audio present on disk but absent from the TSV still belongs
    # to this split's speaker pool. Keep it; we need sound, not transcripts.
    for fn in sorted(os.listdir(os.path.join(EXT, "fleurs", subdir))):
        if not fn.endswith(".wav") or fn in claimed:
            continue
        items.append(dict(
            dataset="fleurs_he_il", licence="CC-BY-4.0",
            speaker_id=f"fleurs_pool_{ 'train' if hint=='train' else 'devtest' }",
            speaker_id_known=False, gender=None,
            src=os.path.join(EXT, "fleurs", subdir, fn), split_hint=hint,
            source_id=f"fleurs/{subdir}/{fn}",
        ))

# ---- Common Voice ------------------------------------------------------------
CV_TSV = os.path.join(STAGE, "cv17_he", "transcript", "he")
cv_dirs = {"train": "he_train_0", "dev": "he_dev_0",
           "test": "he_test_0", "other": "he_other_0"}
seen_clip = set()
for split, subdir in cv_dirs.items():
    with io.open(os.path.join(CV_TSV, f"{split}.tsv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            clip = r["path"]
            if clip in seen_clip:
                continue
            src = os.path.join(EXT, "cv", subdir, clip)
            if not os.path.exists(src):
                continue
            seen_clip.add(clip)
            items.append(dict(
                dataset="cv17_he", licence="CC0-1.0",
                speaker_id="cv_" + r["client_id"][:16],
                speaker_id_known=True,
                gender=(r.get("gender") or "").lower() or None,
                src=src, split_hint=None,
                source_id=f"cv17/{split}/{clip}",
                cv_validated=(split in ("train", "dev", "test")),
            ))

print(f"collected {len(items)} source clips", flush=True)

# ------------------------------------------------- speaker-disjoint split (CV)
# Greedy: heaviest speaker first, assign to whichever side is furthest below quota.
cv_items = [i for i in items if i["dataset"] == "cv17_he"]
by_spk = {}
for i in cv_items:
    by_spk.setdefault(i["speaker_id"], []).append(i)
# proxy weight = file size (duration unknown pre-decode, size is monotone enough)
weight = {s: sum(os.path.getsize(x["src"]) for x in v) for s, v in by_spk.items()}
total_w = sum(weight.values())
assign, got = {}, {"train": 0.0, "heldout": 0.0}
for spk in sorted(weight, key=lambda s: -weight[s]):
    deficit_tr = TRAIN_SHARE * total_w - got["train"]
    deficit_ho = (1 - TRAIN_SHARE) * total_w - got["heldout"]
    side = "train" if deficit_tr >= deficit_ho else "heldout"
    assign[spk] = side
    got[side] += weight[spk]
for i in cv_items:
    i["split_hint"] = assign[i["speaker_id"]]

print("CV speakers: %d  -> train %d / heldout %d" % (
    len(assign),
    sum(1 for v in assign.values() if v == "train"),
    sum(1 for v in assign.values() if v == "heldout")), flush=True)

# --------------------------------------------------------------- convert + write
for sp in ("train", "heldout"):
    os.makedirs(os.path.join(OUT, sp), exist_ok=True)

counters = {}
def dest_for(it):
    sp = it["split_hint"]
    k = (sp, it["dataset"])
    n = counters.get(k, 0)
    counters[k] = n + 1
    return os.path.join(OUT, sp, f"{it['dataset']}_{n:06d}.wav")

for it in items:
    it["dst"] = dest_for(it)

fails = []
def work(it):
    try:
        ffmpeg_to_pcm16(it["src"], it["dst"])
        d, sha = wav_stats(it["dst"])
        it["duration_s"], it["sha256"] = round(d, 4), sha
        return True
    except Exception as e:
        fails.append((it["source_id"], repr(e)[:160]))
        return False

with ThreadPoolExecutor(max_workers=8) as ex:
    done = 0
    for ok in ex.map(work, items):
        done += 1
        if done % 500 == 0:
            print(f"  converted {done}/{len(items)}", flush=True)

good = [i for i in items if "sha256" in i]
print(f"converted OK: {len(good)}  failed: {len(fails)}", flush=True)
for f in fails[:10]:
    print("  FAIL", f, flush=True)

# --------------------------------------------------------------------- manifest
records = []
for i in good:
    records.append(dict(
        path=os.path.relpath(i["dst"], OUT).replace("\\", "/"),
        split=i["split_hint"],
        dataset=i["dataset"],
        licence=i["licence"],
        speaker_id=i["speaker_id"],
        speaker_id_known=i["speaker_id_known"],
        gender=i["gender"],
        duration_s=i["duration_s"],
        sha256=i["sha256"],
        sample_rate=16000, channels=1, encoding="PCM16",
        source_id=i["source_id"],
        cv_validated=i.get("cv_validated"),
    ))

def summarise(recs):
    out = {}
    for sp in ("train", "heldout"):
        s = [r for r in recs if r["split"] == sp]
        out[sp] = dict(
            clips=len(s),
            hours=round(sum(r["duration_s"] for r in s) / 3600, 4),
            speakers_labelled=sorted({r["speaker_id"] for r in s if r["speaker_id_known"]}),
            pools_unlabelled=sorted({r["speaker_id"] for r in s if not r["speaker_id_known"]}),
        )
    return out

summary = summarise(records)
tr_spk = set(summary["train"]["speakers_labelled"])
ho_spk = set(summary["heldout"]["speakers_labelled"])
tr_pool = set(summary["train"]["pools_unlabelled"])
ho_pool = set(summary["heldout"]["pools_unlabelled"])
leak = (tr_spk & ho_spk) | (tr_pool & ho_pool)

manifest = dict(
    created="2026-08-06",
    format=dict(sample_rate=16000, channels=1, encoding="PCM16"),
    sources=[
        dict(dataset="fleurs_he_il", hf_repo="google/fleurs", config="he_il",
             licence="CC-BY-4.0",
             attribution="Google FLEURS (Conneau et al., 2022), CC-BY-4.0",
             speaker_ids_available=False,
             split_basis="native FLEURS split; authors document train speakers as "
                         "disjoint from dev/test speakers"),
        dict(dataset="cv17_he", hf_repo="fsicoli/common_voice_17_0", config="he",
             licence="CC0-1.0",
             attribution="Mozilla Common Voice 17.0 Hebrew, CC0-1.0 public domain",
             speaker_ids_available=True,
             split_basis="own greedy speaker-level split on client_id, ~80/20 by size"),
    ],
    totals=dict(
        clips=len(records),
        hours=round(sum(r["duration_s"] for r in records) / 3600, 4),
        distinct_labelled_speakers=len({r["speaker_id"] for r in records if r["speaker_id_known"]}),
    ),
    splits=summary,
    speaker_leakage_train_heldout=sorted(leak),
    conversion="ffmpeg -ac 1 -ar 16000 -sample_fmt s16 -c:a pcm_s16le (no gain/VAD applied)",
    failures=fails,
    clips=records,
)

with io.open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2)

print(json.dumps({k: manifest[k] for k in
                  ("totals", "speaker_leakage_train_heldout")}, indent=2), flush=True)
for sp in ("train", "heldout"):
    s = summary[sp]
    print(f"{sp:8s} clips={s['clips']:6d} hours={s['hours']:.2f} "
          f"labelled_speakers={len(s['speakers_labelled'])} pools={s['pools_unlabelled']}", flush=True)
print("WROTE", os.path.join(OUT, "manifest.json"), flush=True)
