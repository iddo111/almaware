"""Split Iddo's eran-ah-bah recording into individual syllable clips, report them."""
import os, numpy as np, soundfile as sf, librosa

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "his_voice")
os.makedirs(OUT, exist_ok=True)
SR = 16000

src = r"C:\Users\<user>\Documents\Audacity\eran-ah-bah.mp3"
y, _ = librosa.load(src, sr=SR, mono=True)
print(f"loaded: {len(y)/SR:.1f}s @ {SR}Hz  peak {np.max(np.abs(y)):.2f}", flush=True)

# split on silence into spoken segments
intervals = librosa.effects.split(y, top_db=30, frame_length=2048, hop_length=512)
# keep only segments >= 0.15s (drop clicks)
segs = [(s, e) for s, e in intervals if (e - s) / SR >= 0.15]
print(f"found {len(segs)} syllable segments:", flush=True)
for i, (s, e) in enumerate(segs):
    clip = y[s:e]
    # normalize each clip
    clip = clip / (np.max(np.abs(clip)) + 1e-9) * 0.95
    sf.write(os.path.join(OUT, f"seg_{i:02d}.wav"), clip.astype(np.float32), SR)
    print(f"  seg {i:02d}: {s/SR:5.2f}-{e/SR:5.2f}s  dur {(e-s)/SR:.2f}s", flush=True)
print(f"saved {len(segs)} clips to {OUT}", flush=True)
