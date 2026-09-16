"""alma-mic / test_vad.py — verify STAGE 2: our VAD finds a speech burst between silences.

Deterministic, no hardware needed (clean-mandate: every module unit-testable headless).
"""
import sys
import numpy as np
import vad

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _frame(rms: float, n: int) -> np.ndarray:
    x = np.random.default_rng(0).standard_normal(n).astype(np.float32)
    x *= rms / (np.sqrt(np.mean(x * x)) + 1e-12)
    return x


def test_detects_one_burst():
    v = vad.VAD(block_ms=30)
    block = int(vad.SAMPLE_RATE * 0.03)
    seq = [0.0005] * 20 + [0.05] * 20 + [0.0005] * 20  # silence, speech, silence
    segs = []
    for rms in seq:
        out = v.push(_frame(max(rms, 1e-6), block))
        if out is not None:
            segs.append(out)
    assert len(segs) == 1, f"expected 1 speech segment, got {len(segs)}"
    dur_ms = len(segs[0]) / vad.SAMPLE_RATE * 1000
    print(f"[ok] detected 1 speech segment, ~{dur_ms:.0f} ms")
    assert 500 < dur_ms < 1500, f"segment duration off: {dur_ms} ms"


def test_ignores_silence():
    v = vad.VAD(block_ms=30)
    block = int(vad.SAMPLE_RATE * 0.03)
    segs = [v.push(_frame(0.0005, block)) for _ in range(60)]
    assert all(s is None for s in segs), "false-positive speech in pure silence"
    print("[ok] pure silence -> no false speech")


if __name__ == "__main__":
    test_detects_one_burst()
    test_ignores_silence()
    print("\nSTAGE 2 (VAD) PASS - our own VAD detects speech vs silence.")
