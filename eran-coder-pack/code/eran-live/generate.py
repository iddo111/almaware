"""
generate.py - sample ~200 chars from ERAN's latest checkpoint.

"Watch it learn": early on this is gibberish; as training proceeds it drifts
toward Iddo's words. Reads checkpoints/latest.pt (the live, continuously-updated
checkpoint). Safe to run alongside the trainer.

Run:  python -s generate.py [n_chars] [temperature]
"""

import os
import sys
import json

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tokenizer import tokenizer
from model import build_model


def main():
    n_chars = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    temp = float(sys.argv[2]) if len(sys.argv) > 2 else 0.9

    with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    ckpt_path = os.path.join(cfg["checkpoint_dir"], "latest.pt")

    device = "cuda" if (cfg["gpu"]["device"] == "cuda" and torch.cuda.is_available()) else "cpu"
    if device == "cuda":
        torch.cuda.set_per_process_memory_fraction(float(cfg["gpu"]["vram_fraction"]), 0)

    model = build_model(cfg["model"]).to(device)

    step = 0
    if os.path.exists(ckpt_path):
        ck = torch.load(ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        step = int(ck.get("step", 0))
        print(f"[generate] loaded latest.pt @ step {step}, device={device}")
    else:
        print(f"[generate] no checkpoint yet; sampling from blank (age-zero) model.")

    model.eval()
    start = torch.tensor([[tokenizer.bos_id]], dtype=torch.long, device=device)
    with torch.no_grad():
        out = model.generate(start, max_new_tokens=n_chars, temperature=temp, top_k=40)
    text = tokenizer.decode(out[0].tolist())
    print("----- ERAN says (step %d) -----" % step)
    print(text)
    print("-------------------------------")


if __name__ == "__main__":
    main()
