#!/usr/bin/env python3
"""KESHEV offline replay rig — K0 skeleton (PHASE2-DESIGN.md section 2, tools/replay).

The rig replays recorded audio through KESHEV pipeline stages OFFLINE
(mic-debug-vm pattern, scar 43: debug on the rig, never hot-patch live).
Sacred Audio: the rig never opens any audio device — WAVs are read from disk
and fed as PCM bytes; nothing is ever played.

K0 scope (per the K0 acceptance row): the harness loads the corpus manifest,
reports clip presence honestly, and can push present clips through a pluggable
stage chain. Real stages (segmenter, engines, textguard) plug in at K8-K13;
K0 ships a NullDecoder so the chain is runnable end-to-end today.

Stdlib only — no numpy, no sounddevice, no torch (scar 47).
"""
from __future__ import annotations

import argparse
import json
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "manifest.json"

REQUIRED_CLIP_FIELDS = ("id", "category", "file", "expect")
KNOWN_CATEGORIES = {"silence", "noise", "faint", "he", "en", "code_switch", "laughter", "failing"}


class ManifestError(ValueError):
    """The manifest is malformed — HALT loudly (scar 40 discipline: no silent defaults)."""


@dataclass
class Clip:
    id: str
    category: str
    path: Path
    lang: str | None
    expect: dict

    @property
    def present(self) -> bool:
        return self.path.is_file()


@dataclass
class RigResult:
    clip_id: str
    n_pcm_bytes: int
    sample_rate: int
    duration_ms: int
    stage_trace: list = field(default_factory=list)  # [(stage_name, output_repr)]


def load_manifest(path: Path = DEFAULT_MANIFEST) -> tuple[dict, list[Clip]]:
    """Load + validate the corpus manifest. Raises ManifestError on any defect."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ManifestError(f"manifest not found: {path}")
    except json.JSONDecodeError as e:
        raise ManifestError(f"manifest is not valid JSON: {path}: {e}")

    if data.get("version") != 1:
        raise ManifestError(f"unsupported manifest version: {data.get('version')!r}")
    corpus = data.get("corpus")
    if not isinstance(corpus, list) or not corpus:
        raise ManifestError("manifest has no corpus list")

    clips, seen = [], set()
    for i, entry in enumerate(corpus):
        for f in REQUIRED_CLIP_FIELDS:
            if f not in entry:
                raise ManifestError(f"corpus[{i}] missing required field {f!r}")
        if entry["id"] in seen:
            raise ManifestError(f"duplicate clip id {entry['id']!r}")
        seen.add(entry["id"])
        if entry["category"] not in KNOWN_CATEGORIES:
            raise ManifestError(f"corpus[{i}] unknown category {entry['category']!r}")
        clips.append(Clip(
            id=entry["id"],
            category=entry["category"],
            path=(path.parent / entry["file"]).resolve(),
            lang=entry.get("lang"),
            expect=entry["expect"],
        ))
    return data, clips


def read_pcm(clip: Clip, expected_rate: int) -> tuple[bytes, int]:
    """Read a WAV as raw PCM s16le mono. Loud errors, no coercion magic at K0."""
    with wave.open(str(clip.path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{clip.id}: expected 16-bit PCM, got sampwidth={w.getsampwidth()}")
        if w.getnchannels() != 1:
            raise ValueError(f"{clip.id}: expected mono, got {w.getnchannels()} channels")
        rate = w.getframerate()
        if rate != expected_rate:
            raise ValueError(f"{clip.id}: expected {expected_rate}Hz, got {rate} (resample belongs to K7, not the rig)")
        return w.readframes(w.getnframes()), rate


# ------------------------------------------------------------------ stages

class NullDecoder:
    """K0 placeholder engine: consumes PCM, emits empty text. Lets the chain run
    end-to-end before any real engine exists. Replaced (not wrapped) at K9/K10."""
    name = "null-decoder"

    def __call__(self, pcm: bytes, meta: dict) -> dict:
        return {"text": "", "engine": "null", "n_bytes": len(pcm)}


class ReplayRig:
    """Pushes clips through an ordered chain of stages.

    A stage is any callable `(pcm: bytes, meta: dict) -> object`; its output is
    recorded in the trace and passed forward via meta['prev']. Real pipeline
    stages adapt onto this interface in their own milestones.
    """

    def __init__(self, stages, sample_rate: int = 16000):
        if not stages:
            raise ValueError("rig needs at least one stage")
        self.stages = list(stages)
        self.sample_rate = sample_rate

    def run_clip(self, clip: Clip) -> RigResult:
        pcm, rate = read_pcm(clip, self.sample_rate)
        result = RigResult(
            clip_id=clip.id,
            n_pcm_bytes=len(pcm),
            sample_rate=rate,
            duration_ms=int(len(pcm) / 2 / rate * 1000),
        )
        meta = {"clip": clip, "prev": None}
        for stage in self.stages:
            name = getattr(stage, "name", stage.__class__.__name__)
            out = stage(pcm, meta)
            result.stage_trace.append((name, repr(out)))
            meta["prev"] = out
        return result


# ------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KESHEV offline replay rig (K0 skeleton)")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--check", action="store_true", help="validate manifest + report clip presence, do not run")
    args = ap.parse_args(argv)

    try:
        data, clips = load_manifest(args.manifest)
    except ManifestError as e:
        print(f"MANIFEST ERROR: {e}", file=sys.stderr)
        return 2

    present = [c for c in clips if c.present]
    missing = [c for c in clips if not c.present]
    print(f"manifest ok: version={data['version']} clips={len(clips)} present={len(present)} missing={len(missing)}")
    for c in clips:
        print(f"  [{'PRESENT' if c.present else 'MISSING'}] {c.id:28s} {c.category:12s} {c.path.name}")
    if args.check:
        return 0

    rig = ReplayRig([NullDecoder()], sample_rate=data.get("sample_rate", 16000))
    for c in present:
        r = rig.run_clip(c)
        print(f"  ran {r.clip_id}: {r.duration_ms}ms pcm={r.n_pcm_bytes}B stages={[s for s, _ in r.stage_trace]}")
    if not present:
        print("no WAVs on disk yet (K0 skeleton) — corpus import lands with K8; manifest load is the K0 acceptance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
