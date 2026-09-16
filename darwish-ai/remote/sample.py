# sample.py — Task 7: daily audible sample. Seed 5s of heldout audio tokens,
# generate ~60s continuation, DAC-decode, write generated/YYYYMMDD-HHMM-stepN.mp3.
# No KV-cache v1 (KISS): full recompute per step, ~10-15 min on GB10 - fine for daily.
import datetime
import json
import os
import subprocess

import dac
import numpy as np
import soundfile as sf
import torch

from model import DarwishLM

HOME = os.path.expanduser("~/darwish-ai")
CKPT = os.path.join(HOME, "ckpt", "latest.pt")
TOKENS = os.path.join(HOME, "tokens")
OUT = os.path.join(HOME, "generated")
os.makedirs(OUT, exist_ok=True)

SEED_T = 430        # ~5 s
GEN_T = 5160        # ~60 s
CTX = 4096
TEMP = 0.9
TOP_P = 0.95

if not os.path.exists(CKPT):
    print("no checkpoint yet - brain has not trained; skipping sample")
    raise SystemExit(0)

state = torch.load(CKPT, map_location="cuda", weights_only=False)
model = DarwishLM().cuda().eval()
model.load_state_dict(state["model"])
step = state["step"]

index = json.load(open(os.path.join(TOKENS, "index.json")))
pool = [e for e in index if e["split"] == "heldout"] or index
shard = np.load(os.path.join(TOKENS, f"{pool[0]['sha']}.npy"), mmap_mode="r")
t0 = np.random.randint(0, shard.shape[1] - SEED_T - 1)
seq = torch.from_numpy(np.array(shard[:, t0 : t0 + SEED_T], dtype=np.int64))[None].cuda()

print(f"sampling from step-{step} checkpoint, seed at t={t0}", flush=True)
with torch.no_grad():
    for i in range(GEN_T):
        ctx = seq[..., -CTX:]
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits, _ = model(ctx)
        nxt = []
        for k in range(model.n_codebooks):
            lg = logits[0, k, -1].float() / TEMP
            probs = torch.softmax(lg, dim=-1)
            sp, si = torch.sort(probs, descending=True)
            keep = (torch.cumsum(sp, 0) <= TOP_P).sum().clamp(min=1)
            choice = si[torch.multinomial(sp[:keep] / sp[:keep].sum(), 1)]
            nxt.append(choice)
        seq = torch.cat([seq, torch.stack(nxt, dim=0).view(1, -1, 1)], dim=-1)
        if i % 500 == 0:
            print(f"  gen {i}/{GEN_T}", flush=True)

codes = seq[0, :, SEED_T:][None]  # generated part only [1, 9, GEN_T]
codec = dac.DAC.load(dac.utils.download(model_type="44khz")).cuda().eval()
with torch.no_grad():
    z = codec.quantizer.from_codes(codes.int())[0]
    wav = codec.decode(z)[0, 0].cpu().numpy()

stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
wav_path = f"/tmp/darwish_sample.wav"
sf.write(wav_path, wav, 44100)
mp3 = os.path.join(OUT, f"{stamp}-step{step}.mp3")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, "-b:a", "192k", mp3], check=True)
print("WROTE", mp3, flush=True)
