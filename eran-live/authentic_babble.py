"""
authentic_babble.py - Eran's OWN voice, without TTS.

Honest re-read of what happened for perceptron-movie/audio/eran_babble_voice.mp3:
  the TEXT was real Eran bytes -- but the AUDIO was Microsoft edge-tts
  (a neural TTS model, not Eran). Iddo caught it: "isn't that just TTS?" Yes.

This script builds an authentic audio alternative that is 100% Eran, no TTS,
no external voice model. Chosen technique: **byte-to-tone sonification**.

Why this option over the others:
  1) Byte-to-tone   (this one) -- purely deterministic, every audible event maps
                                   1:1 to a byte Eran emitted. Reversible: given
                                   the audio you can recover his exact byte
                                   stream. Nothing external, nothing synthesized
                                   "on his behalf". No language assumption --
                                   works identically for Hebrew, English, emoji,
                                   punctuation, whatever he babbles.
  2) Hebrew grapheme->formant  -- still a phoneme synthesizer we would build,
                                   and only representative of the ~1/3 of his
                                   output that happens to be Hebrew grapheme
                                   leading bytes. Loses the rest.
  3) Visual byte-stream video  -- honest, but the ask was an audio alternative.

Wiring:
  * Loads Eran from a safe COPY of checkpoints/latest.pt on CPU (never fights the
    trainer's GPU -- same discipline as chat_server.py).
  * Generates a long-ish babble sample (~500 bytes) from a BOS prompt at
    temperature 0.85 -- his normal babble temperature.
  * Maps each output byte to a sine burst:
       - printable-ASCII / UTF-8 leading bytes -> higher-octave pitch
       - UTF-8 continuation bytes (0x80..0xBF) -> mid-octave pitch
       - space / newline                       -> short silence (a breath)
       - special tokens (BOS/EOS/PAD/UNK)      -> dropped (structural, not sound)
    Pitches quantised to a 3-octave pentatonic scale so it is listenable, not
    just noise.
  * ADSR envelope on each burst -> no clicks.
  * A soft heartbeat click on every byte boundary so the tempo is audible.
  * Renders 30 s of audio, saves WAV then transcodes to MP3 via ffmpeg.

Also writes the raw byte-stream text (his actual output) next to the mp3 so
Iddo can read what he "said" -- because in his native format he speaks in bytes,
not in a voice.

Run:  python -s authentic_babble.py
Out:  D:/CLAUDE/eran-live/eran_authentic.mp3
      D:/CLAUDE/eran-live/eran_authentic.txt   (the exact bytes rendered)
"""

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import json
import torch
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tokenizer import tokenizer
from model import build_model

# ---------- knobs ----------
TARGET_SECONDS = 30.0
BYTES_PER_SECOND = 10.0                # 100 ms per byte -> speech-ish tempo
SAMPLE_RATE = 22050
BURST_MS = 90                          # sine-burst length per byte (<= 100ms slot)
GAP_MS = 10                            # small gap -> perceived rhythm
HEARTBEAT_MS = 6                       # sub-click on every byte boundary
TEMPERATURE = 0.85
TOP_K = 40
# generate a bit more than we need, then trim
GEN_TOKENS = int(TARGET_SECONDS * BYTES_PER_SECOND * 1.6)

CKPT = os.path.join(HERE, "checkpoints", "latest.pt")
CFG_PATH = os.path.join(HERE, "config.json")
OUT_WAV = os.path.join(HERE, "eran_authentic.wav")
OUT_MP3 = os.path.join(HERE, "eran_authentic.mp3")
OUT_TXT = os.path.join(HERE, "eran_authentic.txt")


def load_eran_cpu():
    """Copy latest.pt (so we never race the trainer's write) and load on CPU."""
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    tmp = os.path.join(tempfile.gettempdir(), "eran_authentic_ckpt.pt")
    shutil.copyfile(CKPT, tmp)
    ck = torch.load(tmp, map_location="cpu", weights_only=False)
    m = build_model(cfg["model"]).to("cpu")
    m.load_state_dict(ck["model"])
    m.eval()
    step = int(ck.get("step", 0))
    return m, step, int(cfg["model"]["block_size"])


@torch.no_grad()
def generate_bytes(model, block_size, n_tokens):
    """Feed him just <BOS> and let him babble. This is *his* babble, uncoached."""
    ids = [tokenizer.bos_id]
    idx = torch.tensor([ids], dtype=torch.long)
    out = model.generate(idx, max_new_tokens=n_tokens,
                         temperature=TEMPERATURE, top_k=TOP_K)
    return out[0].tolist()[len(ids):]


# ---------- byte -> pitch mapping ----------
# 3-octave pentatonic on A minor: A2..A5, so bursts land on musical notes and
# don't turn into a headache. Bins are STABLE: same byte value -> same pitch,
# every time. The mapping is the "voice" -- his bytes ARE his sound.
PENTATONIC = []
_base = 55.0            # A1
for octave in range(2, 6):   # A2..A5
    for semi in (0, 3, 5, 7, 10):  # minor pentatonic degrees
        PENTATONIC.append(_base * (2 ** ((octave - 1) + semi / 12.0)))
# len(PENTATONIC) == 20 discrete pitches


