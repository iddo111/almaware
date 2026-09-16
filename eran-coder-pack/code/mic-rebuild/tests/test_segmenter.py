"""K8 TDD tests — client/segmenter.py (PHASE2-DESIGN.md section 2 segmenter
row; PHASE1-INQUIRY.md scars 26/27, risk-ledger item 6; K8 acceptance row).

The layered order under test (scar 27, exactly):
  (1) energy gate drops silence pre-model — silence is 100% gated;
  (2) auto-gain peak-normalizes quiet-real speech ONLY when original
      rms >= floor (0.004), gain capped at 40x, never attenuates;
  (3) webrtcvad pre-enqueue — with the risk-6 FAINT-BAND BYPASS, decided
      here at K8 on measured evidence: real webrtcvad at aggressiveness 2
      rejects faint speech below ~0.003 rms (measured 2026-08-12 on
      synthetic vectors: saw@amp0.005/rms0.0029 -> 3/66 speech frames;
      amp0.003/rms0.0017 -> 0/66), which is exactly the 0.002-0.005 band
      the K8 acceptance row protects. Per risk item 6 the segmenter falls
      back to energy-gate-only for that band: the VAD verdict applies only
      when post-gain rms >= the auto-gain floor; fainter segments ride to
      the decoder, where Silero-inside-HE-decode + decode guards are the
      next layers (scar 27 permits this ordering).

Segment close => spool WRITE-AHEAD then enqueue (order proven with a spy);
max 28s with a 0.5s overlap split; criterion 14's pipeline half (device gap
-> flush -> resume without object reconstruction) is here — its device-open
audit half lives in K6, its live replug half is K5-gated.

Synthetic streams only. No device, no audio output, no alma-mic.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.segmenter import (  # noqa: E402
    AUTOGAIN_MAX,
    AUTOGAIN_RMS_FLOOR,
    AUTOGAIN_TARGET_PEAK,
    CLOSE_SILENCE_MS,
    MAX_SEGMENT_S,
    SPLIT_OVERLAP_S,
    Segmenter,
    SegmenterDependencyError,
    make_default_vad,
)
from client.spool import Spool  # noqa: E402

RATE = 16000
FRAME = 480  # 30ms @ 16k — the capture layer's block size (K7)
GATE = 0.004  # the config example's calibrated gate (config/client.json)


def _webrtcvad_available() -> bool:
    try:
        import webrtcvad  # noqa: F401
        return True
    except ImportError:
        return False


# ------------------------------------------------------------- signal fixtures

def frames_of(sig: np.ndarray):
    """Split a float32 signal into 30ms capture frames (dropping any tail)."""
    sig = sig.astype(np.float32)
    return [sig[i:i + FRAME] for i in range(0, len(sig) - FRAME + 1, FRAME)]


def saw(seconds: float, amp: float, freq: float = 120.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (amp * (2 * ((freq * t) % 1.0) - 1.0)).astype(np.float32)


def square(seconds: float, amp: float, freq: float = 120.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (amp * np.sign(np.sin(2 * np.pi * freq * t))).astype(np.float32)


def silence(seconds: float, rms: float = 0.0005, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(seconds * RATE)) * rms).astype(np.float32)


def faint_speech(seconds: float = 2.0) -> np.ndarray:
    """The K8 acceptance band: overall rms inside 0.002-0.005, with syllabic
    150ms voiced (frame rms ~0.0046, crosses the 0.004 gate) / 150ms quiet
    alternation — like real faint speech, loud syllables carry the words."""
    out = []
    n_syllable = int(0.150 * RATE)
    for k in range(int(seconds / 0.150)):
        amp = 0.008 if k % 2 == 0 else 0.002
        out.append(saw(0.150, amp)[:n_syllable])
    return np.concatenate(out)


def accept_all_vad(frame_bytes: bytes) -> bool:
    return True


def reject_all_vad(frame_bytes: bytes) -> bool:
    return False


# ------------------------------------------------------------------- harness

def make(tmp: Path, *, vad=accept_all_vad, gate: float = GATE,
         session: str = "a3f9c2d1", on_event=None):
    spool = Spool(tmp / "spool", on_event=on_event)
    seg = Segmenter(spool, gate_rms=gate, session_id=session,
                    vad=vad, on_event=on_event)
    return seg, spool


def feed_all(seg: Segmenter, sig: np.ndarray) -> list:
    recs = []
    for f in frames_of(sig):
        recs.extend(seg.feed(f))
    return recs


def read_wav_samples(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2")


class Constants(unittest.TestCase):
    def test_design_constants(self):
        self.assertEqual(MAX_SEGMENT_S, 28.0)       # design sec 2: max 28s
        self.assertEqual(SPLIT_OVERLAP_S, 0.5)      # split w/ 0.5s overlap
        self.assertEqual(AUTOGAIN_RMS_FLOOR, 0.004)  # scar 27 floor
        self.assertEqual(AUTOGAIN_MAX, 40.0)        # scar 27 cap 40x


class EnergyGate(unittest.TestCase):
    def test_silence_is_100pct_gated(self):
        """5s of ambient-level noise (rms 0.0005 — the measured-floor class):
        zero segments, zero spool files, and the gating is COUNTED."""
        events = []
        with tempfile.TemporaryDirectory() as td:
            seg, spool = make(Path(td),
                              on_event=lambda evt, **f: events.append((evt, f)))
            recs = feed_all(seg, silence(5.0))
            recs.extend([r for r in [seg.flush()] if r])
            self.assertEqual(recs, [])
            self.assertEqual(spool.qsize(), 0)
            self.assertEqual(list((Path(td) / "spool").glob("*.wav")), [])
            self.assertGreater(seg.gated_frames, 0)
            self.assertEqual([e for e, _ in events if e == "SEG"], [])

    def test_speech_forms_one_segment_and_closes_on_hangover(self):
        events = []
        with tempfile.TemporaryDirectory() as td:
            seg, spool = make(Path(td),
                              on_event=lambda evt, **f: events.append((evt, f)))
            sig = np.concatenate([saw(1.0, 0.3), silence(1.0)])
            recs = feed_all(seg, sig)
            self.assertEqual(len(recs), 1)
            rec = recs[0]
            self.assertTrue(rec.wav_path.is_file())      # write-ahead on disk
            self.assertEqual(spool.qsize(), 1)           # and enqueued
            seg_events = [f for e, f in events if e == "SEG"]
            self.assertEqual(len(seg_events), 1)
            self.assertEqual(seg_events[0]["id"], rec.id)

    def test_faint_speech_passes_the_k8_acceptance_band(self):
        """THE K8 acceptance row: faint speech, overall rms 0.002-0.005,
        passes — with the REAL webrtcvad wired in (the faint-band bypass is
        what makes this hold; risk-ledger item 6, measured 2026-08-12)."""
        if not _webrtcvad_available():
            self.skipTest("webrtcvad not installed")
        with tempfile.TemporaryDirectory() as td:
            seg, spool = make(Path(td), vad=None)        # None -> real webrtcvad
            sig = np.concatenate([faint_speech(2.0), silence(1.0)])
            band_rms = float(np.sqrt(np.mean(np.square(faint_speech(2.0)))))
            self.assertGreaterEqual(band_rms, 0.002)     # fixture honesty
            self.assertLessEqual(band_rms, 0.005)
            recs = feed_all(seg, sig)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0].gain, 1.0)          # below auto-gain floor
            self.assertEqual(spool.qsize(), 1)


class AutoGain(unittest.TestCase):
    def test_gain_capped_at_40x(self):
        """Quiet-real speech (rms >= floor) with a tiny peak: the uncapped
        gain would be 47.5x — it must cap at exactly 40 (scar 27)."""
        with tempfile.TemporaryDirectory() as td:
            seg, _ = make(Path(td))
            sig = np.concatenate([square(1.0, 0.02), silence(1.0)])
            (rec,) = feed_all(seg, sig)
            self.assertEqual(rec.gain, AUTOGAIN_MAX)
            samples = read_wav_samples(rec.wav_path)
            peak = np.max(np.abs(samples)) / 32767.0
            self.assertAlmostEqual(peak, 0.02 * 40, delta=0.005)

    def test_gain_peak_normalizes_to_target(self):
        with tempfile.TemporaryDirectory() as td:
            seg, _ = make(Path(td))
            sig = np.concatenate([square(1.0, 0.1), silence(1.0)])
            (rec,) = feed_all(seg, sig)
            self.assertAlmostEqual(rec.gain, AUTOGAIN_TARGET_PEAK / 0.1, places=2)
            samples = read_wav_samples(rec.wav_path)
            peak = np.max(np.abs(samples)) / 32767.0
            self.assertAlmostEqual(peak, AUTOGAIN_TARGET_PEAK, delta=0.01)

    def test_floor_respected_below_floor_no_gain(self):
        """The scar-27 floor: a segment whose original rms is BELOW 0.004
        gets NO amplification — amplified ambient noise typed חחח all night."""
        with tempfile.TemporaryDirectory() as td:
            seg, _ = make(Path(td))
            sig = np.concatenate([faint_speech(2.0), silence(1.0)])
            (rec,) = feed_all(seg, sig)
            self.assertEqual(rec.gain, 1.0)
            # bytes are the un-gained samples, exactly
            n = int(0.15 * RATE)
            stored = read_wav_samples(rec.wav_path)[:n].astype(np.float32) / 32767.0
            original = faint_speech(2.0)[:n]
            self.assertLess(float(np.max(np.abs(stored - original))), 1.5 / 32767.0)

    def test_never_attenuates(self):
        with tempfile.TemporaryDirectory() as td:
            seg, _ = make(Path(td))
            sig = np.concatenate([square(1.0, 0.99), silence(1.0)])
            (rec,) = feed_all(seg, sig)
            self.assertEqual(rec.gain, 1.0)


class VadPreEnqueue(unittest.TestCase):
    def test_loud_vad_reject_drops_with_gated_event_and_no_file(self):
        """A LOUD segment (post-gain rms >= floor) that the VAD rejects is
        dropped BEFORE the spool — with a GATED line (scar 18), never
        silently. Its consumed id appears in the event for archaeology."""
        events = []
        with tempfile.TemporaryDirectory() as td:
            seg, spool = make(Path(td), vad=reject_all_vad,
                              on_event=lambda evt, **f: events.append((evt, f)))
            recs = feed_all(seg, np.concatenate([saw(1.0, 0.3), silence(1.0)]))
            self.assertEqual(recs, [])
            self.assertEqual(spool.qsize(), 0)
            self.assertEqual(list((Path(td) / "spool").glob("*.wav")), [])
            gated = [f for e, f in events if e == "GATED"]
            self.assertEqual(len(gated), 1)
            self.assertEqual(gated[0]["reason"], "vad")
            self.assertEqual(gated[0]["id"], "a3f9c2d1-000001")

    def test_faint_band_bypasses_vad(self):
        """Risk-6 fallback: below the floor the VAD verdict must NOT apply —
        even a reject-everything VAD cannot eat faint speech."""
        with tempfile.TemporaryDirectory() as td:
            seg, spool = make(Path(td), vad=reject_all_vad)
            recs = feed_all(seg, np.concatenate([faint_speech(2.0), silence(1.0)]))
            self.assertEqual(len(recs), 1)
            self.assertEqual(spool.qsize(), 1)

    def test_vad_dropped_id_is_consumed_next_segment_gets_next_id(self):
        with tempfile.TemporaryDirectory() as td:
            calls = {"n": 0}

            def flaky_vad(frame: bytes) -> bool:
                return calls["n"] > 0   # reject the first segment's frames only

            seg, spool = make(Path(td), vad=flaky_vad)
            feed_all(seg, np.concatenate([saw(1.0, 0.3), silence(1.0)]))
            self.assertEqual(spool.qsize(), 0)            # first was VAD-dropped
            calls["n"] = 1
            (rec,) = feed_all(seg, np.concatenate([saw(1.0, 0.3), silence(1.0)]))
            self.assertEqual(rec.id, "a3f9c2d1-000002")   # 000001 was consumed

    def test_default_vad_is_webrtcvad_and_missing_dep_fails_loudly(self):
        """Scar 6: a missing dependency is a VISIBLE error at construction,
        never a silent degradation."""
        if _webrtcvad_available():
            vad = make_default_vad()
            frame = (square(0.03, 0.3) * 32767).astype("<i2").tobytes()
            self.assertIsInstance(vad(frame), bool)
        blocked = sys.modules.get("webrtcvad")
        sys.modules["webrtcvad"] = None   # forces ImportError on import
        try:
            with self.assertRaises(SegmenterDependencyError):
                make_default_vad()
        finally:
            if blocked is None:
                sys.modules.pop("webrtcvad", None)
            else:
                sys.modules["webrtcvad"] = blocked


class WriteAheadOrder(unittest.TestCase):
    def test_write_ahead_strictly_before_enqueue(self):
        """THE K8 law at the segmenter call site: for every id,
        write_ahead completes before enqueue is even called."""
        order: list[tuple[str, str]] = []

        class SpySpool(Spool):
            def write_ahead(self, pcm, **kw):
                rec = super().write_ahead(pcm, **kw)
                order.append(("write", rec.id))
                return rec

            def enqueue(self, rec):
                # the write must already be REAL on disk
                assert rec.wav_path.is_file() and rec.sidecar_path.is_file()
                order.append(("enqueue", rec.id))
                return super().enqueue(rec)

        with tempfile.TemporaryDirectory() as td:
            spool = SpySpool(Path(td) / "spool")
            seg = Segmenter(spool, gate_rms=GATE, session_id="a3f9c2d1",
                            vad=accept_all_vad)
            sig = np.concatenate([saw(1.0, 0.3), silence(1.0),
                                  saw(1.0, 0.3), silence(1.0)])
            recs = feed_all(seg, sig)
            self.assertEqual(len(recs), 2)
            for rec in recs:
                w = order.index(("write", rec.id))
                e = order.index(("enqueue", rec.id))
                self.assertLess(w, e)


class MaxLengthSplit(unittest.TestCase):
    def test_28s_split_with_half_second_overlap(self):
        """65s of continuous speech: every segment <= 28s, consecutive
        segments share EXACTLY 0.5s of identical samples (design sec 2 —
        run-ons split so no word at a boundary is lost)."""
        with tempfile.TemporaryDirectory() as td:
            seg, spool = make(Path(td))
            recs = feed_all(seg, square(65.0, 0.3))
            tail = seg.flush()
            if tail:
                recs.append(tail)
            self.assertGreaterEqual(len(recs), 3)
            overlap_n = int(SPLIT_OVERLAP_S * RATE)
            total = 0
            for rec in recs:
                self.assertLessEqual(rec.duration_ms, MAX_SEGMENT_S * 1000)
                total += rec.duration_ms
            for a, b in zip(recs, recs[1:]):
                sa = read_wav_samples(a.wav_path)
                sb = read_wav_samples(b.wav_path)
                np.testing.assert_array_equal(sa[-overlap_n:], sb[:overlap_n])
            # nothing lost: segments (minus overlaps) cover the whole signal
            covered = total - (len(recs) - 1) * SPLIT_OVERLAP_S * 1000
            self.assertAlmostEqual(covered, 65_000, delta=100)

    def test_ids_are_session_scoped_and_monotonic(self):
        with tempfile.TemporaryDirectory() as td:
            seg, _ = make(Path(td))
            recs = feed_all(seg, square(65.0, 0.3))
            tail = seg.flush()
            if tail:
                recs.append(tail)
            self.assertEqual([r.id for r in recs],
                             [f"a3f9c2d1-{i:06d}" for i in range(1, len(recs) + 1)])


class Criterion14PipelineHalf(unittest.TestCase):
    """Criterion 14, the pipeline half testable with synthetic streams:
    device disappears mid-speech -> flush preserves the open segment;
    device returns -> the SAME segmenter object resumes, no restart.
    (The device-open audit half is K6's; the live replug is K5-gated.)"""

    def test_unplug_flush_replug_resume_without_restart(self):
        with tempfile.TemporaryDirectory() as td:
            seg, spool = make(Path(td))
            # speaking, then the BRIO vanishes mid-utterance
            for f in frames_of(saw(1.0, 0.3)):
                seg.feed(f)
            rec1 = seg.flush()                    # capture owner's unplug path
            self.assertIsNotNone(rec1)
            self.assertTrue(rec1.wav_path.is_file())
            # replug: same object keeps working
            recs2 = feed_all(seg, np.concatenate([saw(1.0, 0.3), silence(1.0)]))
            self.assertEqual(len(recs2), 1)
            self.assertEqual(spool.qsize(), 2)
            self.assertEqual(rec1.id, "a3f9c2d1-000001")
            self.assertEqual(recs2[0].id, "a3f9c2d1-000002")

    def test_flush_with_no_open_segment_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            seg, _ = make(Path(td))
            self.assertIsNone(seg.flush())


if __name__ == "__main__":
    unittest.main(verbosity=2)
