"""ear.py — frames → segments → spool. The last mile before the decoder.

The loop: the audio backend hands int16 blocks; each block's RMS feeds the
segmenter; while a segment is open the raw frames accumulate; on close the
utterance is written to the spool as a 16 kHz mono WAV (write-ahead — disk
before queue) and the caller is told so it can journal SEG and kick the
router NOW (not at the next beat — a sentence should not wait a minute).

Pure of audio imports: blocks arrive from outside (main owns the device).
"""
from __future__ import annotations

import io
import wave
from typing import Callable, Protocol

from .segmenter import Segment, Segmenter


class _SpoolLike(Protocol):
    def admit(self, rec_id: str, wav_bytes: bytes, meta: dict): ...


def _rms_int16(block: bytes) -> float:
    """RMS of an int16 little-endian block, normalized to 0..1."""
    if not block:
        return 0.0
    try:
        import array
        a = array.array("h")
        a.frombytes(block[: len(block) - (len(block) % 2)])
        if not a:
            return 0.0
        acc = 0
        for v in a:
            acc += v * v
        return (acc / len(a)) ** 0.5 / 32768.0
    except Exception:  # noqa: BLE001 — a broken block is silence, not a crash
        return 0.0


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Ear:
    """Feed me int16 blocks; I hand closed utterances to the spool."""

    def __init__(self, spool: _SpoolLike, session_id: str,
                 on_segment: Callable[[str, Segment], None],
                 segmenter: Segmenter | None = None,
                 rate: int = 16000, on_level=None) -> None:
        self.spool = spool
        self.session_id = session_id
        self.on_segment = on_segment
        self.seg = segmenter or Segmenter()
        self.rate = rate
        self.on_level = on_level          # rms -> None, per block (meter + AUTO)
        self._counter = 0
        self._frames: list[bytes] = []
        self._open_was = False

    def feed_block(self, block: bytes) -> None:
        """One audio block (any length). Never raises."""
        frame_ms = int(len(block) / 2 / self.rate * 1000)
        if frame_ms <= 0:
            return
        rms = _rms_int16(block)
        if self.on_level is not None:
            self.on_level(rms)            # feed the live meter + AUTO tracker

        # collect frames while a segment is (or is becoming) open — the
        # segmenter decides openness AFTER seeing this frame, so buffer
        # first and trim on the verdict.
        self._frames.append(block)
        closed = self.seg.feed(frame_ms, rms)

        if self.seg.open and not self._open_was:
            # segment just opened at THIS frame: everything older is room
            # noise — keep a one-block pre-roll so onsets are not clipped.
            self._frames = self._frames[-2:]
        self._open_was = self.seg.open

        if closed is not None:
            self._counter += 1
            rec_id = f"{self.session_id}-{self._counter:06d}"
            pcm = b"".join(self._frames)
            self._frames = []
            wav = pcm_to_wav(pcm, self.rate)
            self.spool.admit(rec_id, wav, {"ms": closed.dur_ms,
                                           "forced": closed.forced})
            self.on_segment(rec_id, closed)
        elif not self.seg.open:
            # silence between utterances: keep only a short pre-roll
            if len(self._frames) > 4:
                self._frames = self._frames[-2:]
