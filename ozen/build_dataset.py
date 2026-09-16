"""build_dataset.py -- assemble the corpus for OZEN, KESHEV's from-scratch
Hebrew acoustic model.

Iddo's order 2026-08-22: a real from-scratch model with real weights, trained on
his own speech, running in shadow beside Whisper until it is good enough to
replace it. I told him the labelled Hebrew is about twenty times short of what
that normally takes; he reaffirmed, so this builds the best corpus that exists.

TWO RULES, both learned the hard way and both enforced here:

  1. SPLIT BY SESSION, NEVER RANDOMLY. On 2026-08-21 a random split leaked the
     same recording session into train and dev and made the numbers ~14 points
     optimistic. A model can memorise a room, a microphone position and a mood.
     Held-out sessions are whole and never appear in training.

  2. NO SILENT DROPPING. Every utterance that is rejected is counted and the
     reason is printed. A corpus that quietly shrinks is a corpus you cannot
     reason about.
"""
import argparse
import json
import re
import unicodedata
import wave
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:\CLAUDE")
MANIFESTS = sorted((ROOT / "mic-rebuild" / "state" / "corpus-sent").glob("*/manifest.jsonl"))
AUDIO_ROOTS = [
    ROOT / "keshev-fable" / "state" / "spool",
    ROOT / "keshev-next" / "segments",
    ROOT / "mic-rebuild" / "_genizah",
    ROOT / "mic-rebuild" / "state" / "corpus",
    ROOT / "mic-rebuild" / "state" / "corpus-sent",
    ROOT / "mic-rebuild" / "state" / "spool",
]
OUT = ROOT / "ozen" / "data"

HEB = re.compile(r"[\u05D0-\u05EA]")
LATIN = re.compile(r"[A-Za-z]")
# the output alphabet: 22 letters + final forms + space. No niqqud, no punctuation
# beyond what a character model can plausibly hear.
FINALS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}
ALPHABET = list(" אבגדהוזחטיכלמנסעפצקרשת") + ["'"]


def index_audio():
    idx = {}
    for root in AUDIO_ROOTS:
        if not root.exists():
            continue
        for w in root.rglob("*.wav"):
            idx.setdefault(w.name, w)
    return idx


