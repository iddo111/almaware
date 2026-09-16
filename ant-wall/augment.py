#!/usr/bin/env python3
"""Phonetic-identity-preserving augmentation, pure numpy.

Deliberately torch-free so voice-ant-farm can import it without breaking its
"numpy>=1.26,<3 and nothing else" requirements.txt.

Every operation here is chosen to leave the phoneme intact:
  * WSOLA time-stretch changes tempo WITHOUT resampling, so formants and F0
    stay put. A naive `np.interp` speed change of -10% would drag F0 down by
    1.6 semitones and every formant with it, which is a vowel change, not an
    augmentation.
  * gain, additive noise at 20-30 dB SNR, and onset/offset padding do not
    touch the spectral envelope at all.
No pitch shifting, no reversal, no spectral warping.
"""
from __future__ import annotations

import numpy as np

SR = 16000


def periodic_hann(n: int) -> np.ndarray:
    """Periodic (not symmetric) Hann: with 50% overlap this sums to exactly 1.

    np.hanning() is the symmetric variant and does NOT satisfy COLA at hop
    n/2, so overlap-add with it puts a low-frequency ripple on the output.
    """
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n) / n)


def wsola(x: np.ndarray, tempo: float, *, frame: int = 640,
          search: int = 160) -> np.ndarray:
    """Waveform-similarity overlap-add time-stretch. tempo>1 = faster/shorter.

    frame=640 (40 ms) is longer than two pitch periods of any adult voice, and
    search=160 (10 ms) is wider than one pitch period at 100 Hz, so the
    similarity search can always find a phase-aligned splice point. Those two
    numbers are why this does not produce the metallic buzz a fixed-hop OLA
    gives.
    """
    if abs(tempo - 1.0) < 1e-9:
        return x.astype(np.float64, copy=True)
    x = np.asarray(x, dtype=np.float64)
    if x.size < frame + 2 * search + 2:
        return x.copy()

    hop_syn = frame // 2
    hop_ana = hop_syn * tempo

    # One strided view + one matmul per frame instead of a Python loop over
    # ~321 candidate offsets; the naive version took minutes for 600 files.
    sw = np.lib.stride_tricks.sliding_window_view(x, frame)   # (N-frame+1, frame)
    n_pos = sw.shape[0]
    # Per-position energy from a running sum, not (sw**2).sum(axis=1): sw is a
    # stride trick, so squaring it materialises N*frame floats (76 MB for a
    # 1 s clip) and cost 1.2 s per stretch -- 12 min over the full corpus.
    cs = np.concatenate([[0.0], np.cumsum(x * x)])
    sw_norm = np.sqrt(np.maximum(cs[frame:] - cs[:-frame], 0.0)) + 1e-12

    out_len = int(round(x.size / tempo))
    out = np.zeros(out_len + frame, dtype=np.float64)
    norm = np.zeros_like(out)
    win = periodic_hann(frame)

    n_frames = int(out_len // hop_syn) + 1
    prev_tail = None
    for k in range(n_frames):
        target = int(round(k * hop_ana))
        if k == 0 or prev_tail is None:
            a = min(max(target, 0), n_pos - 1)
        else:
            lo = max(0, target - search)
            hi = min(n_pos - 1, target + search)
            if hi <= lo:
                a = min(max(target, 0), n_pos - 1)
            else:
                cand = sw[lo:hi + 1]
                # normalised cross-correlation against the continuation the
                # previous frame "expected" to hear next
                score = (cand @ prev_tail) / sw_norm[lo:hi + 1]
                a = lo + int(np.argmax(score))
        seg = sw[a] * win
        s = k * hop_syn
        out[s:s + frame] += seg
        norm[s:s + frame] += win
        nxt = a + hop_syn
        prev_tail = sw[nxt] if nxt < n_pos else None

    out = out[:out_len]
    norm = norm[:out_len]
    return np.where(norm > 1e-6, out / np.maximum(norm, 1e-6), out)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f noise via spectral shaping -- closer to real mic/room tone than white."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(spec.size)
    shape = np.ones(spec.size)
    shape[1:] = 1.0 / np.sqrt(f[1:])
    y = np.fft.irfft(spec * shape, n=n)
    s = np.std(y)
    return y / s if s > 0 else y


def white_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    y = rng.standard_normal(n)
    s = np.std(y)
    return y / s if s > 0 else y


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def apply_augmentation(base: np.ndarray, plan: dict) -> np.ndarray:
    """Run a recipe dict produced by draw_plan(). Order matters.

    Padding happens BEFORE the noise is added so the leading/trailing silence
    carries the same room tone as the speech does. Padding after would leave
    digitally-zero frames whose log-energy is the -1e-10 floor, a value that
    never occurs in a real recording and that the k-means would happily spend
    a centre on.
    """
    y = wsola(base, plan["tempo"])
    y = y * (10.0 ** (plan["gain_db"] / 20.0))

    lead = int(round(plan["pad_lead_ms"] * SR / 1000.0))
    tail = int(round(plan["pad_tail_ms"] * SR / 1000.0))
    speech_lo, speech_hi = lead, lead + y.size
    y = np.concatenate([np.zeros(lead), y, np.zeros(tail)])

    rng = np.random.default_rng(plan["noise_seed"])
    gen = pink_noise if plan["noise_colour"] == "pink" else white_noise
    n = gen(y.size, rng)
    speech_rms = rms(y[speech_lo:speech_hi])
    target = speech_rms / (10.0 ** (plan["snr_db"] / 20.0))
    y = y + n * target
    return y


def draw_plan(seed: int, *, allow_tempo: bool = True) -> dict:
    """Sample one augmentation recipe from `seed`. Fully reproducible."""
    rng = np.random.default_rng(seed)
    return {
        "aug_seed": int(seed),
        "tempo": float(rng.uniform(0.90, 1.10)) if allow_tempo else 1.0,
        "gain_db": float(rng.uniform(-10.0, -0.5)),
        "snr_db": float(rng.uniform(20.0, 30.0)),
        "pad_lead_ms": float(rng.uniform(10.0, 80.0)),
        "pad_tail_ms": float(rng.uniform(10.0, 80.0)),
        "noise_colour": "pink" if rng.random() < 0.5 else "white",
        "noise_seed": int(rng.integers(0, 2 ** 31 - 1)),
    }
