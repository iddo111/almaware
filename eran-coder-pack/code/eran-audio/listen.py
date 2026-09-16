"""
listen.py — HEAR Eran babble.

Loads the latest checkpoint, lets the age-zero brain dream a few seconds of audio
tokens, and decodes them back through the cochlea into a real .wav you can play.
This is the "watch it learn" for sound: early on it is formless noise; as the loss
drops it should grow vocal texture, rhythm, breath — a baby babbling toward speech.

Runs the cochlea decode on CPU (mic always wins the GPU). Safe to run anytime.

Run:  python -s listen.py
"""

import os
import sys
import json
import glob
import datetime

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from model import build_model
from train import load_config, model_cfg_from, CKPT_DIR
from cochlea import Cochlea


def main():
    cfg = load_config()
    lst = cfg.get("listen", {})
    gen_seconds = float(lst.get("gen_seconds", 4.0))
    temperature = float(lst.get("temperature", 0.95))
    top_k = int(lst.get("top_k", 100))

    ckpt_path = os.path.join(CKPT_DIR, "latest.pt")
    if not os.path.exists(ckpt_path):
        print("[listen] no checkpoint yet — let Eran train a bit first.")
        return

    # CPU-only on purpose: loading EnCodec on CPU inside a hot CUDA context
    # hard-crashes, and we must never contend with the mic for the GPU anyway.
    # The 3M brain generates a few seconds of babble on CPU in ~7s — plenty fast.
    torch.set_num_threads(2)
    device = "cpu"
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    mcfg = ck.get("cfg") or model_cfg_from(cfg)
    step = int(ck.get("step", 0))
    model = build_model(mcfg).to(device)
    model.load_state_dict(ck["model"])
    model.eval()

    codec = cfg["codec"]
    K = codec["n_codebooks"]
    fr = codec["frame_rate"]
    n_frames = int(gen_seconds * fr)
    n_tokens = n_frames * K  # keep whole frames

    # seed from a few real frames of his heard world (snapped to a codebook-0 boundary)
    cache = os.path.join(HERE, "tokens_cache.npy")
    if os.path.exists(cache):
        s = np.load(cache)
        if s.size > 64:
            off = int(torch.randint(0, max(1, s.size - 64), (1,)).item())
            off = (off // K) * K               # align to a frame boundary (codebook 0)
            seed = s[off:off + 10 * K].astype(np.int64)   # ~10 frames of real context
        else:
            seed = np.array([0], dtype=np.int64)
    else:
        seed = np.array([0], dtype=np.int64)

    idx = torch.tensor(seed[None, :], dtype=torch.long, device=device)
    with torch.no_grad():
        out = model.generate(idx, max_new_tokens=n_tokens, temperature=temperature, top_k=top_k)
    gen = out[0].tolist()[len(seed):]          # drop the real seed -> Eran's own babble
    # trim to whole frames
    gen = gen[: (len(gen) // K) * K]

    coch = Cochlea(device="cpu", cfg=cfg)       # decode on CPU
    wav = coch.decode(torch.tensor(gen, dtype=torch.long))

    babbles = os.path.join(HERE, "babbles")
    os.makedirs(babbles, exist_ok=True)
    import soundfile as sf
    latest = os.path.join(HERE, "babble_latest.wav")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = os.path.join(babbles, f"babble_step{step}_{ts}.wav")
    sf.write(latest, wav, codec["sample_rate"])
    sf.write(stamped, wav, codec["sample_rate"])
    dur = len(wav) / codec["sample_rate"]
    print(f"[listen] step {step}: babbled {dur:.1f}s of sound -> {latest}")
    print(f"[listen] also saved {stamped}")


if __name__ == "__main__":
    main()
