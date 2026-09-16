"""K7 acceptance tests for client/resample.py — written FIRST (TDD).

PHASE2-DESIGN.md K7 row + section 2 resample.py spec; PHASE1-INQUIRY.md
section 2, scar 24:

  scar 24  resample to 16kHz in-callback with an anti-aliasing windowed-sinc
           FIR (cutoff ~0.45x16k, state carried across callbacks). Aliased
           HF energy makes Whisper hallucinate; FIR discontinuities click
           at seams.

The math is ported as KNOWLEDGE from the proven alma-mic audio.py streaming
resampler (windowed-sinc Hamming FIR + fractional-position linear
interpolation with carry state) — this is clean new code, tested on golden
vectors. ALL tests are synthetic-signal only: no device, no audio output,
no alma-mic process touched (wave guardrails 1-3).

Golden-vector acceptance (K7 row):
  - 12kHz tone at 48k input is ATTENUATED in the 16k output (anti-alias);
  - 1kHz tone is PRESERVED (amplitude and frequency);
  - phase is CONTINUOUS across chunk boundaries (chunked == single-pass,
    no seam clicks);
  - 48k -> 16k.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client import resample  # noqa: E402
from client.resample import StreamingResampler, design_lowpass  # noqa: E402

TARGET = 16_000


# ---------------------------------------------------------------- helpers

def tone(freq_hz: float, dur_s: float, fs: int, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(dur_s * fs), dtype=np.float64) / fs
    return (amp * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


def rms(x: np.ndarray) -> float:
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def db(ratio: float) -> float:
    return 20.0 * np.log10(max(ratio, 1e-12))


def spectrum_amplitude(x: np.ndarray, fs: int, freq_hz: float) -> float:
    """Amplitude of the spectral component nearest freq_hz (rectangular FFT,
    fine for the exact-bin golden tones used here)."""
    n = len(x)
    spec = np.abs(np.fft.rfft(x.astype(np.float64))) * 2.0 / n
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    return float(spec[int(np.argmin(np.abs(freqs - freq_hz)))])


def resample_all(r: StreamingResampler, x: np.ndarray) -> np.ndarray:
    return r.process(x)


def skip_transient(y: np.ndarray, n: int = 400) -> np.ndarray:
    """Drop the FIR warm-up transient before measuring."""
    return y[n:]


# ---------------------------------------------------------------- FIR design

class FirDesignTests(unittest.TestCase):
    def test_unity_dc_gain(self):
        h = design_lowpass(7200.0, 48_000)
        self.assertAlmostEqual(float(h.sum()), 1.0, places=5)

    def test_float32(self):
        h = design_lowpass(7200.0, 48_000)
        self.assertEqual(h.dtype, np.float32)

    def test_linear_phase_symmetry(self):
        h = design_lowpass(7200.0, 48_000)
        np.testing.assert_allclose(h, h[::-1], atol=1e-7)

    def test_default_taps_odd(self):
        # odd tap count -> integral group delay, symmetric kernel
        h = design_lowpass(7200.0, 48_000)
        self.assertEqual(len(h) % 2, 1)


# ---------------------------------------------------------------- golden vectors

class GoldenVector48kTo16kTests(unittest.TestCase):
    """The K7 acceptance golden vectors, 48k -> 16k."""

    def test_1khz_tone_preserved_amplitude(self):
        x = tone(1000.0, 2.0, 48_000, amp=0.5)
        y = skip_transient(StreamingResampler(48_000, TARGET).process(x))
        self.assertGreater(len(y), TARGET)  # got real output
        # amplitude within 5% of the input tone's
        self.assertAlmostEqual(rms(y), rms(x), delta=0.05 * rms(x))

    def test_1khz_tone_preserved_frequency(self):
        x = tone(1000.0, 2.0, 48_000, amp=0.5)
        y = skip_transient(StreamingResampler(48_000, TARGET).process(x))
        n = len(y)
        freqs = np.fft.rfftfreq(n, d=1.0 / TARGET)
        peak = freqs[int(np.argmax(np.abs(np.fft.rfft(y))))]
        self.assertAlmostEqual(peak, 1000.0, delta=5.0)

    def test_12khz_tone_attenuated(self):
        # 12kHz is above the 16k-output Nyquist (8k): without the anti-alias
        # FIR it would fold to 4kHz and feed Whisper hallucinations (scar 24).
        x = tone(12_000.0, 2.0, 48_000, amp=0.5)
        y = skip_transient(StreamingResampler(48_000, TARGET).process(x))
        atten_db = db(rms(y) / rms(x))
        self.assertLessEqual(atten_db, -30.0,
                             f"12kHz leaked through: {atten_db:.1f} dB")

    def test_12khz_alias_image_suppressed(self):
        # the fold-back image of 12k at fs_out=16k lands at 4kHz — assert the
        # 4kHz bin of the output is tiny relative to the input amplitude.
        x = tone(12_000.0, 2.0, 48_000, amp=0.5)
        y = skip_transient(StreamingResampler(48_000, TARGET).process(x))
        image = spectrum_amplitude(y, TARGET, 4000.0)
        self.assertLessEqual(db(image / 0.5), -30.0,
                             f"4kHz alias image present: {db(image / 0.5):.1f} dB")

    def test_mixed_signal_keeps_speech_kills_alias(self):
        # 1k (speech band) + 12k (alias source) together: 1k survives intact,
        # 12k and its 4k image are both suppressed.
        x = tone(1000.0, 2.0, 48_000, amp=0.3) + tone(12_000.0, 2.0, 48_000, amp=0.3)
        y = skip_transient(StreamingResampler(48_000, TARGET).process(x))
        a1k = spectrum_amplitude(y, TARGET, 1000.0)
        a4k = spectrum_amplitude(y, TARGET, 4000.0)
        self.assertAlmostEqual(a1k, 0.3, delta=0.03)          # preserved
        self.assertLessEqual(db(a4k / 0.3), -30.0)            # alias killed

    def test_output_length_ratio(self):
        x = tone(440.0, 1.0, 48_000)
        y = StreamingResampler(48_000, TARGET).process(x)
        self.assertAlmostEqual(len(y), len(x) / 3.0, delta=8)

    def test_output_dtype_float32(self):
        y = StreamingResampler(48_000, TARGET).process(tone(440.0, 0.1, 48_000))
        self.assertEqual(y.dtype, np.float32)


# ---------------------------------------------------------------- chunk continuity

class ChunkContinuityTests(unittest.TestCase):
    """State carried across callback boundaries — no seams, no clicks (scar 24)."""

    def _chunked(self, x: np.ndarray, sizes) -> np.ndarray:
        r = StreamingResampler(48_000, TARGET)
        out, i = [], 0
        it = iter(sizes)
        while i < len(x):
            n = next(it)
            out.append(r.process(x[i:i + n]))
            i += n
        return np.concatenate(out)

    def test_chunked_equals_single_pass(self):
        rng = np.random.default_rng(7)
        x = tone(1000.0, 1.5, 48_000)
        single = StreamingResampler(48_000, TARGET).process(x)
        sizes = iter(lambda: int(rng.integers(32, 1441)), None)
        chunked = self._chunked(x, sizes)
        n = min(len(single), len(chunked))
        self.assertGreater(n, TARGET)
        np.testing.assert_allclose(chunked[:n], single[:n], atol=1e-4)
        # any residual tail is bounded by one interpolation step
        self.assertLessEqual(abs(len(single) - len(chunked)), 4)

    def test_no_seam_clicks(self):
        # a click at a chunk seam is a sample-to-sample jump far above the
        # tone's own maximum derivative. 1kHz@16k max delta = 2*pi*f/fs*amp.
        x = tone(1000.0, 2.0, 48_000, amp=0.5)
        sizes = iter(lambda: 333, None)   # deliberately awkward, non-divisor size
        y = skip_transient(self._chunked(x, sizes))
        max_delta = float(np.max(np.abs(np.diff(y))))
        theoretical = 2.0 * np.pi * 1000.0 / TARGET * 0.5
        self.assertLessEqual(max_delta, 1.5 * theoretical,
                             f"seam click: delta {max_delta:.4f} vs tone max {theoretical:.4f}")

    def test_exact_multiple_chunk_regression(self):
        # KNOWLEDGE-PORT FIX: the alma-mic original indexed buf[n] when
        # (len-1) was divisible by the step (e.g. a 1024-sample chunk at
        # step=3) — masked in production only by its 1440 block size.
        # The clean code must survive every such size.
        r = StreamingResampler(48_000, TARGET)
        x = tone(1000.0, 1.0, 48_000)
        out = []
        for size in (1024, 1024, 7, 4, 1, 1024, 100, 999):
            out.append(r.process(x[:size]))  # sizes with (n-1) % 3 == 0 included
        self.assertTrue(all(o.dtype == np.float32 for o in out))

    def test_tiny_chunks_accumulate(self):
        # 1-sample feeds must never crash and must eventually produce output
        r = StreamingResampler(48_000, TARGET)
        x = tone(1000.0, 0.02, 48_000)
        total = sum(len(r.process(x[i:i + 1])) for i in range(len(x)))
        self.assertAlmostEqual(total, len(x) / 3.0, delta=8)


# ---------------------------------------------------------------- other rates

class OtherRateTests(unittest.TestCase):
    def test_passthrough_same_rate(self):
        x = tone(1000.0, 0.5, TARGET)
        y = StreamingResampler(TARGET, TARGET).process(x)
        np.testing.assert_allclose(y, x, atol=1e-7)

    def test_44100_to_16000_non_integer_ratio(self):
        x = tone(1000.0, 2.0, 44_100, amp=0.5)
        y = skip_transient(StreamingResampler(44_100, TARGET).process(x))
        self.assertAlmostEqual(rms(y), rms(x), delta=0.05 * rms(x))
        freqs = np.fft.rfftfreq(len(y), d=1.0 / TARGET)
        peak = freqs[int(np.argmax(np.abs(np.fft.rfft(y))))]
        self.assertAlmostEqual(peak, 1000.0, delta=5.0)

    def test_44100_length_ratio(self):
        x = tone(440.0, 1.0, 44_100)
        y = StreamingResampler(44_100, TARGET).process(x)
        self.assertAlmostEqual(len(y), len(x) * TARGET / 44_100, delta=8)

    def test_instances_are_isolated(self):
        a = StreamingResampler(48_000, TARGET)
        b = StreamingResampler(48_000, TARGET)
        a.process(tone(1000.0, 0.1, 48_000))
        # b has seen nothing: its first output matches a fresh instance's
        fresh = StreamingResampler(48_000, TARGET).process(tone(500.0, 0.1, 48_000))
        np.testing.assert_allclose(b.process(tone(500.0, 0.1, 48_000)), fresh, atol=1e-7)

    def test_empty_input(self):
        r = StreamingResampler(48_000, TARGET)
        self.assertEqual(len(r.process(np.empty(0, dtype=np.float32))), 0)

    def test_cutoff_constant_pinned(self):
        # design constant: cutoff = 0.45 x out_rate (scar 24)
        self.assertAlmostEqual(resample.CUTOFF_FRACTION, 0.45)


if __name__ == "__main__":
    unittest.main(verbosity=2)
