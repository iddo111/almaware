#!/usr/bin/env python3
"""Make the colony produce sound from its OWN units, not from a recording.

`acoustic_units.py synthesize` re-speaks an existing wav: it encodes real audio
into unit IDs and rebuilds it. That shows what the colony *hears*. It never
shows what the colony *has*.

This does the other thing. It hands `synthesize_units` a sequence we choose,
so nothing from any recording enters except the exemplar waveforms the colony
learned. Holding one unit ID for a second is the colony sustaining one of its
own sounds — the closest thing it can currently do to saying "ah".

Honest limit, and it matters: this is not speech and not generation. The colony
has a codebook and one learned waveform exemplar per unit. It has no model of
what follows what. Holding a unit is a sustained vowel-ish tone at best; the
colony is not choosing to make it.

    python3 speak_units.py --checkpoint state/ant-a/current.json --out /tmp/voice
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acoustic_units import load_checkpoint, render_soft, synthesize_units, write_wav_atomic


def unit_scores(checkpoint: dict) -> list[dict]:
    """Rank units by how vowel-like their exemplar is.

    A sustained vowel is loud and periodic: high energy, few zero crossings.
    A fricative or silence is the opposite. This is a crude proxy — no pitch
    tracking, no formants — but it is enough to find which of the 64 units is
    worth holding.
    """
    ex = np.asarray(checkpoint["exemplars_pcm16"], dtype=np.float32) / 32768.0
    out = []
    for i, w in enumerate(ex):
        rms = float(np.sqrt(np.mean(w * w)))
        crossings = int(np.sum(np.diff(np.signbit(w)) != 0))
        zcr = crossings / max(1, len(w) - 1)
        out.append({"unit": i, "rms": rms, "zcr": zcr, "vowel_score": rms * (1.0 - zcr)})
    out.sort(key=lambda d: -d["vowel_score"])
    return out


def hold(unit: int, seconds: float, checkpoint: dict, raw: bool = False) -> np.ndarray:
    rate = checkpoint["exemplar_rate"]
    if raw:
        hop = checkpoint["exemplar_hop_samples"]
        frames = max(2, int(seconds * rate / hop))
        ids = np.full(frames, unit, dtype=np.int64)
        return synthesize_units(ids, f"{checkpoint['checkpoint_sha256']}:unit_id", checkpoint)
    # Ear-validated sustain (2026-08-09): 50% Hann overlap-add of the unit's
    # own exemplar, then the soft render. Same learned waveform, no square edge.
    w = np.asarray(checkpoint["exemplars_pcm16"][unit], dtype=np.float32) / 32768.0
    length = len(w)
    window = np.hanning(length).astype(np.float32)
    n = int(seconds * rate)
    buf = np.zeros(n + length, dtype=np.float32)
    norm = np.zeros(n + length, dtype=np.float32)
    pos = 0
    while pos < n:
        buf[pos:pos + length] += w * window
        norm[pos:pos + length] += window
        pos += length // 2
    norm[norm < 1e-6] = 1.0
    return render_soft(buf[:n] / norm[:n], rate)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hold-seconds", type=float, default=1.5)
    ap.add_argument("--raw", action="store_true",
                    help="original square rendering (no overlap-add smoothing, no lowpass)")
    args = ap.parse_args()

    ck = load_checkpoint(Path(args.checkpoint))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rate = ck["exemplar_rate"]

    scores = unit_scores(ck)
    best = scores[0]["unit"]

    # 1. The single most vowel-like unit, sustained. The "ah" candidate.
    write_wav_atomic(out / f"AH-unit{best:02d}.wav", hold(best, args.hold_seconds, ck, args.raw), rate)

    # 2. The top five, each held, back to back — so the ear can compare.
    gap = np.zeros(int(0.35 * rate), dtype=np.float32)
    top = [s["unit"] for s in scores[:5]]
    clip = np.concatenate([np.concatenate([hold(u, 1.0, ck, args.raw), gap]) for u in top])
    write_wav_atomic(out / "TOP5-vowel-like.wav", clip, rate)

    # 3. Every unit the colony owns, 0.4 s each. Its whole alphabet in one file.
    short = np.zeros(int(0.12 * rate), dtype=np.float32)
    alphabet = np.concatenate(
        [np.concatenate([hold(u, 0.4, ck, args.raw), short]) for u in range(ck["units"])]
    )
    write_wav_atomic(out / "ALL-64-units.wav", alphabet, rate)

    print(json.dumps({
        "checkpoint_sha256": ck["checkpoint_sha256"][:16],
        "units": ck["units"],
        "best_unit": best,
        "top5": top,
        "top5_scores": [round(s["vowel_score"], 4) for s in scores[:5]],
        "files": sorted(p.name for p in out.glob("*.wav")),
        "render": ("raw exemplar frames"
                   if args.raw else "hann overlap-add 50% + lowpass 2.5kHz cosine rolloff"),
        "claim_limit": "sustained learned exemplars; not speech, not generation",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
