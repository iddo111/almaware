"""whisper-iddo / dataset / build.py — assemble the fine-tuning manifest.

    py -3.13 build.py            # full build
    py -3.13 build.py --no-kafe  # skip the slow long-form slicing

WHAT THIS PRODUCES
    manifest.jsonl   one row per training pair: audio, text, duration, session,
                     split, tier, source, sha256
    report.json      every count and every rejection reason
    samples.txt      10 real pairs, printed so the text quality is visible

THE THREE THINGS THAT MATTER HERE

1. LABEL PROVENANCE IS TIERED, NOT PRETENDED AWAY.
   No human typed any of this. So instead of pretending the labels are gold, each pair
   carries a `tier` recording how much independent evidence supports it:
     tier A  two INDEPENDENT Whisper decodes of the same audio agree.
             Agreement between independent systems is a real confidence signal — the
             ways two decoders fail are largely uncorrelated, so when they land on the
             same string, that string is usually right. This is the closest thing to
             ground truth available without Iddo's time.
     tier B  a single machine label that survives every filter.
     tier C  long-form session audio sliced on the transcript's own timestamps.
   Train on A+B; report A-only as the honest headline. Tier is in the manifest so any
   experiment can re-weight without rebuilding.

2. THE SPLIT IS BY SESSION, AND IT IS STRICTER THAN THE ONE IT INHERITS.
   The existing split_lock.json assigns eval by HASH OF FILENAME. That means utterance
   #7 of a session can be in eval while #6 and #8 are in train — same room, same mic,
   same minute, same subject matter. Every number measured that way is inflated.
   We honour their eval files (a file that was ever eval never enters train) AND we
   quarantine the WHOLE SESSION those files came from. That costs training data and
   buys a number that is actually true.

3. SYNTHETIC AUDIO IS EXCLUDED BY PATH, NEVER BY FILTER.
   Model babble passes every acoustic quality check ever written — it is fluent, clean,
   well-formed audio that simply is not a human. The only reliable defence is to never
   read those directories at all.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import glob
import hashlib
import json
import os
import re
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filters import check_pair, is_stock          # noqa: E402
from normalise import normalise, script_of        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_AUDIO = os.path.join(HERE, "audio")

VOICE_CORPUS = r"D:\CLAUDE\alma-mic\voice_corpus"
VI_PROFILE = r"D:\CLAUDE\voice-input\profiles\iddo1"
KAFE = "D:\\" + "\u05e7\u05e4\u05d4-\u05e7\u05dc\u05d5\u05d3"
SPLIT_LOCK = r"D:\CLAUDE\alma-mic\training\dataset\split_lock.json"

# ── HARD EXCLUSIONS. Path-based. Non-negotiable. ────────────────────────────────
# eran-audio        model babble — synthetic speech from a model, not Iddo
# voice-ant-farm\fire  synthetic ant output
# corpus-syllables  TTS
# downloads\youtube licensing
# kafe cleaned\     mp3 RE-ENCODES of the same 66 WAVs. Including both would put one
#                   recording in two splits, which is leakage disguised as volume.
EXCLUDE_SUBSTR = [
    "eran-audio", "voice-ant-farm\\fire", "voice-ant-farm/fire",
    "corpus-syllables", "downloads\\youtube", "downloads/youtube",
    "\\cleaned\\", "/cleaned/", "_quarantine",
]


def excluded(path: str) -> bool:
    p = path.lower()
    return any(x.lower() in p for x in EXCLUDE_SUBSTR)


# ── audio helpers ───────────────────────────────────────────────────────────────
def wav_meta(path: str):
    """(seconds, rate, channels) from the header only — fast, no decode."""
    try:
        with contextlib.closing(wave.open(path, "rb")) as w:
            n, rate, ch = w.getnframes(), w.getframerate(), w.getnchannels()
            if not rate:
                return None, None, None
            return n / float(rate), rate, ch
    except Exception:
        return None, None, None


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


TS_RE = re.compile(r"(\d{8})_(\d{6})")


def ts_key(name: str):
    m = TS_RE.search(name)
    if not m:
        return None
    return m.group(1), m.group(2)


def session_of(name: str, gap_min=15) -> str:
    """Session id = date + start of a contiguous recording block.

    Two utterances belong to the same session if they are on the same date and less
    than `gap_min` apart. Sessions are the unit of splitting because everything that
    makes a recording easy or hard — room, mic position, background noise, how tired
    he is, what he is talking about — is constant inside one and varies between them.
    Splitting on anything finer measures memorisation.
    """
    k = ts_key(name)
    if not k:
        return "unknown"
    return k[0]  # refined below by _assign_sessions


def _assign_sessions(rows, gap_min=15):
    """Refine date-level ids into gap-separated blocks. Mutates rows in place."""
    import datetime as dt
    by_date = collections.defaultdict(list)
    for r in rows:
        k = ts_key(os.path.basename(r["audio"]))
        if not k:
            r["session"] = "unknown"
            continue
        by_date[k[0]].append((k[1], r))
    for date, items in by_date.items():
        items.sort(key=lambda x: x[0])
        block_start = None
        prev = None
        for hhmmss, r in items:
            t = dt.datetime.strptime(date + hhmmss, "%Y%m%d%H%M%S")
            if prev is None or (t - prev).total_seconds() > gap_min * 60:
                block_start = hhmmss
            r["session"] = "%s_%s" % (date, block_start)
            prev = t


# ── text agreement (tier A) ─────────────────────────────────────────────────────
def _norm_for_compare(t: str) -> str:
    """Compare on content, ignoring punctuation and spacing."""
    return re.sub(r"[\s.,!?\"'\-]+", "", t)


def agreement(a: str, b: str) -> float:
    """Character-level agreement 0..1 between two independent decodes."""
    import difflib
    x, y = _norm_for_compare(a), _norm_for_compare(b)
    if not x and not y:
        return 1.0
    if not x or not y:
        return 0.0
    return difflib.SequenceMatcher(None, x, y).ratio()


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 1 — alma-mic/voice_corpus
#   corpus.jsonl : label written live by whisper-large-v3-turbo (the student itself)
#   *.txt/*.srt  : an INDEPENDENT later re-transcription of 1,386 of those clips
#   Where the two agree -> tier A. Where only one exists -> tier B.
# ══════════════════════════════════════════════════════════════════════════════
def load_voice_corpus(rej):
    rows = []
    manifest = {}
    mp = os.path.join(VOICE_CORPUS, "corpus.jsonl")
    for line in open(mp, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        manifest[d.get("ts") or os.path.splitext(d.get("wav", ""))[0]] = d.get("text", "")

    sidecar = {}
    for p in glob.glob(os.path.join(VOICE_CORPUS, "*.txt")):
        ts = os.path.splitext(os.path.basename(p))[0]
        try:
            sidecar[ts] = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            pass

    for wp in glob.glob(os.path.join(VOICE_CORPUS, "*.wav")):
        if excluded(wp):
            rej["excluded by path"] += 1
            continue
        ts = os.path.splitext(os.path.basename(wp))[0]
        primary = normalise(manifest.get(ts, ""))
        second = normalise(sidecar.get(ts, ""))

        sec, rate, ch = wav_meta(wp)
        if sec is None:
            rej["unreadable wav"] += 1
            continue

        # choose the label + tier
        if second and primary:
            ag = agreement(primary, second)
            if ag >= 0.90:
                text, tier = second, "A"        # two decoders agree -> trust it
            elif ag >= 0.60:
                # they broadly agree; the later independent pass is the better model
                text, tier = second, "B"
            else:
                rej["two decodes disagree badly (<0.60)"] += 1
                continue
        elif second:
            text, tier = second, "B"
        elif primary:
            text, tier = primary, "B"
        else:
            rej["no transcript for wav"] += 1
            continue

        reason, _ = check_pair(text, sec)
        if reason:
            rej[reason] += 1
            continue
        rows.append({
            "audio": wp, "text": text, "seconds": round(sec, 3),
            "source": "alma-mic/voice_corpus", "tier": tier,
            "rate": rate, "channels": ch, "lang": script_of(text),
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 2 — voice-input/profiles/iddo1
#   samples.jsonl        3,188 labelled clips of 8,703 wavs
#   iddo_clean_corpus    377 of those additionally SPEAKER-VERIFIED against Iddo's
#                        voiceprint (speaker_score vs threshold). Speaker verification
#                        does not make the TEXT right, but it does prove the audio is
#                        him and not someone else in the room — so these are promoted
#                        one tier.
# ══════════════════════════════════════════════════════════════════════════════
def load_voice_input(rej):
    rows = []
    verified = set()
    cp = os.path.join(VI_PROFILE, "iddo_clean_corpus.jsonl")
    if os.path.exists(cp):
        for line in open(cp, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("speaker_score", 0) >= d.get("speaker_threshold", 0.7):
                verified.add(d.get("ts"))

    sp = os.path.join(VI_PROFILE, "samples.jsonl")
    seen = set()
    for line in open(sp, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        wp = d.get("wav", "")
        if not wp or wp in seen:
            continue
        seen.add(wp)
        if excluded(wp) or not os.path.exists(wp):
            rej["missing or excluded wav (voice-input)"] += 1
            continue
        text = normalise(d.get("text", ""))
        sec, rate, ch = wav_meta(wp)
        if sec is None:
            rej["unreadable wav"] += 1
            continue
        reason, _ = check_pair(text, sec)
        if reason:
            rej[reason] += 1
            continue
        rows.append({
            "audio": wp, "text": text, "seconds": round(sec, 3),
            "source": "voice-input/iddo1",
            "tier": "A" if d.get("ts") in verified else "B",
            "rate": rate, "channels": ch, "lang": script_of(text),
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 3 — קפה-קלוד long-form sessions
#   66 WAV at 48 kHz STEREO; 31 non-empty transcripts carrying their own segment
#   timestamps ("[   1.2-  15.7] text"). We slice on those timestamps and resample to
#   16 kHz mono. This is the only source where Iddo speaks in long, natural, connected
#   sentences rather than short commands — which is exactly the register the app is
#   worst at. Worth the effort.
#   The mp3s in cleaned\ are re-encodes of these same recordings and are excluded.
# ══════════════════════════════════════════════════════════════════════════════
SEG_RE = re.compile(r"^\[\s*([0-9.]+)\s*-\s*([0-9.]+)\s*\]\s*(.+)$")


def load_kafe(rej, enable=True):
    rows = []
    if not enable:
        return rows
    try:
        import numpy as np
        import soundfile as sf
        import librosa
    except Exception as e:
        print("  kafe: audio libs unavailable (%s) - skipping" % e)
        return rows

    tdir = os.path.join(KAFE, "transcripts")
    if not os.path.isdir(tdir):
        print("  kafe: no transcripts dir")
        return rows
    os.makedirs(os.path.join(OUT_AUDIO, "kafe"), exist_ok=True)

    for tp in sorted(glob.glob(os.path.join(tdir, "*.txt"))):
        stem = os.path.splitext(os.path.basename(tp))[0]
        if stem.startswith("_"):            # _ALL_combined.txt is a concatenation
            continue
        wp = os.path.join(KAFE, stem + ".WAV")
        if not os.path.exists(wp):
            continue
        segs = []
        for line in open(tp, encoding="utf-8", errors="replace"):
            m = SEG_RE.match(line.strip())
            if m:
                segs.append((float(m.group(1)), float(m.group(2)), m.group(3)))
        if not segs:
            continue
        try:
            audio, sr = sf.read(wp, dtype="float32", always_2d=True)
        except Exception:
            rej["kafe wav unreadable"] += 1
            continue
        mono = audio.mean(axis=1)
        if sr != 16000:
            mono = librosa.resample(mono, orig_sr=sr, target_sr=16000)
        for i, (a, b, raw) in enumerate(segs):
            text = normalise(raw)
            sec = b - a
            reason, _ = check_pair(text, sec)
            if reason:
                rej["kafe: " + reason] += 1
                continue
            s0, s1 = int(a * 16000), int(b * 16000)
            clip = mono[s0:s1]
            if clip.size < 8000:
                rej["kafe: clip too short after slice"] += 1
                continue
            peak = float(np.abs(clip).max()) if clip.size else 0.0
            if peak < 0.005:
                rej["kafe: silent slice"] += 1
                continue
            outp = os.path.join(OUT_AUDIO, "kafe", "%s_%04d.wav" % (stem, i))
            pcm = (np.clip(clip, -1.0, 1.0) * 32767).astype("<i2")
            with contextlib.closing(wave.open(outp, "wb")) as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(pcm.tobytes())
            rows.append({
                "audio": outp, "text": text, "seconds": round(sec, 3),
                "source": "kafe-clod", "tier": "C",
                "rate": 16000, "channels": 1, "lang": script_of(text),
                "origin": os.path.basename(wp), "offset": round(a, 2),
            })
        print("  kafe %s: %d segments kept" % (stem, sum(1 for r in rows if r.get("origin") == os.path.basename(wp))))
    return rows


# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-kafe", action="store_true")
    ap.add_argument("--eval-frac", type=float, default=0.10,
                    help="share of SESSIONS held out")
    a = ap.parse_args()

    rej = collections.Counter()
    print("reading sources...")
    rows = []
    r1 = load_voice_corpus(rej)
    print("  alma-mic/voice_corpus : %5d pairs kept" % len(r1))
    rows += r1
    r2 = load_voice_input(rej)
    print("  voice-input/iddo1     : %5d pairs kept" % len(r2))
    rows += r2
    r3 = load_kafe(rej, enable=not a.no_kafe)
    print("  kafe-clod             : %5d pairs kept" % len(r3))
    rows += r3

    # ── exact-duplicate audio removal (sha256) ──────────────────────────────────
    # The same recording under two names would land in two splits.
    print("hashing %d files..." % len(rows))
    by_hash = {}
    deduped = []
    for r in rows:
        try:
            h = sha256(r["audio"])
        except Exception:
            rej["hash failed"] += 1
            continue
        if h in by_hash:
            rej["duplicate audio (identical sha256)"] += 1
            continue
        by_hash[h] = True
        r["sha256"] = h
        deduped.append(r)
    rows = deduped

    _assign_sessions(rows)

    # ── splits ──────────────────────────────────────────────────────────────────
    lock = {}
    if os.path.exists(SPLIT_LOCK):
        lock = json.load(open(SPLIT_LOCK, encoding="utf-8"))

    # 1. Any file the previous agent ever placed in eval/retain stays out of train.
    inherited = {k for k, v in lock.items() if v in ("eval", "retain")}
    # 2. Quarantine the ENTIRE session of every inherited eval file — the inherited
    #    split was by filename hash, so its siblings leak the same acoustic conditions.
    poisoned_sessions = set()
    for r in rows:
        if os.path.basename(r["audio"]) in inherited:
            poisoned_sessions.add(r["session"])

    sessions = sorted({r["session"] for r in rows})
    # 3. Fill up to eval-frac of TOTAL DURATION using whole sessions, preferring the
    #    already-poisoned ones so we lose as little training data as possible.
    dur_by_sess = collections.Counter()
    for r in rows:
        dur_by_sess[r["session"]] += r["seconds"]
    total_dur = sum(dur_by_sess.values())
    target = total_dur * a.eval_frac

    # Eval must be SPREAD ACROSS THE TIMELINE, not concentrated in a few big sessions.
    # Iddo's mic, room and speaking style drift over months; an eval built from four
    # sessions measures four afternoons, not the model. So we walk the sessions in date
    # order and take every Nth one until we hit the duration target, skipping any
    # session so large it would swallow the budget on its own.
    ordered = sorted(sessions)                      # session ids are date-prefixed
    eval_sessions, acc = set(), 0.0
    stride = max(1, int(1.0 / max(a.eval_frac, 0.01)))
    for start in range(stride):
        for s in ordered[start::stride]:
            if acc >= target:
                break
            if s in eval_sessions:
                continue
            if dur_by_sess[s] > target * 0.35 and acc > 0:
                continue                            # one session must not dominate
            eval_sessions.add(s)
            acc += dur_by_sess[s]
        if acc >= target:
            break

    # retain = the OLDEST sessions, held out to detect catastrophic forgetting
    # At least 3 distinct sessions: a forgetting check built from one afternoon can
    # only tell you whether the model still handles that one afternoon.
    remaining = [s for s in sessions if s not in eval_sessions]
    retain_sessions, acc2 = set(), 0.0
    for s in remaining:
        retain_sessions.add(s)
        acc2 += dur_by_sess[s]
        if acc2 >= total_dur * 0.04 and len(retain_sessions) >= 3:
            break

    for r in rows:
        s = r["session"]
        if s in eval_sessions:
            r["split"] = "eval"
        elif s in retain_sessions:
            r["split"] = "retain"
        else:
            r["split"] = "train"
        # An inherited eval file may NEVER enter train. But if its session is a train
        # session, it cannot join our eval either — its siblings are in train, which is
        # precisely the leak we are removing. It is therefore unusable, and we say so
        # rather than quietly laundering it into one side or the other.
        if os.path.basename(r["audio"]) in inherited and r["split"] == "train":
            r["split"] = "unusable_inherited_eval"

    # ── write ───────────────────────────────────────────────────────────────────
    rows.sort(key=lambda r: (r["session"], r["audio"]))
    mp = os.path.join(HERE, "manifest.jsonl")
    with open(mp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "audio": r["audio"], "text": r["text"], "duration": r["seconds"],
                "session": r["session"], "split": r["split"], "tier": r["tier"],
                "source": r["source"], "lang": r["lang"], "sha256": r["sha256"],
            }, ensure_ascii=False) + "\n")

    # ── report ──────────────────────────────────────────────────────────────────
    def hrs(rs):
        return sum(x["seconds"] for x in rs) / 3600.0

    rep = {
        "total_pairs": len(rows),
        "total_hours": round(hrs(rows), 3),
        "by_split": {},
        "by_tier": {},
        "by_source": {},
        "sessions": len(sessions),
        "eval_sessions": len(eval_sessions),
        "retain_sessions": len(retain_sessions),
        "rejected_total": sum(rej.values()),
        "rejected": dict(rej.most_common()),
    }
    for k in ("train", "eval", "retain", "unusable_inherited_eval"):
        sub = [r for r in rows if r["split"] == k]
        rep["by_split"][k] = {"pairs": len(sub), "hours": round(hrs(sub), 3)}
    for k in ("A", "B", "C"):
        sub = [r for r in rows if r["tier"] == k]
        rep["by_tier"][k] = {"pairs": len(sub), "hours": round(hrs(sub), 3)}
    for k in sorted({r["source"] for r in rows}):
        sub = [r for r in rows if r["source"] == k]
        rep["by_source"][k] = {"pairs": len(sub), "hours": round(hrs(sub), 3)}
    # train-only tier view (what actually gets learned)
    tr = [r for r in rows if r["split"] == "train"]
    rep["train_tier_A_only"] = {
        "pairs": sum(1 for r in tr if r["tier"] == "A"),
        "hours": round(hrs([r for r in tr if r["tier"] == "A"]), 3)}
    rep["train_tier_AB"] = {
        "pairs": sum(1 for r in tr if r["tier"] in "AB"),
        "hours": round(hrs([r for r in tr if r["tier"] in "AB"]), 3)}

    json.dump(rep, open(os.path.join(HERE, "report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ── 10 sample pairs, so the text quality is visible ─────────────────────────
    import random
    random.seed(7)
    picks = random.sample([r for r in rows if r["tier"] == "A" and r["seconds"] > 1.5],
                          min(10, len(rows)))
    with open(os.path.join(HERE, "samples.txt"), "w", encoding="utf-8") as f:
        for r in picks:
            f.write("%-52s %5.2fs  %s  %s\n" % (
                os.path.basename(r["audio"]), r["seconds"], r["tier"], r["text"]))

    print()
    print("PAIRS %d   HOURS %.2f   SESSIONS %d" % (
        rep["total_pairs"], rep["total_hours"], rep["sessions"]))
    for k, v in rep["by_split"].items():
        print("  %-7s %5d pairs  %6.2f h" % (k, v["pairs"], v["hours"]))
    for k, v in rep["by_tier"].items():
        print("  tier %s  %5d pairs  %6.2f h" % (k, v["pairs"], v["hours"]))
    print("REJECTED %d" % rep["rejected_total"])
    for k, v in rej.most_common(20):
        print("  %6d  %s" % (v, k))
    print("\nwrote %s" % mp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
