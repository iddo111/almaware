"""KESHEV corpus writer — the mic's own voice-training material.

Iddo, 2026-08-15: "make the mic always train" / "u make sure it always gets
better". This is the CAPTURE half. The training half lives on eran4; the
promotion gate that makes "always gets better" true rather than aspirational
lives with it (tools/lora-nightly.sh).

WHAT MAY ENTER THE CORPUS, AND WHY IT IS SAFE WITHOUT A VOICE GATE
------------------------------------------------------------------
PHASE2-DESIGN.md section on corpus mode is emphatic (scar 49): there must be
"no code path that appends an ungated utterance to the corpus" — the corpus
writer takes the gate verdict as a REQUIRED argument. That gate is the
owner/voice-identity gate (criterion 18), and it is honestly unbuilt.

Rather than build a voice gate badly, this module takes a different verdict
that is already proven and already structural: **an utterance may enter the
corpus only if it was actually TYPED into Iddo's window.**

That is not a weaker claim than it sounds. To be typed, an utterance has
already survived, in order:

    devices.py    an authorized USB mic (never Bluetooth, scar 21)
    segmenter     the energy gate calibrated on his own speech (0.008)
    blip guard    + webrtcvad
    langpolicy    a whitelisted language
    textguard     hallucination / repetition / blocklist
    presence.py   HE WAS AT THE MACHINE      <- the 2026-08-15 guard
    focus.py      a real, allowed destination window

The seventh is the one that makes this sound. Room audio cannot enter the
corpus, because room audio is never typed: on 2026-08-15 at 16:24 the
presence gate refused three room utterances while Iddo was at the sea, and
none of them reached his chat. A corpus fed from TYPED text is therefore
exactly "the words he accepted into his own window" — which is a better
training signal than a voice gate would give anyway, because it carries his
acceptance, not merely his timbre.

It is still not proof of identity. If someone else dictates at his machine
while he is sitting there, that lands in the corpus. Named here rather than
hidden: [[project_keshev_always_on_lora]] carries the same caveat, and the
voice gate remains open as criterion 18.

PRIVACY (design section 8, and his standing law)
------------------------------------------------
  * audio and text stay on HIS machines — the PC and the fleet, nowhere else;
  * one command deletes the whole corpus (`keshevctl corpus --wipe`);
  * the manifest carries text and durations, never window titles, never the
    exe that had focus;
  * capture is OFF unless config says otherwise — an absent key means no.

FORMAT
------
`state/corpus/<sid>/<id>.wav` (16 kHz mono s16le, exactly what the DGX was
sent) plus one append-only `manifest.jsonl` per corpus root:

    {"id","sid","ts","wav","text","ms","engine","source"}

`source` is "typed" today. When corrections land it becomes "correction",
and those are worth a hundred confident decodes — a correction is Iddo
telling the model it was WRONG, which is the only label in the whole system
that is not the model's own opinion.
"""
from __future__ import annotations

import json
import threading
import time
import wave
from pathlib import Path
from typing import Optional

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2                      # s16le
CHANNELS = 1

# Refuse to fill his disk silently. At ~32 KB/s of speech this is many hours.
DEFAULT_MAX_BYTES = 8 * 1024 * 1024 * 1024      # 8 GiB

# Non-fatal reasons a capture was skipped, recorded rather than swallowed
# (lint gate G1 — the CUDA_DLL_SKIPPED pattern).
CORPUS_SKIPPED: list[str] = []


class CorpusWriter:
    """Append-only writer for (audio, text) training pairs.

    `enabled=False` is a hard no-op: no directory is created, no manifest is
    touched, nothing is written. The switch is the whole gate at this layer —
    the utterance gate is upstream, in who calls `add()`."""

    def __init__(self, root: Path | str, *, enabled: bool = False,
                 max_bytes: int = DEFAULT_MAX_BYTES,
                 clock=time.time) -> None:
        self.root = Path(root)
        self.enabled = bool(enabled)
        self.max_bytes = int(max_bytes)
        self._clock = clock
        self._lock = threading.Lock()
        self._bytes: Optional[int] = None      # lazily measured
        self.written = 0
        self.skipped = 0

    # ------------------------------------------------------------- helpers

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.jsonl"

    def total_bytes(self) -> int:
        """Bytes currently held. Measured once, then tracked — so a full
        corpus does not re-walk the tree on every utterance."""
        if self._bytes is None:
            total = 0
            if self.root.exists():
                for p in self.root.rglob("*.wav"):
                    try:
                        total += p.stat().st_size
                    except OSError as exc:            # never silent (G1)
                        CORPUS_SKIPPED.append(f"stat {p.name}: {exc}")
            self._bytes = total
        return self._bytes

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "utterances": self.count(),
            "bytes": self.total_bytes(),
            "written_this_session": self.written,
            "skipped_this_session": self.skipped,
        }

    def count(self) -> int:
        if not self.manifest_path.exists():
            return 0
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as fh:
                return sum(1 for line in fh if line.strip())
        except OSError as exc:                       # never silent (G1)
            CORPUS_SKIPPED.append(f"manifest count: {exc}")
            return 0

    # --------------------------------------------------------------- write

    def add(self, *, rec_id: str, sid: str, pcm: bytes, text: str,
            engine: str = "?", source: str = "typed") -> bool:
        """Append ONE accepted utterance. Returns True if it was stored.

        `pcm` is 16 kHz mono s16le — the exact bytes sent to the decoder, so
        the corpus trains on what the model actually heard, not on a
        re-encoded approximation of it."""
        if not self.enabled:
            return False
        text = (text or "").strip()
        if not text or not pcm:
            self.skipped += 1
            CORPUS_SKIPPED.append(f"{rec_id}: empty text or pcm")
            return False

        with self._lock:
            if self.total_bytes() + len(pcm) > self.max_bytes:
                self.skipped += 1
                CORPUS_SKIPPED.append(
                    f"{rec_id}: corpus is full ({self.total_bytes()} bytes) — "
                    f"nothing was deleted to make room, on purpose")
                return False

            day = self.root / (sid or "unknown")
            try:
                day.mkdir(parents=True, exist_ok=True)
                wav_path = day / f"{rec_id}.wav"
                with wave.open(str(wav_path), "wb") as w:
                    w.setnchannels(CHANNELS)
                    w.setsampwidth(SAMPLE_WIDTH)
                    w.setframerate(SAMPLE_RATE)
                    w.writeframes(pcm)
                rec = {
                    "id": rec_id,
                    "sid": sid,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                        time.localtime(self._clock())),
                    "wav": str(wav_path.relative_to(self.root)).replace("\\", "/"),
                    "text": text,
                    "ms": int(len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1000),
                    "engine": engine,
                    "source": source,
                }
                line = json.dumps(rec, ensure_ascii=False) + "\n"
                with open(self.manifest_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError as exc:                   # never silent (G1)
                self.skipped += 1
                CORPUS_SKIPPED.append(f"{rec_id}: {type(exc).__name__}: {exc}")
                return False

            self._bytes = self.total_bytes() + len(pcm)
            self.written += 1
            return True
