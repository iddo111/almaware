"""KESHEV streaming FIR resampler — K7 (PHASE2-DESIGN.md section 2;
PHASE1-INQUIRY.md section 2, scar 24).

  scar 24  Open at the format the device accepts, then resample to 16kHz
           in-callback with an anti-aliasing windowed-sinc FIR (cutoff
           ~0.45 x 16k, state carried across callbacks). Why: BRIO rejects
           forced 16kHz (-9997); aliased HF energy makes Whisper
           hallucinate; FIR discontinuities click at seams.

The MATH here is ported as knowledge from the proven alma-mic audio.py
streaming resampler (windowed-sinc Hamming low-pass + fractional-position
linear interpolation with carry state across chunks). This is clean new
code, and it FIXES a latent bound bug in the original: the old
`k_max = floor((n-1-pos)/step)+1` let the interpolation read `buf[n]` when
`(n-1-pos)` was an exact multiple of the step (e.g. a 1024-sample chunk at
step=3) — masked in alma-mic only because its block size happened to be
1440. Here the last buffer sample is never used as a left neighbour; it is
carried to the next chunk instead, so the out-of-range read cannot occur
for any chunk size (regression-tested in tests/test_resample.py).

Pure numpy, no scipy, no sounddevice — this module never touches a device.
"""
from __future__ import annotations

import numpy as np

TARGET_RATE = 16_000       # the one pipeline rate downstream of capture
CUTOFF_FRACTION = 0.45     # scar 24: anti-alias cutoff = 0.45 x out_rate
FIR_TAPS = 101             # odd -> symmetric kernel, linear phase


def design_lowpass(cutoff_hz: float, fs: int, numtaps: int = FIR_TAPS) -> np.ndarray:
    """Windowed-sinc FIR low-pass (Hamming window). Linear phase, unity DC
    gain. Ported as knowledge from alma-mic `_design_lowpass`."""
    wc = min(0.99, cutoff_hz / (fs / 2.0))          # cutoff as fraction of Nyquist
    n = np.arange(numtaps) - (numtaps - 1) / 2.0
    h = wc * np.sinc(wc * n) * np.hamming(numtaps)
    h /= h.sum()                                    # unity DC
    return h.astype(np.float32)


class StreamingResampler:
    """Streaming resampler: mono float32 in, mono float32 out, continuous
    phase across chunk boundaries (no clicks at seams — scar 24).

    When downsampling, an anti-alias FIR runs first (with carry state) so
    energy above the output Nyquist cannot fold back into the speech band.
    Pass-through when in_rate == out_rate.
    """

    def __init__(self, in_rate: int, out_rate: int = TARGET_RATE):
        if in_rate <= 0 or out_rate <= 0:
            raise ValueError(f"rates must be positive: {in_rate} -> {out_rate}")
        self.in_rate = int(in_rate)
        self.out_rate = int(out_rate)
        self._step = self.in_rate / self.out_rate   # input samples per output sample
        self._buf = np.empty(0, dtype=np.float32)   # unconsumed (filtered) input tail
        self._pos = 0.0                              # fractional read position in _buf
        if self.in_rate > self.out_rate:             # anti-alias only when downsampling
            self._fir = design_lowpass(CUTOFF_FRACTION * self.out_rate, self.in_rate)
            self._fir_state = np.zeros(len(self._fir) - 1, dtype=np.float32)
        else:
            self._fir = None
            self._fir_state = None

    def _antialias(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self._fir_state, x])
        y = np.convolve(buf, self._fir, mode="valid")   # exactly len(x) samples out
        self._fir_state = buf[-(len(self._fir) - 1):]
        return y.astype(np.float32, copy=False)

    def process(self, x: np.ndarray) -> np.ndarray:
        """Feed one chunk (any size, including 0 or 1 samples); returns the
        16k samples producible so far. State carries across calls."""
        if self.in_rate == self.out_rate:
            return np.ascontiguousarray(x, dtype=np.float32)
        x = np.asarray(x, dtype=np.float32)
        if len(x) and self._fir is not None:
            x = self._antialias(x)
        self._buf = np.concatenate([self._buf, x])
        n = len(self._buf)
        if n < 2:
            return np.empty(0, dtype=np.float32)

        # Produce outputs only while the RIGHT interpolation neighbour is
        # strictly inside the buffer: left index <= n-2, so buf[i0+1] is
        # always valid. (The bound fix over the alma-mic original — a
        # position landing exactly on the final sample is deferred to the
        # next chunk, where that sample is the carried tail.)
        k_max = int(np.floor((n - 2 - self._pos) / self._step)) + 1
        if k_max <= 0:
            return np.empty(0, dtype=np.float32)
        idx = self._pos + self._step * np.arange(k_max)
        i0 = np.floor(idx).astype(np.int64)
        frac = (idx - i0).astype(np.float32)
        out = self._buf[i0] * (1.0 - frac) + self._buf[i0 + 1] * frac

        # consume fully-read input; keep the tail the next output still needs
        nxt = self._pos + self._step * k_max     # position of the NEXT output
        consume = min(int(np.floor(nxt)), n)     # never slice past the buffer
        self._buf = self._buf[consume:]
        self._pos = nxt - consume
        return out.astype(np.float32, copy=False)