def byte_to_pitch(b):
    """Deterministic byte(0..255) -> pitch mapping.

    - continuation bytes 0x80..0xBF -> LOWER third of scale  (they are 'inside a
      word', so they sound murmured)
    - leading / ASCII bytes         -> UPPER two thirds       (word-starts pop)
    """
    if 0x80 <= b <= 0xBF:
        # murmur range: pitches [0..6]
        idx = int((b - 0x80) / (0x40) * 7)
    else:
        # articulate range: pitches [7..19]
        idx = 7 + (b * 13) // 256
    idx = max(0, min(len(PENTATONIC) - 1, idx))
    return PENTATONIC[idx]


def is_breath(b):
    """Space (0x20), tab (0x09), newline (0x0A), CR (0x0D) -> tiny silence."""
    return b in (0x20, 0x09, 0x0A, 0x0D)


# ---------- sine burst synthesis (numpy, no external synth) ----------
def adsr(n, sr):
    a = int(sr * 0.005); r = int(sr * 0.020)
    a = min(a, n // 4); r = min(r, n // 4)
    env = np.ones(n, dtype=np.float32)
    if a > 0:
        env[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    if r > 0:
        env[-r:] = np.linspace(1.0, 0.0, r, dtype=np.float32)
    return env


def sine_burst(freq, ms, sr):
    n = max(1, int(sr * ms / 1000.0))
    t = np.arange(n, dtype=np.float32) / sr
    # sine + a whisper of 2nd harmonic so it doesn't sound like a bare tone
    wave_arr = 0.85 * np.sin(2 * math.pi * freq * t) \
             + 0.15 * np.sin(2 * math.pi * (2 * freq) * t)
    return wave_arr * adsr(n, sr)


def heartbeat(ms, sr):
    """Very short low click -- makes byte-tempo audible under the bursts."""
    n = max(1, int(sr * ms / 1000.0))
    t = np.arange(n, dtype=np.float32) / sr
    click = np.sin(2 * math.pi * 60.0 * t) * np.exp(-t * 220.0)
    return click.astype(np.float32) * 0.15


def render_audio(byte_stream):
    """byte_stream (list[int] over 0..259 including specials) -> float32 mono."""
    slot_samps = int(SAMPLE_RATE / BYTES_PER_SECOND)  # 100 ms budget per byte
    audio = np.zeros(0, dtype=np.float32)
    hb = heartbeat(HEARTBEAT_MS, SAMPLE_RATE)
    for b in byte_stream:
        if b >= 256:                        # BOS/EOS/PAD/UNK: not sound
            continue
        slot = np.zeros(slot_samps, dtype=np.float32)
        # heartbeat click sits at the very start of every slot
        slot[:len(hb)] += hb
        if is_breath(b):
            # leave the slot near-silent (heartbeat only) = a "breath"
            audio = np.concatenate([audio, slot])
            continue
        freq = byte_to_pitch(b)
        burst = sine_burst(freq, BURST_MS, SAMPLE_RATE) * 0.55
        # position burst after tiny GAP_MS so the click is audible
        start = int(SAMPLE_RATE * GAP_MS / 1000.0)
        end = start + len(burst)
        if end <= slot_samps:
            slot[start:end] += burst
        else:
            slot[start:] += burst[: slot_samps - start]
        audio = np.concatenate([audio, slot])
        if len(audio) / SAMPLE_RATE >= TARGET_SECONDS:
            break
    # trim to exactly TARGET_SECONDS
    max_len = int(TARGET_SECONDS * SAMPLE_RATE)
    audio = audio[:max_len]
    if len(audio) < max_len:
        audio = np.concatenate([audio, np.zeros(max_len - len(audio), dtype=np.float32)])
    # normalize gently
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio / peak * 0.9
    return audio


def write_wav(path, audio_f32, sr):
    pcm = np.clip(audio_f32, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())


def to_mp3(wav_path, mp3_path):
    ff = shutil.which("ffmpeg")
    if not ff:
        print("[authentic] ffmpeg not found; keeping WAV only.", flush=True)
        return False
    subprocess.run(
        [ff, "-y", "-loglevel", "error",
         "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", "128k", mp3_path],
        check=True,
    )
    return True


def main():
    print("[authentic] loading Eran on CPU (safe copy of latest.pt)...", flush=True)
    model, step, block = load_eran_cpu()
    print(f"[authentic] Eran @ step {step:,} loaded. Generating ~{GEN_TOKENS} tokens.", flush=True)
    tok_ids = generate_bytes(model, block, GEN_TOKENS)

    # Save exactly what got sonified (his actual bytes) so the artifact is self-documenting.
    text = tokenizer.decode(tok_ids)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[authentic] wrote raw bytes -> {OUT_TXT}  ({len(tok_ids)} tokens, "
          f"{sum(1 for x in tok_ids if x < 256)} sound-bytes)", flush=True)

    print("[authentic] rendering byte-to-tone audio (no TTS, no voice model)...", flush=True)
    audio = render_audio(tok_ids)
    write_wav(OUT_WAV, audio, SAMPLE_RATE)

    if to_mp3(OUT_WAV, OUT_MP3):
        try:
            os.remove(OUT_WAV)
        except OSError:
            pass
        print(f"[authentic] wrote {OUT_MP3}  ({TARGET_SECONDS:.0f}s, step {step:,})", flush=True)
    else:
        print(f"[authentic] wrote {OUT_WAV}  ({TARGET_SECONDS:.0f}s, step {step:,})", flush=True)


if __name__ == "__main__":
    main()
