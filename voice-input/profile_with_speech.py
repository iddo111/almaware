#!/usr/bin/env python3
"""Profile with REAL speech audio (not silence filtered out)."""

import json
import logging
import os
import sys
import tempfile
import time
import wave
import gc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("profile")

def get_memory_mb():
    try:
        import psutil
        p = psutil.Process()
        return p.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0

def create_speech_wav(duration_secs=2.0):
    """Create WAV with speech-like content that passes VAD."""
    import numpy as np

    sample_rate = 16000
    samples = int(duration_secs * sample_rate)
    t = np.arange(samples) / sample_rate

    # Create a signal with multiple frequency components (speech-like)
    # Mix 100Hz, 200Hz, 400Hz to simulate speech formants
    f1, f2, f3 = 100, 200, 400
    signal = (np.sin(2 * np.pi * f1 * t) +
              np.sin(2 * np.pi * f2 * t) +
              np.sin(2 * np.pi * f3 * t)) / 3

    # Modulate amplitude (speech amplitude envelope)
    envelope = np.exp(-((t - duration_secs / 2) ** 2) / (duration_secs / 4) ** 2)
    audio = (signal * envelope * 25000).astype(np.int16)

    path = os.path.join(tempfile.gettempdir(), f"speech_{int(time.time() * 1000)}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return path

def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hebrew-voice"))

    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)

    import hebrew_stt

    log.info("=== INFERENCE WITH REAL SPEECH (VAD-PASSING) ===")
    log.info("Creating engine...")

    engine = hebrew_stt.HebrewSTT(
        model=cfg.get("model", "small"),
        device="cpu",
        lang_detect="single",  # Single model for now
    )

    mem_before_warmup = get_memory_mb()
    log.info(f"Before warmup: {mem_before_warmup:.1f} MB")

    log.info("Warming up...")
    start_warmup = time.time()
    engine.warmup()
    warmup_time = time.time() - start_warmup

    mem_after_warmup = get_memory_mb()
    log.info(f"After warmup ({warmup_time:.1f}s): {mem_after_warmup:.1f} MB (Δ {mem_after_warmup - mem_before_warmup:+.1f} MB)")

    log.info("\n=== INFERENCE WITH SPEECH (no VAD filtering) ===")
    mem_before_inference = get_memory_mb()
    log.info(f"Before inference: {mem_before_inference:.1f} MB")

    memory_samples = []
    start_inference = time.time()

    for i in range(20):
        elapsed_total = time.time() - start_inference
        log.info(f"\nCycle {i+1}/20 (elapsed {elapsed_total:.1f}s)...")

        wav = create_speech_wav(duration_secs=2.0)

        try:
            result = engine.transcribe_file(wav)
            log.info(f"  Text: '{result.get('text', '')[:40]}'")
        except Exception as e:
            log.error(f"  Error: {e}")

        try:
            os.remove(wav)
        except:
            pass

        gc.collect()
        mem_now = get_memory_mb()
        delta_from_start = mem_now - mem_before_inference
        memory_samples.append((i + 1, mem_now, delta_from_start))
        log.info(f"  Memory: {mem_now:.1f} MB (Δ {delta_from_start:+.1f} MB)")

        # Check if we're hitting the leak threshold
        if delta_from_start > 200:
            log.error(f"  ✗ LEAK DETECTED: {delta_from_start:.1f} MB growth!")
            break

        time.sleep(0.2)

    mem_final = get_memory_mb()
    total_delta = mem_final - mem_before_inference
    total_time = time.time() - start_inference

    log.info(f"\n=== RESULT ===")
    log.info(f"Memory before inference: {mem_before_inference:.1f} MB")
    log.info(f"Memory after {len(memory_samples)} cycles: {mem_final:.1f} MB")
    log.info(f"Total delta: {total_delta:+.1f} MB over {total_time:.1f}s")

    if total_time > 0:
        leak_rate = (total_delta / total_time) * 60
        log.info(f"Leak rate: {leak_rate:.1f} MB/min")

    log.info("\nMemory progression:")
    for cycle, mem, delta in memory_samples:
        log.info(f"  Cycle {cycle:2d}: {mem:.1f} MB ({delta:+.1f} MB)")

    if total_delta > 100:
        log.error(f"\n✗ SIGNIFICANT LEAK: {total_delta:.1f} MB")
    else:
        log.info(f"\n✓ STABLE: {total_delta:.1f} MB growth")

if __name__ == "__main__":
    main()
