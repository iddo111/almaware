#!/usr/bin/env python3
"""Corpus feeder for the Hebrew Voice Ant Farm.

The colony plateaued at 8 training recordings: every fire candidate came back
worse than its incumbent, so the promotion guard correctly refused all of them.
The guard is not the problem — the corpus is. This feeder adds real Hebrew
*speech* to the training split only.

Two invariants, both deliberate:

1. **Held-out and evaluation stay Iddo-only.** Public speakers enter `train`
   and nothing else. `corpus.validate_manifest` already enforces that one
   (speaker_id, session_id) pair lives in exactly one split, so the measurement
   the colony is judged on never moves. If held-out error drops after feeding,
   that is a real improvement on Iddo's voice, not a relabelled ruler.

2. **Waveform-only.** No transcript, no title, no text of any kind is written
   into the corpus. Provenance lives in a sidecar the learner never reads.

Usage
-----
    feeder.py ingest --url URL --speaker ID --session ID [--minutes N]
    feeder.py ingest-file PATH... --speaker ID --session ID
    feeder.py reindex
    feeder.py status
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECORDINGS = HERE / "recordings"
SIDECAR = RECORDINGS / "sources.json"

TARGET_RATE = 16_000
SEGMENT_SECONDS = 12
# The colony's own loader rejects anything under 250 ms. This floor was 1.0 s,
# which silently threw away all 400 of the head's babbles — they are 0.5 s each,
# and the run reported "segments_admitted: 0" with no other complaint. Matching
# the loader's real limit instead of guessing a rounder number.
MIN_SECONDS = 0.3
# Segments quieter than this are silence, breath, or room tone. Feeding them
# teaches the codebook to model nothing, which is how the synthetic fire audio
# has been dragging candidates down.
MIN_RMS = 0.012

SAFE = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return SAFE.sub("-", text.strip().lower()).strip("-") or "x"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def load_sidecar() -> dict:
    if SIDECAR.exists():
        return json.loads(SIDECAR.read_text(encoding="utf-8"))
    return {"format_version": 1, "note": "provenance only; never a learning token", "files": {}}


def save_sidecar(data: dict) -> None:
    tmp = SIDECAR.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SIDECAR)


def ytdlp_python() -> str:
    """yt-dlp lives in a dedicated venv: the system python3 on eran4 is
    PEP-668 managed and refuses to install into it."""
    venv = HERE / ".feeder-venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def fetch_audio(url: str, workdir: Path) -> Path:
    """Pull the audio track of a URL into workdir. yt-dlp handles YouTube and
    several hundred other sites; anything it refuses we hand straight to ffmpeg."""
    out = workdir / "source.%(ext)s"
    try:
        run([
            ytdlp_python(), "-m", "yt_dlp",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "wav",
            "--no-playlist", "--quiet", "--no-warnings",
            "-o", str(out), url,
        ])
    except subprocess.CalledProcessError:
        # Not a yt-dlp site: treat the URL as a plain media file.
        direct = workdir / "source.wav"
        run(["ffmpeg", "-nostdin", "-y", "-i", url, "-vn", str(direct)])
        return direct
    produced = sorted(workdir.glob("source.*"))
    if not produced:
        raise RuntimeError(f"nothing downloaded from {url}")
    return produced[0]


def segment(src: Path, workdir: Path, minutes: float | None) -> list[Path]:
    """Normalise to mono 16 kHz 16-bit PCM and cut into fixed-length pieces."""
    staged = workdir / "seg"
    staged.mkdir(exist_ok=True)
    cmd = ["ffmpeg", "-nostdin", "-y", "-i", str(src)]
    if minutes:
        cmd += ["-t", str(int(minutes * 60))]
    cmd += [
        "-vn", "-ac", "1", "-ar", str(TARGET_RATE), "-acodec", "pcm_s16le",
        "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
        str(staged / "part-%05d.wav"),
    ]
    run(cmd)
    return sorted(staged.glob("part-*.wav"))


def loud_enough(path: Path) -> bool:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            return False
        rate = w.getframerate()
        frames = w.getnframes()
        if frames < rate * MIN_SECONDS:
            return False
        pcm = w.readframes(frames)
    import array
    samples = array.array("h")
    samples.frombytes(pcm)
    if not samples:
        return False
    mean_square = sum(s * s for s in samples) / len(samples)
    return (mean_square ** 0.5) / 32768 >= MIN_RMS


def admit(pieces: list[Path], speaker: str, session: str) -> int:
    """Move accepted segments into recordings/train and record provenance."""
    train = RECORDINGS / "train"
    train.mkdir(parents=True, exist_ok=True)
    side = load_sidecar()
    files = side["files"]
    existing = len([p for p in train.glob(f"{slug(speaker)}__{slug(session)}__*.wav")])
    added = 0
    for piece in pieces:
        if not loud_enough(piece):
            continue
        name = f"{slug(speaker)}__{slug(session)}__{existing + added:05d}.wav"
        shutil.move(str(piece), str(train / name))
        files[f"train/{name}"] = {"speaker_id": speaker, "session_id": session}
        added += 1
    side["files"] = files
    save_sidecar(side)
    return added


def cmd_ingest(args) -> None:
    with tempfile.TemporaryDirectory(prefix="vaf-feed-") as tmp:
        workdir = Path(tmp)
        src = fetch_audio(args.url, workdir)
        pieces = segment(src, workdir, args.minutes)
        added = admit(pieces, args.speaker, args.session)
    print(json.dumps({"url": args.url, "segments_cut": len(pieces),
                      "segments_admitted": added, "split": "train",
                      "speaker_id": args.speaker, "session_id": args.session}))


def cmd_ingest_file(args) -> None:
    total_cut = total_added = 0
    for raw in args.paths:
        with tempfile.TemporaryDirectory(prefix="vaf-feed-") as tmp:
            workdir = Path(tmp)
            pieces = segment(Path(raw), workdir, args.minutes)
            total_cut += len(pieces)
            total_added += admit(pieces, args.speaker, args.session)
    print(json.dumps({"files": len(args.paths), "segments_cut": total_cut,
                      "segments_admitted": total_added, "split": "train",
                      "speaker_id": args.speaker, "session_id": args.session}))


def cmd_reindex(args) -> None:
    """Rebuild the manifest with per-file speaker/session from the sidecar.

    corpus.build_manifest stamps one speaker on every entry, which would label
    public speakers as Iddo and quietly destroy the thing the colony is scored
    on. So the entries are built here instead — but the result is handed to
    corpus.validate_manifest, the same gate the running loop uses. corpus.py is
    not modified; nothing the live cycle depends on changes.
    """
    sys.path.insert(0, str(HERE))
    import corpus
    from acoustic_units import load_wav, write_json_atomic

    overrides = load_sidecar()["files"]
    default_session = {
        "train": args.train_session,
        "heldout": args.heldout_session,
        "evaluation": args.evaluation_session,
    }

    entries = []
    for split in corpus.SPLITS:
        for path in sorted((RECORDINGS / split).glob("*.wav")):
            relative = path.relative_to(RECORDINGS).as_posix()
            meta = overrides.get(relative, {})
            audio = load_wav(path)
            entries.append({
                "path": relative,
                "split": split,
                "speaker_id": meta.get("speaker_id", args.speaker),
                "session_id": meta.get("session_id", default_session[split]),
                "audio_sha256": audio.sha256,
                "pcm_sha256": audio.pcm_sha256,
                "sample_rate": audio.rate,
                "sample_count": int(len(audio.samples)),
            })

    manifest = {
        "format_version": corpus.MANIFEST_FORMAT,
        "architecture": "private-waveform-only-corpus",
        "learning_tokens": "waveform-features-only",
        "private": True,
        "entries": entries,
        "sample_rates": sorted({e["sample_rate"] for e in entries}),
    }
    manifest["manifest_sha256"] = corpus.manifest_digest(manifest)

    out = RECORDINGS / "manifest.json"
    write_json_atomic(out, manifest)
    corpus.validate_manifest(out, RECORDINGS)

    speakers: dict[str, int] = {}
    for e in entries:
        if e["split"] == "train":
            speakers[e["speaker_id"]] = speakers.get(e["speaker_id"], 0) + 1
    print(json.dumps({"manifest_sha256": manifest["manifest_sha256"],
                      "recording_count": len(entries),
                      "train_by_speaker": speakers, "valid": True}, ensure_ascii=False))


def cmd_status(args) -> None:
    side = load_sidecar()
    by_speaker: dict[str, int] = {}
    for meta in side["files"].values():
        by_speaker[meta["speaker_id"]] = by_speaker.get(meta["speaker_id"], 0) + 1
    counts = {s: len(list((RECORDINGS / s).glob("*.wav")))
              for s in ("train", "heldout", "evaluation")}
    print(json.dumps({"split_counts": counts, "fed_by_speaker": by_speaker}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("ingest", help="fetch a URL's audio into the training split")
    p.add_argument("--url", required=True)
    p.add_argument("--speaker", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--minutes", type=float, default=None)
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("ingest-file", help="feed local audio files into the training split")
    p.add_argument("paths", nargs="+")
    p.add_argument("--speaker", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--minutes", type=float, default=None)
    p.set_defaults(fn=cmd_ingest_file)

    p = sub.add_parser("reindex", help="rebuild and validate the corpus manifest")
    p.add_argument("--speaker", default="iddo1")
    # The colony's real session IDs. Held-out and evaluation are named here only
    # so a rebuild reproduces them byte-for-byte; the feeder never writes to
    # those splits.
    p.add_argument("--train-session", default="2026-06-18")
    p.add_argument("--heldout-session", default="2026-06-25")
    p.add_argument("--evaluation-session", default="2026-07-01")
    p.set_defaults(fn=cmd_reindex)

    p = sub.add_parser("status", help="show corpus counts and what has been fed")
    p.set_defaults(fn=cmd_status)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
