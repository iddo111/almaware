"""KESHEV segmenter — K8 (PHASE2-DESIGN.md section 2 segmenter row;
PHASE1-INQUIRY.md scars 26/27, risk-ledger item 6).

The scar-27 layer order, exactly, pre-enqueue:

  (1) ENERGY GATE   frames below the calibrated gate never open a segment —
                    silence is dropped before any disk write or GPU cycle
                    (scar 26: 13,332 EMPTY decodes wasted 172 GPU minutes).
  (2) AUTO-GAIN     peak-normalize quiet-REAL speech ONLY when the original
                    segment rms >= AUTOGAIN_RMS_FLOOR (0.004), gain capped
                    at 40x, never attenuating — amplifying ambient noise is
                    what typed "חחח" all night.
  (3) webrtcvad     pre-enqueue VAD with the FAINT-BAND BYPASS decided at K8
                    on measured evidence (risk-ledger item 6): real webrtcvad
                    at aggressiveness 2 REJECTS faint speech below ~0.003 rms
                    (measured 2026-08-12, synthetic vectors: saw amp 0.005 /
                    rms 0.0029 -> 3/66 speech frames; amp 0.003 / rms 0.0017
                    -> 0/66) — exactly the 0.002-0.005 band the K8 acceptance
                    row protects. So: the VAD verdict applies only when the
                    POST-GAIN rms >= AUTOGAIN_RMS_FLOOR; fainter segments
                    ride to the decoder, where Silero-inside-HE-decode and
                    the decode guards are the next layers (scar 27 permits
                    energy-gate-only pre-enqueue for this band).

Segment close => spool WRITE-AHEAD then enqueue, in that order, always —
the crash window between the two is proven harmless in test_spool.py.
Run-ons split at 28s with a 0.5s overlap so no boundary word is lost.

Synthetic-stream testable: input is 16k mono float32 frames from the K7
capture pipeline; no device, no audio output (scar 22), no torch (scar 47).
"""
from __future__ import annotations

from time import time as _time
from typing import Any, Callable

import numpy as np

from client.spool import Spool, SpoolRecord

# ---------------------------------------------------------------- constants
# Code under git, not config keys (design sec 5). gate_rms is the ONE
# config-carried knob and arrives via the constructor.

SAMPLE_RATE = 16000
FRAME_MS = 30                    # capture block size (K7 BLOCK_MS)
CLOSE_SILENCE_MS = 600           # hangover: sub-gate audio that closes a segment
MAX_SEGMENT_S = 28.0             # design sec 2: max 28s…
SPLIT_OVERLAP_S = 0.5            # …split with 0.5s overlap
AUTOGAIN_RMS_FLOOR = 0.004       # scar 27: gain only when original rms >= this
AUTOGAIN_MAX = 40.0              # scar 27: cap 40x
AUTOGAIN_TARGET_PEAK = 0.95      # peak-normalization target
VAD_AGGRESSIVENESS = 2           # webrtcvad mode for the default VAD
VAD_FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000   # 480 (a legal vad size)
VAD_MIN_SPEECH_FRAMES = 2        # segment keeps if >= this many speech frames

# ------------------------------------------------------------------- the blip
# MEASURED 2026-08-14 on 854 live segments of Iddo's real dictation (session
# c36702e2, BRIO, his room). The segments fell into two clean populations:
#
#   real speech   n=232   median rms 0.0276   p10 0.0122
#   sub-speech    n=622   median rms 0.0031   p90 0.0060
#   fragments <800ms: 365 (43% of everything), median rms 0.0025
#
# 43% of what reached the DGX was a noise blip: VAD_MIN_SPEECH_FRAMES=2 means
# ~60ms of anything the VAD calls speech opens a segment, and CLOSE_SILENCE_MS
# adds 600ms of hangover behind it — so one keyboard knock becomes a 630ms
# "utterance". Whisper does not answer near-silence with silence. It answers
# with a confident, fluent, WRONG sentence. On 2026-08-14 it typed the word
# "רפורמים" — correctly spelled, grammatical, and never spoken — and Claude
# argued religion with Iddo about a word the decoder invented.
#
# So a blip must never reach a decoder. Both conditions are required: SHORT
# **and** at noise level. A short-but-clearly-voiced word ("כן", "לא") is loud,
# passes on energy, and is never dropped for being brief — losing a real word
# is the failure this whole rebuild exists to prevent (scar 17/18), and it is
# strictly worse than passing an occasional blip.
MIN_UTTERANCE_MS = 800           # below this, energy has to prove it is speech
# LOWERED 0.010 -> 0.004 at 23:38 the same night. His speech level COLLAPSED
# over the day: rms 0.027 at 11am, 0.005 at 23:37 with autogain straining at
# 11x, while the room floor stayed ~0.0038. Speech and noise CONVERGED, so the
# two clean populations this constant was measured against no longer exist and
# no threshold can separate them. 0.004 errs toward keeping his words (scar
# 17/18) and leans on textguard's blocklist to catch the "you"/"thank you"
# silence artifacts that now get through. THIS IS A STOPGAP, NOT A FIX: the
# real repair is at the source (mic distance / input level), and structurally
# it wants an ADAPTIVE gate that tracks the room's own floor instead of a
# number measured once at 11am.
BLIP_RMS = 0.004


