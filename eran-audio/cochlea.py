"""
cochlea.py - ERAN v2's artificial cochlea.

A baby has a cochlea that turns sound into neural signals. Here, a PRETRAINED
neural audio codec (Meta's EnCodec) plays that role: it turns raw audio into
DISCRETE audio tokens, and turns audio tokens back into a .wav. The codec is the
ear ONLY. All LEARNING (model.py) starts from a blank, random, age-zero brain.

We use EnCodec @ 24kHz, bandwidth 1.5 kbps -> 2 codebooks (RVQ), each token in
[0, 1023], ~75 frames/sec. We FLATTEN the 2 codebooks into a single token stream
by interleaving with a per-codebook offset, giving a vocab of n_codebooks*1024.
That way a single decoder-only transformer can learn "predict the next sound
token" exactly like a baby learning to predict the next moment of sound.

token layout (flattened/interleaved):
    frame t -> [ q0_t + 0*1024 ,  q1_t + 1*1024 ]
    sequence = q0_0 q1_0  q0_1 q1_1  q0_2 q1_2 ...   (length = 2 * n_frames)
"""
import json
import os
import warnings

import numpy as np
import torch

warnings.filterwarnings("ignore")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_CFG = None


def load_cfg(path=None):
    global _CFG
    if _CFG is None:
        path = path or os.path.join(os.path.dirname(__file__), "config.json")
        with open(path, "r", encoding="utf-8") as f:
            _CFG = json.load(f)
    return _CFG


class Cochlea:
    """Wraps EnCodec. Lives on a chosen device; can be parked on CPU to free VRAM."""

    def __init__(self, device="cuda", cfg=None):
        from transformers import EncodecModel

        self.cfg = cfg or load_cfg()
        c = self.cfg["codec"]
        self.device = device
        self.sample_rate = c["sample_rate"]
        self.bandwidth = c["bandwidth"]
        self.n_codebooks = c["n_codebooks"]
        self.codebook_size = c["codebook_size"]
        self.frame_rate = c["frame_rate"]
        self.vocab_size = self.n_codebooks * self.codebook_size

        self.model = EncodecModel.from_pretrained(c["model"])
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad_(False)
        self.model.to(device)

    # ---- raw audio (float32 mono @ codec sr) -> flat token ids (1D long tensor)
    @torch.no_grad()
    def encode(self, wav_24k):
        if not torch.is_tensor(wav_24k):
            wav_24k = torch.tensor(wav_24k, dtype=torch.float32)
        wav_24k = wav_24k.to(self.device).float()
        x = wav_24k.view(1, 1, -1)
        enc = self.model.encode(x, bandwidth=self.bandwidth)
        codes = enc.audio_codes  # [n_chunks=1, B=1, K, T]
        codes = codes[0, 0]  # [K, T]
        K = min(self.n_codebooks, codes.shape[0])
        codes = codes[:K]  # [K, T]
        # offset each codebook into its own slice of the flat vocab, then interleave
        offsets = (torch.arange(K, device=codes.device) * self.codebook_size).view(K, 1)
        codes = codes + offsets  # [K, T]
        flat = codes.t().reshape(-1).contiguous()  # [T*K]  (q0_0 q1_0 q0_1 q1_1 ...)
        return flat.long().cpu()

    # ---- flat token ids -> raw audio (float32 mono @ codec sr)
    @torch.no_grad()
    def decode(self, flat_ids):
        if not torch.is_tensor(flat_ids):
            flat_ids = torch.tensor(flat_ids, dtype=torch.long)
        K = self.n_codebooks
        # drop a trailing partial frame so length is a multiple of K
        T = (flat_ids.numel() // K) * K
        flat_ids = flat_ids[:T].to(self.device)
        codes = flat_ids.view(-1, K).t().contiguous()  # [K, T]
        # remove per-codebook offset and clamp into valid codebook range
        offsets = (torch.arange(K, device=codes.device) * self.codebook_size).view(K, 1)
        codes = (codes - offsets).clamp_(0, self.codebook_size - 1)
        codes = codes.view(1, 1, K, -1)  # [n_chunks, B, K, T]
        scales = [None]
        audio = self.model.decode(codes, scales)[0]  # [B,1,T_samples]
        return audio.squeeze().float().cpu().numpy()

    def to(self, device):
        self.device = device
        self.model.to(device)
        return self


def resample_to_codec(wav, sr, target_sr):
    """16kHz mic capture -> 24kHz for EnCodec (or pass-through if already 24k)."""
    if sr == target_sr:
        return wav.astype(np.float32)
    from scipy.signal import resample_poly
    from math import gcd

    g = gcd(int(sr), int(target_sr))
    up, down = target_sr // g, sr // g
    return resample_poly(wav, up, down).astype(np.float32)


if __name__ == "__main__":
    # self-test: load codec, tokenize a real wav, decode back, report shapes.
    import glob
    import soundfile as sf

    cfg = load_cfg()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("[cochlea] device:", dev)
    coch = Cochlea(device=dev, cfg=cfg)
    print("[cochlea] vocab_size:", coch.vocab_size, "frame_rate:", coch.frame_rate)
    fs = sorted(glob.glob(os.path.join(cfg["samples_dir"], "*.wav")))
    print("[cochlea] found", len(fs), "wav files")
    wav, sr = sf.read(fs[0], dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    wav24 = resample_to_codec(wav, sr, coch.sample_rate)
    ids = coch.encode(wav24)
    print("[cochlea] tokenized:", os.path.basename(fs[0]), "-> token ids shape", tuple(ids.shape),
          "min", int(ids.min()), "max", int(ids.max()))
    back = coch.decode(ids)
    print("[cochlea] decoded back to audio:", back.shape, "sec", round(len(back) / coch.sample_rate, 2))
    print("[cochlea] OK")
