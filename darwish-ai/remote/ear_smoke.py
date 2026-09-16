# ear_smoke.py — Task 3 EAR gate: encode 10s of a real Darwish set to DAC tokens,
# decode back, write _ear_smoke.mp3. Acceptance = a HUMAN says it sounds like the source.
import glob
import os
import subprocess
import time

import dac
import soundfile as sf
import torch

files = sorted(glob.glob(os.path.expanduser("~/darwish-ai/corpus/*.mp3")))
assert files, "no corpus files on eran3 yet — run sync_corpus.ps1 first"
src = files[0]
print("source:", os.path.basename(src))

subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-ss", "600", "-t", "10", "-i", src,
     "-ar", "44100", "-ac", "1", "/tmp/ear_src.wav"],
    check=True,
)

model_path = dac.utils.download(model_type="44khz")
model = dac.DAC.load(model_path).to("cuda").eval()

wav, sr = sf.read("/tmp/ear_src.wav", dtype="float32")
x = torch.from_numpy(wav)[None, None, :].to("cuda")
t0 = time.time()
with torch.no_grad():
    xp = model.preprocess(x, sr)
    z, codes, *_ = model.encode(xp)
    y = model.decode(z)
dt = time.time() - t0
print(f"codes shape {tuple(codes.shape)}  ({dt:.2f}s for 10s of audio)")

sf.write("/tmp/ear_roundtrip.wav", y[0, 0].cpu().numpy(), 44100)
out = os.path.expanduser("~/darwish-ai/generated/_ear_smoke.mp3")
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-i", "/tmp/ear_roundtrip.wav",
     "-b:a", "192k", out],
    check=True,
)
print("WROTE", out)
