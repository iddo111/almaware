#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_embed_nolibrosa.py — librosa-free speaker embedding for the curator.

WHY THIS EXISTS
On this PC, resemblyzer's audio frontend hangs: `librosa.feature.melspectrogram`
(and even `librosa.load` / `librosa.stft`) never return — a librosa import/runtime
stall on this Python312 environment. numpy/scipy FFT, soundfile, and torch all
work fine; only librosa is wedged. The live mic is unaffected because it uses
faster-whisper (CTranslate2), not librosa.

So this module reproduces EXACTLY what resemblyzer's VoiceEncoder.embed_utterance
does — partial slicing + LSTM forward + L2-normed average — but computes the
40-channel power-mel spectrogram with scipy/numpy instead of librosa. The encoder
weights and the math (resemblyzer hparams) are identical, so embeddings match
resemblyzer's to within float noise and are directly comparable to the existing
profiles/iddo1/voiceprint.npy (built by speaker_id.enroll).

It does NOT modify resemblyzer or speaker_id — it imports VoiceEncoder, reuses its
compute_partial_slices() and forward(), and only swaps the mel step.

Mel parameters (from resemblyzer.hparams, matching librosa.feature.melspectrogram
defaults that resemblyzer relies on):
    sr=16000, n_fft=400 (25ms), hop=160 (10ms), win=400 Hann, center=True,
    n_mels=40, fmin=0, fmax=8000, Slaney mel scale + Slaney ('area') norm,
    power spectrogram (|STFT|**2).
