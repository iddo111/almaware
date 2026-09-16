# -*- coding: utf-8 -*-
"""features.py -- the Ear v3 feature vector. Deterministic, no RNG, no clock.

features(samples_16k_float32) -> np.float64 vector of 996 dims:

  [  0:192)  BLOCK 0  LEGACY-192 (THE GROWTH LAW). The original frozen
             cochlea, computed by legacy/ears.py utterance_from_samples()
             EXACTLY as-is (same code object the organism wears; genome
             constants respected; the legacy code is never modified).
             Fed the RAW samples, not the SPL-gained ones: the legacy ear
             normalizes every frame's spectrum by its own sum, so a scalar
             gain cancels exactly (up to EAR_EPS) -- feeding raw keeps BLOCK
             0 bit-identical to what the organism itself hears from a wav.
  [192:202)  BLOCK L  level (10): 8-slice log-loudness contour over the NAP
             speech span (NOT mean-removed -- level is information) + total
             duration s + speech-span duration s.
  [202:722)  BLOCK S  cochleagram (8x65=520): HWR NAP -> 10 ms non-overlap
             mean-pool -> log(+EPS_LOG) -> speech-span cut -> 8 equal time
             slices x 65 channels. NO per-clip normalization of any kind.
  [722:853)  BLOCK P  pitch (131): see pitch.py.
  [853:996)  BLOCK M  modulation (143): 11 channel groups (np.array_split of
             65 channels: ten of 6 + one of 5) x modulation energies at
             {4,8,16,32,64} Hz (55) + onset map 8 slices x 11 groups (88).
             Modulation energies use a 2.5 ms-hop log-cochleagram (frame rate
             400 Hz) because 64 Hz sits ABOVE the 10 ms hop's 50 Hz Nyquist;
             energy at f = |Goertzel DFT at f of the mean-removed per-group
             series|^2 / T^2. Onset map = half-wave-rectified temporal
             derivative of the 10 ms log-cochleagram, span-cut, 8x11 pooled.

Speech span (shared by L/S/P/M): NAP loudness > SPEECH_FRAC (=0.10, mirroring
genome.EAR_SPEECH_FRAC) of its peak, first live frame to last; if fewer than
8 frames are live, the whole clip is the span (the legacy rule).

Short-clip guard: any span segment shorter than 8 frames is edge-repeat
padded to 8 before slicing (legacy energy_contour's repeat-pad move).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import wave

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LEGACY = os.path.join(_ROOT, "legacy")
CALIB_PATH = os.path.join(_ROOT, "ear3-calib.json")

FS = 16000
HOP = 160                    # 10 ms
N_SLICES = 8
SPEECH_FRAC = 0.10
EPS_LOG = 1e-6
N_CH = 65
N_GROUPS = 11
MOD_FREQS = (4.0, 8.0, 16.0, 32.0, 64.0)
MOD_HOP = 40                 # 2.5 ms -> 400 Hz frame rate (Nyquist 200 Hz)
CARFAC_SHA = "4cdb95ee"
PATCH_ID = "0001-jax-5tap-agc"

BLOCKS = (("legacy192", 192), ("level", 10), ("cochleagram", 520),
          ("pitch", 131), ("modulation", 143))
DIM = sum(d for _, d in BLOCKS)                                   # 996

_LEG = None
_COCH = None
_GAIN = None


# ------------------------------------------------------------------ plumbing

def read_wav(path):
    """16 kHz mono 16-bit PCM -> float32 in [-1,1]. Refuses other formats."""
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected mono 16-bit PCM")
        if w.getframerate() != FS:
            raise ValueError(f"{path}: expected {FS} Hz, got {w.getframerate()}")
        pcm = w.readframes(w.getnframes())
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def spl_gain():
    """The frozen scalar gain from ear3-calib.json (calib.py --spl writes it)."""
    global _GAIN
    if _GAIN is None:
        if not os.path.exists(CALIB_PATH):
            raise RuntimeError(
                f"no {CALIB_PATH}: run  python -m ear3.calib --spl  first")
        with open(CALIB_PATH, encoding="utf-8") as f:
            _GAIN = float(json.load(f)["spl"]["gain"])
    return _GAIN


def legacy_ears():
    """The organism's own frozen ear, from the read-only-archive copy."""
    global _LEG
    if _LEG is None:
        if _LEGACY not in sys.path:
            sys.path.insert(0, _LEGACY)
        import ears as legacy_ears_mod          # legacy/ears.py, verbatim
        _LEG = legacy_ears_mod.Ears()
        if _LEG.repr != "cochlea" or _LEG.dim != 192:
            raise RuntimeError(
                f"legacy ear is not the frozen cochlea: repr={_LEG.repr!r} "
                f"dim={_LEG.dim} -- check legacy/ and state/crown.json")
    return _LEG


def cochlea():
    global _COCH
    if _COCH is None:
        from ear3.carfac_wrap import Ear3Cochlea
        _COCH = Ear3Cochlea(fs=FS, spl_gain=spl_gain())
    return _COCH


def _split8(arr):
    """Split rows into 8 slices, edge-repeat-padding first if too short."""
    a = np.asarray(arr)
    if a.shape[0] == 0:
        a = np.zeros((N_SLICES,) + a.shape[1:])
    elif a.shape[0] < N_SLICES:
        pad = np.repeat(a[-1:], N_SLICES - a.shape[0], axis=0)
        a = np.concatenate([a, pad], axis=0)
    return np.array_split(a, N_SLICES)


def _span(loud):
    """(a, b) inclusive 10 ms frame span. Legacy rule mirrored on NAP loudness."""
    if loud.size == 0:
        return 0, -1
    live = loud > float(np.max(loud)) * SPEECH_FRAC
    idx = np.where(live)[0]
    if len(idx) < N_SLICES:
        return 0, loud.size - 1
    return int(idx[0]), int(idx[-1])


