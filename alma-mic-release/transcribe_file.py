r"""alma-mic / transcribe_file.py — transcribe WAV files WITHOUT a microphone.

Sanity/debug tool: proves the STT engine works on this machine before ever
touching the mic. Uses the exact same Transcriber + config as the live app.

    python transcribe_file.py path\to\clip.wav [more.wav ...]
    python transcribe_file.py --cpu clip.wav        # force CPU

Accepts 16-bit PCM WAV, mono or stereo, any sample rate (resampled to 16 kHz).
Prints the recognized text, the detected language, and the timing — so you can
see what to expect from your computer (on a laptop without a GPU, expect a few
seconds per sentence; the first ever run also downloads the model, ~1.5 GB).
"""
from __future__ import annotations
import argparse
import sys
import time
import wave

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_wav_16k(path: str) -> np.ndarray:
    """16-bit PCM WAV -> mono float32 @16k (linear resample when needed)."""
    with wave.open(path, "rb") as w:
        ch, width, rate, n = (w.getnchannels(), w.getsampwidth(),
                              w.getframerate(), w.getnframes())
        if width != 2:
            raise SystemExit(f"{path}: only 16-bit PCM WAV is supported (got {8*width}-bit). "
                             f"קובץ WAV חייב להיות 16-bit PCM.")
        pcm = np.frombuffer(w.readframes(n), dtype=np.int16)
    x = pcm.astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if rate != 16000:
        idx = np.arange(0, len(x) - 1, rate / 16000.0)
        i0 = idx.astype(np.int64)
        frac = (idx - i0).astype(np.float32)
        x = x[i0] * (1.0 - frac) + x[i0 + 1] * frac
    return np.ascontiguousarray(x, dtype=np.float32)


def main():
    ap = argparse.ArgumentParser(description="Transcribe WAV files with the alma-mic STT engine (no microphone).")
    ap.add_argument("wavs", nargs="+", help="WAV file(s) to transcribe")
    ap.add_argument("--cpu", action="store_true", help="force CPU even if a GPU exists")
    args = ap.parse_args()

    from config import Config
    from stt import Transcriber

    cfg = Config.load()
    if args.cpu:
        cfg.device = "cpu"
    t = Transcriber(cfg)
    t0 = time.time()
    t.load(log=lambda m: print(f"  {m}", flush=True))
    print(f"model ready in {time.time()-t0:.1f}s : {t.desc}\n")

    for path in args.wavs:
        audio = load_wav_16k(path)
        dur = len(audio) / 16000.0
        t0 = time.time()
        text, lang = t.transcribe(audio)
        dt = time.time() - t0
        print(f"{path}")
        print(f"  {dur:.1f}s audio -> {dt:.1f}s on {t.desc.split('[')[-1].rstrip(']')}"
              f"  (x{dt/max(dur,0.01):.2f} realtime)  lang={lang}")
        print(f"  text: {text!r}\n")


if __name__ == "__main__":
    main()
