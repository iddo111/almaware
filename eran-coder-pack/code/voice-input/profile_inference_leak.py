#!/usr/bin/env python3
"""Profile where the 456 MB/min inference leak is happening.

Strategy: Load the model, then run 10 inference cycles on dummy audio while
monitoring memory. Use py-spy to capture the stack at peak memory."""

import json
import logging
import os
import sys
import tempfile
import time
import wave
import gc
import tracemalloc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("profile")

def get_memory_mb():
    """Get process memory usage."""
    try:
        import psutil
        p = psutil.Process()
        return p.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0

def create_test_wav(duration_secs=1.5):
    """Create a dummy WAV file."""
    import numpy as np

    sample_rate = 16000
    samples = int(duration_secs * sample_rate)
    t = np.arange(samples) / sample_rate
    # Generate simple sine wave
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

    # Load config
    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)

    import hebrew_stt

    log.info("=== INFERENCE PHASE LEAK PROFILING ===")
    log.info("Creating engine (CPU mode for stability)...")

    engine = hebrew_stt.HebrewSTT(
        model=cfg.get("model", "small"),
        device="cpu",  # Force CPU to isolate inference leak
        lang_detect="single",  # Single model (not dual) to isolate the leak
    )

    mem_before_warmup = get_memory_mb()
    log.info(f"Before warmup: {mem_before_warmup:.1f} MB")

    log.info("Warming up model (this may take 30-60s)...")
    start_warmup = time.time()
    engine.warmup()
    warmup_time = time.time() - start_warmup

    mem_after_warmup = get_memory_mb()
    warmup_delta = mem_after_warmup - mem_before_warmup
    log.info(f"After warmup ({warmup_time:.1f}s): {mem_after_warmup:.1f} MB (Δ {warmup_delta:+.1f} MB)")

    log.info("\n=== INFERENCE PHASE (this is where the leak happens) ===")

    # Run inference cycles and track memory
    mem_before_inference = get_memory_mb()
    log.info(f"Before inference cycles: {mem_before_inference:.1f} MB")

    inference_times = []
    memory_samples = []

    for i in range(10):
        log.info(f"\nCycle {i+1}/10...")

        wav = create_test_wav(duration_secs=1.5)
        log.info(f"  Created WAV: {os.path.basename(wav)}")

        start = time.time()
        try:
            result = engine.transcribe_file(wav)
            elapsed = time.time() - start
            inference_times.append(elapsed)
            log.info(f"  STT: {elapsed:.2f}s, text='{result.get('text', '')[:30]}'")
        except Exception as e:
            log.error(f"  Error: {e}")
            import traceback
            traceback.print_exc()

        # Clean up WAV
        try:
            os.remove(wav)
        except:
            pass

        # Sample memory after each cycle
        gc.collect()
        mem_now = get_memory_mb()
        delta_from_start = mem_now - mem_before_inference
        memory_samples.append((i + 1, mem_now, delta_from_start))
        log.info(f"  Memory: {mem_now:.1f} MB (Δ {delta_from_start:+.1f} MB from inference start)")

        time.sleep(0.5)

    mem_final = get_memory_mb()
    total_delta = mem_final - mem_before_inference
    inference_phase_time = sum(inference_times)

    log.info(f"\n=== INFERENCE LEAK ANALYSIS ===")
    log.info(f"Memory before inference: {mem_before_inference:.1f} MB")
    log.info(f"Memory after 10 cycles: {mem_final:.1f} MB")
    log.info(f"Total delta: {total_delta:+.1f} MB over {inference_phase_time:.1f}s")

    if inference_phase_time > 0:
        leak_rate = (total_delta / inference_phase_time) * 60  # MB/min
        log.info(f"Leak rate: {leak_rate:.1f} MB/min")

    log.info("\nMemory progression:")
    for cycle, mem, delta in memory_samples:
        log.info(f"  Cycle {cycle}: {mem:.1f} MB ({delta:+.1f} MB)")

    log.info("\nInference times:")
    for i, t in enumerate(inference_times):
        log.info(f"  Cycle {i+1}: {t:.2f}s")

    # Summary
    log.info("\n=== FINDINGS ===")
    if total_delta > 100:
        log.info(f"✗ SIGNIFICANT LEAK: {total_delta:.1f} MB over {inference_phase_time:.1f}s")
        log.info("  Likely culprits:")
        log.info("    - Whisper cache (transcribe_options kept between calls)")
        log.info("    - Base model loaded alongside main model (dual-model path)")
        log.info("    - CUDA tensors not released (if GPU)")
        log.info("    - Segment lists/info objects held in memory")
    else:
        log.info(f"✓ STABLE: Only {total_delta:.1f} MB growth — no inference leak detected")

if __name__ == "__main__":
    main()
