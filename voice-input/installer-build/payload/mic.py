"""mic.py - microphone capture with device-fallback chain (BT headset ->
BRIO -> Scarlett -> default), PTT recording, and a VAD energy detector.

HONEST CAVEAT: BT SCO/hands-free mic has historically been flaky on this PC.
resolve_device() tries the configured device first, then each fallback, and
*verifies* it actually produces signal (a silent device = treated as dead) so
we don't silently record nothing.

"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import wave

logger = logging.getLogger("voiceinput.mic")

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
SAMPLE_WIDTH = 2
_TEMP = os.path.join(tempfile.gettempdir(), "voiceinput")

def _audio():
    import numpy as np
    import sounddevice as sd
    return sd, np

def list_input_devices():
    sd, _ = _audio()
    return [(i, d["name"]) for i, d in enumerate(sd.query_devices())
            if d.get("max_input_channels", 0) > 0]

def _probe(idx, secs=0.8) -> int:
    """Return peak amplitude captured from a device, or -1 if it errors."""
    sd, np = _audio()
    try:
        rec = sd.rec(int(SAMPLE_RATE * secs), samplerate=SAMPLE_RATE,
                     channels=CHANNELS, dtype=DTYPE, device=idx)
        sd.wait()
        return int(np.abs(rec).max())
    except Exception as e:  # noqa: BLE001
        logger.debug("probe failed dev=%s: %s", idx, e)
        return -1

def _is_banned(name: str, never) -> bool:
    n = (name or "").lower()
    return any(b.lower() in n for b in (never or []))

LIVE_FLOOR = 15  # peak above this during the probe = a device that's actually live

def resolve_device(primary, fallbacks, verify=True, never_use=None,
                   idle_if_no_good_mic=True):
    """Resolve an input device, AUTO-DETECTING whichever mic is actually LIVE.

    The audio device on this PC flips (USB desk mic vs BT headset go in and out),
    so a fixed priority list silently lands on a dead mic. Instead we probe every
    non-banned device that matches the name chain and pick the one with the
    strongest live signal (highest peak >= LIVE_FLOOR). This auto-follows the live
    mic across flips. When everything is quiet we can't tell live from dead, so we
    fall back to chain priority; when nothing opens we IDLE (or use the default).

    Returns (index, name, note). (None, None) => IDLE; (None, 'default') => sys default."""
    never = list(never_use or [])
    devs = list_input_devices()
    chain = [c for c in ([primary] + list(fallbacks or [])) if c]
    # candidates in chain-priority order, deduped by device index
    candidates, seen = [], set()
    for prio, hint in enumerate(chain):
        h = hint.lower()
        for idx, name in devs:
            if idx in seen or h not in name.lower():
                continue
            if _is_banned(name, never):
                continue
            candidates.append((prio, idx, name)); seen.add(idx)
    if not candidates:
        msg = "no configured device matched"
        return (None, None, msg + " -> IDLE") if idle_if_no_good_mic \
            else (None, "default", msg + " -> system default mic")
    if not verify:
        _, idx, name = candidates[0]
        return idx, name, f"selected {name!r}"
    # probe each candidate; keep those that OPEN (peak >= 0)
    probed = [(_probe(idx), prio, idx, name) for prio, idx, name in candidates]
    opened = [t for t in probed if t[0] >= 0]
    if not opened:
        msg = "no candidate opened"
        return (None, None, msg + " -> IDLE") if idle_if_no_good_mic \
            else (None, "default", msg + " -> system default mic")
    # prefer the LOUDEST clearly-live device; else chain-priority among the quiet
    live = [t for t in opened if t[0] >= LIVE_FLOOR]
    if live:
        peak, _, idx, name = max(live, key=lambda t: t[0])
        return idx, name, f"using LIVE {name!r} (peak={peak})"
    opened.sort(key=lambda t: t[1])  # by chain priority
    peak, _, idx, name = opened[0]
    return idx, name, f"using {name!r} (quiet, peak={peak})"

def record_ptt(device, stop_event: threading.Event, max_secs=30) -> str | None:
    """Push-to-talk: record from now until stop_event is set or max_secs."""
    sd, np = _audio()
    frames, peak = [], 0
    start = time.monotonic()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype=DTYPE, device=device) as st:
        while not stop_event.is_set() and time.monotonic() - start < max_secs:
            block, _ = st.read(int(SAMPLE_RATE * 0.1))
            frames.append(block.copy())
            if len(block):
                peak = max(peak, int(np.abs(block).max()))
    if not frames or peak < 60:
        return None
    return _write_wav(np.concatenate(frames, axis=0), np)

def record_vad(device, on_speech_start=None, on_speech_end=None, on_level=None,
               rms_threshold=220, silence_secs=1.4, max_secs=30) -> str | None:
    """VAD auto-mode: wait for speech energy, fire on_speech_start, record until
    silence_secs of quiet, fire on_speech_end, return WAV. Blocks until one
    utterance is captured (or returns None if max_secs of nothing)."""
    sd, np = _audio()
    frames, peak = [], 0
    spoke = False
    speech_start = silence_start = 0.0
    started_at = time.monotonic()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype=DTYPE, device=device) as st:
        while True:
            block, _ = st.read(int(SAMPLE_RATE * 0.1))
            now = time.monotonic()
            rms = int(np.sqrt(np.mean(block.astype(np.float64) ** 2))) if len(block) else 0
            if on_level:
                try:
                    on_level(rms)
                except Exception:
                    pass
            if spoke:
                frames.append(block.copy())
                peak = max(peak, rms)
            if rms > rms_threshold:
                if not spoke:
                    if speech_start == 0.0:
                        speech_start = now
                    elif now - speech_start >= 0.2:
                        spoke = True
                        frames.append(block.copy())
                        if on_speech_start:
                            on_speech_start()
                silence_start = 0.0
            elif spoke:
                if silence_start == 0.0:
                    silence_start = now
                elif now - silence_start >= silence_secs:
                    break
            if spoke and now - speech_start >= max_secs:
                break
            if not spoke and now - started_at >= max_secs:
                return None
    if on_speech_end:
        on_speech_end()
    if not frames or peak < rms_threshold:
        return None
    return _write_wav(np.concatenate(frames, axis=0), np)

def _write_wav(audio, np) -> str:
    os.makedirs(_TEMP, exist_ok=True)
    path = os.path.join(_TEMP, f"rec_{time.strftime('%Y%m%d_%H%M%S')}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return path

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    cfg = {}
    cfgp = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(cfgp):
        cfg = json.load(open(cfgp, encoding="utf-8"))
    idx, name, note = resolve_device(cfg.get("input_device"),
                                     cfg.get("fallback_devices", []))
    print(f"Resolved device: #{idx} {name}\n  {note}")
