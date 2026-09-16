"""measure_voice.py — the REAL numbers, from Iddo's own recorded speech.

Fable's job under Iddo's order (2026-08-20 08:57) is to verify the 480B's work
and unblock it. Its plan claimed "Speech Start Threshold RMS > 0.030 (measured
from 50 typical utterances)". Nothing was measured, and 0.030 is HIGHER than the
0.020 that shredded his sentences this morning. So: measure.

Sources of truth, both from the live journal:
  TYPED records      -> audio that really was his speech, accepted end to end
  GUARD_DROP records -> near-silence blips that decoded as "you" (his room)

Reports the two distributions in 100 ms blocks, and — the number that actually
decides fragmentation — how long the QUIET GAPS INSIDE his real sentences are.
"""
from __future__ import annotations

import array
import json
import math
import pathlib
import statistics
import wave

SPOOL = pathlib.Path(r"D:\CLAUDE\keshev-fable\state\spool")
EVENTS = pathlib.Path(r"D:\CLAUDE\keshev-fable\state\events.jsonl")
BLOCK_MS = 100
RATE = 16000


def blocks_rms(pcm: bytes) -> list[float]:
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    n = RATE * BLOCK_MS // 1000
    out = []
    for i in range(0, len(a) - n + 1, n):
        chunk = a[i:i + n]
        out.append((sum(v * v for v in chunk) / len(chunk)) ** 0.5 / 32768.0)
    return out


def classify_ids(limit: int = 4000) -> tuple[list[str], list[str]]:
    typed, junk = [], []
    for ln in EVENTS.read_text(encoding="utf-8").splitlines()[-40000:]:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("evt") == "TYPED":
            typed.append(e["id"])
        elif e.get("evt") == "GUARD_DROP" and e.get("chars") in (3, 4, 5):
            junk.append(e["id"])
    return typed[-limit:], junk[-limit:]


def pct(v: list[float], q: float) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    return s[min(len(s) - 1, max(0, int(q * len(s))))]


def read(rec_id: str) -> bytes | None:
    p = SPOOL / f"{rec_id}.wav"
    if not p.exists():
        return None
    with wave.open(str(p)) as w:
        return w.readframes(w.getnframes())


def main() -> None:
    typed_ids, junk_ids = classify_ids()
    speech_blocks: list[float] = []
    junk_blocks: list[float] = []
    gaps_ms: list[int] = []          # quiet runs INSIDE a real sentence
    n_typed = n_junk = 0

    for rid in typed_ids:
        pcm = read(rid)
        if not pcm:
            continue
        n_typed += 1
        b = blocks_rms(pcm)
        speech_blocks.extend(b)
        # a "quiet" block inside a typed utterance is a mid-sentence pause.
        # Use a low reference (the junk floor is computed after; 0.010 is a
        # deliberately generous mark for "not speaking right now").
        run = 0
        for v in b:
            if v < 0.010:
                run += 1
            else:
                if run:
                    gaps_ms.append(run * BLOCK_MS)
                run = 0

    for rid in junk_ids:
        pcm = read(rid)
        if not pcm:
            continue
        n_junk += 1
        junk_blocks.extend(blocks_rms(pcm))

    print(f"SPEECH  (from {n_typed} TYPED utterances, {len(speech_blocks)} blocks of {BLOCK_MS}ms)")
    for q in (0.05, 0.10, 0.25, 0.50, 0.75, 0.95):
        print(f"   p{int(q*100):02d} = {pct(speech_blocks, q):.4f}")
    print(f"   mean {statistics.fmean(speech_blocks):.4f}" if speech_blocks else "")

    print(f"\nROOM/JUNK (from {n_junk} dropped blips, {len(junk_blocks)} blocks)")
    for q in (0.50, 0.75, 0.90, 0.95, 0.99):
        print(f"   p{int(q*100):02d} = {pct(junk_blocks, q):.4f}")

    print(f"\nMID-SENTENCE GAPS inside his real speech ({len(gaps_ms)} gaps)")
    for q in (0.50, 0.75, 0.90, 0.95, 0.99):
        print(f"   p{int(q*100):02d} = {pct([float(g) for g in gaps_ms], q):.0f} ms")
    if gaps_ms:
        print(f"   max  = {max(gaps_ms)} ms")

    # the decision the numbers actually make
    if speech_blocks and junk_blocks:
        floor = pct(junk_blocks, 0.95)
        start = pct(speech_blocks, 0.25)
        print("\nVERDICT")
        print(f"   room floor  p95 = {floor:.4f}")
        print(f"   speech      p25 = {start:.4f}  p05 = {pct(speech_blocks,0.05):.4f}")
        print(f"   -> a start gate above {pct(speech_blocks,0.05):.4f} cuts into his own voice")
        if gaps_ms:
            print(f"   -> end-of-utterance silence must exceed {pct([float(g) for g in gaps_ms],0.95):.0f} ms "
                  f"(p95 of his mid-sentence pauses) or sentences fragment")


if __name__ == "__main__":
    main()
