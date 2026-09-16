#!/usr/bin/env python3
"""Profile the DUAL-model path specifically (where two models are loaded)."""

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

def create_test_wav(duration_secs=1.5):
    import numpy as np
    sample_rate = 16000
    samples = int(duration_secs * sample_rate)
    t = np.arange(samples) / sample_rate
    audio = (np.sin(2 * np.pi * 1000 * t) * 20000).astype(np.int16)

    path = os.path.join(tempfile.gettempdir(), f"prof_{int(time.time() * 1000)}.wav")
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

    log.info("=== DUAL-MODEL PATH LEAK PROFILING ===")
    log.info("Creating engine with DUAL language detection...")

    engine = hebrew_stt.HebrewSTT(
        model=cfg.get("model", "small"),
        device="cpu",
        lang_detect="dual",  # DUAL-MODEL PATH: loads 2 models
        language=None,  # Don't force a language
    )

    mem_before_warmup = get_memory_mb()
    log.info(f"Before warmup: {mem_before_warmup:.1f} MB")

    log.info("Warming up DUAL model (loads both base + primary)...")
    start_warmup = time.time()
    engine.warmup()
    warmup_time = time.time() - start_warmup

    mem_after_warmup = get_memory_mb()
    warmup_delta = mem_after_warmup - mem_before_warmup
    log.info(f"After warmup ({warmup_time:.1f}s): {mem_after_warmup:.1f} MB (Δ {warmup_delta:+.1f} MB)")
    log.info("(Note: +500MB is expected — both models loaded)")

    log.info("\n=== DUAL INFERENCE PHASE ===")
    mem_before_inference = get_memory_mb()
    log.info(f"Before inference cycles: {mem_before_inference:.1f} MB")

    memory_samples = []

    for i in range(15):
        log.info(f"\nCycle {i+1}/15...")

        wav = create_test_wav(duration_secs=1.5)

        try:
            result = engine.transcribe_file(wav)
            log.info(f"  Result: lang={result.get('lang')}, text='{result.get('text', '')[:20]}'")
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
        log.info(f"  Memory: {mem_now:.1f} MB (Δ {delta_from_start:+.1f} MB from inference start)")

        time.sleep(0.2)

    mem_final = get_memory_mb()
    total_delta = mem_final - mem_before_inference

    log.info(f"\n=== DUAL-MODEL INFERENCE RESULT ===")
    log.info(f"Memory before inference: {mem_before_inference:.1f} MB")
    log.info(f"Memory after 15 cycles: {mem_final:.1f} MB")
    log.info(f"Total delta: {total_delta:+.1f} MB")

    log.info("\nMemory progression:")
    for cycle, mem, delta in memory_samples:
        log.info(f"  Cycle {cycle:2d}: {mem:.1f} MB ({delta:+.1f} MB)")

    if total_delta > 50:
        log.info(f"\n✗ LEAK DETECTED: {total_delta:.1f} MB growth over 15 cycles")
    else:
        log.info(f"\n✓ STABLE: Only {total_delta:.1f} MB growth — dual-model path is OK")

if __name__ == "__main__":
    main()