# ------------------------------------------------------------------ the vector

def _compute(x):
    from ear3 import pitch as pitchmod
    timing = {}

    t0 = time.perf_counter()
    v192 = np.asarray(legacy_ears().utterance_from_samples(x), dtype=np.float64)
    timing["legacy_ms"] = (time.perf_counter() - t0) * 1e3

    t0 = time.perf_counter()
    nap = cochlea().nap(x)                                  # (n, 65) float64
    timing["cochlea_ms"] = (time.perf_counter() - t0) * 1e3

    t0 = time.perf_counter()
    r = np.maximum(nap, 0.0)
    nf = r.shape[0] // HOP
    pooled = r[:nf * HOP].reshape(nf, HOP, r.shape[1]).mean(axis=1)
    loud = pooled.mean(axis=1)                              # (nf,)
    a, b = _span(loud)
    seg_loud = loud[a:b + 1]

    # BLOCK L
    total_dur = x.size / FS
    span_dur = seg_loud.size * HOP / FS
    L = np.array([np.log(float(p.mean()) + EPS_LOG) for p in _split8(seg_loud)]
                 + [total_dur, span_dur])

    # BLOCK S
    logc = np.log(pooled + EPS_LOG)                         # (nf, 65)
    S = np.stack([p.mean(axis=0) for p in _split8(logc[a:b + 1])]).ravel()

    # BLOCK M -- modulation energies on the 2.5 ms grid
    groups = np.array_split(np.arange(r.shape[1]), N_GROUPS)
    nf2 = r.shape[0] // MOD_HOP
    pooled2 = r[:nf2 * MOD_HOP].reshape(nf2, MOD_HOP, r.shape[1]).mean(axis=1)
    logc2 = np.log(pooled2 + EPS_LOG)
    g2 = np.stack([logc2[:, g].mean(axis=1) for g in groups], axis=1)
    k = HOP // MOD_HOP                                      # 4 fine per coarse
    seg2 = g2[a * k:(b + 1) * k]                            # (T, 11)
    T = seg2.shape[0]
    fr2 = FS / MOD_HOP                                      # 400 Hz
    if T >= 2:
        xm = seg2 - seg2.mean(axis=0, keepdims=True)
        tt = np.arange(T)
        Ms = []
        for f in MOD_FREQS:
            ph = np.exp(-2j * np.pi * f * tt / fr2)
            Ms.append(np.abs(ph @ xm) ** 2 / T ** 2)        # (11,)
        Emod = np.stack(Ms, axis=0).ravel()                 # 5 x 11 = 55
    else:
        Emod = np.zeros(len(MOD_FREQS) * N_GROUPS)

    # BLOCK M -- onset map on the 10 ms grid
    d = np.maximum(np.diff(logc, axis=0), 0.0)              # (nf-1, 65)
    go = np.stack([d[:, g].mean(axis=1) for g in groups], axis=1)
    sego = go[a:b] if b > a else go[a:a + 1]
    O = np.stack([p.mean(axis=0) if len(p) else np.zeros(N_GROUPS)
                  for p in _split8(sego)]).ravel()          # 8 x 11 = 88
    M = np.concatenate([Emod, O])
    timing["rest_ms"] = (time.perf_counter() - t0) * 1e3

    # BLOCK P
    t0 = time.perf_counter()
    P, paux = pitchmod.pitch_block(nap, a, b, fs=FS,
                                   cf=cochlea().channel_cfs)
    timing["sai_ms"] = (time.perf_counter() - t0) * 1e3

    vec = np.concatenate([v192, L, S, P, M]).astype(np.float64)
    if vec.size != DIM:
        raise RuntimeError(f"feature dim {vec.size} != {DIM}")
    aux = {"loud": loud, "span": (a, b),
           "total_dur": total_dur, "span_dur": span_dur,
           "occupancy": span_dur / total_dur if total_dur > 0 else 0.0,
           "timing": timing}
    aux.update(paux)
    return vec, aux


def features(samples):
    """The whole Ear-v3 percept. float64 (996,). Deterministic."""
    return _compute(np.asarray(samples, dtype=np.float32))[0]


def features_with_aux(samples):
    return _compute(np.asarray(samples, dtype=np.float32))


def features_from_wav(path):
    return features(read_wav(path))


# ------------------------------------------------------------------ the spec

def feature_spec():
    """Everything that defines the vector. Hash guards the targets cache."""
    from ear3 import pitch as pitchmod
    return {
        "version": "ear3-phase1",
        "carfac_sha": CARFAC_SHA,
        "patch_id": PATCH_ID,
        "fs": FS, "hop": HOP, "n_slices": N_SLICES,
        "speech_frac": SPEECH_FRAC, "eps_log": EPS_LOG,
        "preroll_s": 0.100, "preroll": "state-cached-once", "bucket": 1000,
        "spl": {"target_rms": 0.05, "spl_db": 65.0, "gain": spl_gain()},
        "blocks": [list(bd) for bd in BLOCKS],
        "legacy": {"fed": "raw-ungained", "n_bands": 24, "slices": 8},
        "pitch": pitchmod.spec(),
        "mod": {"freqs": list(MOD_FREQS), "hop": MOD_HOP,
                "groups": N_GROUPS, "onset": "hwr-diff-log-cochleagram-10ms"},
        "loudness": "mean-over-channels HWR NAP, 10ms mean-pool",
    }


def spec_hash():
    blob = json.dumps(feature_spec(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def block_ranges():
    """[(name, lo, hi), ...] index ranges into the 996-d vector."""
    out, lo = [], 0
    for name, d in BLOCKS:
        out.append((name, lo, lo + d))
        lo += d
    return out
