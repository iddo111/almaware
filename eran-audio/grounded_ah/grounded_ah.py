#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grounded_ah.py — Eran learns "ah" GROUNDED in a picture (Iddo's face).

Pipeline:
  picture -> embedding (insightface 512-d) -> MLP -> waveform logits -> vocoder -> /a/ .wav

Reuses:
  - obedience_ah_bah.py's synthetic /a/ formant target
  - family.py's insightface enrollment
  - cochlea.py's encode/decode for audio I/O

The model learns: picture embedding -> exact /a/ waveform on command.

Neuromodulator core (Part 1b) lives in neuromod.py, gating training via correctness
feedback. Here we just build the pipeline and verify it trains.

Run: python grounded_ah.py [steps]  (default 10 for quick verify)
"""

import os
import sys
import argparse
import json
import datetime
import numpy as np
import torch
import torch.nn as nn
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000
N = int(SR * 0.60)  # 0.6 s per syllable
F0 = 120.0

# Append parent paths so we can import sibling modules
sys.path.insert(0, os.path.dirname(HERE))  # eran-audio
sys.path.insert(0, os.path.join(os.path.dirname(HERE), '..', 'eran-faces'))  # eran-faces


def vowel(formants, dur_s=0.55, lead=0.05):
    """Additive formant synthesis of a vowel (reused from obedience_ah_bah.py)."""
    n = int(SR * dur_s)
    tt = np.linspace(0, dur_s, n, endpoint=False)
    y = np.zeros(n, np.float64)
    k = 1
    while k * F0 < SR / 2:
        fk = k * F0
        g = sum(a * (bw ** 2) / ((fk - fc) ** 2 + bw ** 2) for (fc, bw, a) in formants)
        y += g * np.sin(2 * np.pi * fk * tt)
        k += 1
    y /= (np.max(np.abs(y)) + 1e-9)
    env = np.clip(np.minimum(tt / 0.03, (dur_s - tt) / 0.06), 0, 1)
    y *= env
    out = np.zeros(N, np.float32)
    s = int(SR * lead)
    out[s:s + n] = y[:N - s]
    return out


# Target /a/ formant (from obedience training)
TARGET_AH = vowel([(730, 80, 1.0), (1090, 90, 0.6), (2440, 120, 0.25)],
                   dur_s=0.55, lead=0.03)


def get_picture_embedding(fallback=True):
    """
    Load Iddo's face embedding from family.py enrollment, or return a mock embedding.

    Returns: np.ndarray shape (512,) float32

    If fallback=True and no enrollment exists, returns a fixed mock embedding
    (allows testing pipeline before real face enrollment).
    """
    try:
        import family
        # Try to load enrolled embeddings
        recognizer = family.get_recognizer()
        if 'iddo' in recognizer.centroids:
            emb = recognizer.centroids['iddo']
            print(f"[grounded_ah] loaded Iddo embedding from family.py ({emb.shape[0]}-d)")
            return np.asarray(emb, dtype=np.float32)
        else:
            print("[grounded_ah] Iddo not enrolled yet (family.py)")
    except Exception as e:
        print(f"[grounded_ah] family.py load failed: {type(e).__name__}: {e}")

    if fallback:
        # Mock embedding: fixed random seed so it's reproducible, but diverse
        np.random.seed(42)
        mock = np.random.randn(512).astype(np.float32)
        mock = mock / (np.linalg.norm(mock) + 1e-9)
        print(f"[grounded_ah] using mock embedding (fixed seed, normalized)")
        return mock
    raise ValueError("No Iddo enrollment found and fallback=False")


def get_target_ah():
    """
    Load target /a/ waveform. Check target_ah/ folder first, fall back to synthetic.
    """
    target_dir = os.path.join(HERE, 'target_ah')
    if os.path.isdir(target_dir):
        wavs = [f for f in os.listdir(target_dir) if f.endswith('.wav')]
        if wavs:
            path = os.path.join(target_dir, sorted(wavs)[0])
            try:
                wav, sr = sf.read(path, dtype='float32')
                if wav.ndim > 1:
                    wav = wav.mean(axis=1)
                # Resample to 16kHz if needed
                if sr != SR:
                    from scipy.signal import resample_poly
                    from math import gcd
                    g = gcd(int(sr), int(SR))
                    up, down = SR // g, sr // g
                    wav = resample_poly(wav, up, down).astype(np.float32)
                # Pad/trim to N samples
                if len(wav) < N:
                    wav = np.pad(wav, (0, N - len(wav)), mode='constant')
                else:
                    wav = wav[:N]
                print(f"[grounded_ah] loaded target /a/ from {os.path.basename(path)}")
                return wav
            except Exception as e:
                print(f"[grounded_ah] failed to load {path}: {e}, falling back to synthetic")

    print(f"[grounded_ah] using synthetic target /a/")
    return TARGET_AH


class GroundedAhModel(nn.Module):
    """Picture embedding -> /a/ waveform.

    embedding (512-d) -> hidden (128-d) -> waveform logits (N samples)
    """
    def __init__(self, embedding_dim=512, hidden_dim=128, output_dim=None):
        super().__init__()
        if output_dim is None:
            output_dim = N
        self.embed_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim

        # MLP: embedding -> hidden -> waveform
        self.fc1 = nn.Linear(embedding_dim, hidden_dim)
        self.act1 = nn.GELU()
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.act2 = nn.GELU()
        self.fc3 = nn.Linear(hidden_dim, output_dim)

    def forward(self, emb):
        """
        Args:
            emb: shape (B, embedding_dim)
        Returns:
            waveform logits: shape (B, output_dim)
        """
        x = self.fc1(emb)
        x = self.act1(x)
        x = self.fc2(x)
        x = self.act2(x)
        out = self.fc3(x)
        return out


def train_step(model, opt, picture_emb, target_waveform, device='cpu'):
    """
    One training step.

    Args:
        model: GroundedAhModel
        opt: optimizer
        picture_emb: np.ndarray (512,) normalized
        target_waveform: np.ndarray (N,) audio samples
        device: torch device

    Returns:
        loss: scalar float
    """
    # Convert to tensors
    X = torch.tensor(picture_emb[None, :], dtype=torch.float32, device=device)
    Y = torch.tensor(target_waveform[None, :], dtype=torch.float32, device=device)

    # Forward
    pred = model(X)

    # MSE loss: predicted waveform vs target
    loss = ((pred - Y) ** 2).mean()

    # Backward
    opt.zero_grad()
    loss.backward()
    opt.step()

    return float(loss.item())


def compute_metrics(pred_waveform, target_waveform):
    """
    Compute MSE and BPB (bits per byte) of the waveform prediction.

    Args:
        pred_waveform: np.ndarray (N,) float32
        target_waveform: np.ndarray (N,) float32

    Returns:
        dict with 'mse', 'rmse', 'bpb'
    """
    pred = pred_waveform.astype(np.float32)
    targ = target_waveform.astype(np.float32)

    mse = np.mean((pred - targ) ** 2)
    rmse = np.sqrt(mse)

    # BPB: bits per byte if we quantize to 8-bit
    # Normalize waveforms to [-1, 1], quantize to uint8 (256 levels)
    pred_q = np.clip((pred + 1) * 127.5, 0, 255).astype(np.uint8)
    targ_q = np.clip((targ + 1) * 127.5, 0, 255).astype(np.uint8)

    # Cross-entropy: how many bits needed to encode pred given targ
    matches = (pred_q == targ_q).sum()
    n = len(pred_q)
    acc = matches / n if n > 0 else 0.0
    # BPB ~ -log2(acc) if we only count matches, simplified
    bpb = -np.log2(max(acc, 1e-3)) if acc < 1.0 else 0.01

    return {'mse': float(mse), 'rmse': float(rmse), 'bpb': float(bpb)}


def main():
    parser = argparse.ArgumentParser(
        description='Eran learns "ah" grounded in a picture (Iddo).')
    parser.add_argument('steps', nargs='?', type=int, default=10,
                        help='number of training steps (default 10)')
    parser.add_argument('--device', default='cpu',
                        help='torch device (cpu or cuda)')
    args = parser.parse_args()

    steps = args.steps
    device = torch.device(args.device if torch.cuda.is_available() else 'cpu')

    print(f"\n[grounded_ah] Eran learns 'ah' grounded in picture (Iddo's face)")
    print(f"[grounded_ah] device: {device}")
    print(f"[grounded_ah] steps: {steps}\n")

    # Create output directory
    output_dir = os.path.join(HERE, 'output')
    os.makedirs(output_dir, exist_ok=True)

    # Load inputs
    picture_emb = get_picture_embedding(fallback=True)
    target_ah = get_target_ah()

    print(f"[grounded_ah] picture embedding shape: {picture_emb.shape}")
    print(f"[grounded_ah] target /a/ shape: {target_ah.shape}\n")

    # Build model
    torch.manual_seed(0)
    model = GroundedAhModel(embedding_dim=512, hidden_dim=128, output_dim=N)
    model.to(device)

    # Optimizer
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)

    print(f"[grounded_ah] model built: embedding(512) -> hidden(128) -> waveform({N})")
    print(f"[grounded_ah] training...\n")

    # Training loop
    losses = []
    for step in range(steps):
        loss = train_step(model, opt, picture_emb, target_ah, device=device)
        losses.append(loss)

        # Eval: predict the waveform
        model.eval()
        with torch.no_grad():
            X = torch.tensor(picture_emb[None, :], dtype=torch.float32, device=device)
            pred = model(X).cpu().numpy()[0]
        model.train()

        # Metrics
        metrics = compute_metrics(pred, target_ah)

        # Save wav every step
        pred_clipped = np.clip(pred, -1, 1)
        wav_path = os.path.join(output_dir, f'step_{step:03d}.wav')
        sf.write(wav_path, pred_clipped, SR)

        print(f"step {step:3d}  loss {loss:.6f}  mse {metrics['mse']:.6f}  "
              f"bpb {metrics['bpb']:.3f}  -> {os.path.basename(wav_path)}", flush=True)

    # Final eval
    model.eval()
    with torch.no_grad():
        X = torch.tensor(picture_emb[None, :], dtype=torch.float32, device=device)
        final_pred = model(X).cpu().numpy()[0]

    final_metrics = compute_metrics(final_pred, target_ah)

    print(f"\n[grounded_ah] TRAINING COMPLETE")
    print(f"[grounded_ah] final loss: {losses[-1]:.8f}")
    print(f"[grounded_ah] final mse: {final_metrics['mse']:.8f}")
    print(f"[grounded_ah] final bpb: {final_metrics['bpb']:.3f}")

    # Save checkpoint
    ckpt_dir = os.path.join(HERE, 'checkpoints')
    os.makedirs(ckpt_dir, exist_ok=True)
    ckpt_path = os.path.join(ckpt_dir, 'latest.pt')
    torch.save({
        'model': model.state_dict(),
        'step': steps,
        'loss': float(losses[-1]),
        'picture_embedding_shape': picture_emb.shape,
        'target_ah_shape': target_ah.shape,
        'timestamp': datetime.datetime.now().isoformat(),
    }, ckpt_path)
    print(f"[grounded_ah] saved checkpoint -> {os.path.basename(ckpt_path)}")

    # Save final wav
    final_wav_path = os.path.join(output_dir, 'final_ah.wav')
    sf.write(final_wav_path, np.clip(final_pred, -1, 1), SR)
    print(f"[grounded_ah] saved final output -> {os.path.basename(final_wav_path)}")

    # Log run
    log_path = os.path.join(HERE, 'training_log.json')
    log_entry = {
        'timestamp': datetime.datetime.now().isoformat(),
        'steps': steps,
        'device': str(device),
        'final_loss': float(losses[-1]),
        'final_metrics': final_metrics,
        'losses': [float(l) for l in losses],
    }

    logs = []
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f:
                logs = json.load(f)
        except:
            logs = []

    logs.append(log_entry)
    with open(log_path, 'w') as f:
        json.dump(logs, f, indent=2)

    print(f"[grounded_ah] logged run -> training_log.json")
    print(f"\n[grounded_ah] outputs saved to: {output_dir}")
    print(f"[grounded_ah] listen to the .wav files to hear training progress!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
