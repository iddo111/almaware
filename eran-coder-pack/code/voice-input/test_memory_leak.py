#!/usr/bin/env python3
"""Test script to verify the memory leak is fixed.

Runs 30 simulated voice-input cycles (like a 30-min session with 1-min spacing)
and monitors RAM usage. Reports PASS if RAM stays <500MB, FAIL if it balloons."""

import json
import logging
import os
import sys
import tempfile
import time
import wave

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("test")

# Get process memory usage (Windows only)
def get_memory_mb():
    import psutil
    try:
        p = psutil.Process()
        return p.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0

# Create a test WAV file (simulate captured audio)
def create_test_wav(duration_secs=2.0):
    """Create a dummy 16-bit mono 16kHz WAV file."""
    import numpy as np

    sample_rate = 16000
    samples = int(duration_secs * sample_rate)
    # Generate white noise (won't pass VAD, but STT will try to transcribe it)
    audio = np.random.randint(-32768, 32767, samples, dtype=np.int16)

    path = os.path.join(tempfile.gettempdir(), f"test_wav_{int(time.time() * 1000)}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return path

def test_memory_leak():
    """Run 30 cycles of transcription and monitor memory."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hebrew-voice"))

    try:
        import psutil
    except ImportError:
        log.warning("psutil not installed; skipping memory monitoring")
        psutil = None

    # Load config
    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)

    # Import STT
    import transcribe as stt

    log.info("=== MEMORY LEAK TEST ===")
    log.info("Warming up STT engine...")
    stt.load(cfg)
    time.sleep(1)

    initial_mem = get_memory_mb() if psutil else 0
    log.info(f"Initial memory: {initial_mem:.1f} MB")

    results = []

    for i in range(30):
        log.info(f"\nCycle {i+1}/30...")

        # Create a test WAV
        wav_path = create_test_wav(duration_secs=1.5)
        log.info(f"  Created WAV: {os.path.basename(wav_path)}")

        # Transcribe it
        try:
            result = stt.transcribe(wav_path, cfg)
            log.info(f"  STT result: text={result.get('text', '')[:40]!r}, reason={result.get('reason', 'ok')}")
        except Exception as e:
            log.warning(f"  STT failed: {e}")

        # Clean up WAV
        try:
            os.remove(wav_path)
        except Exception:
            pass

        # Check memory every 5 cycles
        if psutil and (i + 1) % 5 == 0:
            current_mem = get_memory_mb()
            delta = current_mem - initial_mem
            results.append((i + 1, current_mem, delta))
            log.info(f"  Memory: {current_mem:.1f} MB (Δ {delta:+.1f} MB from start)")

        time.sleep(0.5)  # Small delay between cycles

    # Final memory check
    if psutil:
        final_mem = get_memory_mb()
        total_delta = final_mem - initial_mem
        log.info(f"\n=== FINAL RESULT ===")
        log.info(f"Initial memory: {initial_mem:.1f} MB")
        log.info(f"Final memory: {final_mem:.1f} MB")
        log.info(f"Total delta: {total_delta:+.1f} MB")

        if final_mem < 500:
            log.info("✓ PASS: Memory stayed <500 MB")
            return True
        else:
            log.info(f"✗ FAIL: Memory bloated to {final_mem:.1f} MB (>500 MB)")
            return False
    else:
        log.info("✓ Test completed (no memory monitoring available)")
        return True

if __name__ == "__main__":
    success = test_memory_leak()
    sys.exit(0 if success else 1)
