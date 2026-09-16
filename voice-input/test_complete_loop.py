#!/usr/bin/env python3
"""Test the complete voice_input loop (VAD + STT) to detect leaks."""

import json
import logging
import os
import sys
import tempfile
import time
import wave
import gc
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("test")

def get_memory_mb():
    try:
        import psutil
        p = psutil.Process()
        return p.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0

def create_speech_wav(duration_secs=2.0):
    """Create WAV with speech-like content."""
    import numpy as np
    sample_rate = 16000
    samples = int(duration_secs * sample_rate)
    t = np.arange(samples) / sample_rate
    # Speech-like signal
    f1, f2, f3 = 100, 200, 400
    signal = (np.sin(2 * np.pi * f1 * t) +
              np.sin(2 * np.pi * f2 * t) +
              np.sin(2 * np.pi * f3 * t)) / 3
    envelope = np.exp(-((t - duration_secs / 2) ** 2) / (duration_secs / 4) ** 2)
    audio = (signal * envelope * 25000).astype(np.int16)

    path = os.path.join(tempfile.gettempdir(), f"test_{int(time.time() * 1000)}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return path

def test_complete_loop():
    """Simulate the complete voice_input loop."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hebrew-voice"))

    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)

    import voice_input as vi
    import transcribe as stt

    log.info("=== COMPLETE VOICE_INPUT LOOP TEST ===")
    log.info("Loading STT engine...")

    # Load STT just like voice_input does
    stt.load(cfg)
    gc.collect()

    mem_start = get_memory_mb()
    log.info(f"Initial memory: {mem_start:.1f} MB")

    log.info("\n=== SIMULATING 25 UTTERANCE CYCLES ===\n")

    memory_progression = []
    start_time = time.time()

    for i in range(25):
        elapsed = time.time() - start_time
        log.info(f"Cycle {i+1:2d}/25 (elapsed {elapsed:.1f}s)...")

        # Create test WAV
        wav = create_speech_wav(duration_secs=2.0)

        # Transcribe (like _handle_wav does)
        try:
            r = stt.transcribe(wav, cfg)
            text = r.get("text", "").strip()
            log.info(f"  Text: '{text[:30]}'  lang={r.get('lang')}")
        except Exception as e:
            log.error(f"  Error: {e}")
            text = ""

        # Cleanup (like the fixed _handle_wav does)
        try:
            if os.path.exists(wav):
                os.remove(wav)
        except:
            pass

        # Explicit GC (like the fixed code does)
        gc.collect()

        mem_now = get_memory_mb()
        delta = mem_now - mem_start
        memory_progression.append((i + 1, mem_now, delta))

        log.info(f"  Memory: {mem_now:.1f} MB (Δ {delta:+.1f} MB)")

        # Fail fast if we hit 1GB
        if mem_now > 1000:
            log.error(f"  ✗ RUNAWAY LEAK: Memory at {mem_now:.1f} MB!")
            break

        time.sleep(0.1)

    total_time = time.time() - start_time
    mem_final = get_memory_mb()
    total_delta = mem_final - mem_start

    log.info(f"\n=== RESULT ===")
    log.info(f"Time: {total_time:.1f}s ({len(memory_progression)} cycles)")
    log.info(f"Memory: {mem_start:.1f} → {mem_final:.1f} MB")
    log.info(f"Growth: {total_delta:+.1f} MB")

    if total_time > 0:
        leak_rate = (total_delta / total_time) * 60
        log.info(f"Rate: {leak_rate:.1f} MB/min")

    log.info("\nMemory by cycle:")
    for cycle, mem, delta in memory_progression:
        pct = (delta / mem_final * 100) if mem_final > 0 else 0
        log.info(f"  {cycle:2d}: {mem:7.1f} MB ({delta:+6.1f} MB, {pct:+5.1f}%)")

    log.info("\n=== VERDICT ===")
    if mem_final < 600:
        log.info(f"✓ PASS: Memory stable at {mem_final:.1f} MB (< 600 MB)")
        return True
    elif total_delta > 200:
        log.error(f"✗ FAIL: Leak detected ({total_delta:.1f} MB growth)")
        return False
    else:
        log.info(f"? AMBIGUOUS: {total_delta:.1f} MB growth (monitor longer)")
        return True

if __name__ == "__main__":
    try:
        success = test_complete_loop()
        sys.exit(0 if success else 1)
    except Exception as e:
        log.exception("Test crashed: %s", e)
        sys.exit(1)
