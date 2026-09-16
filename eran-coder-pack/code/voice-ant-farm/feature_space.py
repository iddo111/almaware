"""Frame-level acoustic feature spaces for the Hebrew Voice Ant Farm (pure numpy).

Why this module exists
----------------------
The colony's original 14-dim frame vector was
    [log(frame energy), zero-crossing-rate, 12 x log(fraction of magnitude
     spectrum in 12 linear-spaced bands over 0-8 kHz)]
and it was measured to hold a 22-way held-out ceiling of 53.8% with no codebook
at all.  Before replacing the learner it was worth asking whether the geometry
of that vector is the thing that is broken.  `verify_geometry.py` measures it;
this module supplies the replacements.

Everything here is:
  * pure numpy (no torch, no scipy, no GPU),
  * deterministic and stateless -- a feature set is a pure function of one
    waveform, so two ants that never share weights still agree on what a frame
    *is*,
  * vectorised over frames, because the corpus is 40+ hours.

`legacy14` is a bit-comparable reimplementation of acoustic_units.features and
exists so that every comparison in state-hebbian/ runs through one code path.

Nothing in here reads a label.  Labels are a scoring key only.

What was measured
-----------------
verify_geometry.py, on 19.6k syllable frames and 85k frames of the 40.6 h human
corpus:
  * log-energy is 1 of 14 dimensions and holds 45-56% of the total variance;
  * Euclidean distance between random frame pairs correlates r = 0.86-0.91 with
    |delta log-energy|;
  * a fitted k=256 partition explains 98.7% of the log-energy variance and
    86.8% of the band variance -- k-means does sort by loudness first;
  * turning one file down 6 dB moves it 26% of the way to a different syllable,
    and 76% of the way at 18 dB.
The mechanism GLM named is not the one operating: acoustic_units.features
normalises the magnitude spectrum before taking the 12 bands, so the bands are
already level-invariant and deleting column 0 makes the gain sweep exactly
zero.  All of the loudness sensitivity is in that one column.

feature_bakeoff.py, leave-one-base-out inside the train split (396 items, the
held-out split untouched during selection), then one shot on held-out:
  legacy14        CV 57.1%   held-out 53.8%   ba/pa 41.7%   da/ta 58.3%
  recommended26   CV 76.3%   held-out 66.7%   ba/pa 58.3%   da/ta 91.7%
  ... and, pooled over all eight minimal pairs, 79.2% -> 89.6% held-out.
Per-utterance CMVN is catastrophic on this corpus (held-out 4.5%, i.e. chance):
these are single-syllable files, so the utterance mean IS the phone.

state-hebbian/gain-robustness.py, held-out audio only, wider gain than the
corpus ever contained:
  logmel26       43.9% -> 23.5% as the jitter widens to 30 dB
  recommended26  66.7% -> 66.7%, unchanged, because it is invariant by
                 construction rather than by luck.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RATE = 16_000
FRAME_SECONDS = 0.025
HOP_SECONDS = 0.010
FRAME = round(RATE * FRAME_SECONDS)   # 400
HOP = round(RATE * HOP_SECONDS)       # 160
EPS = 1e-8


# --------------------------------------------------------------------------
# framing
# --------------------------------------------------------------------------

def frame_signal(samples: np.ndarray, frame: int = FRAME, hop: int = HOP) -> np.ndarray:
    """(n_frames, frame) view-free copy, identical geometry to acoustic_units."""
    samples = np.asarray(samples, dtype=np.float32)
    if len(samples) < frame:
        raise ValueError("not enough samples for one frame")
    count = 1 + (len(samples) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    return samples[idx]


def windowed(samples: np.ndarray) -> np.ndarray:
    return frame_signal(samples) * np.hanning(FRAME).astype(np.float32)


def log_energy(samples: np.ndarray) -> np.ndarray:
    """The colony's own log-energy column; used for the shared speech-span mask."""
    x = windowed(samples)
    return np.log(np.mean(x * x, axis=1, dtype=np.float32) + EPS)


