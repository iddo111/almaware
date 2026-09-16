"""alma-mic / test_audio.py — verify STAGE 1: find a LIVE device and capture real signal.

Run:  python test_audio.py
Pass = picks a live mic (BRIO on a real host API, not dead USBAudio1.0 / silent MME)
and captures real samples (reports RMS and peak so a quiet room != a dead stream).
"""
import sys
import time
import numpy as np
import audio

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def test_enumerate():
    devs = audio.list_input_devices()
    assert devs, "no input devices found"
    print(f"[ok] {len(devs)} input devices:")
    for d in devs[:14]:
        print(f"     #{d.index:<3} [{d.hostapi}]  {d.name}")


def test_pick_live():
    d = audio.pick_device(
        prefer=["brio", "scarlett"],
        avoid=["usbaudio", "wh-1000xm4", "hands-free", "headset", "bluetooth", "mix"])
    assert d is not None, "no LIVE input device found"
    print(f"[ok] picked: #{d.index} [{d.hostapi}] {d.name}")
    return d


def test_capture(d):
    chunks = []
    with audio.AudioCapture(d.index) as cap:
        t0 = time.time()
        for fr in cap.frames():
            chunks.append(fr)
            if time.time() - t0 > 2.0:
                break
    sig = np.concatenate(chunks)
    rms = float(np.sqrt(np.mean(sig ** 2)))
    peak = float(np.max(np.abs(sig)))
    print(f"[ok] captured {len(sig)} samples ({len(sig)/audio.SAMPLE_RATE:.2f}s)  RMS={rms:.5f}  peak={peak:.5f}")
    assert len(sig) > audio.SAMPLE_RATE, "captured too little"
    if peak < 0.001:
        print("  [WARN] near-silent capture — likely a silent room OR a dead/MME stream. "
              "Make some noise and re-run to confirm a real signal.")
    else:
        print("  [ok] real signal present.")


if __name__ == "__main__":
    test_enumerate()
    d = test_pick_live()
    test_capture(d)
    print("\nSTAGE 1: clean ALMAWARE capture path works.")