class SegmenterDependencyError(ImportError):
    """A required dependency is missing — VISIBLE at construction (scar 6:
    the 06-27 silent import failure deafened the mic for 38 days)."""


def make_default_vad() -> Callable[[bytes], bool]:
    """The production VAD: webrtcvad at aggressiveness 2, wrapped as
    frame_bytes -> bool. Missing dependency fails LOUDLY (scar 6)."""
    try:
        import webrtcvad
    except ImportError as e:
        raise SegmenterDependencyError(
            "webrtcvad is not importable — install webrtcvad-wheels; "
            "KESHEV never degrades silently (scar 6)") from e
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    def is_speech(frame_bytes: bytes) -> bool:
        return bool(vad.is_speech(frame_bytes, SAMPLE_RATE))

    return is_speech


def _rms(x: np.ndarray) -> float:
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def _to_s16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


class Segmenter:
    """Streaming segmenter over 16k mono float32 frames.

    Feed capture frames with `feed()`; call `flush()` when the stream owner
    loses the device (criterion 14) or shuts down — the open segment is
    preserved, and the SAME object keeps segmenting when frames resume
    (replug never needs a restart).
    """

    def __init__(self,
                 spool: Spool,
                 gate_rms: float,
                 session_id: str,
                 *,
                 sample_rate: int = SAMPLE_RATE,
                 vad: Callable[[bytes], bool] | None = None,
                 on_event: Callable[..., Any] | None = None,
                 now_fn: Callable[[], float] = _time) -> None:
        self.spool = spool
        self.gate_rms = float(gate_rms)
        self.session_id = str(session_id)
        self.rate = int(sample_rate)
        self._vad = vad if vad is not None else make_default_vad()
        self._on_event = on_event or (lambda evt, **kw: None)
        self._now = now_fn
        # segment state
        self._buf: list[np.ndarray] = []
        self._in_seg = False
        self._seg_samples = 0
        self._silent_samples = 0
        self._seq = 0
        # visible counters (heartbeat / criterion-22 style honesty)
        self.gated_frames = 0
        self.segments_opened = 0
        self.segments_enqueued = 0
        self.segments_vad_dropped = 0
        self.segments_blip_dropped = 0

    # ------------------------------------------------------------- public

    def snapshot(self) -> dict[str, int]:
        return {
            "gated_frames": self.gated_frames,
            "segments_opened": self.segments_opened,
            "segments_enqueued": self.segments_enqueued,
            "segments_vad_dropped": self.segments_vad_dropped,
            "segments_blip_dropped": self.segments_blip_dropped,
        }

    def feed(self, frame: np.ndarray) -> list[SpoolRecord]:
        """One capture frame in; zero or more enqueued records out."""
        frame = np.asarray(frame, dtype=np.float32)
        if len(frame) == 0:
            return []
        out: list[SpoolRecord] = []
        level = _rms(frame)

        if not self._in_seg:
            if level < self.gate_rms:
                self.gated_frames += 1          # counted, not logged per-frame
                return out
            self._open()

        # max-length split BEFORE appending: a closed segment never exceeds 28s
        if self._seg_samples + len(frame) > int(MAX_SEGMENT_S * self.rate):
            rec = self._close(split=True)
            if rec is not None:
                out.append(rec)

        self._buf.append(frame)
        self._seg_samples += len(frame)

        if level < self.gate_rms:
            self._silent_samples += len(frame)
            if self._silent_samples >= int(CLOSE_SILENCE_MS / 1000 * self.rate):
                rec = self._close(split=False)
                if rec is not None:
                    out.append(rec)
        else:
            self._silent_samples = 0
        return out

    def flush(self) -> SpoolRecord | None:
        """Close any open segment NOW (device lost / pause / shutdown).
        The segment rides the normal spool path — never discarded."""
        if not self._in_seg:
            return None
        return self._close(split=False)

    # ------------------------------------------------------------ internals

    def _open(self) -> None:
        self._in_seg = True
        self._buf = []
        self._seg_samples = 0
        self._silent_samples = 0
        self.segments_opened += 1

    def _next_id(self) -> str:
        self._seq += 1
        return f"{self.session_id}-{self._seq:06d}"

    def _vad_keeps(self, pcm: bytes) -> bool:
        frame_bytes = VAD_FRAME_SAMPLES * 2
        n_frames = len(pcm) // frame_bytes
        if n_frames == 0:
            return True                      # sub-frame blip: defer to decoder
        speech = 0
        for i in range(n_frames):
            if self._vad(pcm[i * frame_bytes:(i + 1) * frame_bytes]):
                speech += 1
                if speech >= min(VAD_MIN_SPEECH_FRAMES, n_frames):
                    return True
        return False

    def _close(self, split: bool) -> SpoolRecord | None:
        samples = np.concatenate(self._buf) if self._buf else np.empty(0, np.float32)
        overlap = samples[-int(SPLIT_OVERLAP_S * self.rate):].copy() if split else None

        seg_id = self._next_id()
        duration_ms = int(len(samples) / self.rate * 1000)
        t_end = self._now()
        t_start = t_end - len(samples) / self.rate
        rms_raw = _rms(samples)

        # (2) auto-gain — floor + cap + never attenuate (scar 27)
        gain = 1.0
        peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
        if rms_raw >= AUTOGAIN_RMS_FLOOR and peak > 0.0:
            gain = max(1.0, min(AUTOGAIN_TARGET_PEAK / peak, AUTOGAIN_MAX))
        gained = samples * gain if gain != 1.0 else samples
        pcm = _to_s16(gained)

        # (3) VAD pre-enqueue — verdict applies only above the faint band
        # (risk-6 bypass, measured; see module docstring)
        rec: SpoolRecord | None = None
        post_rms = rms_raw * gain
        if duration_ms < MIN_UTTERANCE_MS and rms_raw < BLIP_RMS:
            # Short AND at noise level — a blip, not speech. Dropped BEFORE the
            # spool so no decoder ever sees it and no hallucination can be typed.
            # Journalled like every other drop: a silent one would be scar 17/18.
            self.segments_blip_dropped += 1
            self._on_event("GATED", id=seg_id, reason="blip",
                           ms=duration_ms, rms=rms_raw)
        elif post_rms >= AUTOGAIN_RMS_FLOOR and not self._vad_keeps(pcm):
            self.segments_vad_dropped += 1
            self._on_event("GATED", id=seg_id, reason="vad",
                           ms=duration_ms, rms=rms_raw)
        else:
            # WRITE-AHEAD first, enqueue second — always this order (K8 law)
            rec = self.spool.write_ahead(
                pcm, seg_id=seg_id, t_start=t_start, t_end=t_end,
                duration_ms=duration_ms, rms_raw=rms_raw, gain=gain)
            self.spool.enqueue(rec)
            self.segments_enqueued += 1
            self._on_event("SEG", id=seg_id, ms=duration_ms,
                           rms=rms_raw, gain=gain)

        # continue or rest
        if split:
            self._in_seg = True
            self._buf = [overlap] if overlap is not None and len(overlap) else []
            self._seg_samples = len(overlap) if overlap is not None else 0
            self._silent_samples = 0
        else:
            self._in_seg = False
            self._buf = []
            self._seg_samples = 0
            self._silent_samples = 0
        return rec
