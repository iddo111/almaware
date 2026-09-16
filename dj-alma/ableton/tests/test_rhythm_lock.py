# -*- coding: utf-8 -*-
"""test_rhythm_lock.py -- tests for bridge/rhythm_lock.py against synthetic
clicks. No audio device, no microphone, no Ableton anywhere in this test --
run with plain pytest or directly with `python test_rhythm_lock.py`.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ABLETON_DIR = os.path.dirname(HERE)  # D:\CLAUDE\dj-alma\ableton
BRIDGE_DIR = os.path.join(os.path.dirname(ABLETON_DIR), "bridge")
for _p in (BRIDGE_DIR, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import protocol
import rhythm_lock
from rhythm_lock import lock, to_command


def clicks(bpm, n=16, jitter=0.0, start=10.0, seed=7):
    """Synthetic steady onsets at bpm with seeded gaussian jitter (seconds),
    like a real beatbox -- never alternating, which biases any median."""
    import random
    rng = random.Random(seed)
    period = 60.0 / bpm
    return [start + i * period + rng.gauss(0.0, jitter) for i in range(n)]


def test_steady_128_locks():
    r = lock(clicks(128.0))
    assert r is not None
    assert abs(r.bpm - 128.0) < 0.5
    assert r.param == protocol.bpm_to_param(128.0)
    assert r.confidence > 0.9


def test_psy_tempo_143_locks():
    r = lock(clicks(143.55, jitter=0.004))
    assert r is not None
    assert abs(r.bpm - 143.55) < 1.0


def test_chaotic_returns_none():
    assert lock([0.0, 0.31, 0.35, 0.9, 0.95, 1.6, 1.62, 2.5]) is None


def test_too_few_returns_none():
    assert lock([0.0, 0.46875, 0.9375]) is None
    assert lock([]) is None


def test_out_of_range_returns_none():
    assert lock(clicks(100.0)) is None  # below TEMPO_MIN_BPM, never clamped
    assert lock(clicks(180.0)) is None  # above TEMPO_MAX_BPM


def test_non_ascending_returns_none():
    assert lock([0.0, 0.5, 0.5, 1.0, 1.5, 2.0, 2.5]) is None


def test_to_command_shape():
    r = lock(clicks(140.0))
    cmd = to_command(r)
    assert cmd["cmd"] == "SET_TEMPO_EXACT"  # exact float, not the 0-127 wire
    assert cmd["bpm"] == r.bpm
    assert cmd["param"] == protocol.bpm_to_param(140.0)  # kept for old consumers


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} passed")
