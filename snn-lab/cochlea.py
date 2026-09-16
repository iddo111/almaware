"""cochlea.py — a FAITHFUL port of ERAN's frozen cochlea (eran-brain/body/ears.py).

Why this file exists: so a spiking network can be asked the SAME question the
prototype organism is asked, on the SAME numbers. If the front-end differed,
"the SNN scored X" would be meaningless — you could not tell whether the spikes
or the ears made the difference.

Ported from D:\\CLAUDE\\eran-brain\\body\\ears.py (EAR_REPR="cochlea", frozen
2026-08-21) with the genome constants inlined. 25 ms Hann frames on a 10 ms hop,
per-frame level-normalised magnitude spectrum summed into 24 log-spaced bands
(50-8000 Hz), log taken; the speech span is cut into 8 fixed windows and each is
mean-pooled, mean-removed and L2'd.

The one deliberate difference: ears.py ravels the (8, 24) matrix into a single
192-vector. We keep the matrix, because for a SPIKING network the 8 slices are
not 8 more features — they are 8 moments in time, which is exactly the axis a
spiking neuron integrates over. `utterance()` below returns the (8, 24) matrix
scaled by 1/sqrt(8); its .ravel() is numerically identical to ears.utterance()
(each slice is unit-norm, so the global L2 of the 192-vector is exactly sqrt(8)).
proof_cochlea.py checks that against the real ears.py, bit for bit.

numpy only. No torch, no scipy, no genome import — this must run anywhere.
"""
import os
import wave

import numpy as np

# ---- genome constants, inlined verbatim from eran-brain/body/genome.py -------
SAMPLE_RATE = 16000
N_FFT = 512
N_BANDS = 24
FRAME_MS = 25
HOP_MS = 10
FMIN_HZ = 50.0
FMAX_HZ = 8000.0
EAR_EPS = 1e-08
EAR_SLICES = 8
EAR_SPEECH_FRAC = 0.1

CLASSES = ['aa', 'ah', 'ba', 'da', 'ga', 'ha', 'ka', 'kha', 'la', 'ma', 'na',
           'pa', 'qa', 'ra', 'sa', 'sha', 'ta', 'tha', 'tsa', 'va', 'ya', 'za']
CHANCE = 1.0 / len(CLASSES)          # 0.04545454...

# The published baselines this lab is measured against (genome.BASELINES).
BASELINES = {
    'chance': 0.045454545454545456,
    'duration_only_floor': 0.05303030303030303,
    'random_real_frames_codebook': 0.4621212121212121,
    'raw_features_speech_span': 0.5378787878787878,
    'raw_features_loudest60': 0.6893939393939394,
}
# The living organism's own scores, for honest comparison in the UI.
ORGANISM = {
    'prototype_organism_heldout': 0.6287878787878788,   # 62.88%, 132-item heldout
    'frozen_cochlea_nearest_centroid': 0.7954545454545454,  # 79.55%, same heldout
}


def read_wav(path):
    """16 kHz mono 16-bit PCM wav -> float32 samples in [-1, 1]."""
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected mono 16-bit PCM")
        rate = w.getframerate()
        pcm = w.readframes(w.getnframes())
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if rate != SAMPLE_RATE:
        n = max(1, round(len(samples) * SAMPLE_RATE / rate))
        src = np.linspace(0.0, 1.0, len(samples), endpoint=False)
        dst = np.linspace(0.0, 1.0, n, endpoint=False)
        samples = np.interp(dst, src, samples).astype(np.float32)
    return samples


def _band_slices(n_bands):
    """Log-spaced band edges 50-8000 Hz mapped to FFT bin ranges.

    Every band is forced to hold at least one bin — low log-spaced bands are
    narrower than one 31.25 Hz bin and an empty band would be a dead constant.
    """
    bins = N_FFT // 2 + 1
    hz_per_bin = SAMPLE_RATE / N_FFT
    edges_hz = np.geomspace(FMIN_HZ, FMAX_HZ, n_bands + 1)
    idx = np.round(edges_hz / hz_per_bin).astype(int)
    idx[0] = max(idx[0], 1)                       # skip DC
    for i in range(1, len(idx)):
        idx[i] = max(idx[i], idx[i - 1] + 1)      # at least one bin per band
    idx = np.minimum(idx, bins)
    return [(int(idx[i]), int(idx[i + 1])) for i in range(n_bands)]