# --------------------------------------------------------------------------
# spectra
# --------------------------------------------------------------------------

def power_spectrum(samples: np.ndarray, n_fft: int = 512,
                   preemphasis: float = 0.0) -> np.ndarray:
    """(n_frames, n_fft//2+1) power spectrum of Hann-windowed frames."""
    s = np.asarray(samples, dtype=np.float32)
    if preemphasis:
        s = np.concatenate([s[:1], s[1:] - preemphasis * s[:-1]]).astype(np.float32)
    x = frame_signal(s) * np.hanning(FRAME).astype(np.float32)
    spec = np.fft.rfft(x, n_fft, axis=1)
    return (spec.real ** 2 + spec.imag ** 2)


def hz_to_mel(f: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def mel_to_hz(m: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)


def mel_filterbank(n_mels: int = 26, n_fft: int = 512, rate: int = RATE,
                   fmin: float = 50.0, fmax: float = 8000.0) -> np.ndarray:
    """(n_mels, n_fft//2+1) triangular, area-normalised mel filters."""
    bins = n_fft // 2 + 1
    freqs = np.linspace(0.0, rate / 2.0, bins)
    edges = mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels + 2))
    fb = np.zeros((n_mels, bins), dtype=np.float64)
    for i in range(n_mels):
        lo, mid, hi = edges[i], edges[i + 1], edges[i + 2]
        rising = (freqs - lo) / max(mid - lo, 1e-9)
        falling = (hi - freqs) / max(hi - mid, 1e-9)
        fb[i] = np.clip(np.minimum(rising, falling), 0.0, None)
    total = fb.sum(axis=1, keepdims=True)
    return fb / np.maximum(total, 1e-9)


def dct2_matrix(n_out: int, n_in: int) -> np.ndarray:
    """Orthonormal DCT-II, (n_out, n_in)."""
    n = np.arange(n_in)[None, :]
    k = np.arange(n_out)[:, None]
    m = np.cos(np.pi * k * (2 * n + 1) / (2 * n_in)) * np.sqrt(2.0 / n_in)
    m[0] *= np.sqrt(0.5)
    return m


# --------------------------------------------------------------------------
# linear prediction
# --------------------------------------------------------------------------

