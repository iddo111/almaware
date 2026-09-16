"""alma-mic / test_stt.py — STAGE 3 smoke: load the Hebrew Whisper model and
transcribe a few live seconds end-to-end (proves stt.py + audio.py work together)."""
import sys
import time
import numpy as np
import audio
from config import Config
from stt import Transcriber

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

cfg = Config.load()
t = Transcriber(cfg)
t0 = time.time()
t.load()
print(f"[ok] model loaded in {time.time()-t0:.1f}s : {t.desc}")

dev = audio.pick_device(prefer=cfg.prefer, avoid=cfg.avoid)
print(f"[ok] device: #{dev.index} [{dev.hostapi}] {dev.name}")
chunks = []
with audio.AudioCapture(dev.index) as cap:
    t0 = time.time()
    for fr in cap.frames():
        chunks.append(fr)
        if time.time() - t0 > 3.0:
            break
sig = np.concatenate(chunks)
t0 = time.time()
text, lang = t.transcribe(sig)
print(f"[ok] transcribed {len(sig)/audio.SAMPLE_RATE:.1f}s in {time.time()-t0:.1f}s  "
      f"lang={lang}  text={text!r}")
print("\nSTAGE 3 (STT) smoke done — model loads and transcribes end-to-end.")