class Cochlea:
    """The frozen ear. wav -> (EAR_SLICES, N_BANDS) frequency-by-time percept."""

    def __init__(self, n_bands=N_BANDS, slices=EAR_SLICES):
        self.n_bands = int(n_bands)
        self.n_slices = int(slices)
        self.dim = self.n_slices * self.n_bands
        self.frame = round(SAMPLE_RATE * FRAME_MS / 1000)   # 400
        self.hop = round(SAMPLE_RATE * HOP_MS / 1000)       # 160
        self.window = np.hanning(self.frame).astype(np.float32)
        self.slices = _band_slices(self.n_bands)

    def frames(self, samples):
        """(n_frames, n_bands) log-band features + (n_frames,) frame RMS."""
        samples = np.asarray(samples, dtype=np.float32)
        if len(samples) < self.frame:
            samples = np.pad(samples, (0, self.frame - len(samples)))
        count = 1 + (len(samples) - self.frame) // self.hop
        starts = self.hop * np.arange(count)
        x = samples[starts[:, None] + np.arange(self.frame)[None, :]] * self.window
        rms = np.sqrt(np.mean(x * x, axis=1) + EAR_EPS)
        spectrum = np.abs(np.fft.rfft(x, N_FFT, axis=1)) + EAR_EPS
        spectrum = spectrum / spectrum.sum(axis=1, keepdims=True)   # level-free
        bands = np.stack([spectrum[:, a:b].sum(axis=1) for a, b in self.slices],
                         axis=1)
        return np.log(bands + EAR_EPS), rms

    def pool(self, feats, rms):
        """The frozen cochlea's pooling: speech span -> 8 windows, each L2'd.

        Per-slice loudness is removed (a cochlea codes SHAPE, and no brain
        should be able to cheat with volume); each slice is L2'd so no slice
        can shout down the others. Returns (n_slices, n_bands), scaled so the
        ravel is globally unit-norm — exactly ears.py's 192-vector.
        """
        live = rms > (float(np.max(rms)) * EAR_SPEECH_FRAC if len(rms) else 0.0)
        idx = np.where(live)[0]
        if len(idx) < self.n_slices:
            idx = np.arange(len(rms))
        seg = feats[idx[0]:idx[-1] + 1]
        M = np.stack([p.mean(axis=0)
                      for p in np.array_split(seg, self.n_slices)])
        M = M - M.mean(axis=1, keepdims=True)
        n = np.linalg.norm(M, axis=1, keepdims=True)
        M = M / np.where(n > 0, n, 1.0)
        gn = np.linalg.norm(M.ravel())
        return (M / gn if gn > 0 else M).astype(np.float32)

    def utterance(self, path):
        """One wav -> one (n_slices, n_bands) percept. Time on axis 0."""
        feats, rms = self.frames(read_wav(path))
        return self.pool(feats, rms)


def label_of(filename):
    """class = the filename prefix before the first underscore (aa_h00_0.wav)."""
    return os.path.basename(filename).split("_")[0]


def load_split(root, split):
    """(N, 8, 24) float32 percepts + (N,) int labels for corpus-syllables/<split>.

    The heldout is the EXAM. It is loaded here only because a lab that reports a
    test number must have one; nothing trains on it.
    """
    d = os.path.join(root, split)
    files = sorted(f for f in os.listdir(d) if f.endswith(".wav"))
    ear = Cochlea()
    X = np.zeros((len(files), ear.n_slices, ear.n_bands), dtype=np.float32)
    y = np.zeros(len(files), dtype=np.int64)
    for i, f in enumerate(files):
        X[i] = ear.utterance(os.path.join(d, f))
        y[i] = CLASSES.index(label_of(f))
    return X, y