"""

from __future__ import annotations

import numpy as np

SR = 16000
N_FFT = 400          # 25 ms window
HOP = 160            # 10 ms step
N_MELS = 40
FMIN = 0.0
FMAX = SR / 2.0      # 8000

_MEL_FB = None       # cached Slaney mel filterbank (n_mels x (n_fft//2+1))
_WINDOW = None        # cached Hann window


# ── Slaney mel filterbank (matches librosa.filters.mel defaults) ──────────────
def _hz_to_mel_slaney(f):
    f = np.asarray(f, dtype=float)
    f_min, f_sp = 0.0, 200.0 / 3
    mels = (f - f_min) / f_sp
    min_log_hz, min_log_mel = 1000.0, (1000.0 - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    big = f >= min_log_hz
    # guard the log against f<=0 in the masked-out (linear) branch
    f_safe = np.where(big, f, min_log_hz)
    mels = np.where(big, min_log_mel + np.log(f_safe / min_log_hz) / logstep, mels)
    return mels


def _mel_to_hz_slaney(mels):
    mels = np.asarray(mels, dtype=float)
    f_min, f_sp = 0.0, 200.0 / 3
    freqs = f_min + f_sp * mels
    min_log_hz, min_log_mel = 1000.0, (1000.0 - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    big = mels >= min_log_mel
    freqs = np.where(big, min_log_hz * np.exp(logstep * (mels - min_log_mel)), freqs)
    return freqs


def _mel_filterbank():
    global _MEL_FB
    if _MEL_FB is not None:
        return _MEL_FB
    n_freqs = N_FFT // 2 + 1
    fft_freqs = np.linspace(0, SR / 2.0, n_freqs)
    min_mel = _hz_to_mel_slaney(FMIN)
    max_mel = _hz_to_mel_slaney(FMAX)
    mel_pts = np.linspace(min_mel, max_mel, N_MELS + 2)
    hz_pts = _mel_to_hz_slaney(mel_pts)

    fdiff = np.diff(hz_pts)
    ramps = hz_pts[:, None] - fft_freqs[None, :]
    fb = np.zeros((N_MELS, n_freqs), dtype=np.float32)
    for i in range(N_MELS):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        fb[i] = np.maximum(0.0, np.minimum(lower, upper))
    # Slaney ('area') normalization: each filter integrates to constant energy.
    enorm = 2.0 / (hz_pts[2:N_MELS + 2] - hz_pts[:N_MELS])
    fb *= enorm[:, None]
    _MEL_FB = fb
    return fb


def _hann():
    global _WINDOW
    if _WINDOW is None:
        # periodic Hann (sym=False), matching scipy.signal.get_window('hann', N, fftbins=True)
        n = np.arange(N_FFT)
        _WINDOW = (0.5 - 0.5 * np.cos(2.0 * np.pi * n / N_FFT)).astype(np.float32)
    return _WINDOW


def _stft_power(wav: np.ndarray) -> np.ndarray:
    """Power spectrogram |STFT|**2 with center=True reflect padding, matching
    librosa.stft defaults. Returns (n_freqs, n_frames)."""
    wav = np.asarray(wav, dtype=np.float32)
    pad = N_FFT // 2
    padded = np.pad(wav, (pad, pad), mode="reflect")
    win = _hann()
    n_frames = 1 + (len(padded) - N_FFT) // HOP
    if n_frames <= 0:
        return np.zeros((N_FFT // 2 + 1, 0), dtype=np.float32)
    # framed view (n_frames, N_FFT)
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = padded[idx] * win[None, :]
    spec = np.fft.rfft(frames, n=N_FFT, axis=1)           # (n_frames, n_freqs)
    power = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)
    return power.T                                         # (n_freqs, n_frames)


def wav_to_mel_spectrogram(wav: np.ndarray) -> np.ndarray:
    """Drop-in for resemblyzer.audio.wav_to_mel_spectrogram, librosa-free.
    Returns (n_frames, n_mels) float32 power-mel (NOT log)."""
    power = _stft_power(wav)                  # (n_freqs, n_frames)
    mel = _mel_filterbank() @ power           # (n_mels, n_frames)
    return mel.astype(np.float32).T           # (n_frames, n_mels)


# ── volume normalize (verbatim from resemblyzer.audio.normalize_volume) ───────
_INT16_MAX = (2 ** 15) - 1


def normalize_volume(wav, target_dBFS=-30, increase_only=True):
    rms = np.sqrt(np.mean((wav * _INT16_MAX) ** 2)) + 1e-12
    wave_dBFS = 20 * np.log10(rms / _INT16_MAX)
    dBFS_change = target_dBFS - wave_dBFS
    if dBFS_change < 0 and increase_only:
        return wav
    return wav * (10 ** (dBFS_change / 20))


# ── the embed (mirrors VoiceEncoder.embed_utterance, librosa-free mel) ────────
def embed_utterance(encoder, wav: np.ndarray, rate: float = 1.3,
                    min_coverage: float = 0.75):
    """Compute resemblyzer's utterance embedding for a preprocessed 16k mono
    float32 waveform, using `encoder` (a resemblyzer.VoiceEncoder) for the LSTM
    forward but our librosa-free mel. Returns a 256-d L2-normed np.float32, or
    None if the clip is too short to yield any partial."""
    import torch
    wav = np.asarray(wav, dtype=np.float32)
    if len(wav) < int(0.4 * SR):
        return None
    wav_slices, mel_slices = encoder.compute_partial_slices(len(wav), rate, min_coverage)
    max_wave_length = wav_slices[-1].stop
    if max_wave_length >= len(wav):
        wav = np.pad(wav, (0, max_wave_length - len(wav)), "constant")

    mel = wav_to_mel_spectrogram(wav)
    try:
        mels = np.array([mel[s] for s in mel_slices])
    except Exception:
        return None
    if mels.size == 0:
        return None
    with torch.no_grad():
        mels_t = torch.from_numpy(mels).to(encoder.device)
        partial_embeds = encoder(mels_t).cpu().numpy()
    raw = np.mean(partial_embeds, axis=0)
    n = np.linalg.norm(raw, 2)
    if n < 1e-12:
        return None
    return (raw / n).astype(np.float32)