def normalise(text):
    """Hebrew text as an acoustic model can be asked to produce it: no niqqud,
    final forms folded to their base letter (they are the same sound), digits
    and latin removed, whitespace collapsed. Returns None if nothing survives."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("־", " ").replace("–", " ").replace("—", " ")
    t = "".join(FINALS.get(c, c) for c in t)
    t = re.sub(r"[^\u05D0-\u05EA' ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def duration(path):
    try:
        with wave.open(str(path), "rb") as f:
            return f.getnframes() / f.getframerate(), f.getframerate()
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-sec", type=float, default=0.30)
    ap.add_argument("--max-sec", type=float, default=20.0)
    ap.add_argument("--min-chars", type=int, default=2)
    ap.add_argument("--dev-frac", type=float, default=0.15,
                    help="fraction of total DURATION held out, as whole sessions")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    idx = index_audio()
    print(f"audio index: {len(idx)} unique wav filenames")
    print(f"manifests  : {len(MANIFESTS)}")

    rows = []
    rej = Counter()
    for m in MANIFESTS:
        for line in m.open(encoding="utf-8"):
            try:
                d = json.loads(line)
            except Exception:
                rej["unparseable manifest line"] += 1
                continue
            name = Path(d.get("wav", "")).name
            path = idx.get(name)
            if path is None:
                rej["audio file not on disk"] += 1
                continue
            raw = (d.get("text") or "").strip()
            if not raw:
                rej["empty transcript"] += 1
                continue
            if not HEB.search(raw):
                rej["not hebrew (english/other)"] += 1
                continue
            if LATIN.search(raw):
                rej["mixed hebrew+latin"] += 1
                continue
            text = normalise(raw)
            if not text or len(text.replace(" ", "")) < args.min_chars:
                rej["nothing left after normalisation"] += 1
                continue
            sec, sr = duration(path)
            if sec is None:
                rej["unreadable wav"] += 1
                continue
            if sec < args.min_sec:
                rej["too short"] += 1
                continue
            if sec > args.max_sec:
                rej["too long"] += 1
                continue
            rows.append({
                "id": d.get("id"),
                "sid": d.get("sid") or (d.get("id") or "").split("-")[0],
                "wav": str(path),
                "sec": round(sec, 3),
                "sr": sr,
                "text": text,
                "raw": raw,
                "ts": d.get("ts"),
                "engine": d.get("engine"),
            })

    print(f"\nkept: {len(rows)} utterances")
    print("rejected:")
    for k, v in rej.most_common():
        print(f"   {v:6d}  {k}")

    if not rows:
        print("\nnothing to build.")
        return

    by_sid = defaultdict(list)
    for r in rows:
        by_sid[r["sid"]].append(r)
    sids = sorted(by_sid, key=lambda s: -sum(x["sec"] for x in by_sid[s]))
    print(f"\nsessions: {len(sids)}")
    for s in sids[:12]:
        tot = sum(x["sec"] for x in by_sid[s])
        print(f"   {s}  {len(by_sid[s]):5d} utts  {tot/60:6.1f} min")

    # Hold out whole sessions until the dev set is big enough to MEASURE with.
    # A fixed count of sessions gave 30 utterances here, because the session
    # sizes are wildly skewed -- two sessions hold 57 of the 70 minutes. Thirty
    # utterances cannot separate a 40% error rate from a 55% one, so the number
    # it produces would be theatre. Size the dev set by duration instead, and
    # never take the largest session, which the model needs to learn from.
    # Accumulate from the SMALLEST session upward. Taking the next-largest
    # session overshot badly -- one 21-minute session became a 30% dev set and
    # left 50 minutes to train on. Going small-first hits the target closely,
    # puts SEVERAL different sessions in dev (different rooms, moods, mic
    # positions -- which is the whole point of holding sessions out), and leaves
    # the two large sessions where they are worth most: in training.
    total_sec = sum(r["sec"] for r in rows)
    target = total_sec * args.dev_frac
    held, acc = [], 0.0
    for s in reversed(sids):
        if acc >= target:
            break
        held.append(s)
        acc += sum(x["sec"] for x in by_sid[s])
    if not held:
        held = sids[-1:]
    k = len(held)
    train = [r for r in rows if r["sid"] not in held]
    dev = [r for r in rows if r["sid"] in held]

    def hrs(rs):
        return sum(r["sec"] for r in rs) / 3600

    print(f"\nheld-out sessions ({k}): {held}")
    print(f"TRAIN {len(train):5d} utts   {hrs(train):.2f} h")
    print(f"DEV   {len(dev):5d} utts   {hrs(dev):.2f} h")
    assert not (set(r['sid'] for r in train) & set(r['sid'] for r in dev)), "session leak!"

    chars = Counter()
    for r in rows:
        chars.update(r["text"])
    unknown = sorted(set(chars) - set(ALPHABET))
    print(f"\nalphabet: {len(ALPHABET)} symbols; characters seen: {len(chars)}")
    if unknown:
        print(f"   NOT in alphabet (will be dropped at training): {unknown}")

    for name, rs in (("train", train), ("dev", dev)):
        p = OUT / f"{name}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {p}  ({len(rs)} rows)")

    (OUT / "alphabet.json").write_text(
        json.dumps({"blank": 0, "symbols": ALPHABET}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # the unlabelled pool, for self-supervised pretraining -- this is the larger
    # half of the corpus and the only reason a from-scratch model is thinkable
    used = {Path(r["wav"]).name for r in rows}
    pool = []
    for name, path in idx.items():
        if name in used:
            continue
        sec, sr = duration(path)
        if sec and 0.30 <= sec <= 20.0:
            pool.append({"wav": str(path), "sec": round(sec, 3), "sr": sr})
    (OUT / "unlabelled.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in pool), encoding="utf-8")
    print(f"wrote {OUT/'unlabelled.jsonl'}  ({len(pool)} clips, "
          f"{sum(p['sec'] for p in pool)/3600:.2f} h unlabelled)")


if __name__ == "__main__":
    main()
