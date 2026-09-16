"""Log-mel on the GPU, numerically matched to WhisperFeatureExtractor.

WHY: doing feature extraction in forked DataLoader workers deadlocked this box.
The parent had already initialised CUDA, and the forked child hung in
futex_do_wait on the first call into the threaded numpy/OMP stack -- a textbook
fork-after-threads deadlock, confirmed with py-spy (main thread blocked in
_try_get_data, workers blocked in futex with 21 threads each).

Rather than paper over it with num_workers=0 and eat the CPU cost, the mel moves
to the GPU where it is nearly free. The dataloader then only slices a memmap,
which is safe to fork and cheap enough to need no workers at all.

CORRECTNESS IS NOT ASSUMED. A subtly wrong mel trains a subtly broken model and
nothing would ever flag it, so verify() checks this against the real
WhisperFeatureExtractor and the trainer refuses to start if it disagrees.

The one detail that is easy to get wrong: the dynamic-range floor uses a
PER-SAMPLE max (max - 8.0), not a per-batch max. Using a batch max silently
couples every clip in a batch to the loudest one.
"""
from __future__ import annotations

import numpy as np
import torch

N_FFT = 400
HOP = 160
N_SAMPLES = 480000          # 30 s at 16 kHz


class GpuMel:
    def __init__(self, feature_extractor, device="cuda"):
        # reuse the exact filterbank the reference extractor uses
        filters = np.asarray(feature_extractor.mel_filters, dtype=np.float32)
        # HF stores (1 + n_fft//2, n_mels); we want (n_mels, freqs)
        if filters.shape[0] != N_FFT // 2 + 1:
            filters = filters.T
        self.filters = torch.from_numpy(filters.T.copy()).to(device, torch.float32)
        self.window = torch.hann_window(N_FFT, device=device, dtype=torch.float32)
        self.device = device

    @torch.no_grad()
    def __call__(self, wav):
        """wav: (B, N_SAMPLES) float32 on device -> (B, n_mels, 3000) float32."""
        stft = torch.stft(wav, N_FFT, HOP, window=self.window, return_complex=True)
        mag = stft[..., :-1].abs() ** 2
        mel = self.filters @ mag
        log = torch.clamp(mel, min=1e-10).log10()
        mx = log.amax(dim=(-2, -1), keepdim=True)      # PER-SAMPLE, see docstring
        log = torch.maximum(log, mx - 8.0)
        return (log + 4.0) / 4.0


def pad_batch(arrs, n=N_SAMPLES):
    out = np.zeros((len(arrs), n), dtype=np.float32)
    for i, a in enumerate(arrs):
        m = min(len(a), n)
        out[i, :m] = a[:m]
    return out


def verify(feature_extractor, device="cuda", tol=2e-3, seed=0):
    """Compare against the reference extractor on random audio. Raises on drift."""
    rng = np.random.RandomState(seed)
    clips = [rng.randn(rng.randint(8000, 400000)).astype(np.float32) * 0.1
             for _ in range(4)]
    ref = feature_extractor(clips, sampling_rate=16000,
                            return_tensors="pt").input_features.float()
    gm = GpuMel(feature_extractor, device)
    got = gm(torch.from_numpy(pad_batch(clips)).to(device)).cpu()
    if got.shape != ref.shape:
        raise RuntimeError(f"mel shape mismatch: gpu {tuple(got.shape)} vs ref {tuple(ref.shape)}")
    d = (got - ref).abs().max().item()
    if not np.isfinite(d) or d > tol:
        raise RuntimeError(f"GPU mel disagrees with WhisperFeatureExtractor: max|diff|={d:.6f}")
    return d


if __name__ == "__main__":
    from transformers import WhisperFeatureExtractor
    fe = WhisperFeatureExtractor.from_pretrained("openai/whisper-large-v3-turbo")
    print("max abs diff vs reference:", verify(fe))
    print("OK")
