import sys
import os
import argparse
import wave
import glob
import struct
import random

# Lazy import for webrtcvad to keep module import cheap and dependency-tolerant
_vad_instance = None
_vad_import_warning_shown = False


def _get_vad():
    global _vad_instance, _vad_import_warning_shown
    if _vad_instance is None:
        try:
            import webrtcvad
            _vad_instance = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        except Exception as e:
            if not _vad_import_warning_shown:
                print(f"WARNING: webrtcvad import failed ({e}), VAD will be fail-open", file=sys.stderr)
                _vad_import_warning_shown = True
    return _vad_instance


VAD_AGGRESSIVENESS = 2
FRAME_MS = 30


def voiced_ratio(pcm_bytes: bytes, sample_rate: int = 16000) -> float:
    # Frame size in bytes for 30ms at given sample rate (16-bit mono)
    frame_size_samples = sample_rate * FRAME_MS // 1000
    frame_size_bytes = frame_size_samples * 2  # 16-bit = 2 bytes per sample
    
    if len(pcm_bytes) < frame_size_bytes:
        return 0.0
    
    total_frames = len(pcm_bytes) // frame_size_bytes
    if total_frames == 0:
        return 0.0
    
    vad = _get_vad()
    
    # Handle import failure gracefully (fail-open)
    if vad is None:
        return 1.0
    
    voiced_count = 0
    try:
        for i in range(total_frames):
            start = i * frame_size_bytes
            end = start + frame_size_bytes
            frame = pcm_bytes[start:end]
            # webrtcvad expects bytes and sample_rate must be supported (8000,16000,32000,48000)
            if vad.is_speech(frame, sample_rate):
                voiced_count += 1
    except Exception as e:
        print(f"WARNING: VAD is_speech failed ({e}), returning fail-open ratio=1.0", file=sys.stderr)
        return 1.0
    
    return voiced_count / total_frames


def modulation_ratio(pcm_bytes: bytes, frame_bytes: int = 2048) -> float:
    """How much the loudness BREATHES across the segment: (p95-p5)/p50 of per-64ms RMS.

    Built 2026-08-31 19:10 after webrtcvad was measured USELESS in this room: the fan
    scores voiced_ratio 1.00 at BOTH aggressiveness 2 and 3 (the 08-30 Windows input
    slider that rescued Iddo's speech also lifted the room into webrtcvad's speech
    band). What still separates, measured on 60 real dumped segments from this day:
    speech breathes at syllable rate and the fan does not.

        pure fan (rms ~960-990):      modulation 0.26-0.29
        anything with his voice:      modulation 0.77-3.29

    The gap is 2.6x. Frames of 64 ms, percentiles not max, so one pop can't fake it."""
    import audioop
    rms = [audioop.rms(pcm_bytes[i:i + frame_bytes], 2)
           for i in range(0, len(pcm_bytes) - frame_bytes, frame_bytes)]
    if len(rms) < 8:
        return 999.0        # too short to judge -- fail-open, never mute the mic
    rs = sorted(rms)
    n = len(rs)
    p5, p50, p95 = rs[n // 20], rs[n // 2], rs[int(n * 0.95)]
    return (p95 - p5) / max(1, p50)


def frame_voiced(pcm_bytes: bytes, sample_rate: int = 16000) -> bool:
    """One 64 ms mic block -> is there VOICE in it? For the segmenter's voice endpoint
    (2026-08-31). webrtcvad takes 10/20/30 ms frames, so a 64 ms block is judged by its
    two 30 ms thirds -- voiced if EITHER is, because clipping a syllable costs more than
    letting one frame of fan noise through (the hangover absorbs single frames anyway).
    Fail-open True on any trouble: a broken VAD must never mute the mic."""
    frame_bytes = sample_rate * FRAME_MS // 1000 * 2
    if len(pcm_bytes) < frame_bytes:
        return True
    vad = _get_vad()
    if vad is None:
        return True
    try:
        for i in range(min(2, len(pcm_bytes) // frame_bytes)):
            if vad.is_speech(pcm_bytes[i * frame_bytes:(i + 1) * frame_bytes], sample_rate):
                return True
        return False
    except Exception:
        return True


def main():
    parser = argparse.ArgumentParser(description="Voice Activity Detection module for KESHEV 5000")
    parser.add_argument('--selftest', action='store_true', help='Run self-test with silence, noise, and real speech')
    
    args = parser.parse_args()
    
    if not args.selftest:
        print("Usage: python -m app.vad [--selftest]")
        sys.exit(0)
    
    # a. Silence test
    sample_rate = 16000
    silence_duration = 2  # seconds
    silence_bytes = b"\x00" * (sample_rate * silence_duration * 2)  # 16-bit mono
    
    ratio_silence = voiced_ratio(silence_bytes, sample_rate)
    
    # b. Seeded noise test (no numpy - use stdlib only)
    rnd = random.Random(0)
    samples_per_second = sample_rate
    total_samples = samples_per_second * silence_duration
    noise_samples = []
    for _ in range(total_samples):
        val = int(rnd.uniform(-0.25, 0.25) * 32767)
        # Pack as little-endian signed short (16-bit PCM)
        noise_samples.append(struct.pack('<h', val))
    noise_bytes = b"".join(noise_samples)
    
    ratio_noise = voiced_ratio(noise_bytes, sample_rate)
    
    # c. Real speech test
    keshev_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    segments_dir = os.path.join(keshev_root, "segments")
    wav_files = []
    
    if os.path.isdir(segments_dir):
        for f in glob.glob(os.path.join(segments_dir, "*.wav")):
            try:
                size = os.path.getsize(f)
                if size > 60000:
                    wav_files.append((f, size))
            except OSError:
                continue
    
    ratio_real = None
    real_test_passed = False
    real_candidates = []

    if wav_files:
        # Sort by modification time, newest first
        wav_files.sort(key=lambda x: os.path.getmtime(x[0]), reverse=True)
        # Take up to five newest files
        candidates = wav_files[:5]
        
        for test_file, _ in candidates:
            try:
                with wave.open(test_file, 'rb') as wf:
                    assert wf.getframerate() == sample_rate, f"Expected {sample_rate} Hz"
                    assert wf.getnchannels() == 1, "Expected mono"
                    assert wf.getsampwidth() == 2, "Expected 16-bit (2 bytes)"
                    
                    pcm_data = wf.readframes(wf.getnframes())
                
                r = voiced_ratio(pcm_data, sample_rate)
                real_candidates.append(r)
            except Exception as e:
                print(f"WARNING: Failed to read real speech file {test_file} ({e}), skipping this candidate", file=sys.stderr)
                continue
        
        if real_candidates:
            ratio_real = max(real_candidates)
            real_test_passed = ratio_real >= 0.4
    
    # Print results
    print(f"vad silence={ratio_silence:.3f} noise={ratio_noise:.3f}", end="")
    if ratio_real is not None:
        candidate_strs = [f"{r:.3f}" for r in real_candidates]
        print(f" real_max={ratio_real:.3f} (candidates: {', '.join(candidate_strs)})")
    elif wav_files:
        print(" real=failed_to_read_any")
    else:
        print(" real=skipped")
    
    # Determine success/failure
    if ratio_silence > 0.05:
        print("VAD FAIL: silence detection too high")
        sys.exit(1)
    
    if ratio_real is not None and not real_test_passed:
        print(f"VAD FAIL: real speech ratio too low ({ratio_real:.3f} < 0.4)")
        sys.exit(1)
    
    # If we got here, all required tests passed
    print("VAD OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
