#!/usr/bin/env python3
"""Quick memory leak test: run 5 cycles and check if the dual-model path cleans up."""

import json
import logging
import os
import sys
import tempfile
import time
import wave
import gc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("test")

def get_memory_mb():
    """Get process memory usage (Windows only)."""
    try:
        import psutil
        p = psutil.Process()
        return p.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0

def create_test_wav(duration_secs=2.0):
    """Create a dummy 16-bit mono 16kHz WAV file with some speech-like content."""
    import numpy as np

    sample_rate = 16000
    samples = int(duration_secs * sample_rate)
    # Generate simple sine wave (more realistic than pure noise)
    t = np.arange(samples) / sample_rate
    freq = 1000  # 1kHz tone
    audio = (np.sin(2 * np.pi * freq * t) * 20000).astype(np.int16)

    path = os.path.join(tempfile.gettempdir(), f"test_wav_{int(time.time() * 1000)}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return path

def test():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hebrew-voice"))

    # Load config
    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)

    # Test DIRECT dual-transcribe path (where the memory leak was)
    import hebrew_stt

    log.info("Testing hebrew_stt dual-transcribe memory cleanup...")
    engine = hebrew_stt.HebrewSTT(
        model=cfg.get("model", "small"),
        device=cfg.get("device", "cpu"),
        lang_detect="dual",
        language=None,  # Force dual-model path
    )
    engine.warmup()

    mem_before = get_memory_mb()
    log.info(f"Memory before: {mem_before:.1f} MB")

    for i in range(5):
        log.info(f"\nCycle {i+1}/5...")
        wav = create_test_wav(duration_secs=1.0)
        log.info(f"  Created: {os.path.basename(wav)}")

        try:
            result = engine.transcribe_file(wav)
            log.info(f"  Result: text='{result.get('text', '')[:30]}'")
        except Exception as e:
            log.error(f"  Error: {e}")

        try:
            os.remove(wav)
        except:
            pass

        # Force cleanup
        gc.collect()

        mem_now = get_memory_mb()
        delta = mem_now - mem_before
        log.info(f"  Memory: {mem_now:.1f} MB (Δ {delta:+.1f} MB)")

    mem_final = get_memory_mb()
    total_delta = mem_final - mem_before
    log.info(f"\n=== RESULT ===")
    log.info(f"Before: {mem_before:.1f} MB")
    log.info(f"After 5 cycles: {mem_final:.1f} MB")
    log.info(f"Total delta: {total_delta:+.1f} MB")

    if mem_final < 400 or total_delta < 50:
        log.info("✓ PASS: Memory is stable")
        return True
    else:
        log.info(f"✗ SUSPICIOUS: Memory grew {total_delta:+.1f} MB")
        return False

if __name__ == "__main__":
    success = test()
    sys.exit(0 if success else 1)