def lpc(frames: np.ndarray, order: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """Batched Levinson-Durbin.  Returns (a, gain) with a[:, 0] == 1."""
    n, length = frames.shape
    n_fft = 1 << int(np.ceil(np.log2(2 * length)))
    spec = np.fft.rfft(frames, n_fft, axis=1)
    r = np.fft.irfft(spec.real ** 2 + spec.imag ** 2, n_fft, axis=1)[:, :order + 1]
    r = r.copy()
    r[:, 0] = r[:, 0] * 1.0001 + 1e-9          # ridge: keeps A(z) minimum-phase
    a = np.zeros((n, order + 1), dtype=np.float64)
    a[:, 0] = 1.0
    err = r[:, 0].copy()
    for i in range(1, order + 1):
        acc = r[:, i].copy()
        if i > 1:
            acc += np.sum(a[:, 1:i] * r[:, i - 1:0:-1], axis=1)
        k = -acc / np.maximum(err, 1e-12)
        k = np.clip(k, -0.999999, 0.999999)
        prev = a[:, 1:i].copy()
        if i > 1:
            a[:, 1:i] = prev + k[:, None] * prev[:, ::-1]
        a[:, i] = k
        err = err * (1.0 - k * k)
        err = np.maximum(err, 1e-12)
    return a, np.sqrt(err)


def lpc_envelope(a: np.ndarray, gain: np.ndarray, n_fft: int = 512) -> np.ndarray:
    """(n_frames, n_fft//2+1) power of the all-pole envelope G^2/|A(w)|^2."""
    A = np.fft.rfft(a, n_fft, axis=1)
    denom = A.real ** 2 + A.imag ** 2
    return (gain[:, None] ** 2) / np.maximum(denom, 1e-12)


def formants(a: np.ndarray, n: int = 3, rate: int = RATE) -> np.ndarray:
    """(n_frames, 2n): [F1..Fn (kHz), B1..Bn (kHz)] from the LPC roots.

    Roots inside the unit circle with 90 Hz < f < 5 kHz and bandwidth < 1 kHz,
    sorted by frequency.  Missing formants are filled with the last one found
    (never with zero, which would put an off-manifold point in the middle of
    the vowel space).
    """
    order = a.shape[1] - 1
    n_frames = a.shape[0]
    companion = np.zeros((n_frames, order, order), dtype=np.float64)
    companion[:, 0, :] = -a[:, 1:] / a[:, :1]
    idx = np.arange(order - 1)
    companion[:, idx + 1, idx] = 1.0
    roots = np.linalg.eigvals(companion)
    angle = np.abs(np.angle(roots))
    freq = angle * rate / (2 * np.pi)
    radius = np.abs(roots)
    band = -np.log(np.maximum(radius, 1e-9)) * rate / np.pi
    ok = (np.angle(roots) > 0) & (freq > 90.0) & (freq < 5000.0) & (band < 1000.0)
    freq = np.where(ok, freq, np.inf)
    order_idx = np.argsort(freq, axis=1)
    freq = np.take_along_axis(freq, order_idx, axis=1)
    band = np.take_along_axis(np.where(ok, band, np.inf), order_idx, axis=1)
    out_f = np.empty((n_frames, n))
    out_b = np.empty((n_frames, n))
    for j in range(n):
        col_f, col_b = freq[:, j], band[:, j]
        if j == 0:
            fill_f, fill_b = 500.0, 200.0
        else:
            fill_f, fill_b = out_f[:, j - 1] + 200.0, out_b[:, j - 1]
        out_f[:, j] = np.where(np.isfinite(col_f), col_f, fill_f)
        out_b[:, j] = np.where(np.isfinite(col_b), col_b, fill_b)
    return np.concatenate([out_f / 1000.0, out_b / 1000.0], axis=1)


# --------------------------------------------------------------------------
# post-processing
# --------------------------------------------------------------------------

def voicing(samples: np.ndarray, fmin: float = 60.0, fmax: float = 400.0
            ) -> np.ndarray:
    """(n_frames, 2): [normalised autocorrelation peak, log F0 in Hz].

    The textbook voicing cue, and the one thing no cepstral feature carries.
    ba/pa and da/ta are voicing contrasts; a representation with no periodicity
    dimension is being asked to infer voicing from spectral tilt alone.
    Unvoiced frames get log F0 = log(fmin), so the column stays on-manifold.
    """
    x = windowed(samples).astype(np.float64)
    x = x - x.mean(axis=1, keepdims=True)
    n_fft = 1 << int(np.ceil(np.log2(2 * x.shape[1])))
    spec = np.fft.rfft(x, n_fft, axis=1)
    ac = np.fft.irfft(spec.real ** 2 + spec.imag ** 2, n_fft, axis=1)
    energy = np.maximum(ac[:, :1], 1e-12)
    lo, hi = int(RATE / fmax), int(RATE / fmin)
    window = ac[:, lo:hi + 1] / energy
    best = window.argmax(axis=1)
    peak = np.clip(window[np.arange(len(window)), best], 0.0, 1.0)
    f0 = RATE / (best + lo).astype(np.float64)
    voiced = peak > 0.30
    return np.stack([peak, np.log(np.where(voiced, f0, fmin))], axis=1)


def deltas(x: np.ndarray, width: int = 2) -> np.ndarray:
    """Regression-window first difference, edge-replicated.  Same shape as x."""
    if len(x) == 1:
        return np.zeros_like(x)
    pad = np.concatenate([np.repeat(x[:1], width, axis=0), x,
                          np.repeat(x[-1:], width, axis=0)], axis=0)
    out = np.zeros_like(x, dtype=np.float64)
    norm = 2.0 * sum(n * n for n in range(1, width + 1))
    for n in range(1, width + 1):
        out += n * (pad[width + n: width + n + len(x)]
                    - pad[width - n: width - n + len(x)])
    return out / norm


def cmvn(x: np.ndarray, mask: np.ndarray | None = None,
         variance: bool = True) -> np.ndarray:
    """Per-utterance mean (and optionally variance) normalisation.

    `mask` restricts the statistics to the speech span so that the amount of
    leading room tone does not move the mean.
    """
    ref = x if mask is None else x[mask]
    if len(ref) < 2:
        return x - x.mean(axis=0, keepdims=True)
    out = x - ref.mean(axis=0, keepdims=True)
    if variance:
        sd = ref.std(axis=0, keepdims=True)
        out = out / np.where(sd < 1e-6, 1.0, sd)
    return out


# --------------------------------------------------------------------------
# the feature sets
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureSet:
    name: str
    dim: int
    note: str
    fn: object          # (samples, mask) -> (n_frames, dim) float64

    def __call__(self, samples: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        return np.asarray(self.fn(samples, mask), dtype=np.float64)


def _legacy14(samples, mask=None):
    """Bit-comparable reimplementation of acoustic_units.features."""
    x = windowed(samples)
    energy = np.log(np.mean(x * x, axis=1, dtype=np.float32) + EPS)
    sign = np.signbit(x)
    zcr = np.mean(sign[:, 1:] != sign[:, :-1], axis=1)
    spectrum = np.abs(np.fft.rfft(x, axis=1)) + EPS
    spectrum = spectrum / spectrum.sum(axis=1, keepdims=True)
    bands = np.stack([np.log(part.sum(axis=1) + EPS)
                      for part in np.array_split(spectrum, 12, axis=1)], axis=1)
    return np.concatenate([energy[:, None], zcr[:, None], bands], axis=1)


_MEL26 = mel_filterbank(26)
_MEL24 = mel_filterbank(24)
_DCT13 = dct2_matrix(13, 26)


def _logmel26(samples, mask=None):
    return np.log(power_spectrum(samples, preemphasis=0.97) @ _MEL26.T + EPS)


def _mfcc13(samples, mask=None):
    return _logmel26(samples) @ _DCT13.T


def _mfcc12(samples, mask=None):
    """MFCC c1..c12: the level-free part of the cepstrum."""
    return _mfcc13(samples)[:, 1:]


def _lpc_mfcc(samples, mask=None, order: int = 12, n_out: int = 13):
    a, gain = lpc(windowed(np.concatenate(
        [np.asarray(samples, np.float32)[:1],
         np.asarray(samples, np.float32)[1:]
         - 0.97 * np.asarray(samples, np.float32)[:-1]]).astype(np.float32)), order)
    env = lpc_envelope(a, gain)
    return np.log(env @ _MEL26.T + EPS) @ dct2_matrix(n_out, 26).T


def _formants6(samples, mask=None):
    s = np.asarray(samples, np.float32)
    pre = np.concatenate([s[:1], s[1:] - 0.97 * s[:-1]]).astype(np.float32)
    a, _ = lpc(windowed(pre), 12)
    return formants(a, 3)


def _with_deltas(base):
    def fn(samples, mask=None):
        x = base(samples, mask)
        d1 = deltas(x)
        return np.concatenate([x, d1], axis=1)
    return fn


def _with_deltas2(base):
    def fn(samples, mask=None):
        x = base(samples, mask)
        d1 = deltas(x)
        d2 = deltas(d1)
        return np.concatenate([x, d1, d2], axis=1)
    return fn


def _cmvn_of(base, variance=True):
    def fn(samples, mask=None):
        return cmvn(base(samples, mask), mask, variance)
    return fn


def _legacy14_no_energy(samples, mask=None):
    return _legacy14(samples)[:, 1:]


def _legacy14_cmvn(samples, mask=None):
    return cmvn(_legacy14(samples), mask, True)


def _mel_energy_scaled(samples, mask=None, weight: float = 0.25):
    """MFCC c1..c12 + deltas, with c0 kept but attenuated to `weight`."""
    c = _mfcc13(samples)
    d = deltas(c)
    out = np.concatenate([c, d], axis=1)
    out[:, 0] *= weight
    out[:, 13] *= weight
    return out


CANONICAL = "mfcc20_mel26_pd6w4"
_CANON_FB = mel_filterbank(26, n_fft=512, fmin=50.0, fmax=8000.0)
_CANON_DCT = dct2_matrix(21, 26)[1:]           # c1..c20; c0 (level) is dropped
FLOOR_DB = 80.0                                # per-frame dynamic range


def _recommended(samples, mask=None):
    """The recommended 26-dim frame vector.  See RECOMMENDED below.

    Written out in full rather than composed from the sweep helpers, because
    every learner in the next phase depends on it and it must be readable and
    stable.  `mask` is accepted and ignored: this vector needs no per-utterance
    statistics, so an ant can featurise a frame without seeing the rest of the
    file, and two ants that never share weights still agree on what a frame is.

    The mel floor is 80 dB below each frame's own strongest band rather than an
    absolute epsilon.  An absolute floor silently reintroduces loudness -- a
    quiet frame has more bands sitting on the floor than a loud one, so the two
    stop being a constant offset apart and dropping c0 no longer removes level.
    With a relative floor the whole log-mel vector shifts by exactly
    2*log(gain) under a gain change, and c0 absorbs all of it.
    """
    power = power_spectrum(samples, n_fft=512, preemphasis=0.97)
    mel = power @ _CANON_FB.T
    mel = np.maximum(mel, mel.max(axis=1, keepdims=True) * 10.0 ** (-FLOOR_DB / 10.0))
    c = np.log(np.maximum(mel, 1e-300)) @ _CANON_DCT.T     # (n, 20)
    d = deltas(c[:, :6], width=4)                          # (n, 6), +/- 40 ms
    return np.concatenate([c, d], axis=1)


def _mfcc_cmvn_d1d2(samples, mask=None):
    c = cmvn(_mfcc13(samples), mask, variance=False)
    d1 = deltas(c)
    return np.concatenate([c, d1, deltas(d1)], axis=1)


def linear_filterbank(n_bands: int = 24, n_fft: int = 512, rate: int = RATE,
                      fmin: float = 50.0, fmax: float = 8000.0) -> np.ndarray:
    """Triangular filters on a LINEAR frequency axis: the mel control."""
    bins = n_fft // 2 + 1
    freqs = np.linspace(0.0, rate / 2.0, bins)
    edges = np.linspace(fmin, fmax, n_bands + 2)
    fb = np.zeros((n_bands, bins), dtype=np.float64)
    for i in range(n_bands):
        lo, mid, hi = edges[i], edges[i + 1], edges[i + 2]
        fb[i] = np.clip(np.minimum((freqs - lo) / max(mid - lo, 1e-9),
                                   (hi - freqs) / max(hi - mid, 1e-9)), 0.0, None)
    return fb / np.maximum(fb.sum(axis=1, keepdims=True), 1e-9)


def _logbank(fb):
    def fn(samples, mask=None):
        return np.log(power_spectrum(samples, preemphasis=0.97) @ fb.T + EPS)
    return fn


def _levelfree(base):
    """Subtract each frame's own mean across bands: removes level, keeps shape.

    This is the ablation control.  It is level-free like MFCC but the
    dimensions stay correlated, because no DCT has been applied.
    """
    def fn(samples, mask=None):
        x = base(samples, mask)
        return x - x.mean(axis=1, keepdims=True)
    return fn


def _cepstra(fb, lo: int, hi: int, lifter: float = 0.0):
    """DCT-II of a log filterbank, coefficients [lo, hi)."""
    n_bands = fb.shape[0]
    d = dct2_matrix(hi, n_bands)[lo:hi]
    weight = None
    if lifter:
        k = np.arange(lo, hi)
        weight = 1.0 + (lifter / 2.0) * np.sin(np.pi * k / lifter)

    def fn(samples, mask=None):
        c = np.log(power_spectrum(samples, preemphasis=0.97) @ fb.T + EPS) @ d.T
        return c * weight if weight is not None else c
    return fn


def _only_deltas(base, second: bool = False):
    def fn(samples, mask=None):
        d1 = deltas(base(samples, mask))
        return deltas(d1) if second else d1
    return fn


def _scaled_deltas(base, weight: float):
    def fn(samples, mask=None):
        x = base(samples, mask)
        return np.concatenate([x, weight * deltas(x)], axis=1)
    return fn


SETS: dict[str, FeatureSet] = {}


def register(name: str, dim: int, note: str, fn) -> FeatureSet:
    fs = FeatureSet(name, dim, note, fn)
    SETS[name] = fs
    return fs


register("legacy14", 14,
         "the colony's current vector: log-energy, ZCR, 12 linear log bands",
         _legacy14)
register("legacy14_noenergy", 13,
         "legacy14 with the log-energy column deleted", _legacy14_no_energy)
register("legacy14_cmvn", 14,
         "legacy14, per-utterance mean+variance normalised over the speech span",
         _legacy14_cmvn)
register("logmel26", 26,
         "log energy in 26 mel bands, 50-8000 Hz, pre-emphasis 0.97", _logmel26)
register("logmel26_cmvn", 26,
         "logmel26, per-utterance CMVN over the speech span", _cmvn_of(_logmel26))
register("mfcc13", 13, "DCT-II of logmel26, c0..c12", _mfcc13)
register("mfcc12", 12, "DCT-II of logmel26, c1..c12 (level dropped)", _mfcc12)
register("mfcc13_cmvn", 13, "mfcc13, per-utterance CMVN", _cmvn_of(_mfcc13))
register("mfcc13_d1", 26, "mfcc13 + first difference", _with_deltas(_mfcc13))
register("mfcc13_d1d2", 39, "mfcc13 + first and second differences",
         _with_deltas2(_mfcc13))
register("mfcc12_d1d2", 36, "mfcc12 (no c0) + first and second differences",
         _with_deltas2(_mfcc12))
register("mfcc13_cmvn_d1d2", 39,
         "per-utterance mean-normalised mfcc13 + d1 + d2", _mfcc_cmvn_d1d2)
register("mfcc13_energyscaled_d1", 26,
         "mfcc13 + d1 with c0 attenuated to 0.25", _mel_energy_scaled)
register("logmel26_d1d2", 78, "logmel26 + d1 + d2", _with_deltas2(_logmel26))
register("lpc_mfcc13", 13, "DCT-II of the mel-binned order-12 LPC envelope",
         _lpc_mfcc)
register("lpc_mfcc13_d1d2", 39, "lpc_mfcc13 + d1 + d2", _with_deltas2(_lpc_mfcc))
register("formants6", 6, "F1-F3 and B1-B3 from the LPC roots, in kHz", _formants6)
register("formants6_d1", 12, "formants6 + first difference", _with_deltas(_formants6))
register("legacy14_d1d2", 42, "legacy14 + d1 + d2", _with_deltas2(_legacy14))

# --- ablation: {linear, mel} x {correlated, DCT-decorrelated}, all level-free --
_LIN24 = linear_filterbank(24)
register("logmel26_levelfree", 26,
         "logmel26 minus each frame's own band-mean: level removed, dimensions "
         "still correlated", _levelfree(_logbank(_MEL26)))
register("loglin24_levelfree", 24,
         "24 LINEAR log bands minus each frame's own band-mean: the mel control",
         _levelfree(_logbank(_LIN24)))
register("lincep12", 12,
         "DCT-II of 24 linear log bands, c1..c12: decorrelated but not mel",
         _cepstra(_LIN24, 1, 13))

# --- resolution sweep around the winner -----------------------------------
for _n in (20, 26, 32, 40):
    register(f"mfcc12_mel{_n}", 12,
             f"DCT-II of {_n} mel bands, c1..c12", _cepstra(mel_filterbank(_n), 1, 13))
for _hi in (9, 17, 21):
    register(f"mfcc{_hi - 1}_mel26", _hi - 1,
             f"DCT-II of 26 mel bands, c1..c{_hi - 1}",
             _cepstra(_MEL26, 1, _hi))
register("mfcc12_lifter22", 12, "mfcc12 with a sinusoidal lifter, L=22",
         _cepstra(_MEL26, 1, 13, lifter=22.0))

# --- is the delta information there at all, or only diluted? ---------------
register("mfcc12_d1only", 12, "first difference of mfcc12, statics deleted",
         _only_deltas(_mfcc12))
register("mfcc12_d2only", 12, "second difference of mfcc12, statics deleted",
         _only_deltas(_mfcc12, second=True))
register("mfcc12_d1_half", 24, "mfcc12 + 0.5 x first difference",
         _scaled_deltas(_mfcc12, 0.5))
register("mfcc12_d1_quarter", 24, "mfcc12 + 0.25 x first difference",
         _scaled_deltas(_mfcc12, 0.25))
register("mfcc12_d1", 24, "mfcc12 + first difference", _with_deltas(_mfcc12))
register("mfcc12_formants", 18, "mfcc12 + F1-F3 and B1-B3 from the LPC roots",
         lambda s, m=None: np.concatenate([_mfcc12(s), _formants6(s)], axis=1))

# --- how many cepstral coefficients, over how many mel bands ---------------
for _bands in (26, 32, 40):
    for _keep in (16, 20, 24):
        if _keep >= _bands:
            continue
        register(f"mfcc{_keep}_mel{_bands}", _keep,
                 f"DCT-II of {_bands} mel bands, c1..c{_keep}",
                 _cepstra(mel_filterbank(_bands), 1, _keep + 1))
        register(f"mfcc{_keep}_mel{_bands}_d1", 2 * _keep,
                 f"DCT-II of {_bands} mel bands, c1..c{_keep}, + first difference",
                 _with_deltas(_cepstra(mel_filterbank(_bands), 1, _keep + 1)))
register("mfcc20_mel26_d1d2", 60, "mfcc20_mel26 + d1 + d2",
         _with_deltas2(_cepstra(_MEL26, 1, 21)))
register("mfcc20_mel26_formants", 26, "mfcc20_mel26 + F1-F3 and B1-B3",
         lambda s, m=None: np.concatenate(
             [_cepstra(_MEL26, 1, 21)(s), _formants6(s)], axis=1))

# --- voicing, and deltas over a window long enough to hold a VOT -----------
_MFCC16_32 = _cepstra(mel_filterbank(32), 1, 17)
_MFCC20_26 = _cepstra(_MEL26, 1, 21)


def _voicing2(samples, mask=None):
    return voicing(samples)


def _wide_delta(base, width: int):
    def fn(samples, mask=None):
        x = base(samples, mask)
        return np.concatenate([x, deltas(x, width)], axis=1)
    return fn


def _partial_delta(base, keep: int, width: int = 3):
    """Statics in full, first differences of the first `keep` coefficients only."""
    def fn(samples, mask=None):
        x = base(samples, mask)
        return np.concatenate([x, deltas(x[:, :keep], width)], axis=1)
    return fn


def _plus_voicing(base):
    def fn(samples, mask=None):
        return np.concatenate([base(samples, mask), voicing(samples)], axis=1)
    return fn


register("voicing2", 2, "normalised autocorrelation peak and log F0", _voicing2)
register("mfcc16_mel32_d1w3", 32, "mfcc16_mel32 + d1 over a +/-30 ms window",
         _wide_delta(_MFCC16_32, 3))
register("mfcc16_mel32_d1w4", 32, "mfcc16_mel32 + d1 over a +/-40 ms window",
         _wide_delta(_MFCC16_32, 4))
register("mfcc20_mel26_d1w3", 40, "mfcc20_mel26 + d1 over a +/-30 ms window",
         _wide_delta(_MFCC20_26, 3))
register("mfcc16_mel32_pd6", 22, "mfcc16_mel32 + d1 of c1..c6 only, +/-30 ms",
         _partial_delta(_MFCC16_32, 6, 3))
register("mfcc20_mel26_pd6", 26, "mfcc20_mel26 + d1 of c1..c6 only, +/-30 ms",
         _partial_delta(_MFCC20_26, 6, 3))
register("mfcc16_mel32_voi", 18, "mfcc16_mel32 + voicing2", _plus_voicing(_MFCC16_32))
register("mfcc20_mel26_voi", 22, "mfcc20_mel26 + voicing2", _plus_voicing(_MFCC20_26))
register("mfcc20_mel26_voi_pd6", 28,
         "mfcc20_mel26 + voicing2 + d1 of c1..c6 only, +/-30 ms",
         _plus_voicing(_partial_delta(_MFCC20_26, 6, 3)))
register("mfcc16_mel32_voi_pd6", 24,
         "mfcc16_mel32 + voicing2 + d1 of c1..c6 only, +/-30 ms",
         _plus_voicing(_partial_delta(_MFCC16_32, 6, 3)))
register("mfcc12_voi", 14, "mfcc12 + voicing2, a like-for-like 14-dim swap for "
         "legacy14", _plus_voicing(_mfcc12))

# --- neighbourhood of the leader, to check it is a plateau and not a spike -
for _bands in (26, 32):
    for _keep in (16, 20, 24):
        for _pd in (4, 6, 8, 12):
            for _w in (2, 3, 4):
                register(f"mfcc{_keep}_mel{_bands}_pd{_pd}w{_w}", _keep + _pd,
                         f"c1..c{_keep} of {_bands} mel bands + d1 of the first "
                         f"{_pd}, +/-{10 * _w} ms",
                         _partial_delta(_cepstra(mel_filterbank(_bands), 1,
                                                 _keep + 1), _pd, _w))

RECOMMENDED = register(
    "recommended26", 26,
    "c1..c20 of the DCT-II of a 26-band log-mel filterbank (50-8000 Hz, "
    "pre-emphasis 0.97, 25 ms Hann frame, 10 ms hop, 512-point FFT), plus the "
    "first difference of c1..c6 over a +/-40 ms regression window. c0 is "
    "dropped, so the vector is level-invariant by construction.",
    _recommended)
SETS[CANONICAL] = RECOMMENDED   # the sweep name and the canonical name agree


def frame_features(samples: np.ndarray) -> np.ndarray:
    """The one entry point every learner in the next phase should call.

    samples: mono float32 in [-1, 1] at 16 kHz.
    returns: (n_frames, 26) float64, 25 ms frames on a 10 ms hop.
    """
    return _recommended(samples)


def variance_scaler(frames: np.ndarray, floor: float = 1e-6) -> np.ndarray:
    """Per-dimension standard deviations, for a learner that wants isotropy.

    Measured on the syllable corpus, `recommended26` is not isotropic: c1 alone
    holds ~50% of the frame variance, because spectral tilt really is the widest
    axis in speech.  An unweighted Euclidean k-means will therefore weight c1
    about as heavily as legacy14 weighted log-energy -- the difference being
    that c1 is linguistic and log-energy was not.  Whether that is a problem is
    a question for the learner, not for the feature, and it was NOT settled
    here: the fixed 1-NN probe z-scores its descriptors, so it cannot see any
    difference this would make.

    If a learner wants to try it, each ant must call this on its OWN frames.
    Passing one ant's scaler to another would be sharing a fitted parameter.
    """
    return np.maximum(np.asarray(frames, dtype=np.float64).std(axis=0), floor)


def extract(name: str, samples: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    return SETS[name](samples, mask)
