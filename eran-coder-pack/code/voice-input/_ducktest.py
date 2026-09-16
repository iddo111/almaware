"""Standalone duck self-test: spawn our OWN audio session (a near-silent sine
played by THIS python process), then duck the WHOLE machine's media sessions to
10%, read volumes back, restore, read back again. Proves duck+restore works
without touching Iddo's Chrome volume permanently (Chrome is restored too).
"""
import sys, time, threading
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, sounddevice as sd
from ducking import Ducker, list_sessions

SR = 44100
t = np.arange(SR * 30) / SR
tone = (0.02 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)  # quiet 220Hz
stop = threading.Event()

def player():
    idx = 0
    def cb(outdata, frames, tinfo, status):
        nonlocal idx
        chunk = tone[idx:idx+frames]
        if len(chunk) < frames:
            chunk = np.concatenate([chunk, tone[:frames-len(chunk)]]); idx = 0
        else:
            idx += frames
        outdata[:, 0] = chunk
    with sd.OutputStream(samplerate=SR, channels=1, callback=cb):
        while not stop.is_set():
            time.sleep(0.1)

threading.Thread(target=player, daemon=True).start()
time.sleep(1.2)  # let the session register

print("=== BEFORE (media sessions) ===")
for s in list_sessions():
    print(f"  {s['name']:<22} vol={s['volume']:.0%}")

d = Ducker(duck_pct=10)
ducked = d.duck()
print("\nDucked sessions:", ducked)
print("=== DURING (should be ~10%) ===")
for s in list_sessions():
    print(f"  {s['name']:<22} vol={s['volume']:.0%}")

time.sleep(1.0)
d.restore()
print("\n=== AFTER restore (should be back to original) ===")
for s in list_sessions():
    print(f"  {s['name']:<22} vol={s['volume']:.0%}")
stop.set()
