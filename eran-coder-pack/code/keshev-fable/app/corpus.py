"""corpus.py — every typed sentence becomes training material.

Iddo, 2026-08-15: "make the mic always train". The loop: this module writes
(audio, accepted-text) pairs into D:\\CLAUDE\\mic-rebuild\\state\\corpus\\;
tools/corpus-push.ps1 (scheduled task KESHEV-Corpus-Push, 03:00) tars that
directory to eran4; keshev-lora.timer trains a LoRA on it at 03:30 and
promotes it ONLY if it beats the deployed model. The loop starved from the
2026-08-18 cutover to this app until this module existed — KESHEV A's
client/corpus.py fed it, and A was retired with the mic.

WHY ONLY TYPED, AND WHY THAT IS ENOUGH (client/corpus.py's law, inherited):
an utterance may enter the corpus only if it was actually TYPED into Iddo's
window. To be typed here it has already survived the USB-mic law, the energy
gate, the hallucination/language gates, the OWNER floor (cos ≥ 0.60 to HIS
voice — a gate A never had), the presence guard and the focus guard. Room
audio is never typed, so room audio can never be trained on. The typed text
carries his acceptance, not merely his timbre.

FORMAT — pinned by tests/test_corpus.py against a real pushed archive
(state/corpus-sent/20260819-030350), because eran4's trainer reads it:

    <root>/<sid>/<rec_id>.wav      16 kHz mono s16le, the exact PCM decoded
    <root>/manifest.jsonl          {"id","sid","ts","wav","text","ms",
                                    "engine","source"} per line, appended

PRIVACY (his standing law): audio and text go to HIS fleet and nowhere
else; the manifest never carries window titles or exes; corpus-push MOVES,
never deletes; one Remove-Item wipes everything.

A corpus problem must never cost a typed sentence: every refusal returns
False and journals one ALARM(kind="corpus") — the router adds its own fence
above this for anything unforeseen.
"""
from __future__ import annotations

import json
import pathlib
import threading
import time
import wave
from typing import Protocol

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2                      # s16le
CHANNELS = 1

# Refuse to fill his disk silently. ~32 KB/s of speech — many hours.
DEFAULT_MAX_BYTES = 8 * 1024 * 1024 * 1024      # 8 GiB


class _JournalLike(Protocol):
    def event(self, name: str, **fields: object) -> dict: ...


class Corpus:
    """Append-only writer for (audio, typed-text) training pairs.

    `enabled=False` is a hard silent no-op: no directory, no manifest, no
    journal line — an off switch is intent, not a fault. The utterance gate
    is upstream, in who calls `add()` (the router, on TYPED only)."""

    def __init__(self, root: pathlib.Path | str, journal: _JournalLike, *,
                 enabled: bool = True, engine: str = "dgx",
                 max_bytes: int = DEFAULT_MAX_BYTES, clock=time.time) -> None:
        self.root = pathlib.Path(root)
        self.journal = journal
        self.enabled = bool(enabled)
        self.engine = engine
        self.max_bytes = int(max_bytes)
        self._clock = clock
        self._lock = threading.Lock()
        self._bytes: int | None = None        # lazily measured, then tracked
        self.written = 0
        self.skipped = 0

    # ------------------------------------------------------------- helpers
    def _refuse(self, rec_id: str, why: str) -> bool:
        self.skipped += 1
        self.journal.event("ALARM", kind="corpus", id=rec_id, err=why[:300])
        return False

    def _total_bytes(self) -> int:
        """Bytes currently held: measured once by walking, then tracked —
        a full corpus never re-walks the tree per utterance."""
        if self._bytes is None:
            total = 0
            if self.root.exists():
                for p in self.root.rglob("*.wav"):
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass              # a vanishing file only shrinks the sum
            self._bytes = total
        return self._bytes

    # --------------------------------------------------------------- write
    def add(self, rec_id: str, pcm: bytes, text: str) -> bool:
        """Store ONE typed utterance. `pcm` is 16 kHz mono s16le — the exact
        bytes the decoder heard, so training matches inference. True = stored."""
        if not self.enabled:
            return False
        text = (text or "").strip()
        if not text:
            return self._refuse(rec_id, "empty text")
        if not pcm:
            return self._refuse(rec_id, "empty pcm")

        with self._lock:
            if self._total_bytes() + len(pcm) > self.max_bytes:
                return self._refuse(
                    rec_id, f"corpus is full ({self._total_bytes()} bytes) — "
                    "nothing was deleted to make room, on purpose")

            sid = rec_id.rsplit("-", 1)[0] if "-" in rec_id else "unknown"
            try:
                sid_dir = self.root / sid
                sid_dir.mkdir(parents=True, exist_ok=True)
                with wave.open(str(sid_dir / f"{rec_id}.wav"), "wb") as w:
                    w.setnchannels(CHANNELS)
                    w.setsampwidth(SAMPLE_WIDTH)
                    w.setframerate(SAMPLE_RATE)
                    w.writeframes(pcm)
                rec = {
                    "id": rec_id,
                    "sid": sid,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                        time.localtime(self._clock())),
                    "wav": f"{sid}/{rec_id}.wav",
                    "text": text,
                    "ms": len(pcm) // 32,     # 16000 Hz * 2 B / 1000 ms
                    "engine": self.engine,
                    "source": "typed",
                }
                # open-per-append, like the journal: the 03:00 push MOVES the
                # manifest away mid-session and the next add must rebuild it.
                with open(self.root / "manifest.jsonl", "a",
                          encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError as exc:
                return self._refuse(rec_id, f"{type(exc).__name__}: {exc}")

            self._bytes = self._total_bytes() + len(pcm)
            self.written += 1
            return True
